"""The Academy page: course (lesson + quiz + compact video panel + VBD), glossary quiz, video library, progress, team."""

from __future__ import annotations

import random
from datetime import date

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from academy import content_sync, notify, quiz, report, track, ui
from academy import content_xlsx as content
from academy.access import load_access, save_access
from academy.catalog import (DEFAULT_SHEET, SEVERITIES, VENDORS, Catalog, vendor_of, catalog_from_tables, load_materials, parse_grid, parse_text, read_xlsx,
                             save_catalog, save_materials, sheet_names, slug, validate_catalog, validate_materials)
from academy import assistant as ai
from academy.exam_page import assistant_box, exams_tab, material_links
from academy.certs import Certs
from academy.certs_page import certs_admin, my_certs
from academy.demand_page import demand_tab
from academy.forum import Forum
from academy.forum_page import forum_tab
from academy.i18n import L, T, columns, message
from academy.pack import Pack, Resource
from academy.route import ITEM_POINTS, RouteTracker, build_routes, is_learn
from academy.progress import VBD_POINTS, Tracker, team
from academy.videos import DEFAULT_SIZE, SIZES, embed_src

LEVEL_EN = {"básico": "basic", "intermedio": "intermediate", "avanzado": "advanced"}


# ---------------------------------------------------------------------------------------------- small pieces
def _label(r: Resource) -> str:
    icon = {"video": "▶", "playlist": "☰", "link": "↗"}.get(r.kind, "▶")
    return f"{icon} [{r.lang.upper()}] {r.title} — {r.channel}"


def _size_picker(lang: str, key: str) -> None:
    names = {"XS": "Mini", "S": "Chico" if lang == "es" else "Small", "M": "Mediano" if lang == "es" else "Medium",
             "L": "Grande" if lang == "es" else "Large"}
    if st.session_state.get(key) not in SIZES:
        st.session_state[key] = DEFAULT_SIZE
    st.segmented_control(T("video_size", lang), list(SIZES), key=key, format_func=lambda k: names[k], label_visibility="collapsed")


def play(r: Resource, lang: str, key: str, size_key: str) -> None:
    """A small fixed-size player (explicit iframe width/height, so it stays small in any column) or a link."""
    src = embed_src(r.url) if r.kind in ("video", "playlist") else None
    if src:
        w = SIZES.get(st.session_state.get(size_key, DEFAULT_SIZE), SIZES[DEFAULT_SIZE])
        h = int(w * 9 / 16) + 2
        if hasattr(st, "iframe"):  # Streamlit ≥ 1.56; the components.v1 version is being retired
            st.iframe(src, width=w, height=h)
        else:
            components.iframe(src, width=w, height=h)
    else:
        st.link_button(T("open", lang), r.url)


def details(r: Resource, why: str, lang: str) -> None:
    level = LEVEL_EN.get(r.level, r.level) if lang == "en" else r.level
    who = f" · {r.who}" if r.who else ""
    st.markdown(f"**{r.title}**")
    st.caption(f"{r.channel}{who} · {r.lang.upper()} · {level}")
    st.markdown(T("why_here", lang) + why)


def link(target: dict, default_label: str) -> None:
    if not target:
        return
    label = target.get("label") or default_label
    if target.get("url"):
        st.link_button(f"{label} ↗", target["url"])
    else:
        st.caption(f"→ {label}")


# ---------------------------------------------------------------------------------------------- sections
def header(pack: Pack, tr: Tracker, lang: str) -> None:
    pts = tr.total_points()
    cur, need = tr.rank(pts)
    nxt = pack.ranks[cur + 1].name if need is not None else None
    note = T("note_next", lang, p=f"{pts:,}", n=f"{need:,}", lvl=nxt) if nxt else T("note_top", lang, p=f"{pts:,}")
    st.markdown(track.track_html(pack, pts, note), unsafe_allow_html=True)
    c = st.columns(4)
    c[0].metric(T("points", lang), f"{pts:,}", border=True)
    c[1].metric(T("rank", lang), pack.ranks[cur].name, delta=T("to_next", lang, n=need, lvl=nxt) if nxt else T("top", lang),
                delta_color="off", border=True)
    c[2].metric(T("lessons_done", lang), f"{len(tr.completed_lessons())} / {len(pack.lessons)}", border=True)
    c[3].metric(T("vbds_done", lang), f"{len(tr.vbds_done())} / {sum(1 for x in pack.lessons if x.vbd)}", border=True)


def lesson_panel(pack: Pack, lesson_id: str, lang: str) -> None:
    items = pack.for_lesson(lesson_id)
    if lang == "en":  # English view: only the English resources, unless the lesson has none
        items = [it for it in items if it[0].lang == "en"] or items
    if not items:
        return
    st.markdown(T("videos_for", lang, n=sum(r.kind != "link" for r, _ in items)))
    idx = st.selectbox(T("choose_video", lang), list(range(len(items))), key=f"ak_vid_{lesson_id}",
                       format_func=lambda i: _label(items[i][0]), label_visibility="collapsed")
    r, why = items[idx]
    _size_picker(lang, "ak_vid_size")
    play(r, lang, key=f"ak_play_{lesson_id}_{idx}", size_key="ak_vid_size")
    details(r, why, lang)
    with st.expander(T("all_resources", lang, n=len(items))):
        for i, (res, w) in enumerate(items):
            st.markdown(f"{i + 1}. **{res.title}** — {res.channel}  \n{w}")
            st.link_button(T("open_source", lang), res.url)
    st.caption(T("third_party", lang))


def vbd_box(pack: Pack, tr: Tracker, lesson_id: str, lang: str) -> None:
    les = pack.lesson(lesson_id)
    v = les.vbd
    if v is None:
        return
    done = lesson_id in tr.vbds_done()
    with st.container(border=True):
        st.markdown(T("vbd_title", lang))
        st.markdown(f"**{v.deliverable}**")
        st.markdown(T("done_when", lang))
        checks = tr.checks(lesson_id)
        for i, crit in enumerate(v.done_when):
            val = st.checkbox(crit, value=checks.get(i, False), key=f"ak_vbd_{tr.learner}_{lesson_id}_{i}")
            if val != checks.get(i, False):
                tr.set_check(lesson_id, i, val)
        st.caption(T("value", lang) + v.value)
        link(v.where, T("where", lang))
        if done:
            st.success(T("vbd_already", lang))
        else:
            all_ticked = all(st.session_state.get(f"ak_vbd_{tr.learner}_{lesson_id}_{i}") for i in range(len(v.done_when)))
            ev = st.text_input(T("evidence", lang), key=f"ak_vbd_ev_{lesson_id}")
            if st.button(T("mark_vbd", lang), key=f"ak_vbd_btn_{lesson_id}", disabled=not all_ticked, type="primary"):
                pts = tr.complete_vbd(lesson_id, ev)
                ui.fx("win")
                st.session_state[f"ak_vbd_fb_{lesson_id}"] = pts
                st.rerun()
        fb = st.session_state.pop(f"ak_vbd_fb_{lesson_id}", None)
        if fb is not None:
            st.toast(T("vbd_ok", lang, pts=T("plus_pts", lang, p=fb) if fb else ""))


