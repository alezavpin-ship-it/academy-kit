"""Certification prep: study modules, interactive exercises, practice by domain and timed mock exams.

One folder per certification: exams/<id>/exam.json with
* meta      - code, title, family (skills catalog), pass score, mock size and minutes, official links;
* domains   - the exam's skill areas with their weight;
* modules   - study units (summary, key points, support materials, exercises of type order | match | lab);
* questions - the practice bank: original questions, each tied to a module (and through it to a domain).

Everything here is pure logic; the screen lives in academy/exam_page.py.
"""

from __future__ import annotations

import json
import random
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

EXAMS_DIR = Path(__file__).resolve().parents[1] / "exams"
PRACTICE_POINTS, EXERCISE_POINTS, PASS_POINTS = 5, 10, 50
SCALE = 1000  # mock results are reported on the 0-1000 scale certification exams use


@dataclass(frozen=True)
class ExamQuestion:
    id: str
    module: str
    q: str
    options: list[str]
    answer: int
    why: str


@dataclass(frozen=True)
class Exercise:
    id: str
    type: str  # order | match | lab
    prompt: str
    steps: list[str] = field(default_factory=list)  # order: the right sequence; lab: the checklist
    pairs: list[list[str]] = field(default_factory=list)  # match: [left, right]
    url: str = ""
    label: str = ""


@dataclass(frozen=True)
class Module:
    id: str
    domain: str
    title: str
    summary: str
    points: list[str]
    materials: list[dict] = field(default_factory=list)
    exercises: list[Exercise] = field(default_factory=list)


@dataclass
class Exam:
    id: str
    code: str
    title: str
    provider: str
    family: str
    skills: list[str]
    pass_score: int
    mock_questions: int
    mock_minutes: int
    disclaimer: str
    links: list[dict]
    domains: list[dict]
    modules: list[Module]
    questions: list[ExamQuestion]
    version: str = "1.0"
    outline_date: str = ""

    @property
    def pack_id(self) -> str:
        """Key used in the events table, so exam activity sits next to course activity."""
        return f"exam:{self.id}"

    @property
    def name(self) -> str:
        return f"{self.code}: {self.title}"

    def module(self, module_id: str) -> Module:
        return next(m for m in self.modules if m.id == module_id)

    def domain_of(self, question: ExamQuestion) -> str:
        return self.module(question.module).domain

    def question(self, qid: str) -> ExamQuestion:
        return next(q for q in self.questions if q.id == qid)

    def exercises(self) -> list[Exercise]:
        return [e for m in self.modules for e in m.exercises]


def _parse(data: dict) -> Exam:
    meta = data["meta"]
    modules = [Module(m["id"], m["domain"], m["title"], m["summary"], list(m["points"]), list(m.get("materials", [])),
                      [Exercise(e["id"], e["type"], e["prompt"], list(e.get("steps", [])), [list(p) for p in e.get("pairs", [])],
                                e.get("url", ""), e.get("label", "")) for e in m.get("exercises", [])]) for m in data["modules"]]
    questions = [ExamQuestion(q["id"], q["module"], q["q"], list(q["options"]), int(q["answer"]), q["why"]) for q in data["questions"]]
    return Exam(meta["id"], meta["code"], meta["title"], meta.get("provider", ""), meta.get("family", ""), list(meta.get("skills", [])),
                int(meta.get("pass_score", 700)), int(meta.get("mock_questions", 25)), int(meta.get("mock_minutes", 45)),
                meta.get("disclaimer", ""), list(meta.get("links", [])), list(data["domains"]), modules, questions,
                meta.get("version", "1.0"), meta.get("outline_date", ""))


def load_exam(path: str | Path) -> Exam:
    p = Path(path)
    if not p.exists():
        p = EXAMS_DIR / str(path)
    if p.is_dir():
        p = p / "exam.json"
    return _parse(json.loads(p.read_text(encoding="utf-8")))


def available_exams() -> list[str]:
    if not EXAMS_DIR.exists():
        return []
    return sorted(d.name for d in EXAMS_DIR.iterdir() if (d / "exam.json").exists() and not d.name.startswith("_"))


