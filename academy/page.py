"""The Academy page: course (lesson + quiz + compact video panel), glossary quiz, video library, progress, team."""

from __future__ import annotations

import os
import random
from datetime import date

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from academy import content_sync, editor, notify, quiz, report, report_pdf, track, ui
from academy import content_xlsx as content
from academy.access import load_access, save_access
from academy.catalog import (DEFAULT_SHEET, Catalog, vendor_of, load_materials, parse_grid, parse_text, read_xlsx,
                             save_catalog, sheet_names, validate_catalog)
from academy import assistant as ai
from academy.exam_page import assistant_box, exams_tab, material_links
from academy.certs import Certs
from academy.certs_page import certs_admin, my_certs
from academy.demand_page import demand_tab
from academy.forum import Forum
from academy.forum_page import forum_tab
from academy import inventory_page, news_page, rhythm_page
from academy.i18n import T
from academy.pack import Pack, Resource
from academy.route import ITEM_POINTS, RouteTracker, build_routes, is_learn
from academy.progress import Tracker, team
from academy.videos import DEFAULT_SIZE, SIZES, embed_src



# ---------------------------------------------------------------------------------------------- small pieces
def _label(r: Resource) -> str:
    icon = {"video": "▶", "playlist": "☰", "link": "↗"}.get(r.kind, "▶")
    return f"{icon} {r.title} — {r.channel}"


def _size_picker(lang: str, key: str) -> None:
    names = {"XS": "Mini", "S": "Small", "M": "Medium",
             "L": "Large"}
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
    level = r.level
    who = f" · {r.who}" if r.who else ""
    st.markdown(f"**{r.title}**")
    st.caption(f"{r.channel}{who} · {level}")
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
    c[3].metric("Questions answered right",
                f"{len(tr.correct_items())} / {sum(len(x.quiz) for x in pack.lessons)}", border=True)


def lesson_panel(pack: Pack, lesson_id: str, lang: str) -> None:
    items = pack.for_lesson(lesson_id)
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


def course(pack: Pack, tr: Tracker, lang: str, role: str | None) -> None:
    done = tr.completed_lessons()
    scope = {x.id for x in pack.lessons_in_scope(role)}
    narrowed = len(scope) < len(pack.lessons)
    if narrowed:  # a role is chosen in the sidebar: its lessons only, unless the learner asks for every lesson
        c = st.columns([3, 2])
        c[0].caption(f"Showing the **{len(scope)}** lessons of the **{role}** role. Your champion sets your role.")
        if c[1].toggle("Show every lesson", key="ak_all_lessons"):
            scope = {x.id for x in pack.lessons}
    by_level = {lv: [x for x in items if x.id in scope] for lv, items in pack.by_level().items()}
    levels = [lv for lv in pack.levels if by_level.get(lv)] or list(pack.levels)
    if st.session_state.get("ak_level") not in levels:
        st.session_state.pop("ak_level", None)
    level = st.radio(T("level", lang), levels, horizontal=True, key="ak_level",
                     format_func=lambda lv: f"{lv} ({sum(1 for x in by_level.get(lv, []) if x.id in done)}/{len(by_level.get(lv, []))})")
    items = by_level.get(level, [])
    if not items:
        return
    ids = [x.id for x in items]
    if st.session_state.get(f"ak_lesson_{level}") not in ids:
        st.session_state.pop(f"ak_lesson_{level}", None)
    lid = st.selectbox(T("lesson", lang), ids, key=f"ak_lesson_{level}",
                       format_func=lambda i: ("✅ " if i in done else "○ ") + next(x.title for x in items if x.id == i))
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
    topics = [k for k in pack.topics if pack.by_topic(k)]
    if not topics:
        return
    c = st.columns([2, 1])
    topic = c[0].selectbox(T("topic", lang), topics, key="ak_lib_topic", format_func=lambda k: f"{pack.topics[k]} ({len(pack.by_topic(k))})")
    items = pack.by_topic(topic)
    left, right = st.columns([1, 1], gap="large")
    with left:
        idx = st.radio(T("resources", lang), list(range(len(items))), key=f"ak_lib_pick_{topic}", format_func=lambda i: _label(items[i]))
    r = items[idx]
    with right:
        _size_picker(lang, "ak_lib_size")
        play(r, lang, key=f"ak_lib_{topic}_{idx}", size_key="ak_lib_size")
        details(r, r.why, lang)
        used = [les.id for les in pack.lessons if r.key in les.resources]
        if used:
            st.caption(T("used_in", lang) + ", ".join(used))
    st.caption(T("third_party", lang))
    st.divider()
    from academy.study_page import study_bank

    study_bank(None, False, key="lib_sm", player=True)  # the practice's study material (John Savill and more), to watch here


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
        done, rec = tr.completed_lessons(), pack.lessons_for_role(role)
        st.dataframe(pd.DataFrame([{"ID": les.id, T("level", lang): les.level, T("lesson", lang): les.title,
                                    "✅": "✅" if les.id in done else ""}
                                   for les in pack.lessons if les.id in rec]), hide_index=True, width="stretch")
    ev = tr.events()
    ev = ev[ev["kind"] != "vbd"] if len(ev) else ev  # value deliverables were retired; older rows stay out of view
    if len(ev):
        st.markdown(T("recent", lang))
        st.dataframe(ev.sort_values("id", ascending=False).head(30)[["time", "kind", "item", "points", "correct"]],
                     hide_index=True, width="stretch")