def course(pack: Pack, tr: Tracker, lang: str, role: str | None) -> None:
    done = tr.completed_lessons()
    by_level = pack.by_level()
    rec = pack.lessons_for_role(role) if role else set()
    level = st.radio(T("level", lang), pack.levels, horizontal=True, key="ak_level",
                     format_func=lambda lv: f"{lv} ({sum(1 for x in by_level[lv] if x.id in done)}/{len(by_level[lv])})")
    items = by_level[level]
    if not items:
        return
    lid = st.selectbox(T("lesson", lang), [x.id for x in items], key=f"ak_lesson_{level}",
                       format_func=lambda i: ("✅ " if i in done else "○ ") + ("⭐ " if i in rec else "")
                       + next(x.title for x in items if x.id == i))
    if rec:
        st.caption(T("for_role", lang))
    les = pack.lesson(lid)
    ui.lesson_progress(tr, les, lang)
    main, side = st.columns([3, 2], gap="large")
    with side:  # compact video panel that stays in view while you scroll through the questions
        st.markdown('<style>div[data-testid="stColumn"]:has(.st-key-ak_side){position:sticky;top:3.75rem;align-self:flex-start}</style>', unsafe_allow_html=True)
        with st.container(key="ak_side"):
            lesson_panel(pack, lid, lang)
    with main:
        with st.container(border=True):
            st.markdown(f"### {les.title}")
            st.markdown(f"_{les.summary}_")
            st.markdown(ui.points_html(les.points), unsafe_allow_html=True)
            link(les.practice, T("practice", lang))
        st.markdown(T("check_title", lang))
        for k, q in enumerate(les.quiz):
            item = f"{lid}:{k}"
            opts, ci = quiz.shuffled(item, q.options, q.answer)
            with st.container(border=True):
                choice = st.radio(f"**{k + 1}. {q.q}**", list(range(len(opts))), format_func=lambda j, o=opts: o[j], index=None,
                                  key=f"ak_q_{tr.learner}_{item}")
                if st.button(T("check", lang), key=f"ak_check_{item}", disabled=choice is None):
                    ok = choice == ci
                    was_done = lid in tr.completed_lessons()
                    st.session_state[f"ak_fb_{tr.learner}_{item}"] = (ok, tr.answer_quiz(item, ok))
                    ui.fx(("win" if not was_done and lid in tr.completed_lessons() else "ok") if ok else "bad")
                fb = st.session_state.get(f"ak_fb_{tr.learner}_{item}")
                if fb:
                    ok, pts = fb
                    if ok:
                        st.success(T("correct", lang) + (T("plus_pts", lang, p=pts) if pts else "") + f". {q.why}")
                    else:
                        st.error(T("wrong", lang))
        if lid in tr.completed_lessons():
            st.success(T("lesson_done", lang))
        vbd_box(pack, tr, lid, lang)


def glossary(pack: Pack, tr: Tracker, lang: str) -> None:
    if len(pack.glossary) < 4:
        return
    st.markdown(T("gloss_intro", lang))
    if "ak_gq_n" not in st.session_state:
        st.session_state["ak_gq_n"] = random.randint(0, 10_000)
    n = st.session_state["ak_gq_n"]
    gq = quiz.glossary_question(pack.glossary, random.Random(n), lang)
    with st.container(border=True):
        st.caption(f"{T('category', lang)}: {gq['category']}")
        pick = st.radio(gq["prompt"], list(range(4)), format_func=lambda j: gq["options"][j], index=None, key=f"ak_gq_pick_{n}")
        c = st.columns([1, 1, 3])
        if c[0].button(T("check", lang), key="ak_gq_check", disabled=pick is None):
            ok = pick == gq["correct"]
            tr.record("glossary", gq["term"], 10 if ok else 0, ok)
            ui.fx("ok" if ok else "bad")
            st.session_state["ak_gq_fb"] = (n, ok)
        if c[1].button(T("next_q", lang), key="ak_gq_next"):
            st.session_state["ak_gq_n"] += 1
            st.rerun()
        fb = st.session_state.get("ak_gq_fb")
        if fb and fb[0] == n:
            (st.success if fb[1] else st.error)((T("correct", lang) + " (+10). " if fb[1] else T("not_this", lang)) + gq["explanation"])
    with st.expander(T("browse", lang, n=len(pack.glossary))):
        q = st.text_input(T("search", lang), key="ak_gloss_search")
        gdf = pd.DataFrame(pack.glossary)[["term", "category", "definition"]]
        if q:
            gdf = gdf[gdf.apply(lambda r: q.lower() in (r["term"] + " " + r["definition"]).lower(), axis=1)]
        st.dataframe(gdf, hide_index=True, width="stretch")


def library(pack: Pack, lang: str) -> None:
    st.markdown(T("library_intro", lang))
    def by_topic(k: str) -> list[Resource]:  # English view: only the English resources
        return [r for r in pack.by_topic(k) if lang != "en" or r.lang == "en"]

    topics = [k for k in pack.topics if by_topic(k)]
    if not topics:
        return
    c = st.columns([2, 1])
    topic = c[0].selectbox(T("topic", lang), topics, key="ak_lib_topic", format_func=lambda k: f"{pack.topics[k]} ({len(by_topic(k))})")
    only_es = lang != "en" and c[1].toggle(T("only_es", lang), key="ak_lib_es")
    items = [r for r in by_topic(topic) if not only_es or r.lang == "es"]
    if not items:
        st.info(T("no_es", lang))
        return
    left, right = st.columns([1, 1], gap="large")
    with left:
        idx = st.radio(T("resources", lang), list(range(len(items))), key=f"ak_lib_pick_{topic}_{only_es}", format_func=lambda i: _label(items[i]))
    r = items[idx]
    with right:
        _size_picker(lang, "ak_lib_size")
        play(r, lang, key=f"ak_lib_{topic}_{idx}", size_key="ak_lib_size")
        details(r, r.why, lang)
        used = [les.id for les in pack.lessons if r.key in les.resources]
        if used:
            st.caption(T("used_in", lang) + ", ".join(used))
    st.caption(T("third_party", lang))


def progress_tab(pack: Pack, tr: Tracker, lang: str, role: str | None) -> None:
    header(pack, tr, lang)
    st.markdown(T("badges", lang))
    bdg = tr.badges(lang)
    st.dataframe(pd.DataFrame([{"": "🏅" if ok else "", T("badges", lang).strip("# "): n, T("how", lang): how}
                               for n, how, ok in bdg]), hide_index=True, width="stretch")
    st.markdown(T("ranks", lang))
    st.caption(" → ".join(f"{r.emoji} {r.name} ({r.points}+)" for r in pack.ranks))
    if role:
        st.markdown(T("role_path", lang, r=role))
        done, vbds, rec = tr.completed_lessons(), tr.vbds_done(), pack.lessons_for_role(role)
        st.dataframe(pd.DataFrame([{"ID": les.id, T("level", lang): les.level, T("lesson", lang): les.title,
                                    "✅": "✅" if les.id in done else "", "🎯": "🎯" if les.id in vbds else ""}
                                   for les in pack.lessons if les.id in rec]), hide_index=True, width="stretch")
    ev = tr.events()
    if len(ev):
        st.markdown(T("recent", lang))
        st.dataframe(ev.sort_values("id", ascending=False).head(30)[["time", "kind", "item", "points", "correct"]],
                     hide_index=True, width="stretch")


def team_tab(conn, pack: Pack, lang: str) -> None:
    st.markdown(T("team_intro", lang))
    df = columns(team(conn, pack), lang)
    if df.empty:
        st.info(T("no_team", lang))
        return
    st.dataframe(df, hide_index=True, width="stretch")
    st.download_button(T("download", lang), df.to_csv(index=False).encode("utf-8-sig"), file_name=L(lang, f"progreso_{pack.id}.csv", f"progress_{pack.id}.csv"),
                       mime="text/csv")


