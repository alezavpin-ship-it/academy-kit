"""Edit mode: owners change the content of a section right where they read it, with drop-down lists.

Every section of the academy is made of tables of the content workbook (the course: lessons, questions, the videos of each
lesson; the glossary: terms; the demand: the practice definition…). The owner switches «✏️ Edit mode» on and edits those
tables in place:

* columns that point to something else (course, lesson, video, topic, family, skill, level) are drop-down lists of what exists;
* columns with fixed values (correct letter, kind, scope, severity…) are drop-down lists of those values;
* columns with free but repeated values (channel, provider, category, vendor, champion…) are drop-down lists of the values
  already used, and «➕ New option» adds one more;
* columns that hold several values (skills, aliases) take several choices and accept new ones typed in place;
* rows are added at the bottom of each table and removed by selecting them.

Saving goes through exactly the checks of an imported file (``content_xlsx.build``): with a problem nothing is written and
the problems are listed; when everything is right the files are written (after a backup) and the Excel content file is
rewritten so it always mirrors the app.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from academy import content_sync, ui
from academy import content_xlsx as content
from academy.catalog import VENDORS, slug

# the tables behind each section of the app (the order is the order of the inner tabs)
SECTION_TABLES: dict[str, list[str]] = {
    "tab_route": ["LearningPaths", "Skills", "Families"],
    "tab_course": ["Lessons", "Questions", "LessonResources", "Levels", "Courses"],
    "tab_glossary": ["Glossary"],
    "tab_library": ["Resources", "Topics"],
    "tab_progress": ["Ranks", "Roles"],
    "tab_skills": ["Families", "Skills", "LearningPaths"],
    "tab_reports": ["Families"],
    "tab_demand": ["PracticeSkills", "PracticeRoles", "Practice"],
    "tab_news": ["NewsSources"],
}
TABLE_NAME = {"Courses": "Courses", "Levels": "Levels", "Ranks": "Ranks", "Topics": "Topics", "Roles": "Course roles", "Lessons": "Lessons",
              "Questions": "Questions", "Resources": "Videos and links", "LessonResources": "Videos of each lesson", "Glossary": "Glossary",
              "Families": "Skill families", "Skills": "Skills", "LearningPaths": "Learning paths (classes)", "Practice": "Practice",
              "PracticeSkills": "Practice skills", "PracticeRoles": "Practice roles", "NewsSources": "News sources"}
ABOUT = {"Lessons": "One row per lesson: level, title, summary, key points and the skills it builds.",
         "Questions": "The 3 questions of each lesson: 4 options and the correct letter.",
         "LessonResources": "Which videos each lesson shows and in what order (at least 2, from 2 channels).",
         "LearningPaths": "Each skill's path: Class = 1, 2, 3… is the order; without a number it is reference material.",
         "PracticeSkills": "How the demand writes each practice skill, which catalog skill it maps to and its scope.",
         "NewsSources": "The sites of the Knowledge exchange. FeedUrl (RSS / Atom) gives the latest items; Splash = yes opens the academy with its latest news."}
NUMBERS = {"SortOrder", "Points", "GapVolume", "RoleImpact", "ImpactedRoles", "Class"}
LINKS = {"Url", "PracticeUrl", "FeedUrl"}
LONG = {"Summary", "Question", "Why", "Definition", "Description", "Subtitle", "Disclaimer", "Title", "Note"}
# primary keys: written freely (they are what the other tables choose from)
KEYS = {("Courses", "PackId"), ("Lessons", "LessonId"), ("Resources", "ResourceKey"), ("Topics", "TopicId"), ("Families", "FamilyId"),
        ("Skills", "SkillId"), ("Levels", "Level"), ("Glossary", "Term"), ("PracticeSkills", "Term"), ("PracticeRoles", "RoleTitle"),
        ("Roles", "Role"), ("Ranks", "Name"), ("Practice", "Name"), ("NewsSources", "Name")}
# copied from Skills when the file is written: shown, not edited
INFO = {("LearningPaths", "Family"), ("LearningPaths", "Vendor"), ("LearningPaths", "Skill")}
# several values in one cell, separated by ";"
MULTI = {("Lessons", "Skills"), ("Lessons", "CatalogSkills"), ("Roles", "Skills"), ("PracticeSkills", "Aliases"), ("PracticeRoles", "Aliases")}
# free text columns that still repeat values: offered as a list of what is already used (+ new options)
REPEATED = {"Channel", "Provider", "Category", "Vendor", "Champion", "Target", "Who", "Level", "Emoji", "Color", "PracticeLabel"}
# when a new row leaves its id empty, it is made from this column
ID_FROM = {("Families", "FamilyId"): "Name", ("Skills", "SkillId"): "Name", ("Lessons", "LessonId"): "Title",
           ("Resources", "ResourceKey"): "Title", ("Topics", "TopicId"): "Name"}
LABEL = {"PackId": "Course", "LessonId": "Lesson", "SortOrder": "Order", "AnswerLetter": "Correct", "ResourceKey": "Video / link",
         "Note": "Note for this lesson", "TopicId": "Topic", "Who": "Expert", "FamilyId": "Family", "GapVolume": "Gap volume",
         "RoleImpact": "Roles affected", "ChampionEmail": "Champion e-mail", "SkillId": "Skill", "Target": "Target level",
         "ImpactedRoles": "Roles with the gap", "Provider": "Source", "RoleTitle": "Role title", "CatalogSkills": "Catalog skills",
         "PracticeLabel": "Practice (label)", "PracticeUrl": "Practice (link)", "FeedUrl": "Feed (RSS / Atom)", "Splash": "Opening news"}
PROVIDERS = ["Microsoft Learn", "Workday Learning", "AWS Skill Builder", "Google Cloud Skills Boost", "Cisco Networking Academy", "IBM SkillsBuild"]


def label(col: str) -> str:
    return LABEL.get(col, col)


# ------------------------------------------------------------------------------------------------ data
@st.cache_data(show_spinner=False)
def _tables(signature: tuple) -> dict[str, list[dict]]:
    return content.tables()


def signature() -> tuple:
    from academy.catalog import catalog_path, materials_path
    from academy.practice import practice_path

    files = content.pack_files() + [catalog_path(), materials_path(), practice_path()]
    return tuple((str(f), f.stat().st_mtime_ns) for f in files if f.exists())


def _values(rows: list[dict], col: str) -> list[str]:
    return [str(r[col]).strip() for r in rows if r.get(col) not in (None, "") and str(r[col]).strip()]


def _split(values: list[str]) -> list[str]:
    return [x.strip() for v in values for x in v.replace(",", ";").split(";") if x.strip()]


def _uniq(*groups) -> list[str]:
    return list(dict.fromkeys(v for g in groups for v in g if v))


def options(table: str, col: str, data: dict[str, list[dict]], extra: dict) -> list[str] | None:
    """The drop-down list of a column (None = free text)."""
    if (table, col) in KEYS or (table, col) in INFO or col in NUMBERS or col in LINKS:
        return None
    own = _values(data.get(table, []), col)
    own = _split(own) if (table, col) in MULTI else own
    added = extra.get((table, col), [])
    fixed = content.CHOICES.get((table, col)) or content.CHOICES.get(col)
    if fixed:
        return _uniq(fixed, own, added)
    refs = {"PackId": ("Courses", "PackId"), "LessonId": ("Lessons", "LessonId"), "ResourceKey": ("Resources", "ResourceKey"),
            "TopicId": ("Topics", "TopicId"), "FamilyId": ("Families", "FamilyId"), "SkillId": ("Skills", "SkillId"),
            "CatalogSkills": ("Skills", "SkillId")}
    if (table, col) == ("Lessons", "Level"):
        return _uniq(_values(data.get("Levels", []), "Level"), own, added)
    if col in refs and (table, col) != refs[col]:
        t, c = refs[col]
        return _uniq(_values(data.get(t, []), c), own, added)
    if (table, col) == ("Lessons", "Skills"):
        return _uniq(_split(_values(data.get("Roles", []), "Skills")), own, added)
    if (table, col) == ("Roles", "Skills"):
        return _uniq(_split(_values(data.get("Lessons", []), "Skills")), own, added)
    if col == "Vendor":
        return _uniq(VENDORS, own, added)
    if (table, col) == ("NewsSources", "Category"):
        from academy.news import CATEGORIES

        return _uniq(CATEGORIES, own, added)
    if col == "Provider":
        return _uniq(PROVIDERS, own, added)
    if (table, col) in MULTI or col in REPEATED:
        return _uniq(own, added)
    return None


def _frame(table: str, rows: list[dict]) -> pd.DataFrame:
    cols = content.SHEETS[table]
    df = pd.DataFrame(rows, columns=cols)
    for col in cols:
        if col in NUMBERS:
            df[col] = pd.to_numeric(df[col].replace("", None), errors="coerce").astype("Int64")
        elif (table, col) in MULTI:
            df[col] = df[col].map(lambda v: _split([str(v or "")]))
        else:
            df[col] = df[col].map(lambda v: None if v is None or str(v).strip() == "" else str(v)).astype("string")
    return df


def _rows(table: str, df: pd.DataFrame) -> list[dict]:
    out = []
    for r in df.to_dict("records"):
        rec = {}
        for col in content.SHEETS[table]:
            v = r.get(col)
            if isinstance(v, (list, tuple)):
                rec[col] = "; ".join(str(x).strip() for x in v if str(x).strip())
            elif v is None or pd.isna(v):
                rec[col] = ""
            elif col in NUMBERS:
                rec[col] = int(v)
            else:
                rec[col] = str(v).strip()
        if any(str(x).strip() for x in rec.values()):
            out.append(rec)
    return out


def _column(table: str, col: str, opts: list[str] | None):
    cc = st.column_config
    help_ = f"Excel column: {col}"
    if (table, col) in INFO:
        return cc.TextColumn(label(col), disabled=True, help="Taken from Skills on save.")
    if col in NUMBERS:
        return cc.NumberColumn(label(col), min_value=0, step=1, help=help_)
    if col in LINKS:
        return cc.LinkColumn(label(col), validate=r"^https://.+", help=help_ + " · https://…")
    if (table, col) in MULTI:
        if hasattr(cc, "MultiselectColumn"):
            try:
                return cc.MultiselectColumn(label(col), options=opts or [], accept_new_options=True,
                                            help=help_ + " · pick several or type a new one")
            except TypeError:  # an older Streamlit without new options
                pass
        return cc.ListColumn(label(col), help=help_)
    if opts is not None:
        return cc.SelectboxColumn(label(col), options=opts, help=help_ + " · missing an option? «➕ New option»")
    return cc.TextColumn(label(col), width="large" if col in LONG else None, help=help_)


# ------------------------------------------------------------------------------------------------ filters
def _filters(section: str, tables: list[str], data: dict, pack_id: str) -> dict[str, str]:
    """Course / lesson filters for the tables that have those columns ('' = all)."""
    cols = {c for t in tables for c in content.SHEETS[t]}
    out: dict[str, str] = {}
    if "PackId" not in cols:
        return out
    packs = _uniq(_values(data["Courses"], "PackId"))
    c = st.columns([2, 3])
    if len(packs) > 1:
        out["PackId"] = c[0].selectbox("Course", packs, index=packs.index(pack_id) if pack_id in packs else 0, key=f"ed_{section}_pack")
    elif packs:
        out["PackId"] = packs[0]
    if "Questions" in tables or "LessonResources" in tables:
        mine = [r for r in data["Lessons"] if r["PackId"] == out.get("PackId")]
        names = {"": "All lessons"} | {r["LessonId"]: f"{r['LessonId']} · {r['Title']}" for r in mine}
        out["LessonId"] = c[1].selectbox("Lesson (for questions and videos)", list(names), format_func=lambda k: names[k], key=f"ed_{section}_lesson")
    return out


def _match(table: str, row: dict, flt: dict[str, str]) -> bool:
    for col, val in flt.items():
        if not val or col not in content.SHEETS[table] or (col == "LessonId" and table == "Lessons"):
            continue  # the lessons table always shows every lesson of the course
        if str(row.get(col, "")) != val:
            return False
    return True


def _merge(table: str, full: list[dict], edited: list[dict], flt: dict[str, str]) -> list[dict]:
    """The full table with the filtered block replaced by what was edited (in the place of the block)."""
    for r in edited:  # a new row takes the values of the filter it was added under
        for col, val in flt.items():
            if val and col in content.SHEETS[table] and not r.get(col) and not (col == "LessonId" and table == "Lessons"):
                r[col] = val
    out, placed = [], False
    for r in full:
        if _match(table, r, flt):
            if not placed:
                out += edited
                placed = True
        else:
            out.append(r)
    return out if placed else out + edited


def _fill_ids(data: dict[str, list[dict]]) -> None:
    for (table, col), source in ID_FROM.items():
        for r in data.get(table, []):
            if not str(r.get(col) or "").strip() and str(r.get(source) or "").strip():
                r[col] = slug(r[source])[:60]
    for r in data.get("LearningPaths", []):  # informative columns follow Skills
        sk = next((s for s in data.get("Skills", []) if s["SkillId"] == r.get("SkillId")), None)
        if sk:
            fam = next((f["Name"] for f in data.get("Families", []) if f["FamilyId"] == sk["FamilyId"]), "")
            r.update(Family=fam, Vendor=sk.get("Vendor", ""), Skill=sk["Name"])


# ------------------------------------------------------------------------------------------------ UI
def toggle(section: str) -> bool:
    """The «✏️ Edit mode» switch of a section (owners only)."""
    return st.toggle("✏️ Edit mode", key=f"ed_on_{section}",
                     help="Edit this section's content with drop-down lists. Saving checks everything and updates the Excel content file.")


def edit_mode(section: str, pack_id: str = "", tables: list[str] | None = None) -> None:
    """The editor of a section: one inner tab per table, the drop-down lists, «➕ New option», save / discard."""
    tables = tables or SECTION_TABLES[section]
    data = _tables(signature())
    extra: dict = st.session_state.setdefault("ed_extra", {})
    version = st.session_state.get(f"ed_v_{section}", 0)
    with st.container(border=True, key=f"ed_box_{section}"):
        st.markdown("#### ✏️ Edit mode")
        st.caption("Change cells, pick from the lists, add rows at the bottom of each table or select rows to delete them. "
                   "Nothing is saved until «Save changes»: then everything is checked as if you imported the Excel file.")
        flt = _filters(section, tables, data, pack_id)
        with st.popover("➕ New option for a list"):
            cols = [(t, c) for t in tables for c in content.SHEETS[t] if (t, c) not in MULTI and options(t, c, data, extra) is not None]
            if cols:
                pick = st.selectbox("List", cols, key=f"ed_{section}_optcol", format_func=lambda tc: f"{TABLE_NAME[tc[0]]} → {label(tc[1])}")
                value = st.text_input("New option", key=f"ed_{section}_optval")
                if st.button("Add to the list", key=f"ed_{section}_optadd", disabled=not value.strip()):
                    extra.setdefault(pick, [])
                    if value.strip() not in extra[pick]:
                        extra[pick].append(value.strip())
                    st.toast(f"\"{value.strip()}\" now shows in the list.")
                    st.rerun()
            st.caption("Columns with several values (skills, aliases) take new options by typing them directly in the cell.")
        tabs = st.tabs([TABLE_NAME[t] for t in tables]) if len(tables) > 1 else [st.container()]
        edited: dict[str, tuple[list[dict], list[dict]]] = {}
        stamp = "_".join(f"{k}-{v}" for k, v in flt.items())
        for tab, table in zip(tabs, tables):
            with tab:
                if table in ABOUT:
                    st.caption(ABOUT[table])
                shown = [r for r in data[table] if _match(table, r, flt)]
                df = _frame(table, shown)
                config = {c: _column(table, c, options(table, c, data, extra)) for c in df.columns}
                for c, v in flt.items():  # the filter already says it: the column is hidden and new rows take its value
                    if v and c in df.columns and not (c == "LessonId" and table == "Lessons"):
                        config[c] = None
                out = st.data_editor(df, num_rows="dynamic", hide_index=True, width="stretch", column_config=config,
                                     key=f"ed_{section}_{table}_{stamp}_{version}")
                st.caption(f"{len(out)} row(s)")
                edited[table] = (shown, _rows(table, out))
        changed = [t for t, (before, after) in edited.items() if _rows(t, _frame(t, before)) != after]
        a, b, c = st.columns([2, 1, 3])
        save = a.button("💾 Save changes", type="primary", key=f"ed_{section}_save", disabled=not changed, width="stretch")
        if b.button("Discard", key=f"ed_{section}_undo", disabled=not changed, width="stretch"):
            st.session_state[f"ed_v_{section}"] = version + 1
            st.rerun()
        c.caption(f"Tables with unsaved changes: {', '.join(TABLE_NAME[t] for t in changed)}" if changed else "No changes.")
        if save:
            full = {name: [dict(r) for r in rows] for name, rows in data.items()}
            for t in changed:
                full[t] = _merge(t, full[t], edited[t][1], flt)
            _fill_ids(full)
            result = content.build(full)
            if result["problems"]:
                st.error(f"Nothing was saved: {len(result['problems'])} problem(s) to fix.")
                st.code("\n".join(result["problems"][:40]), language=None, wrap_lines=True)
            else:
                content.apply(result)
                content_sync.refresh()
                st.cache_data.clear()
                st.session_state[f"ed_v_{section}"] = version + 1
                st.session_state["ed_saved"] = "Changes saved (a backup of the previous content was made)."
                ui.fx("step")
                st.rerun()


def saved_notice() -> None:
    msg = st.session_state.pop("ed_saved", None)
    if msg:
        st.toast(msg)