def team_tab(conn, pack: Pack, lang: str) -> None:
    st.markdown(T("team_intro", lang))
    df = team(conn, pack)
    if df.empty:
        st.info(T("no_team", lang))
        return
    st.dataframe(df, hide_index=True, width="stretch")
    st.download_button(T("download", lang), df.to_csv(index=False).encode("utf-8-sig"), file_name=f"progress_{pack.id}.csv",
                       mime="text/csv")


def champion_team(conn, packs: list[Pack], exams: list, catalog, families: set[str], lang: str) -> set[str]:
    """What a champion sees: only the people working on their families, counted on those families' lessons and exams."""
    names = [f.name for f in catalog.families if f.id in families]
    st.markdown("#### My family: " + ", ".join(names))
    st.caption("You only see people taking lessons or certifications of your role family.")
    st.caption("Run your family's career path (classes on / off, your own decks, the family's CSV) in **Learning route → 🧭 Manage the career path**.")
    rows = notify.family_team(conn, packs, exams, catalog, families)
    if not rows:
        st.info("Nobody has started your family's content yet.")
        return set()
    df = pd.DataFrame(rows)
    st.dataframe(df, hide_index=True, width="stretch")
    st.download_button(T("download", lang), df.to_csv(index=False).encode("utf-8-sig"),
                       file_name="my_family_progress.csv", mime="text/csv",
                       key="ak_fam_csv")
    return {r["Person"] for r in rows}


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
    return st.column_config.NumberColumn("Class", min_value=1, step=1,
                                         help="Order in the skill's path: class 1, class 2…")


def _material_item(r: dict) -> dict:
    item = {k: ("" if pd.isna(r.get(k)) else str(r[k]).strip()) for k in ("title", "url", "provider", "kind", "verified")}
    if pd.notna(r.get("order")):
        item["order"] = int(r["order"])
    return item


def reports_tab(conn, packs: list[Pack], exams: list, catalog, lang: str, who: str, only: set[str] | None = None) -> None:
    """The reports of the academy: every family for an owner, only their own (``only``) for a champion.

    Families (status), people (who is keeping up with the career path and who is not), certifications (held, desired,
    about to expire) and the administration of the certification register."""
    if not catalog:
        st.info("Reports are organized by role family: load the catalog in the Skills map first.")
        return
    rep = report.build(conn, packs, exams, catalog, lang, only)
    people_names = report.roster(conn)
    rep["certs"] = Certs(conn).report(catalog, lang, only, people_names)
    t, s, cs = report.titles(lang), rep["summary"], rep["certs"]["summary"]
    st.caption(f"{t['generated']}: {rep['generated']} · {t['rules']}")
    c = st.columns(6)
    for col, (label, value) in zip(c, ((t["families"], s["families"]), (t["on_track"], s["on_track"]), (t["active_people"], s["people"]),
                                        (t["behind"], s["behind"]), (t["not_started"], s["not_started"]),
                                        ("Current certifications", cs["current"]))):
        col.metric(label, value, border=True)
    stamp = rep["generated"][:10]
    a, b = st.columns(2)
    a.download_button("Download the whole report as Excel", report.to_xlsx(rep),
                      file_name=f"academy_report_{stamp}.xlsx",
                      mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="ak_rep_xlsx", width="stretch")
    if report_pdf.available():
        b.download_button("Download the report as PDF", report_pdf.to_pdf(rep),
                          file_name=f"academy_report_{stamp}.pdf", mime="application/pdf",
                          key="ak_rep_pdf", width="stretch", type="primary")
    else:
        b.button("Download the report as PDF", disabled=True, key="ak_rep_pdf_off", width="stretch",
                 help="The PDF component is missing: close the app, double-click «Install components.bat» and open it again.")
    tabs = st.tabs(["Role families", "People and career path",
                    "Certifications", "Manage certifications", "Skills matrix"])
    with tabs[0]:
        st.markdown(f"#### {t['report']}")
        st.dataframe(pd.DataFrame(report.visible(rep["status"])), hide_index=True, width="stretch")
    with tabs[1]:
        st.markdown(f"#### {t['people']}")
        st.caption("One row per person, whoever is not keeping up first. The status is the worst across their families.")
        if rep["people"]:
            st.dataframe(pd.DataFrame(report.visible(rep["people"])), hide_index=True, width="stretch")
        else:
            st.info(t["empty"])
        st.markdown(f"#### {t['paths']}")
        names = dict(report.PATH)
        fam_names = sorted({r[next(iter(r))] for r in rep["paths"]})
        f1, f2 = st.columns([2, 3])
        fam = f1.selectbox("Role family", [""] + fam_names, key="ak_rep_fam",
                           format_func=lambda k: k or "All")
        states = f2.multiselect("Status on the path", report.PATH_ORDER, format_func=lambda k: names[k],
                                default=[report.BEHIND, report.AT_RISK, report.GOING, report.DONE], key="ak_rep_states")
        rows = [r for r in rep["paths"] if (not fam or r[next(iter(r))] == fam) and r["_path"] in states]
        if rows:
            st.dataframe(pd.DataFrame(report.visible(rows)), hide_index=True, width="stretch")
        else:
            st.info("Nobody matches that filter.")
        st.markdown(f"#### {t['followup']}")
        late = [r for r in rep["followup"] if r["_late"]]
        if late:
            st.dataframe(pd.DataFrame(report.visible(late)), hide_index=True, width="stretch")
        else:
            st.success("Nobody needs follow-up today.")
    with tabs[2]:
        m = st.columns(4)
        m[0].metric("People with a certification", f"{cs['people_with']} / {cs['people']}", border=True)
        m[1].metric("Current certifications", cs["current"], border=True)
        m[2].metric("Desired certifications", cs["desired"], border=True)
        m[3].metric("Expire within 90 days or already did", cs["expiring"], border=True)
        st.markdown(f"#### {t['certs_fam']}")
        if rep["certs"]["families"]:
            st.dataframe(pd.DataFrame(rep["certs"]["families"]), hide_index=True, width="stretch")
        else:
            st.info("No family has certifications defined yet: add them under Manage certifications.")
        st.markdown(f"#### {t['certs_people']}")
        if rep["certs"]["people"]:
            st.dataframe(pd.DataFrame(rep["certs"]["people"]), hide_index=True, width="stretch")
        if rep["certs"]["expiring"]:
            st.markdown(f"#### {t['certs_exp']}")
            st.dataframe(pd.DataFrame(rep["certs"]["expiring"]), hide_index=True, width="stretch")
    with tabs[3]:
        if st.session_state.get("ed_on_tab_certs") and only is None:  # the same editor is open in the Certifications tab
            st.info("Certification management is open in the Certifications tab (✏️ Edit mode).")
        else:
            certs_admin(conn, catalog, lang, {f.id for f in catalog.families} if only is None else set(only), who, people_names)
    with tabs[4]:
        inventory_page.skills_matrix(conn, catalog, who, owner=only is None,
                                     people=None if only is None else {r[next(iter(r))] for r in rep["people"]})