def validate_exam(exam: Exam, catalog=None) -> list[str]:
    errs: list[str] = []
    dom = {d["id"] for d in exam.domains}
    mods = {m.id for m in exam.modules}
    if abs(sum(float(d["weight"]) for d in exam.domains) - 100) > 0.01:
        errs.append("Los pesos de los dominios deben sumar 100.")
    if len(mods) != len(exam.modules):
        errs.append("Hay módulos repetidos.")
    qids = [q.id for q in exam.questions]
    if len(qids) != len(set(qids)):
        errs.append("Hay ids de pregunta repetidos.")
    for m in exam.modules:
        if m.domain not in dom:
            errs.append(f"[módulo {m.id}] dominio '{m.domain}' no existe.")
        if len(m.points) < 3:
            errs.append(f"[módulo {m.id}] necesita al menos 3 puntos clave.")
        if not m.materials:
            errs.append(f"[módulo {m.id}] necesita al menos un material de apoyo.")
        if not any(q.module == m.id for q in exam.questions):
            errs.append(f"[módulo {m.id}] no tiene preguntas.")
        for mat in m.materials:
            if urlparse(mat.get("url", "")).scheme != "https" or not mat.get("title"):
                errs.append(f"[módulo {m.id}] material sin título o sin URL https.")
        for e in m.exercises:
            if e.type == "order" and len(e.steps) < 3:
                errs.append(f"[ejercicio {e.id}] 'order' necesita al menos 3 pasos.")
            elif e.type == "match" and (len(e.pairs) < 3 or len({p[1] for p in e.pairs}) != len(e.pairs)):
                errs.append(f"[ejercicio {e.id}] 'match' necesita al menos 3 pares con respuestas distintas.")
            elif e.type == "lab" and len(e.steps) < 2:
                errs.append(f"[ejercicio {e.id}] 'lab' necesita al menos 2 pasos.")
            elif e.type not in ("order", "match", "lab"):
                errs.append(f"[ejercicio {e.id}] tipo '{e.type}' desconocido.")
    for q in exam.questions:
        if q.module not in mods:
            errs.append(f"[{q.id}] módulo '{q.module}' no existe.")
        if len(q.options) != 4 or len(set(q.options)) != 4:
            errs.append(f"[{q.id}] necesita 4 opciones distintas.")
        if not 0 <= q.answer < len(q.options):
            errs.append(f"[{q.id}] 'answer' fuera de rango.")
        if not q.why:
            errs.append(f"[{q.id}] falta la explicación.")
    for d in exam.domains:
        have = sum(1 for q in exam.questions if q.module in mods and exam.domain_of(q) == d["id"])
        if have < quota(exam)[d["id"]]:
            errs.append(f"[dominio {d['id']}] el banco tiene {have} preguntas y el simulacro pide {quota(exam)[d['id']]}.")
    if catalog is not None:
        fams = {f.id for f in catalog.families}
        if exam.family and exam.family not in fams:
            errs.append(f"La familia '{exam.family}' no existe en el catálogo de skills.")
        for s in exam.skills:
            if s not in catalog.skill_ids():
                errs.append(f"La skill '{s}' no existe en el catálogo.")
    return errs


def quota(exam: Exam) -> dict[str, int]:
    """How many mock questions each domain gets, following the official weights (largest remainder)."""
    n = exam.mock_questions
    raw = {d["id"]: n * float(d["weight"]) / 100 for d in exam.domains}
    out = {k: int(v) for k, v in raw.items()}
    for k in sorted(raw, key=lambda k: raw[k] - out[k], reverse=True)[: n - sum(out.values())]:
        out[k] += 1
    return out


def build_mock(exam: Exam, rng: random.Random) -> list[str]:
    """Question ids for one mock exam: weighted by domain, spread across modules, shuffled."""
    picked: list[str] = []
    for dom, k in quota(exam).items():
        pool = [q for q in exam.questions if exam.domain_of(q) == dom]
        rng.shuffle(pool)
        by_mod: dict[str, list[ExamQuestion]] = {}
        for q in pool:
            by_mod.setdefault(q.module, []).append(q)
        chosen: list[ExamQuestion] = []
        while len(chosen) < k and any(by_mod.values()):  # round-robin so every module of the domain is represented
            for mod in list(by_mod):
                if by_mod[mod] and len(chosen) < k:
                    chosen.append(by_mod[mod].pop())
        picked += [q.id for q in chosen]
    rng.shuffle(picked)
    return picked