def champion_team(conn, packs: list[Pack], exams: list, catalog, families: set[str], lang: str) -> set[str]:
    """What a champion sees: only the people working on their families, counted on those families' lessons and exams."""
    names = [f.name for f in catalog.families if f.id in families]
    st.markdown(L(lang, "#### Mi familia: ", "#### My family: ") + ", ".join(names))
    st.caption(L(lang, "Ves solo a quienes cursan lecciones o certificaciones de tu familia de skills.",
                 "You only see people taking lessons or certifications of your skill family."))
    family_courses_editor(catalog, families, lang)
    rows = notify.family_team(conn, packs, exams, catalog, families)
    if not rows:
        st.info(L(lang, "Todavía nadie ha empezado contenido de tu familia.", "Nobody has started your family's content yet."))
        return set()
    df = columns(pd.DataFrame(rows), lang)
    st.dataframe(df, hide_index=True, width="stretch")
    st.download_button(T("download", lang), df.to_csv(index=False).encode("utf-8-sig"),
                       file_name=L(lang, "progreso_mi_familia.csv", "my_family_progress.csv"), mime="text/csv",
                       key="ak_fam_csv")
    return {r["Persona"] for r in rows}


PROVIDERS = ["Microsoft Learn", "Workday Learning", "AWS Skill Builder", "Google Cloud Skills Boost", "Cisco Networking Academy", "IBM SkillsBuild",
             "Anthropic Academy", "GitHub", "Linux Foundation", "PMI", "Interno", "Otro"]


def _materials_table(groups: list[tuple[str, list[dict]]], default_kind: str) -> pd.DataFrame:
    """The learning-path editor's rows: one per class or reference item, with its class number."""
    from academy.route import class_order

    rows = []
    for skill, items in groups:
        number = {id(m): n for n, m in enumerate(class_order(items), start=1)}
        rows += [{"skill": skill, "order": number.get(id(m)), "title": m.get("title", ""), "url": m.get("url", ""),
                  "provider": m.get("provider", ""), "kind": m.get("kind", default_kind), "verified": m.get("verified", "")} for m in items]
    df = pd.DataFrame(rows, columns=["skill", "order", "title", "url", "provider", "kind", "verified"])
    return df.astype({"skill": "string", "order": "Int64", "title": "string", "url": "string", "provider": "string", "kind": "string",
                      "verified": "string"})


def _class_column(lang: str):
    return st.column_config.NumberColumn(L(lang, "Clase", "Class"), min_value=1, step=1,
                                         help=L(lang, "Orden en la ruta de la skill: clase 1, clase 2…", "Order in the skill's path: class 1, class 2…"))


def _material_item(r: dict) -> dict:
    item = {k: ("" if pd.isna(r.get(k)) else str(r[k]).strip()) for k in ("title", "url", "provider", "kind", "verified")}
    if pd.notna(r.get("order")):
        item["order"] = int(r["order"])
    return item


def family_courses_editor(catalog, families: set[str], lang: str) -> None:
    """The family lead adds or removes the route's steps for THEIR skills: Microsoft Learn, the vendor's path, or courses of
    the company's own portal (Workday Learning). The app only links to them; each person opens the course with their own sign-in."""
    skills = [s for s in catalog.skills if s.family in families]
    by_name = {s.name: s.id for s in skills}
    mats = load_materials()
    with st.expander(L(lang, "Cursos de mi familia: agregar o quitar pasos de la ruta", "My family's courses: add or remove route steps")):
        st.caption(L(lang, "Pega el enlace del curso (Microsoft Learn, la ruta del fabricante o Workday Learning). Lo que tenga tipo "
                           "módulo, ruta, curso o laboratorio cuenta como paso de la ruta; guía, documento y video son material de consulta.",
                     "Paste the course link (Microsoft Learn, the vendor's path or Workday Learning). Module, path, course and lab "
                     "count as route steps; guide, doc and video are reference material."))
        df = _materials_table([(s.name, mats.get(s.id, [])) for s in skills], "course")
        ed = st.data_editor(df, num_rows="dynamic", hide_index=True, width="stretch", key="ak_fam_courses", column_config={
            "skill": st.column_config.SelectboxColumn(T("sk_col_skill", lang), options=list(by_name), required=True),
            "order": _class_column(lang),
            "title": st.column_config.TextColumn(L(lang, "Título del curso", "Course title"), required=True),
            "url": st.column_config.LinkColumn("URL", required=True, validate=r"^https://.+"),
            "provider": st.column_config.SelectboxColumn(L(lang, "Proveedor", "Provider"), options=PROVIDERS, required=True),
            "kind": st.column_config.SelectboxColumn(L(lang, "Tipo", "Kind"), options=["course", "path", "module", "lab", "video", "guide", "doc"],
                                                     required=True),
            "verified": st.column_config.TextColumn(L(lang, "Verificado (fecha)", "Verified (date)"))})
        if st.button(L(lang, "Guardar cursos de mi familia", "Save my family's courses"), key="ak_fam_courses_save", type="primary"):
            new: dict[str, list[dict]] = {}
            for r in ed.to_dict("records"):
                if pd.notna(r.get("skill")) and pd.notna(r.get("title")) and pd.notna(r.get("url")) and r["skill"] in by_name:
                    item = _material_item(r)
                    item["verified"] = item["verified"] or date.today().isoformat()
                    new.setdefault(by_name[r["skill"]], []).append(item)
            errs = validate_materials(new, catalog)
            if errs:
                for e in errs:
                    st.error(message(e, lang))
            else:
                merged = {k: v for k, v in mats.items() if k not in by_name.values()}  # other families' material is untouched
                merged.update(new)
                save_materials(merged)
                content_sync.refresh()  # the content file always mirrors what the app holds
                st.toast(L(lang, "Cursos guardados.", "Courses saved."))