def certifications_tab(exams: list, conn, learner: str, lang: str, catalog, leader: bool) -> None:
    """My certifications (what I hold and what I aim for) and the preparation for an exam."""
    views = {"mine": "My certifications", "skills": "My skills", "prep": "Prepare for an exam"}
    view = st.segmented_control("certs_view", list(views), default="mine", format_func=lambda k: views[k], key="ak_cert_view",
                                label_visibility="collapsed") or "mine"
    if view == "mine":
        my_certs(conn, catalog, learner, lang)
    elif view == "skills":
        inventory_page.my_skills(conn, catalog, learner)
    else:
        exams_tab(exams, conn, learner, lang, catalog, leader=leader)


def notices_section(conn, packs: list[Pack], exams: list, catalog, lang: str, only: set[str] | None = None) -> None:
    """Notices ready to send (with copy to the family champion). Offline they open in Outlook; in M365 a flow sends them."""
    st.markdown("#### Notices to send")
    st.caption((f"Rules: course finished · mock passed · {notify.INACTIVE_DAYS} days inactive · {notify.STALLED_DAYS} days without progress. "
                 "Each notice is copied to the role family champion."))
    todo = [n for n in notify.pending(conn, packs, exams, catalog, lang=lang) if only is None or n.learner in only]
    if not todo:
        st.info("No pending notices.")
        return
    st.download_button(f"Download the queue ({len(todo)}) as CSV",
                       pd.DataFrame(notify.queue_rows(todo)).to_csv(index=False).encode("utf-8-sig"), file_name="pending_notices.csv",
                       mime="text/csv", key="ak_nt_csv")
    icon = {"course_done": "🎉", "exam_passed": "🏅", "inactive": "⏰", "stalled": "🐢"}
    for i, n in enumerate(todo):
        with st.expander(f"{icon.get(n.kind, '✉️')} {n.learner} — {n.subject}"):
            st.markdown("**To:** " + (n.to or "_no e-mail on file_") + "  \n"
                        + "**CC:** " + (", ".join(n.cc) or (", ".join(n.champions) + " _(e-mail missing)_" if n.champions
                                                            else "_family without champion_")))
            st.text(n.body)
            c1, c2 = st.columns(2)
            c1.link_button("✉️ Open in Outlook", notify.mailto(n), width="stretch")
            if c2.button("Mark as sent", key=f"ak_nt_sent_{i}_{n.kind}_{n.ref}", width="stretch"):
                notify.mark_sent(conn, n)
                st.rerun()


def my_notices(conn, packs: list[Pack], exams: list, catalog, learner: str, lang: str) -> None:
    """What the learner sees at the top: the same messages that would reach their inbox."""
    for n in notify.pending(conn, packs, exams, catalog, learner=learner.strip() or "me", include_sent=True, lang=lang):
        first = n.body.split("\n\n")[1] if n.body.count("\n\n") >= 2 else n.subject
        (st.success if n.kind in ("course_done", "exam_passed") else st.warning)(f"**{n.subject}.** {first}")