def grade(exam: Exam, qids: list[str], answers: dict[str, int | None]) -> dict:
    """answers: question id -> index of the chosen option in the ORIGINAL option order (None = unanswered)."""
    by_dom: dict[str, list[int]] = {d["id"]: [0, 0] for d in exam.domains}
    wrong = []
    for qid in qids:
        q = exam.question(qid)
        ok = answers.get(qid) == q.answer
        by_dom[exam.domain_of(q)][1] += 1
        by_dom[exam.domain_of(q)][0] += int(ok)
        if not ok:
            wrong.append(qid)
    right = sum(v[0] for v in by_dom.values())
    score = round(SCALE * right / len(qids)) if qids else 0
    return {"score": score, "passed": score >= exam.pass_score, "correct": right, "total": len(qids), "wrong": wrong,
            "unanswered": sum(1 for qid in qids if answers.get(qid) is None),
            "domains": {k: {"correct": v[0], "total": v[1]} for k, v in by_dom.items()}}


def check_order(ex: Exercise, chosen: list[str]) -> bool:
    return list(chosen) == list(ex.steps)


def check_match(ex: Exercise, chosen: dict[str, str]) -> list[bool]:
    return [chosen.get(left) == right for left, right in ex.pairs]


# ---------------------------------------------------------------------------------------------- progress
def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ExamTracker:
    """Exam activity for one learner, stored in the same events table as the courses (pack = 'exam:<id>')."""

    def __init__(self, conn: sqlite3.Connection, exam: Exam, learner: str):
        self.conn, self.exam, self.learner = conn, exam, (learner.strip() or "yo")

    def _record(self, kind: str, item: str, points: int, correct: bool, detail: str = "") -> None:
        with self.conn:
            self.conn.execute("INSERT INTO events(time, pack, learner, kind, item, points, correct, detail) VALUES (?,?,?,?,?,?,?,?)",
                              (_now(), self.exam.pack_id, self.learner, kind, item, int(points), int(bool(correct)), detail))

    def _rows(self, kind: str, item: str | None = None):
        sql = "SELECT * FROM events WHERE pack=? AND learner=? AND kind=?" + (" AND item=?" if item is not None else "") + " ORDER BY id"
        args = (self.exam.pack_id, self.learner, kind) + ((item,) if item is not None else ())
        return self.conn.execute(sql, args).fetchall()

    def answer_practice(self, qid: str, correct: bool) -> int:
        """Points only the first time a question is answered right."""
        already = any(r["correct"] for r in self._rows("exam_practice", qid))
        pts = PRACTICE_POINTS if correct and not already else 0
        self._record("exam_practice", qid, pts, correct)
        return pts

    def complete_exercise(self, ex_id: str) -> int:
        pts = 0 if self._rows("exercise", ex_id) else EXERCISE_POINTS
        self._record("exercise", ex_id, pts, True)
        return pts

    def record_mock(self, result: dict, seconds: int) -> int:
        """Store a mock attempt. Passing for the first time earns PASS_POINTS."""
        first_pass = result["passed"] and not self.passed()
        pts = PASS_POINTS if first_pass else 0
        detail = json.dumps({"score": result["score"], "correct": result["correct"], "total": result["total"],
                             "domains": result["domains"], "seconds": int(seconds)})
        self._record("exam_mock", str(len(self.attempts()) + 1), pts, result["passed"], detail)
        return pts

    def attempts(self) -> list[dict]:
        return [{"n": i + 1, "time": r["time"], "passed": bool(r["correct"]), **json.loads(r["detail"] or "{}")}
                for i, r in enumerate(self._rows("exam_mock"))]

    def passed(self) -> bool:
        return any(r["correct"] for r in self._rows("exam_mock"))

    def practiced(self) -> set[str]:
        return {r["item"] for r in self._rows("exam_practice") if r["correct"]}

    def exercises_done(self) -> set[str]:
        return {r["item"] for r in self._rows("exercise")}

    def total_points(self) -> int:
        r = self.conn.execute("SELECT COALESCE(SUM(points),0) AS p FROM events WHERE pack=? AND learner=?",
                              (self.exam.pack_id, self.learner)).fetchone()
        return int(r["p"])

    def readiness(self) -> float:
        """0-1: share of the question bank answered right at least once and of the exercises completed."""
        total = len(self.exam.questions) + len(self.exam.exercises())
        return (len(self.practiced()) + len(self.exercises_done() & {e.id for e in self.exam.exercises()})) / total if total else 0.0

    def weak_modules(self) -> list[tuple[str, int, int]]:
        """(module id, answered right, questions) for modules below 60 %, weakest first."""
        ok = self.practiced()
        out = []
        for m in self.exam.modules:
            qs = [q.id for q in self.exam.questions if q.module == m.id]
            got = len(ok & set(qs))
            if qs and got / len(qs) < 0.6:
                out.append((m.id, got, len(qs)))
        return sorted(out, key=lambda x: x[1] / x[2])
