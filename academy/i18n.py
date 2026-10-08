"""Interface texts in Spanish and English. The lesson content comes from the pack, in the pack's language."""

from __future__ import annotations

UI: dict[str, tuple[str, str]] = {  # key: (español, English)
    "points": ("Puntos", "Points"),
    "rank": ("Rango", "Rank"),
    "lessons_done": ("Lecciones completadas", "Lessons completed"),
    "vbds_done": ("VBDs entregados", "VBDs delivered"),
    "to_next": ("{n} para {lvl}", "{n} to {lvl}"),
    "top": ("rango máximo", "top rank"),
    "note_next": ("{p} puntos · faltan {n} para {lvl}", "{p} points · {n} more to reach {lvl}"),
    "note_top": ("{p} puntos · llegaste al rango máximo", "{p} points · top rank reached"),
    "tab_course": ("Curso", "Course"),
    "tab_glossary": ("Glosario", "Glossary"),
    "tab_library": ("Videoteca", "Video library"),
    "tab_progress": ("Progreso e insignias", "Progress & badges"),
    "tab_team": ("Equipo", "Team"),
    "tab_forum": ("Foro", "Forum"),
    "tab_reports": ("Reportes", "Reports"),
    "tab_demand": ("Demanda", "Demand"),
    "tab_skills": ("Mapa de skills", "Skills map"),
    "email": ("Tu correo (para avisos)", "Your e-mail (for notices)"),
    "email_help": ("Opcional. A este correo se dirigen los avisos de avance; con Microsoft 365 se tomará de tu sesión.",
                   "Optional. Progress notices are addressed here; with Microsoft 365 it will come from your session."),
    "view_owner": ("Vista de owner", "Owner view"),
    "view_owner_help": ("Muestra las mediciones del equipo, los avisos y la administración del catálogo. Apágala para ver la app como usuario final.",
                        "Shows team measurements, notices and catalog administration. Turn it off to see the app as an end user."),
    "view_champion": ("Vista de champion", "Champion view"),
    "view_champion_help": ("Muestra el avance, los avisos y las cifras de brecha de tu familia de skills. Apágala para ver la app como usuario final.",
                           "Shows the progress, notices and gap numbers of your skill family. Turn it off to see the app as an end user."),
    "pin": ("PIN de líderes", "Leaders PIN"),
    "pin_bad": ("PIN incorrecto.", "Wrong PIN."),
    "claim": ("Aún no hay owners. Si tú administras la academia, regístrate como el primero.",
              "No owners yet. If you run the academy, register as the first one."),
    "claim_btn": ("Registrarme como owner", "Register me as owner"),
    "tab_route": ("Ruta de aprendizaje", "Learning route"),
    "tab_certs": ("Certificaciones", "Certifications"),
    "skills_intro": ("Las familias de skills del equipo, de mayor a menor brecha. Cada una tiene un champion que lidera su upskilling.",
                     "The team's skill families, biggest gap first. Each one has a champion who leads its upskilling."),
    "sk_gap": ("Brecha", "Gap"),
    "sk_roles": ("Roles afectados", "Roles affected"),
    "sk_cover": ("Skills con lección", "Skills with a lesson"),
    "sk_champion": ("Champion: **{n}**", "Champion: **{n}**"),
    "sk_no_champion": ("Champion: _por asignar_", "Champion: _to be assigned_"),
    "sk_none": ("sin lección todavía", "no lesson yet"),
    "sk_unconfirmed": ("familia por confirmar", "family to be confirmed"),
    "sk_col_skill": ("Skill", "Skill"),
    "sk_col_lessons": ("Lecciones que la cubren", "Lessons that cover it"),
    "sk_mode_view": ("Ver mapa", "View map"),
    "sk_mode_import": ("Importar de Excel", "Import from Excel"),
    "sk_mode_paste": ("Pegar tabla", "Paste table"),
    "sk_mode_edit": ("Editar a mano", "Edit by hand"),
    "sk_local": ("🔒 El archivo se lee en esta computadora y solo la pestaña que elijas. Se guarda cuántos roles tiene cada brecha, no cuáles.",
                 "🔒 The file is read on this computer, and only the sheet you pick. Only how many roles each gap has is kept, not which."),
    "sk_upload": ("Archivo de Excel (.xlsx)", "Excel file (.xlsx)"),
    "sk_sheet": ("Pestaña a leer", "Sheet to read"),
    "sk_keep_roles": ("Guardar también los nombres de los roles afectados", "Also keep the names of the impacted roles"),
    "sk_paste": ("Copia en Excel la tabla (con sus encabezados) y pégala aquí", "Copy the table in Excel (with its headers) and paste it here"),
    "sk_paste_help": ("Encabezados mínimos: Skill Family y Unaligned / Missing Skill. Opcionales: Gap Severity, Impacted Roles, Required Target Proficiency, Target Champion.",
                      "Minimum headers: Skill Family and Unaligned / Missing Skill. Optional: Gap Severity, Impacted Roles, Required Target Proficiency, Target Champion."),
    "sk_found": ("Encontré **{f} familias** y **{s} skills** (encabezados en la fila {r}).", "Found **{f} families** and **{s} skills** (headers on row {r})."),
    "sk_no_summary": ("No vi la tabla resumen (Gap Volume / Role Impact Count): calculé la brecha a partir de los roles afectados.",
                      "No summary table (Gap Volume / Role Impact Count) found: the gap was computed from the impacted roles."),
    "sk_missing_cols": ("Columnas que no encontré (quedan vacías): {c}.", "Columns not found (left empty): {c}."),
    "sk_dupes": ("Skills repetidas que omití: {c}.", "Repeated skills skipped: {c}."),
    "sk_orphans": ("Lecciones que apuntan a skills que ya no estarían en el catálogo: {c}.", "Lessons pointing to skills that would no longer be in the catalog: {c}."),
    "sk_save": ("Usar como catálogo", "Use as catalog"),
    "sk_saved": ("Catálogo guardado.", "Catalog saved."),
    "sk_edit_fam": ("##### Familias", "##### Families"),
    "sk_edit_sk": ("##### Skills", "##### Skills"),
    "sk_edit_help": ("Agrega filas al final de cada tabla; para borrar, selecciona la fila y presiona Supr.", "Add rows at the end of each table; to delete, select the row and press Delete."),
    "sk_save_edit": ("Guardar cambios", "Save changes"),
    "sk_empty": ("Todavía no hay catálogo. Impórtalo de Excel, pégalo o captúralo a mano.", "No catalog yet. Import it from Excel, paste it or type it in."),
    "sk_col_family": ("Familia", "Family"),
    "sk_col_sev": ("Severidad", "Severity"),
    "sk_col_target": ("Nivel objetivo", "Target level"),
    "sk_col_impact": ("Roles afectados", "Roles affected"),
    "sk_col_gap": ("Brecha", "Gap volume"),
    "sk_col_champion": ("Champion", "Champion"),
    "sk_total": ("**{c} de {n}** skills tienen al menos una lección.", "**{c} of {n}** skills have at least one lesson."),
    "level": ("Nivel", "Level"),
    "lesson": ("Lección", "Lesson"),
    "for_role": ("⭐ = recomendada para tu rol", "⭐ = recommended for your role"),
    "practice": ("Practica", "Practice"),
    "check_title": ("#### Comprueba lo que aprendiste", "#### Check your understanding"),
    "check": ("Revisar", "Check"),
    "correct": ("**Correcto**", "**Correct**"),
    "plus_pts": (" (+{p} puntos)", " (+{p} points)"),
    "wrong": ("**Todavía no.** Relee los puntos clave e inténtalo de nuevo (un acierto al reintentar da 5 puntos).",
              "**Not quite.** Read the key points again and retry (a correct retry earns 5 points)."),
    "lesson_done": ("✅ Lección completada.", "✅ Lesson complete."),
    "videos_for": ("##### 📺 Videos de esta lección ({n})", "##### 📺 Videos for this lesson ({n})"),
    "choose_video": ("Elige un video", "Choose a video"),
    "video_size": ("Tamaño del video", "Video size"),
    "why_here": ("**Por qué aquí:** ", "**Why here:** "),
    "all_resources": ("Los {n} recursos y por qué cada uno", "All {n} resources and why each one"),
    "open_source": ("Abrir en la fuente ↗", "Open on the source ↗"),
    "open": ("Abrir ↗", "Open ↗"),
    "third_party": ("Contenido educativo de terceros.", "Third-party educational content."),
    "vbd_title": ("#### 🎯 Entregable de valor (VBD)", "#### 🎯 Value-based deliverable (VBD)"),
    "done_when": ("**Listo cuando** (marca cada criterio cuando lo cumplas):", "**Done when** (tick each criterion when you meet it):"),
    "value": ("Valor: ", "Value: "),
    "where": ("Dónde hacerlo", "Where to do it"),
    "evidence": ("Evidencia (enlace o nota, opcional)", "Evidence (link or note, optional)"),
    "mark_vbd": ("Marcar VBD como entregado", "Mark VBD as delivered"),
    "vbd_ok": ("🎯 VBD entregado{pts}.", "🎯 VBD delivered{pts}."),
    "vbd_already": ("🎯 Ya entregaste este VBD.", "🎯 You already delivered this VBD."),
    "gloss_intro": ("Una pregunta a la vez (término → definición o al revés). 10 puntos por acierto.",
                    "One question at a time (term → definition or the reverse). 10 points per correct answer."),
    "category": ("Categoría", "Category"),
    "next_q": ("Siguiente pregunta ▶", "Next question ▶"),
    "not_this": ("**Esta no.** ", "**Not this one.** "),
    "browse": ("Ver el glosario ({n} términos)", "Browse the glossary ({n} terms)"),
    "search": ("Buscar", "Search"),
    "topic": ("Tema", "Topic"),
    "only_es": ("Solo en español", "Only in Spanish"),
    "resources": ("Recursos", "Resources"),
    "no_es": ("Aún no hay contenido en español para este tema.", "No Spanish content for this topic yet."),
    "used_in": ("Usado en las lecciones: ", "Used in lessons: "),
    "library_intro": ("Videos seleccionados de fuentes profesionales, por tema. Cada lección muestra los suyos.",
                      "Curated videos from professional sources, by topic. Each lesson shows its own."),
    "badges": ("#### Insignias", "#### Badges"),
    "how": ("Cómo ganarla", "How to earn it"),
    "earned": ("Ganada", "Earned"),
    "ranks": ("#### Rangos", "#### Ranks"),
    "role_path": ("#### Ruta para tu rol: {r}", "#### Path for your role: {r}"),
    "recent": ("#### Actividad reciente", "#### Recent activity"),
    "team_intro": ("Progreso de todas las personas que usan esta academia en esta computadora.",
                   "Progress of everyone using this academy on this computer."),
    "download": ("Descargar CSV", "Download CSV"),
    "no_team": ("Aún no hay actividad.", "No activity yet."),
    "who": ("Tu nombre", "Your name"),
    "who_help": ("Tu progreso se guarda con este nombre.", "Your progress is saved under this name."),
    "role": ("Tu rol", "Your role"),
    "any_role": ("(todos)", "(all)"),
    "pack": ("Academia", "Academy"),
    "lang": ("Idioma de la interfaz", "Interface language"),
}