def _skills_map(catalog: Catalog, packs: list[Pack], lang: str, owner: bool = True, families: set[str] | None = None) -> None:
    """``families``: for a champion, the families whose gap numbers they may see."""
    cov = catalog.coverage(packs)
    mats = load_materials()
    st.markdown(T("sk_total", lang, c=sum(1 for v in cov.values() if v), n=len(cov)) + " "
                + f"**{sum(1 for s in catalog.skills if mats.get(s.id))}** have support material.")
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
                row = {"Technology / vendor": vendor_of(s, mats)}
                if any(x.category for x in skills):
                    row["Category"] = s.category
                row[T("sk_col_skill", lang)] = s.name + ("" if s.confirmed else f" · {T('sk_unconfirmed', lang)}")
                if any(x.severity for x in skills):
                    row[T("sk_col_sev", lang)] = s.severity
                if any(x.target for x in skills):
                    row[T("sk_col_target", lang)] = s.target
                if numbers and any(x.impacted_roles is not None for x in skills):
                    row[T("sk_col_impact", lang)] = s.impacted_roles
                row[T("sk_col_lessons", lang)] = " · ".join(t for _, t in cov[s.id]) or T("sk_none", lang)
                row["Material"] = len(mats.get(s.id, []))
                rows.append(row)
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
            with_mat = [s for s in skills if mats.get(s.id)]
            if with_mat:
                with st.expander(f"Support material ({sum(len(mats[s.id]) for s in with_mat)})"):
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
        st.error(rep["error"])
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
        st.error(e)
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
    _preview(read_xlsx(up, sheet), catalog, packs, lang, keep, f"Excel: sheet \"{sheet}\"", "xlsx")


def _skills_paste(catalog: Catalog | None, packs: list[Pack], lang: str) -> None:
    text = st.text_area(T("sk_paste", lang), height=220, key="ak_sk_text", help=T("sk_paste_help", lang))
    st.caption(T("sk_paste_help", lang))
    if text.strip():
        _preview(parse_text(text), catalog, packs, lang, False, "Tabla pegada", "paste")


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
    st.markdown("#### Practice content")
    path = content_sync.content_path()
    st.markdown((f"All the content lives in **one Excel workbook**: `{path}`, with **one tab per section** (the tab color shows the section; "
                  "the LEEME tab has the index). Edit, save, close Excel and reopen the app: it is checked in full and applied only if it is "
                  "right. With errors nothing changes."))
    last = st.session_state.get("ak_content_sync") or {}
    if last.get("status") == "problems":
        st.error(f"The content file has {len(last['problems'])} problem(s); the app keeps the last valid content:")
        st.code("\n".join(last["problems"][:40]), language=None, wrap_lines=True)
    elif last.get("status") == "locked":
        st.warning("The content file is open in another program; close it so the app can read it.")
    elif last.get("status") == "none":
        if st.button("Create the content file", key="ak_ct_make"):
            content_sync.refresh()
            st.rerun()
    _, as_xlsx = _content_files(_content_signature())
    st.download_button("Download the content (Excel, one tab per section)",
                       as_xlsx, file_name="academy_content.xlsx", type="primary",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="ak_ct_xlsx")
    up = st.file_uploader("Import a content file (Excel; the former CSV is accepted too)",
                          type=["csv", "xlsx"], key="ak_ct_file")
    if up is not None:
        result = content.read(up.getvalue())
        if result["summary"]:
            st.dataframe(pd.DataFrame(result["summary"]), hide_index=True, width="stretch")
        st.caption(f"Families: {result.get('families', 0)} · skills: {result.get('skills', 0)} · learning paths: {result.get('learning_paths', 0)}"
                   + (f" · people: {len(result['people'])}" if result.get("people") is not None else ""))
        for note in result.get("notes", []):
            st.info(note)
        if result["problems"]:
            st.error(f"{len(result['problems'])} problem(s). Fix them in the file and upload it again; nothing was saved.")
            st.code("\n".join(result["problems"][:60]), language=None, wrap_lines=True)
        elif st.button("Apply this content", type="primary", key="ak_ct_apply"):
            content.apply(result)
            content_sync.refresh()
            st.cache_data.clear()
            ui.fx("step")
            st.toast("Content updated (a backup of the previous one was saved).")
            st.rerun()
    st.divider()


def _owners_editor(directory, acc, scope: str, title: str, help_text: str, key: str, me: str, email: str) -> None:
    """One list of owners: the global ones (``scope`` empty) or a practice's."""
    from academy import content_sync
    from academy import people as directory_mod

    cap = directory_mod.max_owners()
    current = [(p.name, p.email) for p in directory_mod.owners(directory, scope)]
    if not scope:
        for o in acc.owners:  # owners of the earlier list (config/access.json) move into People when this is saved
            if not any(o.strip().lower() in (n.lower(), e.lower()) for n, e in current):
                current.append((o.split("@")[0].replace(".", " ").title() if "@" in o else o, o if "@" in o else ""))
    with st.expander(f"👑 {title} ({len(current)} of {cap})"):
        st.caption(help_text)
        if not scope and os.environ.get("ACADEMY_OWNERS", "").strip():
            st.info("The global owners are set in Azure (app setting ACADEMY_OWNERS) and applied on every restart: change them there.")
        with st.form(f"{key}_form", border=False, enter_to_submit=False):
            df = st.data_editor(pd.DataFrame(current, columns=["Person", "Email"]), num_rows="dynamic", hide_index=True, width="stretch",
                                key=f"{key}_ed", column_config={"Person": st.column_config.TextColumn("Person", required=True),
                                                                "Email": st.column_config.TextColumn("Work e-mail", required=True)})
            submitted = st.form_submit_button("Save owners", key=f"{key}_save", type="primary")
        rows = [(str(r.Person or ""), str(r.Email or "")) for r in df.itertuples() if str(r.Person or "").strip() or str(r.Email or "").strip()]
        if submitted and len(rows) > cap:
            st.error(f"At most {cap} owners: remove {len(rows) - cap}.")
        elif submitted:
            mine = {me.strip().lower(), email.strip().lower()} - {"", "me"}
            new, problems = directory_mod.set_owners(directory, rows, scope)
            if not scope and not problems and mine and not any({n.lower(), e.lower()} & mine for n, e in rows):
                problems = ["Keep yourself in the list (another owner can remove you later), so the app is never left without you mid-change."]
            if problems:
                st.error("\n\n".join(problems))
            else:
                directory_mod.save(new)
                if not scope:
                    acc.owners = []  # one list of owners: People
                    save_access(acc)
                content_sync.refresh()
                st.cache_data.clear()
                st.toast("Owners saved.")
                st.rerun()