def reports_tab(conn, packs: list[Pack], exams: list, catalog, lang: str, who: str, only: set[str] | None = None) -> None:
    """The reports of the academy: every family for an owner, only their own (``only``) for a champion.

    Families (status), people (who is keeping up with the career path and who is not), certifications (held, desired,
    about to expire) and the administration of the certification register."""
    if not catalog:
        st.info(L(lang, "Los reportes se organizan por familia de skills: primero carga el catálogo en «Mapa de skills».",
                  "Reports are organized by skill family: load the catalog in the Skills map first."))
        return
    rep = report.build(conn, packs, exams, catalog, lang, only)
    people_names = report.roster(conn)
    rep["certs"] = Certs(conn).report(catalog, lang, only, people_names)
    t, s, cs = report.titles(lang), rep["summary"], rep["certs"]["summary"]
    st.caption(f"{t['generated']}: {rep['generated']} · {t['rules']}")
    c = st.columns(6)
    for col, (label, value) in zip(c, ((t["families"], s["families"]), (t["on_track"], s["on_track"]), (t["active_people"], s["people"]),
                                        (t["behind"], s["behind"]), (t["not_started"], s["not_started"]),
                                        (L(lang, "Certificaciones actuales", "Current certifications"), cs["current"]))):
        col.metric(label, value, border=True)
    stamp = rep["generated"][:10]
    a, b = st.columns(2)
    a.download_button(L(lang, "Descargar todo el reporte en Excel", "Download the whole report as Excel"), report.to_xlsx(rep),
                      file_name=L(lang, f"reporte_academia_{stamp}.xlsx", f"academy_report_{stamp}.xlsx"),
                      mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="ak_rep_xlsx", width="stretch")
    b.download_button(L(lang, "Descargar reporte para imprimir (HTML)", "Download printable report (HTML)"), report.to_html(rep).encode("utf-8"),
                      file_name=L(lang, f"reporte_academia_{stamp}.html", f"academy_report_{stamp}.html"), mime="text/html",
                      key="ak_rep_html", width="stretch")
    tabs = st.tabs([L(lang, "Familias de skills", "Skill families"), L(lang, "Personas y ruta de carrera", "People and career path"),
                    L(lang, "Certificaciones", "Certifications"), L(lang, "Administrar certificaciones", "Manage certifications")])
    with tabs[0]:
        st.markdown(f"#### {t['report']}")
        st.dataframe(pd.DataFrame(report.visible(rep["status"])), hide_index=True, width="stretch")
    with tabs[1]:
        st.markdown(f"#### {t['people']}")
        st.caption(L(lang, "Una fila por persona, primero quien no está cumpliendo. El estado es el peor de sus familias.",
                     "One row per person, whoever is not keeping up first. The status is the worst across their families."))
        if rep["people"]:
            st.dataframe(pd.DataFrame(report.visible(rep["people"])), hide_index=True, width="stretch")
        else:
            st.info(t["empty"])
        st.markdown(f"#### {t['paths']}")
        names = {k: L(lang, *v) for k, v in report.PATH.items()}
        fam_names = sorted({r[next(iter(r))] for r in rep["paths"]})
        f1, f2 = st.columns([2, 3])
        fam = f1.selectbox(L(lang, "Familia de skills", "Skill family"), [""] + fam_names, key="ak_rep_fam",
                           format_func=lambda k: k or L(lang, "Todas", "All"))
        states = f2.multiselect(L(lang, "Estado en la ruta", "Status on the path"), report.PATH_ORDER, format_func=lambda k: names[k],
                                default=[report.BEHIND, report.AT_RISK, report.GOING, report.DONE], key="ak_rep_states")
        rows = [r for r in rep["paths"] if (not fam or r[next(iter(r))] == fam) and r["_path"] in states]
        if rows:
            st.dataframe(pd.DataFrame(report.visible(rows)), hide_index=True, width="stretch")
        else:
            st.info(L(lang, "Nadie con ese filtro.", "Nobody matches that filter."))
        st.markdown(f"#### {t['followup']}")
        late = [r for r in rep["followup"] if r["_late"]]
        if late:
            st.dataframe(pd.DataFrame(report.visible(late)), hide_index=True, width="stretch")
        else:
            st.success(L(lang, "Nadie requiere seguimiento hoy.", "Nobody needs follow-up today."))
    with tabs[2]:
        m = st.columns(4)
        m[0].metric(L(lang, "Personas con alguna certificación", "People with a certification"), f"{cs['people_with']} / {cs['people']}", border=True)
        m[1].metric(L(lang, "Certificaciones actuales", "Current certifications"), cs["current"], border=True)
        m[2].metric(L(lang, "Certificaciones deseables", "Desired certifications"), cs["desired"], border=True)
        m[3].metric(L(lang, "Vencen en 90 días o ya vencieron", "Expire within 90 days or already did"), cs["expiring"], border=True)
        st.markdown(f"#### {t['certs_fam']}")
        if rep["certs"]["families"]:
            st.dataframe(pd.DataFrame(rep["certs"]["families"]), hide_index=True, width="stretch")
        else:
            st.info(L(lang, "Ninguna familia tiene certificaciones definidas todavía: agrégalas en «Administrar certificaciones».",
                      "No family has certifications defined yet: add them under Manage certifications."))
        st.markdown(f"#### {t['certs_people']}")
        if rep["certs"]["people"]:
            st.dataframe(pd.DataFrame(rep["certs"]["people"]), hide_index=True, width="stretch")
        if rep["certs"]["expiring"]:
            st.markdown(f"#### {t['certs_exp']}")
            st.dataframe(pd.DataFrame(rep["certs"]["expiring"]), hide_index=True, width="stretch")
    with tabs[3]:
        certs_admin(conn, catalog, lang, {f.id for f in catalog.families} if only is None else set(only), who, people_names)


def certifications_tab(exams: list, conn, learner: str, lang: str, catalog, leader: bool) -> None:
    """My certifications (what I hold and what I aim for) and the preparation for an exam."""
    views = {"mine": L(lang, "Mis certificaciones", "My certifications"), "prep": L(lang, "Preparar un examen", "Prepare for an exam")}
    view = st.segmented_control("certs_view", list(views), default="mine", format_func=lambda k: views[k], key="ak_cert_view",
                                label_visibility="collapsed") or "mine"
    if view == "mine":
        my_certs(conn, catalog, learner, lang)
    else:
        exams_tab(exams, conn, learner, lang, catalog, leader=leader)


def notices_section(conn, packs: list[Pack], exams: list, catalog, lang: str, only: set[str] | None = None) -> None:
    """Notices ready to send (with copy to the family champion). Offline they open in Outlook; in M365 a flow sends them."""
    st.markdown(L(lang, "#### Avisos por enviar", "#### Notices to send"))
    st.caption(L(lang, f"Reglas: curso terminado · simulacro aprobado · {notify.INACTIVE_DAYS} días sin actividad · {notify.STALLED_DAYS} días sin avance. "
                       "Cada aviso va con copia al champion de la familia de skills.",
                 f"Rules: course finished · mock passed · {notify.INACTIVE_DAYS} days inactive · {notify.STALLED_DAYS} days without progress. "
                 "Each notice is copied to the skill family champion."))
    todo = [n for n in notify.pending(conn, packs, exams, catalog, lang=lang) if only is None or n.learner in only]
    if not todo:
        st.info(L(lang, "No hay avisos pendientes.", "No pending notices."))
        return
    st.download_button(L(lang, f"Descargar la cola ({len(todo)}) en CSV", f"Download the queue ({len(todo)}) as CSV"),
                       pd.DataFrame(notify.queue_rows(todo)).to_csv(index=False).encode("utf-8-sig"), file_name=L(lang, "avisos_pendientes.csv", "pending_notices.csv"),
                       mime="text/csv", key="ak_nt_csv")
    icon = {"course_done": "🎉", "exam_passed": "🏅", "inactive": "⏰", "stalled": "🐢"}
    for i, n in enumerate(todo):
        with st.expander(f"{icon.get(n.kind, '✉️')} {n.learner} — {n.subject}"):
            st.markdown(L(lang, "**Para:** ", "**To:** ") + (n.to or L(lang, "_sin correo registrado_", "_no e-mail on file_")) + "  \n"
                        + "**CC:** " + (", ".join(n.cc) or (", ".join(n.champions) + L(lang, " _(falta su correo)_", " _(e-mail missing)_") if n.champions
                                                            else L(lang, "_familia sin champion_", "_family without champion_"))))
            st.text(n.body)
            c1, c2 = st.columns(2)
            c1.link_button(L(lang, "✉️ Abrir en Outlook", "✉️ Open in Outlook"), notify.mailto(n), width="stretch")
            if c2.button(L(lang, "Marcar como enviado", "Mark as sent"), key=f"ak_nt_sent_{i}_{n.kind}_{n.ref}", width="stretch"):
                notify.mark_sent(conn, n)
                st.rerun()


def my_notices(conn, packs: list[Pack], exams: list, catalog, learner: str, lang: str) -> None:
    """What the learner sees at the top: the same messages that would reach their inbox."""
    for n in notify.pending(conn, packs, exams, catalog, learner=learner.strip() or "yo", include_sent=True, lang=lang):
        first = n.body.split("\n\n")[1] if n.body.count("\n\n") >= 2 else n.subject
        (st.success if n.kind in ("course_done", "exam_passed") else st.warning)(f"**{n.subject}.** {first}")