def T(key: str, lang: str = "es", **kw) -> str:
    es, en = UI[key]
    s = en if lang == "en" else es
    return s.format(**kw) if kw else s


def L(lang: str, es: str, en: str) -> str:
    """Inline pair for texts used in a single place."""
    return en if lang == "en" else es


# Table columns are built in Spanish (they are also the CSV headers the team already uses); shown in English when asked.
COLUMNS_EN = {"Persona": "Person", "Puntos": "Points", "Rango": "Rank", "Lecciones": "Lessons", "VBDs": "VBDs",
              "Última actividad": "Last activity", "Ruta (pasos del proveedor)": "Route (provider steps)",
              "Lecciones de la familia": "Family lessons", "Mejor simulacro": "Best mock exam"}


def columns(df, lang: str):
    """The same table with its headers in ``lang``."""
    return df.rename(columns=COLUMNS_EN) if lang == "en" else df


# Catalog checks are written in Spanish (academy/catalog.py); these patterns show them in English.
_MESSAGES_EN = [
    (r"^El catálogo necesita al menos una familia y una skill\.$", "The catalog needs at least one family and one skill."),
    (r"^Hay familias repetidas\.$", "There are repeated families."),
    (r"^Hay skills repetidas: (.*)\.$", r"There are repeated skills: \1."),
    (r"^\[skill (.*)\] la familia '(.*)' no existe\.$", r"[skill \1] the family '\2' does not exist."),
    (r"^\[familia (.*)\] no tiene skills\.$", r"[family \1] has no skills."),
    (r"^No encontré una tabla con las columnas «Skill Family» y «Unaligned / Missing Skill»\.$",
     'I could not find a table with the columns "Skill Family" and "Unaligned / Missing Skill".'),
    (r"^Encontré los encabezados, pero ninguna fila con skills debajo\.$", "I found the headers, but no rows with skills below them."),
    (r"^\[material\] la skill '(.*)' no existe en el catálogo\.$", r"[material] the skill '\1' does not exist in the catalog."),
    (r"^\[material de (.*)\] falta el título o la URL no es https\.$", r"[material of \1] the title is missing or the URL is not https."),
]


def message(text: str, lang: str) -> str:
    """A catalog check message in ``lang`` (unknown messages pass through unchanged)."""
    if lang != "en":
        return text
    import re

    for pattern, en in _MESSAGES_EN:
        if re.match(pattern, text):
            return re.sub(pattern, en, text)
    return text