def access_section(lang: str, me: str = "", email: str = "", global_owner: bool = False) -> None:
    """Owners: the global owners (global owners only), the owners of this practice, the optional PIN and security group."""
    from academy import people as directory_mod
    from academy import workspace

    acc = load_access()
    directory = directory_mod.load()
    cap = directory_mod.max_owners()
    here = workspace.find(workspace.current())
    if global_owner:
        _owners_editor(directory, acc, "", "Global owners",
                       f"Global owners see and run every practice and add new ones. Up to {cap}, each with the work e-mail they sign in with.",
                       "ak_owners", me, email)
    if here is not None:
        _owners_editor(directory, acc, here.id, f"Owners of {here.name}",
                       f"They run this practice only: reports, demand, edit mode and its team. Up to {cap}; global owners are owners here too.",
                       f"ak_owners_{here.id}", me, email)
    with st.expander("Access: PIN and security group"), st.form("ak_acc_form", border=False, enter_to_submit=False):
        st.caption(("Offline the owner view is not a security control. On Azure, Microsoft Entra ID signs everyone in and the owners "
                     "above are matched by their work e-mail."))
        group = st.text_input("Entra ID security group (for the integration)",
                              value=acc.security_group, key="ak_acc_group", placeholder="SG-Academia-Cloud-Owners")
        pin = st.text_input("New owner PIN (empty = keep)", type="password", key="ak_acc_pin")
        drop = st.checkbox("Remove the PIN", key="ak_acc_nopin") if acc.has_pin() else False
        if st.form_submit_button("Save access", key="ak_acc_save"):
            acc.security_group = group.strip()
            if drop:
                acc.set_pin("")
            elif pin:
                acc.set_pin(pin)
            save_access(acc)
            st.toast("Access saved.")


def roster_section(packs: list) -> None:
    """Owners and champions: the practice's people and the course role each one learns (in the app or from a roster file)."""
    from academy import content_sync, workspace
    from academy import people as pm

    pid, first = workspace.current(), workspace.default_id()
    roles = sorted({r for p in packs for r in p.roles})
    directory = pm.load()
    members = pm.members(directory, pid, first)
    with st.expander(f"🧑‍🤝‍🧑 Roster and course roles ({len(members)} people)"):
        st.caption("The course role decides which lessons each person sees on the dashboard and in the Course tab. Set it here, add "
                   "people at the bottom, or upload a roster file. Nobody is removed from here (use ✏️ Edit mode → People).")
        if not roles:
            st.info("The courses of this practice have no course roles yet: add them in ✏️ Edit mode, Progress tab → Course roles.")
        with st.form(f"ak_roster_form_{len(members)}", border=False, enter_to_submit=False):
            df = pd.DataFrame([{"Person": m.name, "Email": m.email, "Course role": m.course_role or None} for m in members],
                              columns=["Person", "Email", "Course role"]).astype("string")
            ed = st.data_editor(df, num_rows="dynamic", hide_index=True, width="stretch", key=f"ak_roster_ed_{len(members)}", column_config={
                "Person": st.column_config.TextColumn("Person", required=True),
                "Email": st.column_config.TextColumn("Work e-mail"),
                "Course role": st.column_config.SelectboxColumn("Course role", options=roles, help="Empty = every lesson")})
            save = st.form_submit_button("Save the roster", type="primary", key="ak_roster_save")
        rows = [{"Person": "" if pd.isna(r["Person"]) else str(r["Person"]), "Email": "" if pd.isna(r["Email"]) else str(r["Email"]),
                 "CourseRole": "" if pd.isna(r["Course role"]) else str(r["Course role"])} for r in ed.to_dict("records")]
        a, b = st.columns(2)
        a.download_button("Download the roster (CSV)", pm.roster_csv(members), file_name="roster.csv", mime="text/csv",
                          key="ak_roster_csv", width="stretch")
        with b.popover("Upload a roster (CSV)", width="stretch"):
            st.caption("Columns: Person, Email, CourseRole. People already in the app are matched by e-mail (or name) and get their "
                       "course role; new ones are added as learners of this practice.")
            up = st.file_uploader("Roster", type=["csv"], key="ak_roster_up", label_visibility="collapsed")
            if up is not None:
                rows, save = pm.parse_roster(up.getvalue()), st.button(f"Apply the roster ({len(pm.parse_roster(up.getvalue()))} rows)",
                                                                       key="ak_roster_apply", type="primary")
        if save:
            new, problems, added = pm.apply_roster(directory, rows, pid, first, set(roles))
            if problems:
                st.error("Nothing was saved:\n\n" + "\n\n".join(problems[:15]))
            else:
                pm.save(new)
                content_sync.refresh()
                st.cache_data.clear()
                st.toast(f"Roster saved{f': {added} new people' if added else ''}.")
                st.rerun()