def _skills_map(catalog: Catalog, packs: list[Pack], lang: str, owner: bool = True, families: set[str] | None = None) -> None:
    """``families``: for a champion, the families whose gap numbers they may see."""
    cov = catalog.coverage(packs)
    mats = load_materials()
    st.markdown(T("sk_total", lang, c=sum(1 for v in cov.values() if v), n=len(cov)) + " "
                + L(lang, f"**{sum(1 for s in catalog.skills if mats.get(s.id))}** tienen material de apoyo.",
                    f"**{sum(1 for s in catalog.skills if mats.get(s.id))}** have support material."))
    for fam in catalog.by_gap():
        skills = catalog.in_family(fam.id)
        covered = sum(1 for s in skills if cov[s.id])
        with st.container(border=True):
            st.markdown(f"#### {fam.name}")
            st.markdown(T("sk_champion", lang, n=fam.champion) if fam.champion else T("sk_no_champion", lang))
            numbers = owner or fam.id in (families or set())  # gap numbers: owners, and each champion for their own family
            if numbers:
                c = st.columns(3)
                c[0].metric(T("sk_gap", lang), "—" if fam.gap_volume is None else f"{fam.gap_volume:,}")
                c[1].metric(T("sk_roles", lang), "—" if fam.role_impact is None else f"{fam.role_impact:,}")
                c[2].metric(T("sk_cover", lang), f"{covered} / {len(skills)}")
            else:
                st.caption(f"{T('sk_cover', lang)}: {covered} / {len(skills)}")
            st.progress(covered / len(skills) if skills else 0.0)
            rows = []
            vendors = list(dict.fromkeys(vendor_of(s, mats) for s in skills))
            for s in sorted(skills, key=lambda s: (vendors.index(vendor_of(s, mats)), s.category)):  # family -> vendor -> category -> skill
                row = {L(lang, "Tecnología / vendor", "Technology / vendor"): vendor_of(s, mats)}
                if any(x.category for x in skills):
                    row[L(lang, "Categoría", "Category")] = s.category
                row[T("sk_col_skill", lang)] = s.name + ("" if s.confirmed else f" · {T('sk_unconfirmed', lang)}")
                if any(x.severity for x in skills):
                    row[T("sk_col_sev", lang)] = s.severity
                if any(x.target for x in skills):
                    row[T("sk_col_target", lang)] = s.target
                if numbers and any(x.impacted_roles is not None for x in skills):
                    row[T("sk_col_impact", lang)] = s.impacted_roles
                row[T("sk_col_lessons", lang)] = " · ".join(t for _, t in cov[s.id]) or T("sk_none", lang)
                row[L(lang, "Material", "Material")] = len(mats.get(s.id, []))
                rows.append(row)
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
            with_mat = [s for s in skills if mats.get(s.id)]
            if with_mat:
                with st.expander(L(lang, f"Material de apoyo ({sum(len(mats[s.id]) for s in with_mat)})",
                                   f"Support material ({sum(len(mats[s.id]) for s in with_mat)})")):
                    for s in with_mat:
                        st.markdown(f"**{s.name}**")
                        material_links(mats[s.id])


def _orphans(cat: Catalog, packs: list[Pack]) -> list[str]:
    known = cat.skill_ids()
    return sorted({sid for p in packs for les in p.lessons for sid in les.catalog_skills if sid not in known})


def _save(cat: Catalog, source: str) -> None:
    save_catalog(cat, source=source, updated=date.today().isoformat())
    content_sync.refresh()  # the content file always mirrors what the app holds
    st.session_state["ak_sk_saved"] = True
    st.rerun()


def _preview(rows: list[list], catalog: Catalog | None, packs: list[Pack], lang: str, keep_roles: bool, source: str, key: str) -> None:
    new, rep = parse_grid(rows, keep_roles=keep_roles, previous=catalog)
    if new is None:
        st.error(message(rep["error"], lang))
        return
    st.success(T("sk_found", lang, f=rep["families"], s=rep["skills"], r=rep["header_row"]))
    if not rep["summary"]:
        st.caption(T("sk_no_summary", lang))
    if rep["missing_columns"]:
        st.caption(T("sk_missing_cols", lang, c=", ".join(rep["missing_columns"])))
    if rep["duplicates"]:
        st.warning(T("sk_dupes", lang, c=", ".join(rep["duplicates"])))
    lost = _orphans(new, packs)
    if lost:
        st.warning(T("sk_orphans", lang, c=", ".join(lost)))
    names = {f.id: f.name for f in new.families}
    st.dataframe(pd.DataFrame([{T("sk_col_family", lang): f.name, T("sk_col_gap", lang): f.gap_volume, T("sk_col_impact", lang): f.role_impact,
                                T("sk_col_champion", lang): f.champion} for f in new.by_gap()]), hide_index=True, width="stretch")
    st.dataframe(pd.DataFrame([{T("sk_col_family", lang): names[s.family], T("sk_col_skill", lang): s.name, T("sk_col_sev", lang): s.severity,
                                T("sk_col_target", lang): s.target, T("sk_col_impact", lang): s.impacted_roles} for s in new.skills]),
                 hide_index=True, width="stretch")
    errs = validate_catalog(new)
    for e in errs:
        st.error(message(e, lang))
    if st.button(T("sk_save", lang), key=f"ak_sk_save_{key}", type="primary", disabled=bool(errs)):
        _save(new, source)


def _skills_import(catalog: Catalog | None, packs: list[Pack], lang: str) -> None:
    st.info(T("sk_local", lang))
    up = st.file_uploader(T("sk_upload", lang), type=["xlsx", "xlsm"], key="ak_sk_file")
    if up is None:
        return
    try:
        names = sheet_names(up)
    except Exception as e:  # noqa: BLE001 - protected or damaged workbook: tell the person, don't crash
        st.error(str(e))
        return
    sheet = st.selectbox(T("sk_sheet", lang), names, index=names.index(DEFAULT_SHEET) if DEFAULT_SHEET in names else 0, key="ak_sk_sheet")
    keep = st.checkbox(T("sk_keep_roles", lang), value=False, key="ak_sk_keep")
    up.seek(0)
    _preview(read_xlsx(up, sheet), catalog, packs, lang, keep, L(lang, f"Excel: pestaña «{sheet}»", f"Excel: sheet \"{sheet}\""), "xlsx")


def _skills_paste(catalog: Catalog | None, packs: list[Pack], lang: str) -> None:
    text = st.text_area(T("sk_paste", lang), height=220, key="ak_sk_text", help=T("sk_paste_help", lang))
    st.caption(T("sk_paste_help", lang))
    if text.strip():
        _preview(parse_text(text), catalog, packs, lang, False, "Tabla pegada", "paste")


