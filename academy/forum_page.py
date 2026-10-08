"""The «Foro» tab: ask a question to the experts of a role family, read and answer, and (owners / champions) run it."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from academy import ui
from academy.forum import CHAMPION, MAX_BODY, MAX_TITLE, OWNER, SME, Forum, Question


def _badge(role: str, lang: str) -> str:
    return {OWNER: " · 🟠 Owner", CHAMPION: " · 🟠 Champion", SME: " · 🟠 SME (expert)"}.get(role, "")


def _open(qid: int | None) -> None:
    st.session_state["fo_open"] = qid


def _ask_box(f: Forum, catalog, me: str, lang: str) -> None:
    n = st.session_state.get("fo_ask_n", 0)  # a new number empties the form after posting
    with st.expander("✍️ Ask a question", expanded=st.session_state.get("fo_asking", False)):
        fams = {x.id: x.name for x in catalog.families}
        c = st.columns(2)
        fam = c[0].selectbox("Role family", list(fams), format_func=lambda k: fams[k], key=f"fo_fam_{n}",
                             help="The experts (SMEs) of this family get your question.")
        skills = {"": "(the family in general)"} | {x.id: x.name for x in catalog.in_family(fam)}
        skill = c[1].selectbox("Skill", list(skills), format_func=lambda k: skills[k], key=f"fo_skill_{n}_{fam}")
        title = st.text_input("Your question, in one line", max_chars=MAX_TITLE, key=f"fo_title_{n}")
        body = st.text_area("Details: what you tried, what you expected, what happened (no customer data)", max_chars=MAX_BODY,
                            key=f"fo_body_{n}", height=140)
        if st.button("Post question", type="primary", key=f"fo_post_{n}", disabled=not title.strip()):
            qid = f.ask(me, fam, title, body, skill)
            st.session_state.update(fo_ask_n=n + 1, fo_asking=False)
            _open(qid)
            ui.fx("step")
            st.toast("Question posted. The family's experts can see it now.")
            st.rerun()


def _question(f: Forum, q: Question, catalog, me: str, my_role: str, admin: bool, lang: str) -> None:
    fams = {x.id: x.name for x in catalog.families}
    skills = {x.id: x.name for x in catalog.skills}
    answers = q.answers if admin else q.visible_answers()
    state = ("🔒 " if q.closed else "") + ("✅" if q.answered else "❓")
    label = f"{'📌 ' if q.pinned else ''}{state} {q.title} · {len(q.visible_answers())} {'replies'}" \
            + (" · hidden" if q.hidden else "")
    with st.expander(label, expanded=st.session_state.get("fo_open") == q.id):
        where = fams.get(q.family, q.family) + (f" · {skills.get(q.skill, q.skill)}" if q.skill else "")
        st.caption(f"{q.author} · {q.time[:10]} · {where}")
        if q.body:
            st.markdown(q.body)
        for a in answers:
            with st.container(border=True):
                mark = "✅ **Accepted answer** · " if a.accepted else ""
                st.markdown(f"{mark}**{a.author}**{_badge(a.role, lang)} · {a.time[:10]}" + (" · _hidden_" if a.hidden else ""))
                st.markdown(a.body)
                can_accept = (admin or my_role or me.lower() == q.author.lower()) and not a.hidden
                cols = st.columns([1, 1, 4])
                if can_accept and cols[0].button("Unaccept" if a.accepted else "Mark as accepted",
                                                 key=f"fo_acc_{a.id}"):
                    f.accept(a.id, not a.accepted)
                    _open(q.id)
                    ui.fx("ok")
                    st.rerun()
                if admin and cols[1].button("Show" if a.hidden else "Hide", key=f"fo_hide_a_{a.id}"):
                    f.hide_answer(a.id, not a.hidden)
                    _open(q.id)
                    st.rerun()
        if q.closed:
            st.info("Closed question: no more replies.")
        elif not q.hidden:
            n = st.session_state.get(f"fo_rep_n_{q.id}", 0)
            hint = "Answer as an expert of this family" if my_role \
                else "Share what you know or ask for more detail"
            text = st.text_area("Your reply", key=f"fo_rep_{q.id}_{n}", max_chars=MAX_BODY, placeholder=hint, height=110)
            if st.button("Reply", key=f"fo_rep_btn_{q.id}", type="primary", disabled=not text.strip()):
                f.answer(q.id, me, text, my_role)
                st.session_state[f"fo_rep_n_{q.id}"] = n + 1
                _open(q.id)
                ui.fx("step")
                st.rerun()
        if admin:  # the family's champion or an owner runs the thread
            st.caption("Administration (champion / owner)")
            c = st.columns(3)
            if c[0].button("Unpin" if q.pinned else "📌 Pin to top", key=f"fo_pin_{q.id}", width="stretch"):
                f.pin(q.id, not q.pinned)
                _open(q.id)
                st.rerun()
            if c[1].button("Reopen" if q.closed else "🔒 Close", key=f"fo_close_{q.id}", width="stretch"):
                f.close(q.id, not q.closed)
                _open(q.id)
                st.rerun()
            if c[2].button("Show question" if q.hidden else "Hide question",
                           key=f"fo_hide_{q.id}", width="stretch"):
                f.hide_question(q.id, not q.hidden)
                _open(q.id)
                st.rerun()


def _admin(f: Forum, catalog, admin_fams: set[str], lang: str) -> None:
    with st.expander("⚙️ Run the forum: experts (SMEs) per family and export"):
        st.caption(("Type each expert's name or e-mail exactly as they enter it in the sidebar, separated by commas. "
                     "Their replies carry the SME badge and the question counts as answered."))
        current = f.smes()
        for fam in [x for x in catalog.families if x.id in admin_fams]:
            c = st.columns([2, 4, 1])
            c[0].markdown(f"**{fam.name}**  \n{'Champion'}: {fam.champion or '—'}")
            text = c[1].text_input("SMEs", value=", ".join(current.get(fam.id, [])), key=f"fo_sme_{fam.id}", label_visibility="collapsed",
                                   placeholder="ana.lopez@company.com, Luis Perez")
            if c[2].button("Save", key=f"fo_sme_save_{fam.id}", width="stretch"):
                f.set_smes(fam.id, text.replace(";", ",").split(","))
                st.toast("Experts saved.")
                st.rerun()
        rows = f.rows(admin_fams)
        if rows:
            st.download_button("Download the forum as CSV",
                               pd.DataFrame(rows).to_csv(index=False).encode("utf-8-sig"), file_name="forum.csv",
                               mime="text/csv", key="fo_csv")


def forum_tab(conn, catalog, learner: str, email: str, lang: str, owner: bool = False, champion_of: set[str] | None = None) -> None:
    """``owner`` / ``champion_of``: who runs the forum (every family / these families), as switched on in the sidebar."""
    if not catalog:
        st.info("The forum is organized by role family: load the catalog in the Skills map first.")
        return
    f = Forum(conn)
    me = learner.strip() or "me"
    champion_of = champion_of or set()
    admin_fams = {x.id for x in catalog.families} if owner else set(champion_of)
    expert_fams = admin_fams | f.sme_families(me, email)
    st.markdown("Ask what was not clear: the experts (SMEs) of each role family answer, and any colleague can add to it.")
    everything = f.questions(include_hidden=bool(admin_fams))
    everything = [q for q in everything if not q.hidden or q.family in admin_fams]
    waiting = [q for q in everything if not q.answered and not q.closed and not q.hidden]
    for_me = [q for q in waiting if q.family in expert_fams]
    c = st.columns(4)
    c[0].metric("Questions", len([q for q in everything if not q.hidden]), border=True)
    c[1].metric("Waiting for an expert", len(waiting), border=True)
    c[2].metric("Answered", len([q for q in everything if q.answered and not q.hidden]), border=True)
    c[3].metric("My questions", len([q for q in everything if q.author.lower() == me.lower()]), border=True)
    if for_me:
        st.warning(f"**{len(for_me)} question(s) in your families are waiting for your answer.**")
    _ask_box(f, catalog, me, lang)
    fams = {"": "All families"} | {x.id: x.name for x in catalog.families}
    views = {"all": "All", "waiting": "Waiting for an expert",
             "answered": "Answered", "mine": "Mine"}
    if expert_fams:
        views["for_me"] = "For me to answer"
    c = st.columns([2, 3, 2])
    fam = c[0].selectbox("Family", list(fams), format_func=lambda k: fams[k], key="fo_f_fam")
    view = c[1].segmented_control("Show", list(views), default="all", format_func=lambda k: views[k], key="fo_f_view") or "all"
    text = c[2].text_input("Search", key="fo_f_text").strip().lower()
    shown = [q for q in everything
             if (not fam or q.family == fam)
             and (view != "waiting" or (not q.answered and not q.closed)) and (view != "answered" or q.answered)
             and (view != "mine" or q.author.lower() == me.lower()) and (view != "for_me" or q in for_me)
             and (not text or text in (q.title + " " + q.body + " " + " ".join(a.body for a in q.visible_answers())).lower())]
    if not shown:
        st.info("No questions here yet. Be the first to ask."
                if not everything else "No question matches the filter.")
    for q in shown:
        _question(f, q, catalog, me, f.role_in(q.family, me, email, owner, champion_of), q.family in admin_fams, lang)
    if admin_fams:
        _admin(f, catalog, admin_fams, lang)