def practices_section() -> None:
    """Global owners: the practices of the organization, and a new one with its own space (courses, people, content)."""
    from academy import workspace

    items = workspace.load()
    with st.expander(f"🏢 Practices ({len(items)})"):
        st.caption("Each practice is its own space: courses, role families and skills, learning paths, demand, study material, news "
                   "sources and content workbook. People belong to one practice (column Practice in People); global owners open any "
                   "of them from the sidebar.")
        with st.form("ak_practices_form", border=False, enter_to_submit=False):
            df = st.data_editor(pd.DataFrame([{"Id": x.id, "Name": x.name, "Description": x.description, "Active": x.active} for x in items]),
                                hide_index=True, width="stretch", key="ak_practices_ed", num_rows="fixed", disabled=["Id"],
                                column_config={"Active": st.column_config.CheckboxColumn("Active")})
            save_practices = st.form_submit_button("Save practices", key="ak_practices_save")
        if save_practices:
            try:
                workspace.update([workspace.Practice(str(r.Id), str(r.Name or "").strip() or str(r.Id), str(r.Description or "").strip(), bool(r.Active))
                                  for r in df.itertuples()])
            except ValueError as e:
                st.error(str(e))
            else:
                st.toast("Practices saved.")
                st.rerun()
        st.markdown("**Add a practice**")
        with st.form("ak_practice_new_form", border=False, enter_to_submit=False):
            c = st.columns([2, 3])
            name = c[0].text_input("Name", key="ak_practice_new_name", placeholder="PPM")
            desc = c[1].text_input("Description", key="ak_practice_new_desc", placeholder="Program and product management")
            create = st.form_submit_button("Create the practice", key="ak_practice_new", type="primary")
        if create and not name.strip():
            st.error("Write the practice's name.")
        elif create:
            try:
                new = workspace.create(name, desc)
            except ValueError as e:
                st.error(str(e))
            else:
                st.session_state["ak_practice_next"] = new.id  # opened on the next run
                st.cache_data.clear()
                st.rerun()


def route_tab(catalog: Catalog | None, conn, learner: str, lang: str, manage: set[str] | None = None) -> None:
    """The learning route: per role family, the vendor's own training (Microsoft Learn for Microsoft skills) as steps."""
    if not catalog:
        st.info("The skills catalog is not loaded yet.")
        return
    routes = build_routes(catalog, load_materials())
    tr = RouteTracker(conn, learner)
    st.markdown(("Your route follows the vendor's official training: **Microsoft Learn** for Microsoft skills and the vendor's own "
                  "career path for the rest. Open each step, complete it on its site and mark it here."))
    labels = {r.family_id: f"{r.family} ({len(r.steps)} {'steps'})" for r in routes}
    fid = st.selectbox("Role family", list(labels), key="rt_family", format_func=lambda k: labels[k])
    if fid in (manage or set()):  # the family's champion (or an owner) runs its path here
        from academy.family_page import manage_family

        manage_family(catalog, fid, learner.strip() or "me")
    route = next(r for r in routes if r.family_id == fid)
    vendors, vendor = route.vendors(), "*"
    if len(vendors) > 1:  # family -> technology / vendor -> skill -> class 1, class 2…
        vendor = st.segmented_control("Technology / vendor", ["*"] + vendors, default="*", key=f"rt_vendor_{fid}",
                                      format_func=lambda v: "All" if v == "*" else v) or "*"
    shown = [x for x in route.steps if vendor == "*" or x.vendor == vendor]
    done = tr.done()
    got, total = tr.progress(route)
    c = st.columns(3)
    c[0].metric("Steps completed", f"{got} / {total}", border=True)
    c[1].metric("Route points", f"{tr.total_points():,}", border=True)
    nxt = tr.next_step(route)
    c[2].metric("Next step", nxt.skill if nxt else ("✅" if total else "—"), border=True)
    st.progress(got / total if total else 0.0)
    fb = st.session_state.pop("rt_fb", None)
    if fb is not None:
        st.toast("Step completed!" + (f" +{fb} pts" if fb else ""))
    if not route.steps:
        st.info("This family has no official training steps yet. An owner can add them with ✏️ Edit mode at the top of this tab.")
    kind_name = {"path": "Path", "module": "Module", "course": "Course",
                 "lab": "Lab", "tutorial": "Tutorial"}
    last_skill = None
    for stp in shown:
        ok = stp.key in done
        if stp.skill_id != last_skill:  # one block per skill: its classes in order
            last_skill = stp.skill_id
            mine = [x for x in shown if x.skill_id == stp.skill_id]
            st.markdown(f"##### {stp.skill}")
            st.caption(" · ".join(x for x in (stp.vendor, stp.category, f"{sum(x.key in done for x in mine)} / {len(mine)} "
                                                + "classes") if x))
        with st.container(border=True):
            st.markdown(f"{'✅' if ok else '🟠' if nxt and stp.key == nxt.key else '○'} **{'Class'} {stp.number} · {stp.title}**")
            st.caption(f"{kind_name.get(stp.kind, stp.kind)} · {stp.provider}")
            a, b = st.columns([1, 2])
            from academy.family_page import download_step

            if not download_step(stp.url, stp.title, f"rt_dl_{stp.key}", a):
                a.link_button(f"Open on {stp.provider} ↗", stp.url, width="stretch")
            if ok:
                b.caption("Completed" + (f" · [{'evidence'}]({done[stp.key]})" if done[stp.key].startswith("https://") else ""))
            else:
                ev = b.text_input("Link to your achievement (optional)", key=f"rt_ev_{stp.key}",
                                  label_visibility="collapsed", placeholder="Link to your achievement or badge (optional)")
                if b.button(f"Mark as completed (+{ITEM_POINTS} pts)", key=f"rt_done_{stp.key}"):
                    st.session_state["rt_fb"] = tr.complete(stp, ev)
                    ui.fx("step")
                    st.rerun()
    if nxt:
        target = next((s.target for s in catalog.skills if s.id == nxt.skill_id), "")
        assistant_box(ai.prompt_step_coach(route.family, nxt.skill, nxt.title, nxt.provider, target, lang=lang), lang, f"coach_{nxt.key}",
                      "Get ready for your next step with the AI tutor")
    if route.uncovered:
        st.caption("Skills of this family without official training yet: "
                   + ", ".join(route.uncovered) + ".")
    if route.extras:
        with st.expander("Reference material (does not count as a step)"):
            for skill, items in route.extras.items():
                st.markdown(f"**{skill}**")
                material_links(items)