def _skills_edit(catalog: Catalog | None, packs: list[Pack], lang: str) -> None:
    st.caption(T("sk_edit_help", lang))
    fams = catalog.families if catalog else []
    names = {f.id: f.name for f in fams}
    fdf = pd.DataFrame([{"name": f.name, "gap": f.gap_volume, "impact": f.role_impact, "champion": f.champion, "email": f.champion_email}
                        for f in fams], columns=["name", "gap", "impact", "champion", "email"]
                       ).astype({"name": "string", "gap": "Int64", "impact": "Int64", "champion": "string", "email": "string"})
    all_mats = load_materials()
    sdf = pd.DataFrame([{"family": names[s.family], "vendor": vendor_of(s, all_mats), "category": s.category, "name": s.name,
                         "severity": s.severity or None, "target": s.target, "impact": s.impacted_roles}
                        for s in (catalog.skills if catalog else [])], columns=["family", "vendor", "category", "name", "severity", "target", "impact"]
                       ).astype({"family": "string", "vendor": "string", "category": "string", "name": "string", "severity": "string",
                                 "target": "string", "impact": "Int64"})
    st.markdown(T("sk_edit_fam", lang))
    fed = st.data_editor(fdf, num_rows="dynamic", hide_index=True, width="stretch", key="ak_sk_fam", column_config={
        "name": st.column_config.TextColumn(T("sk_col_family", lang), required=True),
        "gap": st.column_config.NumberColumn(T("sk_col_gap", lang), min_value=0, step=1),
        "impact": st.column_config.NumberColumn(T("sk_col_impact", lang), min_value=0, step=1),
        "champion": st.column_config.TextColumn(T("sk_col_champion", lang)),
        "email": st.column_config.TextColumn(L(lang, "Correo del champion", "Champion e-mail"))})
    fam_names = [str(x).strip() for x in fed["name"].tolist() if pd.notna(x) and str(x).strip()]
    st.markdown(T("sk_edit_sk", lang))
    sed = st.data_editor(sdf, num_rows="dynamic", hide_index=True, width="stretch", key="ak_sk_skills", column_config={
        "family": st.column_config.SelectboxColumn(T("sk_col_family", lang), options=fam_names, required=True),
        "vendor": st.column_config.TextColumn(L(lang, "Tecnología / vendor", "Technology / vendor"),
                                              help=L(lang, "Por ejemplo: ", "For example: ") + ", ".join(VENDORS)),
        "category": st.column_config.TextColumn(L(lang, "Categoría", "Category")),
        "name": st.column_config.TextColumn(T("sk_col_skill", lang), required=True),
        "severity": st.column_config.SelectboxColumn(T("sk_col_sev", lang), options=SEVERITIES),
        "target": st.column_config.TextColumn(T("sk_col_target", lang), help="P1 … P5"),
        "impact": st.column_config.NumberColumn(T("sk_col_impact", lang), min_value=0, step=1)})
    st.markdown(L(lang, "##### Material de apoyo (Microsoft Learn u otra fuente)", "##### Support material (Microsoft Learn or other source)"))
    sk_names = [str(x).strip() for x in sed["name"].tolist() if pd.notna(x) and str(x).strip()]
    by_id = {s.id: s.name for s in (catalog.skills if catalog else [])}
    mdf = _materials_table([(by_id.get(sid, sid), items) for sid, items in all_mats.items()], "doc")
    med = st.data_editor(mdf, num_rows="dynamic", hide_index=True, width="stretch", key="ak_sk_mat", column_config={
        "skill": st.column_config.SelectboxColumn(T("sk_col_skill", lang), options=sk_names, required=True),
        "order": _class_column(lang),
        "title": st.column_config.TextColumn(L(lang, "Título", "Title"), required=True),
        "url": st.column_config.LinkColumn("URL", required=True, validate=r"^https://.+"),
        "provider": st.column_config.SelectboxColumn(L(lang, "Proveedor", "Provider"), options=PROVIDERS),
        "kind": st.column_config.SelectboxColumn(L(lang, "Tipo", "Kind"), options=["path", "module", "course", "lab", "video", "guide", "doc"]),
        "verified": st.column_config.TextColumn(L(lang, "Verificado (fecha)", "Verified (date)"))})
    new = catalog_from_tables(fed.to_dict("records"), sed.to_dict("records"), previous=catalog)
    new_mats: dict[str, list[dict]] = {}
    for r in med.to_dict("records"):
        if pd.notna(r.get("skill")) and pd.notna(r.get("title")) and pd.notna(r.get("url")):
            new_mats.setdefault(slug(r["skill"]), []).append(_material_item(r))
    errs = validate_catalog(new) + validate_materials(new_mats, new)
    lost = _orphans(new, packs)
    if lost:
        st.warning(T("sk_orphans", lang, c=", ".join(lost)))
    if st.button(T("sk_save_edit", lang), key="ak_sk_save_edit", type="primary"):
        if errs:
            for e in errs:
                st.error(message(e, lang))
        else:
            save_materials(new_mats)
            _save(new, L(lang, "Edición manual", "Manual edit"))


@st.cache_data(show_spinner=False)
def _content_files(signature: tuple) -> tuple[bytes, bytes]:
    """(the single CSV, the Excel workbook) for the content on disk; rebuilt only when a content file changes."""
    return content.csv_bytes(content.export_csv()), content.export_bytes()


def _content_signature() -> tuple:
    from academy.catalog import catalog_path, materials_path

    files = content.pack_files() + [catalog_path(), materials_path()]
    return tuple((str(f), f.stat().st_mtime_ns) for f in files if f.exists())


def content_section(lang: str) -> None:
    """Owners: the whole content (courses, lessons, questions, videos, learning paths, skills catalog) as one file."""
    st.markdown(L(lang, "#### Contenido de la academia", "#### Academy content"))
    path = content_sync.content_path()
    st.markdown(L(lang,
                  f"Todo el contenido vive en **un archivo**: `{path}`. Ábrelo en Excel, filtra por la columna **Tabla**, edita, guarda y "
                  "vuelve a abrir la app: se revisa completo y, si está bien, se aplica. Con errores no cambia nada.",
                  f"All the content lives in **one file**: `{path}`. Open it in Excel, filter by the **Tabla** column, edit, save and "
                  "reopen the app: it is checked in full and applied only if it is right. With errors nothing changes."))
    last = st.session_state.get("ak_content_sync") or {}
    if last.get("status") == "problems":
        st.error(L(lang, f"El archivo de contenido tiene {len(last['problems'])} problema(s); la app sigue con el último contenido válido:",
                   f"The content file has {len(last['problems'])} problem(s); the app keeps the last valid content:"))
        st.code("\n".join(last["problems"][:40]), language=None, wrap_lines=True)
    elif last.get("status") == "locked":
        st.warning(L(lang, "El archivo de contenido está abierto en otro programa; ciérralo para que la app lo lea.",
                     "The content file is open in another program; close it so the app can read it."))
    elif last.get("status") == "none":
        if st.button(L(lang, "Crear el archivo de contenido", "Create the content file"), key="ak_ct_make"):
            content_sync.refresh()
            st.rerun()
    as_csv, as_xlsx = _content_files(_content_signature())
    c = st.columns(2)
    c[0].download_button(L(lang, "Descargar todo en un CSV", "Download everything as one CSV"), as_csv,
                         file_name="academia_contenido.csv", mime="text/csv", key="ak_ct_csv", width="stretch")
    c[1].download_button(L(lang, "Descargar como libro de Excel (una hoja por tabla)", "Download as an Excel workbook (one sheet per table)"),
                         as_xlsx, file_name="academia_contenido.xlsx",
                         mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="ak_ct_xlsx", width="stretch")
    up = st.file_uploader(L(lang, "Importar un archivo de contenido (CSV o Excel)", "Import a content file (CSV or Excel)"),
                          type=["csv", "xlsx"], key="ak_ct_file")
    if up is not None:
        result = content.read(up.getvalue())
        if result["summary"]:
            st.dataframe(pd.DataFrame(result["summary"]), hide_index=True, width="stretch")
        st.caption(L(lang, f"Familias: {result.get('families', 0)} · skills: {result.get('skills', 0)} · learning paths: {result.get('learning_paths', 0)}",
                     f"Families: {result.get('families', 0)} · skills: {result.get('skills', 0)} · learning paths: {result.get('learning_paths', 0)}"))
        if result["problems"]:
            st.error(L(lang, f"{len(result['problems'])} problema(s). Corrígelos en el archivo y vuelve a subirlo; no se guardó nada.",
                       f"{len(result['problems'])} problem(s). Fix them in the file and upload it again; nothing was saved."))
            st.code("\n".join(result["problems"][:60]), language=None, wrap_lines=True)
        elif st.button(L(lang, "Aplicar este contenido", "Apply this content"), type="primary", key="ak_ct_apply"):
            content.apply(result)
            content_sync.refresh()
            st.cache_data.clear()
            ui.fx("step")
            st.toast(L(lang, "Contenido actualizado (se guardó un respaldo del anterior).", "Content updated (a backup of the previous one was saved)."))
            st.rerun()
    st.divider()


