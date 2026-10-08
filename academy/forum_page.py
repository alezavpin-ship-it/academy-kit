"""The «Foro» tab: ask a question to the experts of a skill family, read and answer, and (owners / champions) run it."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from academy import ui
from academy.forum import CHAMPION, MAX_BODY, MAX_TITLE, OWNER, SME, Forum, Question
from academy.i18n import L


def _badge(role: str, lang: str) -> str:
    return {OWNER: " · 🟠 Owner", CHAMPION: " · 🟠 Champion", SME: L(lang, " · 🟠 SME (experto)", " · 🟠 SME (expert)")}.get(role, "")


def _open(qid: int | None) -> None:
    st.session_state["fo_open"] = qid


def _ask_box(f: Forum, catalog, me: str, lang: str) -> None:
    n = st.session_state.get("fo_ask_n", 0)  # a new number empties the form after posting
    with st.expander(L(lang, "✍️ Hacer una pregunta", "✍️ Ask a question"), expanded=st.session_state.get("fo_asking", False)):
        fams = {x.id: x.name for x in catalog.families}
        c = st.columns(2)
        fam = c[0].selectbox(L(lang, "Familia de skills", "Skill family"), list(fams), format_func=lambda k: fams[k], key=f"fo_fam_{n}",
                             help=L(lang, "Los expertos (SME) de esta familia reciben tu pregunta.", "The experts (SMEs) of this family get your question."))
        skills = {"": L(lang, "(general de la familia)", "(the family in general)")} | {x.id: x.name for x in catalog.in_family(fam)}
        skill = c[1].selectbox("Skill", list(skills), format_func=lambda k: skills[k], key=f"fo_skill_{n}_{fam}")
        title = st.text_input(L(lang, "Tu pregunta, en una línea", "Your question, in one line"), max_chars=MAX_TITLE, key=f"fo_title_{n}")
        body = st.text_area(L(lang, "Detalle: qué intentaste, qué esperabas, qué pasó (sin datos de clientes)",
                              "Details: what you tried, what you expected, what happened (no customer data)"), max_chars=MAX_BODY,
                            key=f"fo_body_{n}", height=140)
        if st.button(L(lang, "Publicar pregunta", "Post question"), type="primary", key=f"fo_post_{n}", disabled=not title.strip()):
            qid = f.ask(me, fam, title, body, skill)
            st.session_state.update(fo_ask_n=n + 1, fo_asking=False)
            _open(qid)
            ui.fx("step")
            st.toast(L(lang, "Pregunta publicada. Los expertos de la familia ya pueden verla.", "Question posted. The family's experts can see it now."))
            st.rerun()


def _question(f: Forum, q: Question, catalog, me: str, my_role: str, admin: bool, lang: str) -> None:
    fams = {x.id: x.name for x in catalog.families}
    skills = {x.id: x.name for x in catalog.skills}
    answers = q.answers if admin else q.visible_answers()
    state = ("🔒 " if q.closed else "") + ("✅" if q.answered else "❓")
    label = f"{'📌 ' if q.pinned else ''}{state} {q.title} · {len(q.visible_answers())} {L(lang, 'resp.', 'replies')}" \
            + (L(lang, " · oculta", " · hidden") if q.hidden else "")
    with st.expander(label, expanded=st.session_state.get("fo_open") == q.id):
        where = fams.get(q.family, q.family) + (f" · {skills.get(q.skill, q.skill)}" if q.skill else "")
        st.caption(f"{q.author} · {q.time[:10]} · {where}")
        if q.body:
            st.markdown(q.body)
        for a in answers:
            with st.container(border=True):
                mark = L(lang, "✅ **Respuesta aceptada** · ", "✅ **Accepted answer** · ") if a.accepted else ""
                st.markdown(f"{mark}**{a.author}**{_badge(a.role, lang)} · {a.time[:10]}" + (L(lang, " · _oculta_", " · _hidden_") if a.hidden else ""))
                st.markdown(a.body)
                can_accept = (admin or my_role or me.lower() == q.author.lower()) and not a.hidden
                cols = st.columns([1, 1, 4])
                if can_accept and cols[0].button(L(lang, "Quitar aceptada", "Unaccept") if a.accepted else L(lang, "Marcar como aceptada", "Mark as accepted"),
                                                 key=f"fo_acc_{a.id}"):
                    f.accept(a.id, not a.accepted)
                    _open(q.id)
                    ui.fx("ok")
                    st.rerun()
                if admin and cols[1].button(L(lang, "Mostrar", "Show") if a.hidden else L(lang, "Ocultar", "Hide"), key=f"fo_hide_a_{a.id}"):
                    f.hide_answer(a.id, not a.hidden)
                    _open(q.id)
                    st.rerun()
        if q.closed:
            st.info(L(lang, "Pregunta cerrada: ya no admite respuestas.", "Closed question: no more replies."))
        elif not q.hidden:
            n = st.session_state.get(f"fo_rep_n_{q.id}", 0)
            hint = L(lang, "Responde como experto de esta familia", "Answer as an expert of this family") if my_role \
                else L(lang, "Aporta lo que sepas o pide más detalle", "Share what you know or ask for more detail")
            text = st.text_area(L(lang, "Tu respuesta", "Your reply"), key=f"fo_rep_{q.id}_{n}", max_chars=MAX_BODY, placeholder=hint, height=110)
            if st.button(L(lang, "Responder", "Reply"), key=f"fo_rep_btn_{q.id}", type="primary", disabled=not text.strip()):
                f.answer(q.id, me, text, my_role)
                st.session_state[f"fo_rep_n_{q.id}"] = n + 1
                _open(q.id)
                ui.fx("step")
                st.rerun()
        if admin:  # the family's champion or an owner runs the thread
            st.caption(L(lang, "Administración (champion / owner)", "Administration (champion / owner)"))
            c = st.columns(3)
            if c[0].button(L(lang, "Desfijar", "Unpin") if q.pinned else L(lang, "📌 Fijar arriba", "📌 Pin to top"), key=f"fo_pin_{q.id}", width="stretch"):
                f.pin(q.id, not q.pinned)
                _open(q.id)
                st.rerun()
            if c[1].button(L(lang, "Reabrir", "Reopen") if q.closed else L(lang, "🔒 Cerrar", "🔒 Close"), key=f"fo_close_{q.id}", width="stretch"):
                f.close(q.id, not q.closed)
                _open(q.id)
                st.rerun()
            if c[2].button(L(lang, "Mostrar pregunta", "Show question") if q.hidden else L(lang, "Ocultar pregunta", "Hide question"),
                           key=f"fo_hide_{q.id}", width="stretch"):
                f.hide_question(q.id, not q.hidden)
                _open(q.id)
                st.rerun()


def _admin(f: Forum, catalog, admin_fams: set[str], lang: str) -> None:
    with st.expander(L(lang, "⚙️ Administrar el foro: expertos (SME) por familia y exportación", "⚙️ Run the forum: experts (SMEs) per family and export")):
        st.caption(L(lang, "Escribe el nombre o correo de cada experto tal como lo pone en la barra lateral, separados por coma. "
                           "Sus respuestas llevan la insignia SME y la pregunta cuenta como contestada.",
                     "Type each expert's name or e-mail exactly as they enter it in the sidebar, separated by commas. "
                     "Their replies carry the SME badge and the question counts as answered."))
        current = f.smes()
        for fam in [x for x in catalog.families if x.id in admin_fams]:
            c = st.columns([2, 4, 1])
            c[0].markdown(f"**{fam.name}**  \n{L(lang, 'Champion', 'Champion')}: {fam.champion or '—'}")
            text = c[1].text_input("SMEs", value=", ".join(current.get(fam.id, [])), key=f"fo_sme_{fam.id}", label_visibility="collapsed",
                                   placeholder=L(lang, "ana.lopez@empresa.com, Luis Pérez", "ana.lopez@company.com, Luis Perez"))
            if c[2].button(L(lang, "Guardar", "Save"), key=f"fo_sme_save_{fam.id}", width="stretch"):
                f.set_smes(fam.id, text.replace(";", ",").split(","))
                st.toast(L(lang, "Expertos guardados.", "Experts saved."))
                st.rerun()
        rows = f.rows(admin_fams)
        if rows:
            st.download_button(L(lang, "Descargar el foro en CSV", "Download the forum as CSV"),
                               pd.DataFrame(rows).to_csv(index=False).encode("utf-8-sig"), file_name=L(lang, "foro.csv", "forum.csv"),
                               mime="text/csv", key="fo_csv")


def forum_tab(conn, catalog, learner: str, email: str, lang: str, owner: bool = False, champion_of: set[str] | None = None) -> None:
    """``owner`` / ``champion_of``: who runs the forum (every family / these families), as switched on in the sidebar."""
    if not catalog:
        st.info(L(lang, "El foro se organiza por familia de skills: primero carga el catálogo en «Mapa de skills».",
                  "The forum is organized by skill family: load the catalog in the Skills map first."))
        return
    f = Forum(conn)
    me = learner.strip() or "yo"
    champion_of = champion_of or set()
    admin_fams = {x.id for x in catalog.families} if owner else set(champion_of)
    expert_fams = admin_fams | f.sme_families(me, email)
    st.markdown(L(lang, "Pregunta lo que no te quedó claro: los expertos (SME) de cada familia de skills contestan, y cualquier compañero puede aportar.",
                  "Ask what was not clear: the experts (SMEs) of each skill family answer, and any colleague can add to it."))
    everything = f.questions(include_hidden=bool(admin_fams))
    everything = [q for q in everything if not q.hidden or q.family in admin_fams]
    waiting = [q for q in everything if not q.answered and not q.closed and not q.hidden]
    for_me = [q for q in waiting if q.family in expert_fams]
    c = st.columns(4)
    c[0].metric(L(lang, "Preguntas", "Questions"), len([q for q in everything if not q.hidden]), border=True)
    c[1].metric(L(lang, "Esperan a un experto", "Waiting for an expert"), len(waiting), border=True)
    c[2].metric(L(lang, "Contestadas", "Answered"), len([q for q in everything if q.answered and not q.hidden]), border=True)
    c[3].metric(L(lang, "Mis preguntas", "My questions"), len([q for q in everything if q.author.lower() == me.lower()]), border=True)
    if for_me:
        st.warning(L(lang, f"**{len(for_me)} pregunta(s) de tus familias esperan tu respuesta.**", f"**{len(for_me)} question(s) in your families are waiting for your answer.**"))
    _ask_box(f, catalog, me, lang)
    fams = {"": L(lang, "Todas las familias", "All families")} | {x.id: x.name for x in catalog.families}
    views = {"all": L(lang, "Todas", "All"), "waiting": L(lang, "Sin respuesta de experto", "Waiting for an expert"),
             "answered": L(lang, "Contestadas", "Answered"), "mine": L(lang, "Mías", "Mine")}
    if expert_fams:
        views["for_me"] = L(lang, "Para contestar yo", "For me to answer")
    c = st.columns([2, 3, 2])
    fam = c[0].selectbox(L(lang, "Familia", "Family"), list(fams), format_func=lambda k: fams[k], key="fo_f_fam")
    view = c[1].segmented_control(L(lang, "Ver", "Show"), list(views), default="all", format_func=lambda k: views[k], key="fo_f_view") or "all"
    text = c[2].text_input(L(lang, "Buscar", "Search"), key="fo_f_text").strip().lower()
    shown = [q for q in everything
             if (not fam or q.family == fam)
             and (view != "waiting" or (not q.answered and not q.closed)) and (view != "answered" or q.answered)
             and (view != "mine" or q.author.lower() == me.lower()) and (view != "for_me" or q in for_me)
             and (not text or text in (q.title + " " + q.body + " " + " ".join(a.body for a in q.visible_answers())).lower())]
    if not shown:
        st.info(L(lang, "Todavía no hay preguntas aquí. Sé la primera persona en preguntar.", "No questions here yet. Be the first to ask.")
                if not everything else L(lang, "Ninguna pregunta coincide con el filtro.", "No question matches the filter."))
    for q in shown:
        _question(f, q, catalog, me, f.role_in(q.family, me, email, owner, champion_of), q.family in admin_fams, lang)
    if admin_fams:
        _admin(f, catalog, admin_fams, lang)