def assistant_section(lang: str) -> None:
    """Owners connect the company's AI assistant: where people open it and, when available, its endpoint for integrations."""
    cfg = ai.load_assistant()
    with st.expander(f"AI assistant ({cfg.name})"):
        st.caption(("Without an endpoint, the academy prepares the message and the person pastes it into the assistant. With an endpoint "
                     "and key, it answers right here. The key is never stored in files: it is read from an environment variable."))
        st.markdown("Current mode: " + (f"**API**" if cfg.mode == "api" else "**copy and open**"))
        with st.form("ak_ai_form", border=False, enter_to_submit=False):
            on = st.checkbox("Show the assistant to people", value=cfg.enabled, key="ak_ai_on")
            name = st.text_input("Name", value=cfg.name, key="ak_ai_name")
            url = st.text_input("Assistant page (to open it)", value=cfg.url, key="ak_ai_url",
                                placeholder="https://…")
            api = st.text_input("Endpoint for integrations (optional)", value=cfg.api_url,
                                key="ak_ai_api", placeholder="https://…/chat/completions")
            model = st.text_input("Model or deployment (optional)", value=cfg.model, key="ak_ai_model")
            env = st.text_input("Environment variable holding the key", value=cfg.key_env, key="ak_ai_env")
            hdr = st.selectbox("Auth header", ["Authorization", "api-key"],
                               index=0 if cfg.auth_header == "Authorization" else 1, key="ak_ai_hdr")
            saved = st.form_submit_button("Save assistant", key="ak_ai_save")
        if saved:
            bad = [u for u in (url.strip(), api.strip()) if u and not u.startswith("https://")]
            if bad or not name.strip():
                st.error("A name is required and addresses must start with https://")
            else:
                ai.save_assistant(ai.AssistantConfig(name.strip(), on, url.strip(), api.strip(), model.strip(), env.strip() or "AMETHYST_API_KEY", hdr))
                st.toast("Assistant saved.")


def skills_tab(catalog: Catalog | None, packs: list[Pack], lang: str, owner: bool = True, families: set[str] | None = None) -> None:
    """Role families by gap, their champion and lesson coverage, plus (owners only) the three ways to load the catalog."""
    st.markdown(T("skills_intro", lang))
    if not owner:
        if catalog:
            _skills_map(catalog, packs, lang, owner=False, families=families)
        else:
            st.info("The skills catalog is not loaded yet.")
        return
    if st.session_state.pop("ak_sk_saved", False):
        st.toast(T("sk_saved", lang))
    modes = {"view": "sk_mode_view", "import": "sk_mode_import", "paste": "sk_mode_paste"}
    if st.session_state.get("ak_sk_mode") not in modes:
        st.session_state["ak_sk_mode"] = "view"
    mode = st.segmented_control("skills_mode", list(modes), key="ak_sk_mode", format_func=lambda m: T(modes[m], lang),
                                label_visibility="collapsed") or "view"
    if mode == "import":
        _skills_import(catalog, packs, lang)
    elif mode == "paste":
        _skills_paste(catalog, packs, lang)
    elif catalog:
        _skills_map(catalog, packs, lang)
    else:
        st.info(T("sk_empty", lang))


# ---------------------------------------------------------------------------------------------- edit mode
def _team_editor(pack: Pack) -> None:
    """Every table of the content workbook, by section (the same groups and order as the Excel file)."""
    groups = {title: names for title, _, names, _ in content.SECTIONS}
    pick = st.segmented_control("Section of the content", list(groups), default=list(groups)[0], key="ed_team_group") or list(groups)[0]
    editor.edit_mode(f"team_{list(groups).index(pick)}", pack.id, groups[pick])