def access_section(lang: str) -> None:
    """Owners manage who else is an owner, the optional PIN and the security group that will replace this list."""
    acc = load_access()
    with st.expander(L(lang, "Acceso: quién ve la vista de owner", "Access: who gets the owner view")):
        st.caption(L(lang, "Sin conexión esto separa vistas, no es un control de seguridad. En Microsoft 365 lo sustituye la pertenencia "
                           "al security group. Los champions no van en esta lista: ven solo a quienes cursan su familia.",
                     "Offline this separates views; it is not a security control. In Microsoft 365 it is replaced by membership of the "
                     "security group. Champions are not listed here: they only see people taking their family."))
        owners = st.text_area(L(lang, "Owners y líderes (un nombre o correo por línea)", "Owners and leaders (one name or e-mail per line)"),
                              value="\n".join(acc.owners), key="ak_acc_owners", height=120)
        group = st.text_input(L(lang, "Security group de Entra ID (para la integración)", "Entra ID security group (for the integration)"),
                              value=acc.security_group, key="ak_acc_group", placeholder="SG-Academia-Cloud-Owners")
        pin = st.text_input(L(lang, "Nuevo PIN de owner (vacío = no cambiar)", "New owner PIN (empty = keep)"), type="password", key="ak_acc_pin")
        drop = st.checkbox(L(lang, "Quitar el PIN", "Remove the PIN"), key="ak_acc_nopin") if acc.has_pin() else False
        if st.button(L(lang, "Guardar acceso", "Save access"), key="ak_acc_save"):
            new = [o.strip() for o in owners.splitlines() if o.strip()]
            if not new:
                st.error(L(lang, "Debe quedar al menos un owner.", "At least one owner must remain."))
            else:
                acc.owners, acc.security_group = new, group.strip()
                if drop:
                    acc.set_pin("")
                elif pin:
                    acc.set_pin(pin)
                save_access(acc)
                st.toast(L(lang, "Acceso guardado.", "Access saved."))


def route_tab(catalog: Catalog | None, conn, learner: str, lang: str) -> None:
    """The learning route: per skill family, the vendor's own training (Microsoft Learn for Microsoft skills) as steps."""
    if not catalog:
        st.info(L(lang, "El catálogo de skills todavía no está cargado.", "The skills catalog is not loaded yet."))
        return
    routes = build_routes(catalog, load_materials())
    tr = RouteTracker(conn, learner)
    st.markdown(L(lang, "Tu ruta sigue la formación oficial del proveedor: **Microsoft Learn** para las skills de Microsoft y la ruta "
                        "de carrera del fabricante para las demás. Abre cada paso, complétalo en su sitio y márcalo aquí.",
                  "Your route follows the vendor's official training: **Microsoft Learn** for Microsoft skills and the vendor's own "
                  "career path for the rest. Open each step, complete it on its site and mark it here."))
    labels = {r.family_id: f"{r.family} ({len(r.steps)} {L(lang, 'pasos', 'steps')})" for r in routes}
    fid = st.selectbox(L(lang, "Familia de skills", "Skill family"), list(labels), key="rt_family", format_func=lambda k: labels[k])
    route = next(r for r in routes if r.family_id == fid)
    vendors, vendor = route.vendors(), "*"
    if len(vendors) > 1:  # family -> technology / vendor -> skill -> class 1, class 2…
        vendor = st.segmented_control(L(lang, "Tecnología / vendor", "Technology / vendor"), ["*"] + vendors, default="*", key=f"rt_vendor_{fid}",
                                      format_func=lambda v: L(lang, "Todas", "All") if v == "*" else v) or "*"
    shown = [x for x in route.steps if vendor == "*" or x.vendor == vendor]
    done = tr.done()
    got, total = tr.progress(route)
    c = st.columns(3)
    c[0].metric(L(lang, "Pasos completados", "Steps completed"), f"{got} / {total}", border=True)
    c[1].metric(L(lang, "Puntos de ruta", "Route points"), f"{tr.total_points():,}", border=True)
    nxt = tr.next_step(route)
    c[2].metric(L(lang, "Siguiente paso", "Next step"), nxt.skill if nxt else ("✅" if total else "—"), border=True)
    st.progress(got / total if total else 0.0)
    fb = st.session_state.pop("rt_fb", None)
    if fb is not None:
        st.toast(L(lang, "¡Paso completado!", "Step completed!") + (f" +{fb} pts" if fb else ""))
    if not route.steps:
        st.info(L(lang, "Esta familia todavía no tiene pasos de formación oficial. El champion puede agregarlos en «Mapa de skills → Editar a mano».",
                  "This family has no official training steps yet. The champion can add them in Skills map → Edit by hand."))
    kind_name = {"path": L(lang, "Ruta", "Path"), "module": L(lang, "Módulo", "Module"), "course": L(lang, "Curso", "Course"),
                 "lab": L(lang, "Laboratorio", "Lab"), "tutorial": "Tutorial"}
    last_skill = None
    for stp in shown:
        ok = stp.key in done
        if stp.skill_id != last_skill:  # one block per skill: its classes in order
            last_skill = stp.skill_id
            mine = [x for x in shown if x.skill_id == stp.skill_id]
            st.markdown(f"##### {stp.skill}")
            st.caption(" · ".join(x for x in (stp.vendor, stp.category, f"{sum(x.key in done for x in mine)} / {len(mine)} "
                                                + L(lang, "clases", "classes")) if x))
        with st.container(border=True):
            st.markdown(f"{'✅' if ok else '🟠' if nxt and stp.key == nxt.key else '○'} **{L(lang, 'Clase', 'Class')} {stp.number} · {stp.title}**")
            st.caption(f"{kind_name.get(stp.kind, stp.kind)} · {stp.provider}")
            a, b = st.columns([1, 2])
            a.link_button(L(lang, f"Abrir en {stp.provider} ↗", f"Open on {stp.provider} ↗"), stp.url, width="stretch")
            if ok:
                b.caption(L(lang, "Completado", "Completed") + (f" · [{L(lang, 'evidencia', 'evidence')}]({done[stp.key]})" if done[stp.key].startswith("https://") else ""))
            else:
                ev = b.text_input(L(lang, "Enlace de tu logro (opcional)", "Link to your achievement (optional)"), key=f"rt_ev_{stp.key}",
                                  label_visibility="collapsed", placeholder=L(lang, "Enlace de tu logro o insignia (opcional)", "Link to your achievement or badge (optional)"))
                if b.button(L(lang, f"Marcar como completado (+{ITEM_POINTS} pts)", f"Mark as completed (+{ITEM_POINTS} pts)"), key=f"rt_done_{stp.key}"):
                    st.session_state["rt_fb"] = tr.complete(stp, ev)
                    ui.fx("step")
                    st.rerun()
    if nxt:
        target = next((s.target for s in catalog.skills if s.id == nxt.skill_id), "")
        assistant_box(ai.prompt_step_coach(route.family, nxt.skill, nxt.title, nxt.provider, target, lang=lang), lang, f"coach_{nxt.key}",
                      L(lang, "Prepárate para tu siguiente paso con el tutor de IA", "Get ready for your next step with the AI tutor"))
    if route.uncovered:
        st.caption(L(lang, "Skills de esta familia sin formación oficial todavía: ", "Skills of this family without official training yet: ")
                   + ", ".join(route.uncovered) + ".")
    if route.extras:
        with st.expander(L(lang, "Material de consulta (no cuenta como paso)", "Reference material (does not count as a step)")):
            for skill, items in route.extras.items():
                st.markdown(f"**{skill}**")
                material_links(items)


