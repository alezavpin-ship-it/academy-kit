# Formato del paquete de contenido (`packs/<tema>/pack.json`)

Un paquete = un archivo JSON. Copia `packs/_plantilla/` a `packs/<tu-tema>/`, llénalo y valida con
`python tools/validate_pack.py packs/<tu-tema>`. Las carpetas que empiezan con `_` no aparecen en la app.

```jsonc
{
  "meta": {
    "id": "cloud-security",            // único; separa el progreso de cada academia en la base de datos
    "title": "Academia de Cloud Security",
    "subtitle": "Una línea",
    "language": "es",                  // idioma del contenido
    "version": "1.0", "updated": "2026-10-01",
    "disclaimer": "Aviso al pie (opcional)",
    "ranks": [                         // 5 recomendados; en orden; el primero en 0 puntos
      {"name": "Recluta", "points": 0, "emoji": "🔰", "color": "#8A99AD", "image": "rango1.webp"}  // image: opcional, en assets/
    ]
  },
  "levels": ["Fundamentos", "Identidad y acceso", "..."],   // orden de los niveles
  "roles": {"Cloud Engineer": ["iam", "red", "..."]},        // opcional: rol → habilidades
  "topics": {"fundamentos": "Fundamentos y riesgo"},         // temas de la videoteca
  "lessons": [{
    "id": "f1", "level": "Fundamentos", "title": "...", "summary": "...",
    "points": ["3 a 5 puntos clave"],
    "skills": ["fundamentos"],                               // deben existir en algún rol (si hay roles)
    "practice": {"label": "Qué practicar", "url": "https://..."},   // url opcional
    "quiz": [{"q": "...", "options": ["4 opciones distintas"], "answer": 1, "why": "explicación"}],  // exactamente 3
    "vbd": {"deliverable": "...", "done_when": ["≥ 3 criterios"], "value": "...", "where": {"label": "...", "url": "..."}},
    "resources": ["clave_video_1", "clave_video_2"],         // ≥ 2 videos de ≥ 2 canales; el primero es el que se ve
    "resource_notes": {"clave_video_2": "por qué ESTE video en ESTA lección (opcional)"}
  }],
  "glossary": [{"term": "...", "category": "...", "definition": "..."}],   // ≥ 8 términos, sin repetir
  "resources": {
    "clave_video_1": {
      "title": "Título EXACTO de YouTube", "url": "https://www.youtube.com/watch?v=ID",
      "channel": "Canal EXACTO", "lang": "es", "topic": "fundamentos",
      "why": "qué explica, en una línea", "kind": "video",   // video | playlist | link
      "level": "básico", "who": "experto que habla (opcional)", "verified": "2026-10-01"
    }
  }
}
```

## Reglas que revisa el validador
- ids de lección únicos; cada `level` existe en `levels`; rangos en orden empezando en 0.
- ≥ 3 puntos clave; exactamente 3 preguntas con 4 opciones distintas, `answer` válido y `why`.
- VBD con entregable, valor y ≥ 3 criterios.
- ≥ 2 videos por lección, de ≥ 2 canales distintos; todas las claves de `resources` existen.
- URLs https; `video`/`playlist` deben ser de YouTube (si no, usa `link`); `topic` existe en `topics`; sin URLs repetidas.
- Glosario sin términos repetidos y con ≥ 8 términos.

## Imágenes de rango (opcional)
Pon `assets/rango1.webp` … en la carpeta del paquete y refiérelas en `ranks[].image`. Sin imagen se usa el emoji.

## Catálogo de skills (`catalog/skills.json`)
El vocabulario común de skills vive fuera de los paquetes, porque lo comparten todos los paquetes, roles y perfiles.

```jsonc
{
  "families": [{"id": "m365-security", "name": "Microsoft 365 Security", "gap_volume": 194, "role_impact": 97,
                "champion": "Nombre de quien lidera el upskilling de la familia (vacío = por asignar)"}],
  "skills":   [{"id": "exchange-online", "name": "Exchange Online", "family": "m365-security", "confirmed": true}]
}
```
- Cada lección declara `"catalog_skills": ["exchange-online"]` con los ids de las skills que desarrolla.
- El validador revisa que esos ids existan, que cada skill tenga familia y que ninguna familia esté vacía.
- La pestaña «Mapa de skills» ordena las familias por brecha y muestra champion, cobertura y lecciones por skill.

## Certificaciones (`exams/<id>/exam.json`)
```jsonc
{
  "meta": {"id": "ai-901", "code": "AI-901", "title": "Microsoft Azure AI Fundamentals", "provider": "Microsoft",
           "family": "ai-security-governance", "skills": ["azure-ai-security"],          // ids del catálogo
           "pass_score": 700, "mock_questions": 25, "mock_minutes": 45,                  // el simulacro
           "outline_date": "2026-04-15", "verified": "2026-10-01", "disclaimer": "...",
           "links": [{"title": "Guía de estudio oficial", "url": "https://...", "kind": "guide", "provider": "Microsoft Learn"}]},
  "domains": [{"id": "concepts", "title": "...", "weight": 42.5, "official": "40–45%"}],  // los pesos suman 100
  "modules": [{"id": "rai", "domain": "concepts", "title": "...", "summary": "...", "points": ["≥ 3"],
               "materials": [{"title": "...", "url": "https://...", "kind": "module", "provider": "Microsoft Learn", "verified": "2026-10-01"}],
               "exercises": [{"id": "rai-match", "type": "match", "prompt": "...", "pairs": [["situación", "respuesta"]]},
                             {"id": "x-order", "type": "order", "prompt": "...", "steps": ["en el orden correcto"]},
                             {"id": "x-lab", "type": "lab", "prompt": "...", "url": "https://...", "label": "...", "steps": ["lista de verificación"]}]}],
  "questions": [{"id": "q01", "module": "rai", "q": "situación", "options": ["4 distintas"], "answer": 1, "why": "explicación"}]
}
```
Reglas: cada módulo con ≥ 3 puntos, ≥ 1 material https y ≥ 1 pregunta; el banco debe alcanzar para el simulacro en cada dominio;
los enlaces se verifican antes de escribirlos (nunca inventar una URL); las preguntas son **originales**, nunca copiadas de exámenes reales.

## Material de apoyo (`catalog/materials.json`)
`{"<skill id>": [{"title": "...", "url": "https://...", "provider": "Microsoft Learn", "kind": "path", "verified": "2026-10-01"}]}`.
`kind`: path | module | course | lab | video | guide | doc.