def _editable(key: str, draw, pack: Pack, conn, catalog, learner: str, lang: str):
    """The section with its «✏️ Edit mode» switch: on, the section shows its editor instead of the learner's view."""
    special = {"tab_certs": lambda: certs_admin(conn, catalog, lang, {f.id for f in catalog.families} if catalog else set(),
                                                learner.strip() or "me", report.roster(conn)),
               "tab_team": lambda: _team_editor(pack)}
    if key not in editor.SECTION_TABLES and key not in special:
        return draw  # the forum is run in place by owners and champions; nothing else to edit there

    def run() -> None:
        if editor.toggle(key):
            st.caption("Switch edit mode off to see the section as learners see it.")
            special[key]() if key in special else editor.edit_mode(key, pack.id)
            return
        draw()

    return run


# ---------------------------------------------------------------------------------------------- page
def render(pack: Pack, conn, learner: str, lang: str = "es", role: str | None = None, catalog: Catalog | None = None,
           packs: list[Pack] | None = None, exams: list | None = None, owner: bool = False, families: set[str] | None = None,
           email: str = "", global_owner: bool = False) -> None:
    """``owner``: the owner view (whole team's measurements, notices, gap numbers, catalog administration).
    ``families``: for a champion who is not an owner, the role families they lead; they see only those people and numbers."""
    families = set() if owner else (families or set())
    packs, exams = packs or [pack], exams or []
    tr = Tracker(conn, pack, learner)
    ui.inject_css()
    st.title(pack.title)
    if pack.subtitle:
        st.caption(pack.subtitle)
    editor.saved_notice()
    news_page.splash()  # the latest Microsoft security news, once per session, in a window that closes
    ui.hero(pack, tr, lang, role)  # what to study next + overall progress; ranks and medals live in the Progress tab
    my_notices(conn, packs, exams, catalog, learner, lang)
    if catalog:  # experts, champions and owners: questions of their families still waiting in the forum
        forum = Forum(conn)
        mine = ({f.id for f in catalog.families} if owner else set(families)) | forum.sme_families(learner.strip() or "me", email)
        pending = len(forum.waiting(mine)) if mine else 0
        if pending:
            st.warning(f"**Forum:** {pending} question(s) in your role families are waiting for an expert's answer. Open them in the Forum tab.")
    sections = [("tab_route", lambda: route_tab(catalog, conn, learner, lang, ({f.id for f in catalog.families} if owner else families) if catalog else set())), ("tab_course", lambda: course(pack, tr, lang, role)), ("tab_glossary", lambda: glossary(pack, tr, lang)),
                ("tab_library", lambda: library(pack, lang)), ("tab_progress", lambda: progress_tab(pack, tr, lang, role)),
                ("tab_skills", lambda: skills_tab(catalog, packs, lang, owner, families)),
                ("tab_certs", lambda: certifications_tab(exams, conn, learner, lang, catalog, leader=owner or bool(families))),
                ("tab_forum", lambda: forum_tab(conn, catalog, learner, email, lang, owner, families)),
                ("tab_rhythm", lambda: rhythm_page.rhythm_tab(conn, catalog, packs, exams, learner, owner, families)),
                ("tab_news", lambda: news_page.knowledge_tab(lang, catalog, leader=owner or bool(families)))]  # Knowledge exchange: the practice's reading bank
    if owner or families:  # reports are for owners (every family) and champions (their own)
        sections.append(("tab_reports", lambda: reports_tab(conn, packs, exams, catalog, lang, learner.strip() or "me", None if owner else families)))
        sections.append(("tab_demand", lambda: demand_tab(catalog, packs, lang, owner, conn)))  # what the market asks for, against the practice and the courses
    if owner:  # team measurements are for owners and leaders only

        def team_view() -> None:
            roster_section(packs)
            team_tab(conn, pack, lang)
            notices_section(conn, packs, exams, catalog, lang)
            content_section(lang)
            access_section(lang, learner, email, global_owner)
            if global_owner:
                practices_section()
            assistant_section(lang)

        sections.append(("tab_team", team_view))
    elif families and catalog:  # a champion: only the people and notices of their own families

        def family_view() -> None:
            roster_section(packs)
            people = champion_team(conn, packs, exams, catalog, families, lang)
            notices_section(conn, packs, exams, catalog, lang, only=people)

        sections.append(("tab_team", family_view))
    if owner:  # ✏️ Edit mode: the owner edits the section's own content with drop-down lists
        sections = [(key, _editable(key, draw, pack, conn, catalog, learner, lang)) for key, draw in sections]
    labels = [f"{n} · {T(key, lang)}" for n, (key, _) in enumerate(sections, start=1)]
    leader_tabs = [n for n, (key, _) in enumerate(sections) if key in ("tab_reports", "tab_demand", "tab_team")]
    if leader_tabs:  # two rows: the learner's sections, then the owner / champion tools in another color
        ui.tab_rows(leader_tabs[0], "Owner tools" if owner else "Champion tools")
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
    st.caption(f"{pack.title} · v{pack.version}")
    ui.legal_footer(lang)
    ui.play_fx(sound=st.session_state.get("ak_sound", True))  # the sound / celebration of what just happened