def assistant_section(lang: str) -> None:
    """Owners connect the company's AI assistant: where people open it and, when available, its endpoint for integrations."""
    cfg = ai.load_assistant()
    with st.expander(L(lang, f"Asistente de IA ({cfg.name})", f"AI assistant ({cfg.name})")):
        st.caption(L(lang, "Sin endpoint, la academia prepara el mensaje y la persona lo pega en el asistente. Con endpoint y llave, "
                           "responde aquí mismo. La llave nunca se guarda en archivos: se lee de una variable de entorno.",
                     "Without an endpoint, the academy prepares the message and the person pastes it into the assistant. With an endpoint "
                     "and key, it answers right here. The key is never stored in files: it is read from an environment variable."))
        st.markdown(L(lang, "Modo actual: ", "Current mode: ") + (f"**API**" if cfg.mode == "api" else L(lang, "**copiar y abrir**", "**copy and open**")))
        on = st.checkbox(L(lang, "Mostrar el asistente a las personas", "Show the assistant to people"), value=cfg.enabled, key="ak_ai_on")
        name = st.text_input(L(lang, "Nombre", "Name"), value=cfg.name, key="ak_ai_name")
        url = st.text_input(L(lang, "Página del asistente (para abrirlo)", "Assistant page (to open it)"), value=cfg.url, key="ak_ai_url",
                            placeholder="https://…")
        api = st.text_input(L(lang, "Endpoint para integraciones (opcional)", "Endpoint for integrations (optional)"), value=cfg.api_url,
                            key="ak_ai_api", placeholder="https://…/chat/completions")
        model = st.text_input(L(lang, "Modelo o despliegue (opcional)", "Model or deployment (optional)"), value=cfg.model, key="ak_ai_model")
        env = st.text_input(L(lang, "Variable de entorno con la llave", "Environment variable holding the key"), value=cfg.key_env, key="ak_ai_env")
        hdr = st.selectbox(L(lang, "Cabecera de autenticación", "Auth header"), ["Authorization", "api-key"],
                           index=0 if cfg.auth_header == "Authorization" else 1, key="ak_ai_hdr")
        if st.button(L(lang, "Guardar asistente", "Save assistant"), key="ak_ai_save"):
            bad = [u for u in (url.strip(), api.strip()) if u and not u.startswith("https://")]
            if bad or not name.strip():
                st.error(L(lang, "El nombre es obligatorio y las direcciones deben empezar con https://", "A name is required and addresses must start with https://"))
            else:
                ai.save_assistant(ai.AssistantConfig(name.strip(), on, url.strip(), api.strip(), model.strip(), env.strip() or "AMETHYST_API_KEY", hdr))
                st.toast(L(lang, "Asistente guardado.", "Assistant saved."))


def skills_tab(catalog: Catalog | None, packs: list[Pack], lang: str, owner: bool = True, families: set[str] | None = None) -> None:
    """Skill families by gap, their champion and lesson coverage, plus (owners only) the three ways to load the catalog."""
    st.markdown(T("skills_intro", lang))
    if not owner:
        if catalog:
            _skills_map(catalog, packs, lang, owner=False, families=families)
        else:
            st.info(L(lang, "El catálogo de skills todavía no está cargado.", "The skills catalog is not loaded yet."))
        return
    if st.session_state.pop("ak_sk_saved", False):
        st.toast(T("sk_saved", lang))
    modes = {"view": "sk_mode_view", "import": "sk_mode_import", "paste": "sk_mode_paste", "edit": "sk_mode_edit"}
    if st.session_state.get("ak_sk_mode") not in modes:
        st.session_state["ak_sk_mode"] = "view"
    mode = st.segmented_control("skills_mode", list(modes), key="ak_sk_mode", format_func=lambda m: T(modes[m], lang),
                                label_visibility="collapsed") or "view"
    if mode == "import":
        _skills_import(catalog, packs, lang)
    elif mode == "paste":
        _skills_paste(catalog, packs, lang)
    elif mode == "edit":
        _skills_edit(catalog, packs, lang)
    elif catalog:
        _skills_map(catalog, packs, lang)
    else:
        st.info(T("sk_empty", lang))


# ---------------------------------------------------------------------------------------------- page
def render(pack: Pack, conn, learner: str, lang: str = "es", role: str | None = None, catalog: Catalog | None = None,
           packs: list[Pack] | None = None, exams: list | None = None, owner: bool = False, families: set[str] | None = None,
           email: str = "") -> None:
    """``owner``: the owner view (whole team's measurements, notices, gap numbers, catalog administration).
    ``families``: for a champion who is not an owner, the skill families they lead; they see only those people and numbers."""
    families = set() if owner else (families or set())
    packs, exams = packs or [pack], exams or []
    tr = Tracker(conn, pack, learner)
    ui.inject_css()
    st.title(pack.title)
    if pack.subtitle:
        st.caption(pack.subtitle)
    ui.hero(pack, tr, lang, role)  # what to study next + overall progress; ranks and medals live in the Progress tab
    my_notices(conn, packs, exams, catalog, learner, lang)
    if catalog:  # experts, champions and owners: questions of their families still waiting in the forum
        forum = Forum(conn)
        mine = ({f.id for f in catalog.families} if owner else set(families)) | forum.sme_families(learner.strip() or "yo", email)
        pending = len(forum.waiting(mine)) if mine else 0
        if pending:
            st.warning(L(lang, f"**Foro:** {pending} pregunta(s) de tus familias de skills esperan respuesta de un experto. Ábrelas en la pestaña «Foro».",
                         f"**Forum:** {pending} question(s) in your skill families are waiting for an expert's answer. Open them in the Forum tab."))
    sections = [("tab_route", lambda: route_tab(catalog, conn, learner, lang)), ("tab_course", lambda: course(pack, tr, lang, role)), ("tab_glossary", lambda: glossary(pack, tr, lang)),
                ("tab_library", lambda: library(pack, lang)), ("tab_progress", lambda: progress_tab(pack, tr, lang, role)),
                ("tab_skills", lambda: skills_tab(catalog, packs, lang, owner, families)),
                ("tab_certs", lambda: certifications_tab(exams, conn, learner, lang, catalog, leader=owner or bool(families))),
                ("tab_forum", lambda: forum_tab(conn, catalog, learner, email, lang, owner, families))]
    if owner or families:  # reports are for owners (every family) and champions (their own)
        sections.append(("tab_reports", lambda: reports_tab(conn, packs, exams, catalog, lang, learner.strip() or "yo", None if owner else families)))
        sections.append(("tab_demand", lambda: demand_tab(catalog, packs, lang)))  # what the market asks for, against the practice and the courses
    if owner:  # team measurements are for owners and leaders only

        def team_view() -> None:
            team_tab(conn, pack, lang)
            notices_section(conn, packs, exams, catalog, lang)
            content_section(lang)
            access_section(lang)
            assistant_section(lang)

        sections.append(("tab_team", team_view))
    elif families and catalog:  # a champion: only the people and notices of their own families

        def family_view() -> None:
            people = champion_team(conn, packs, exams, catalog, families, lang)
            notices_section(conn, packs, exams, catalog, lang, only=people)

        sections.append(("tab_team", family_view))
    labels = [f"{n} · {T(key, lang)}" for n, (key, _) in enumerate(sections, start=1)]
    goto = st.session_state.pop("ak_goto", None)  # set by the «start lesson» button: open that tab
    target = next((lb for lb, (key, _) in zip(labels, sections) if key == goto), None)
    try:
        if target:
            st.session_state["ak_tabs"] = target
        tabs = st.tabs(labels, key="ak_tabs", on_change="rerun")
    except Exception:  # older Streamlit: tabs cannot be opened from code, the learner clicks «Curso»
        st.session_state.pop("ak_tabs", None)
        tabs = st.tabs(labels)
    for tab, (_, draw) in zip(tabs, sections):
        with tab:
            draw()
    if pack.disclaimer:
        st.caption(pack.disclaimer)
    st.caption(f"{pack.title} · v{pack.version} · {VBD_POINTS} pts/VBD")
    ui.legal_footer(lang)
    ui.play_fx(sound=st.session_state.get("ak_sound", True))  # the sound / celebration of what just happened
