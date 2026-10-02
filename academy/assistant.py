"""AI assistant of the company (Amethyst) inside the academy.

Two ways of working, chosen by configuration (config/assistant.json, or the file named by ACADEMY_ASSISTANT):
* handoff (default, works offline and without credentials): the academy writes the prompt with the right context, the
  person copies it and opens the assistant in its own page;
* api (when the company provides an endpoint for integrations): the academy sends the prompt and shows the answer.
  The request uses the chat-completions format most enterprise gateways expose; the key is read from an environment
  variable and is never written to disk. Adjust ``ask`` if the company's endpoint uses another contract.

Privacy rule for every prompt built here: only learning content and the learner's OWN result. Never other people's
progress, the team's gap numbers or anything from the confidential gap report.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path

ASSISTANT_PATH = Path(__file__).resolve().parents[1] / "config" / "assistant.json"
SYSTEM = ("Eres el tutor de Academia - Cloud, la plataforma de upskilling de un equipo de Cloud Security. Responde en español, claro y "
          "concreto, para profesionales de TI. Si no estás seguro de un dato de producto, dilo y remite a la documentación oficial.")


def assistant_path() -> Path:
    return Path(os.environ.get("ACADEMY_ASSISTANT") or ASSISTANT_PATH)


@dataclass
class AssistantConfig:
    name: str = "Amethyst"
    enabled: bool = True
    url: str = ""  # page where people open the assistant (handoff mode)
    api_url: str = ""  # endpoint for integrations (api mode)
    model: str = ""  # model or deployment name, if the endpoint needs it
    key_env: str = "AMETHYST_API_KEY"  # name of the environment variable that holds the key
    auth_header: str = "Authorization"  # "Authorization" (Bearer <key>) or "api-key" (<key>)

    @property
    def mode(self) -> str:
        return "api" if self.api_url and os.environ.get(self.key_env) else "handoff"


def load_assistant(path: str | Path | None = None) -> AssistantConfig:
    p = Path(path) if path else assistant_path()
    if not p.exists():
        return AssistantConfig()
    d = json.loads(p.read_text(encoding="utf-8"))
    return AssistantConfig(**{k: v for k, v in d.items() if k in AssistantConfig.__dataclass_fields__})


def save_assistant(cfg: AssistantConfig, path: str | Path | None = None) -> Path:
    p = Path(path) if path else assistant_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(asdict(cfg), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return p


# ---------------------------------------------------------------------------------------------- prompts
def prompt_explain(question: str, options: list[str], correct: str, why: str, chosen: str = "", topic: str = "") -> str:
    """Tutor for a question the learner missed."""
    mine = f"Yo elegí: {chosen}\n" if chosen else ""
    return (f"Estoy estudiando {topic or 'seguridad en la nube'} y fallé esta pregunta de práctica.\n\n"
            f"Pregunta: {question}\nOpciones:\n" + "\n".join(f"- {o}" for o in options) + f"\n{mine}Respuesta correcta: {correct}\n"
            f"Explicación breve que me dieron: {why}\n\n"
            "1. Explícame con un ejemplo cotidiano por qué esa es la respuesta correcta.\n"
            "2. Dime por qué cada una de las otras opciones no lo es.\n"
            "3. Hazme una pregunta nueva, parecida, para comprobar que lo entendí, y espera mi respuesta antes de corregirla.")


def prompt_study_plan(exam_name: str, score: int, pass_score: int, domains: list[tuple[str, int, int]], modules: list[str],
                      materials: list[tuple[str, str]]) -> str:
    """One-week plan after a mock exam, built from the learner's own result."""
    dom = "\n".join(f"- {t}: {c} de {n}" for t, c, n in domains)
    mats = "\n".join(f"- {t}: {u}" for t, u in materials) or "- (sin material listado)"
    return (f"Hice un simulacro de {exam_name} y obtuve {score} de 1000 (se aprueba con {pass_score}).\n\nAciertos por dominio:\n{dom}\n\n"
            "Módulos donde más fallé:\n" + ("\n".join(f"- {m}" for m in modules) or "- ninguno en particular") +
            f"\n\nMaterial oficial que tengo disponible:\n{mats}\n\n"
            "Arma un plan de estudio de 7 días, 30 minutos al día, que ataque primero mis puntos débiles usando SOLO ese material. "
            "Para cada día dime qué estudiar, qué practicar y cómo sabré que lo dominé. Termina con qué día repetir el simulacro.")


def prompt_step_coach(family: str, skill: str, step: str, provider: str, target: str = "") -> str:
    """Coach before starting a step of the learning route."""
    goal = f" Mi nivel objetivo es {target}." if target else ""
    return (f"Voy a empezar «{step}» de {provider}, para desarrollar la skill «{skill}» (familia {family}).{goal}\n\n"
            "1. Dime en 5 puntos qué debo llevarme de este contenido y en qué fijarme.\n"
            "2. Dame un ejercicio práctico corto para hacerlo al terminar, en un entorno de pruebas.\n"
            "3. Dime cómo se usa esta skill en un proyecto real de seguridad en la nube, para saber cuándo aplicarla.")


def prompt_draft_questions(exam_name: str, module: str, points: list[str], n: int = 5) -> str:
    """For the family lead: a draft of new practice questions, in the exam.json format, to review before adding."""
    return (f"Soy el responsable del contenido de {exam_name}. Escribe {n} preguntas de práctica ORIGINALES para el módulo «{module}».\n\n"
            "Puntos clave del módulo:\n" + "\n".join(f"- {p}" for p in points) + "\n\n"
            "Reglas: preguntas de situación (no de definición); 4 opciones distintas con una sola correcta; distractores plausibles; "
            "explicación de una línea de por qué la correcta lo es; no copies preguntas de exámenes reales.\n"
            'Devuelve solo JSON, una lista con este formato: {"module": "<id del módulo>", "q": "...", "options": ["...", "...", "...", "..."], '
            '"answer": <índice 0-3 de la correcta>, "why": "..."}')


# ---------------------------------------------------------------------------------------------- api mode
def ask(cfg: AssistantConfig, prompt: str, timeout: int = 60) -> tuple[bool, str]:
    """Send the prompt to the assistant's endpoint. Returns (ok, answer or error message)."""
    key = os.environ.get(cfg.key_env, "")
    if not (cfg.api_url and key):
        return False, "El asistente no está configurado para integraciones (falta la URL o la llave)."
    if not cfg.api_url.startswith("https://"):
        return False, "La URL del asistente debe ser https."
    body = {"messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}]}
    if cfg.model:
        body["model"] = cfg.model
    headers = {"Content-Type": "application/json", cfg.auth_header: f"Bearer {key}" if cfg.auth_header.lower() == "authorization" else key}
    req = urllib.request.Request(cfg.api_url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - https enforced above
            data = json.loads(resp.read().decode("utf-8"))
        return True, data["choices"][0]["message"]["content"].strip()
    except urllib.error.HTTPError as e:
        return False, f"El asistente respondió con error {e.code}."
    except (urllib.error.URLError, TimeoutError):
        return False, "No se pudo contactar al asistente (red o tiempo de espera)."
    except (KeyError, IndexError, ValueError):
        return False, "El asistente respondió en un formato que la academia no reconoce; hay que ajustar academy/assistant.py."
