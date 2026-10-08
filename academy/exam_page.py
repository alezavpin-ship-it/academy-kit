"""The «Certificaciones» tab: study route with interactive exercises, practice by module, timed mock exam and history."""

from __future__ import annotations

import random
import time

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from academy import assistant as ai
from academy import quiz, ui
from academy.exam import EXERCISE_POINTS, PASS_POINTS, PRACTICE_POINTS, Exam, ExamTracker, Exercise, build_mock, check_match, check_order, grade
from academy.i18n import L

KIND_ICON = {"path": "🧭", "module": "📘", "course": "🎓", "lab": "🧪", "video": "▶", "guide": "📄", "exam": "🏅", "practice": "📝",
             "sandbox": "🖥️", "tutorial": "🛠️", "hub": "🗂️", "doc": "📄"}


def material_links(items: list[dict], cols: int = 2) -> None:
    """Support material as link buttons (title, provider)."""
    grid = st.columns(cols)
    for i, m in enumerate(items):
        label = f"{KIND_ICON.get(m.get('kind', 'doc'), '📄')} {m['title']}"
        grid[i % cols].link_button(label, m["url"], help=m.get("provider", ""), width="stretch")


def assistant_box(prompt: str, lang: str, key: str, label: str = "") -> None:
    """«Ask Amethyst»: the prompt, ready with context. Handoff: copy it and open the assistant. API: ask from here."""
    cfg = ai.load_assistant()
    if not cfg.enabled:
        return
    with st.expander(f"✨ {label or L(lang, f'Preguntar a {cfg.name}', f'Ask {cfg.name}')}"):
        if cfg.mode == "api":
            if st.button(L(lang, f"Preguntar a {cfg.name}", f"Ask {cfg.name}"), key=f"ai_ask_{key}", type="primary"):
                with st.spinner(L(lang, "Consultando…", "Asking…")):
                    st.session_state[f"ai_ans_{key}"] = ai.ask(cfg, prompt, lang=lang)
            ans = st.session_state.get(f"ai_ans_{key}")
            if ans:
                (st.markdown if ans[0] else st.error)(ans[1])
                st.caption(L(lang, "Respuesta generada por IA: verifica los datos de producto en la documentación oficial.",
                             "AI-generated answer: verify product facts in the official documentation."))
            with st.popover(L(lang, "Ver lo que se envía", "See what is sent")):
                st.code(prompt, language=None, wrap_lines=True)
        else:
            st.caption(L(lang, f"Copia este mensaje (botón de la esquina) y pégalo en {cfg.name}. Solo incluye el contenido de estudio y tu propio resultado.",
                         f"Copy this message (corner button) and paste it into {cfg.name}. It only includes study content and your own result."))
            st.code(prompt, language=None, wrap_lines=True)
            if cfg.url:
                st.link_button(L(lang, f"Abrir {cfg.name} ↗", f"Open {cfg.name} ↗"), cfg.url)


# ---------------------------------------------------------------------------------------------- exercises
def _exercise(ex: Exercise, tr: ExamTracker, lang: str) -> None:
    done = ex.id in tr.exercises_done()
    with st.container(border=True):
        st.markdown(("✅ " if done else "🧩 ") + f"**{ex.prompt}**")
        fb_key = f"ex_fb_{tr.learner}_{ex.id}"
        if ex.type == "order":
            opts = list(ex.steps)
            random.Random(quiz._seed(ex.id)).shuffle(opts)
            chosen = st.multiselect(L(lang, "Elige los pasos en el orden correcto", "Pick the steps in the right order"), opts,
                                    key=f"ex_o_{tr.learner}_{ex.id}", placeholder=L(lang, "Primero…", "First…"))
            if st.button(L(lang, "Revisar orden", "Check order"), key=f"ex_b_{ex.id}", disabled=len(chosen) != len(opts)):
                ok = check_order(ex, chosen)
                right = sum(a == b for a, b in zip(chosen, ex.steps))
                st.session_state[fb_key] = (ok, tr.complete_exercise(ex.id) if ok else 0, f"{right}/{len(opts)}")
                ui.fx("step" if ok else "bad")
        elif ex.type == "match":
            rights = [p[1] for p in ex.pairs]
            random.Random(quiz._seed(ex.id)).shuffle(rights)
            chosen = {}
            for i, (left, _) in enumerate(ex.pairs):
                chosen[left] = st.selectbox(left, rights, index=None, key=f"ex_m_{tr.learner}_{ex.id}_{i}",
                                            placeholder=L(lang, "Elige…", "Choose…"))
            if st.button(L(lang, "Revisar relaciones", "Check matches"), key=f"ex_b_{ex.id}", disabled=any(v is None for v in chosen.values())):
                res = check_match(ex, chosen)
                st.session_state[fb_key] = (all(res), tr.complete_exercise(ex.id) if all(res) else 0, f"{sum(res)}/{len(res)}")
                ui.fx("step" if all(res) else "bad")
        else:  # lab: a guided hands-on practice with a checklist
            if ex.url:
                st.link_button(f"🧪 {ex.label or L(lang, 'Abrir la práctica', 'Open the lab')} ↗", ex.url)
            ticks = [st.checkbox(s, key=f"ex_l_{tr.learner}_{ex.id}_{i}", value=done) for i, s in enumerate(ex.steps)]
            if st.button(L(lang, "Marcar práctica terminada", "Mark lab as done"), key=f"ex_b_{ex.id}", disabled=done or not all(ticks),
                         type="primary"):
                st.session_state[fb_key] = (True, tr.complete_exercise(ex.id), "")
                ui.fx("step" if True else "bad")
        fb = st.session_state.get(fb_key)
        if fb:
            ok, pts, detail = fb
            if ok:
                st.success(L(lang, "**¡Correcto!**", "**Correct!**") + (f" (+{pts} pts)" if pts else ""))
            else:
                st.error(L(lang, f"**Casi.** Llevas {detail} en su lugar; ajusta e inténtalo de nuevo.",
                           f"**Almost.** {detail} are in place; adjust and try again."))


def _study(exam: Exam, tr: ExamTracker, lang: str, leader: bool = False) -> None:
    ok, done = tr.practiced(), tr.exercises_done()
    dom_title = {d["id"]: d["title"] for d in exam.domains}
    for i, m in enumerate(exam.modules):
        qs = [q.id for q in exam.questions if q.module == m.id]
        got = len(ok & set(qs))
        ex_done = sum(1 for e in m.exercises if e.id in done)
        complete = got == len(qs) and ex_done == len(m.exercises)
        head = f"{'✅' if complete else '📘'} {L(lang, 'Módulo', 'Module')} {i + 1} · {m.title} — {got}/{len(qs)} {L(lang, 'preguntas', 'questions')}"
        with st.expander(head, expanded=False):
            st.caption(dom_title.get(m.domain, m.domain))
            st.markdown(f"_{m.summary}_")
            st.markdown("\n".join(f"- {p}" for p in m.points))
            st.markdown(L(lang, "**Material de apoyo**", "**Support material**"))
            material_links(m.materials)
            if m.exercises:
                st.markdown(L(lang, "**Ejercicios**", "**Exercises**") + f" · +{EXERCISE_POINTS} pts")
                for ex in m.exercises:
                    _exercise(ex, tr, lang)
            if leader:  # content owners: a draft of new questions to review, never added automatically
                assistant_box(ai.prompt_draft_questions(exam.name, f"{m.title} (id: {m.id})", m.points, lang=lang), lang, f"draft_{m.id}",
                              L(lang, "Para líderes: borrador de preguntas nuevas con IA", "For leaders: draft new questions with AI"))


# ---------------------------------------------------------------------------------------------- practice
def _practice(exam: Exam, tr: ExamTracker, lang: str) -> None:
    weak = [w[0] for w in tr.weak_modules()]
    opts = ["*"] + (["weak"] if weak else []) + [m.id for m in exam.modules]
    names = {"*": L(lang, "Todos los módulos", "All modules"), "weak": L(lang, "Mis puntos débiles", "My weak spots"),
             **{m.id: m.title for m in exam.modules}}
    pick = st.selectbox(L(lang, "Qué practicar", "What to practice"), opts, key="ex_p_mod", format_func=lambda k: names[k])
    pool = [q for q in exam.questions if pick == "*" or (pick == "weak" and q.module in weak) or q.module == pick]
    ok = tr.practiced()
    pool.sort(key=lambda q: q.id in ok)  # what you have not answered right yet comes first
    if not pool:
        return
    pos_key = f"ex_p_pos_{pick}"
    pos = st.session_state.get(pos_key, 0) % len(pool)
    q = pool[pos]
    st.progress(len(ok & {x.id for x in pool}) / len(pool),
                text=L(lang, f"{len(ok & {x.id for x in pool})} de {len(pool)} dominadas", f"{len(ok & {x.id for x in pool})} of {len(pool)} mastered"))
    options, ci = quiz.shuffled(f"p:{q.id}", q.options, q.answer)
    with st.container(border=True):
        st.caption(exam.module(q.module).title)
        choice = st.radio(f"**{q.q}**", list(range(4)), format_func=lambda j: options[j], index=None, key=f"ex_p_{tr.learner}_{q.id}_{pos}")
        fb_key = f"ex_p_fb_{tr.learner}_{q.id}"
        c1, c2 = st.columns([1, 1])
        if c1.button(L(lang, "Revisar", "Check"), key=f"ex_p_check_{q.id}", disabled=choice is None, type="primary"):
            st.session_state[fb_key] = (choice == ci, tr.answer_practice(q.id, choice == ci))
            ui.fx("ok" if choice == ci else "bad")
        if c2.button(L(lang, "Siguiente pregunta →", "Next question →"), key=f"ex_p_next_{q.id}"):
            st.session_state[pos_key] = pos + 1
            st.session_state.pop(fb_key, None)
            st.rerun()
        fb = st.session_state.get(fb_key)
        if fb:
            if fb[0]:
                st.success(L(lang, "**Correcto**", "**Correct**") + (f" (+{fb[1]} pts)" if fb[1] else "") + f". {q.why}")
            else:
                st.error(L(lang, "**Todavía no.**", "**Not yet.**") + f" {L(lang, 'Respuesta correcta', 'Right answer')}: **{q.options[q.answer]}**. {q.why}")
                material_links(exam.module(q.module).materials[:2])
                assistant_box(ai.prompt_explain(q.q, q.options, q.options[q.answer], q.why, options[choice] if choice is not None else "",
                                                exam.name, lang=lang), lang, f"p_{q.id}", L(lang, "Que me lo explique el tutor de IA", "Have the AI tutor explain it"))


# ---------------------------------------------------------------------------------------------- mock exam
def _countdown(seconds_left: int, lang: str) -> None:
    components.html(f"""<div id="t" style="font:600 20px Inter,system-ui,sans-serif;color:#FF5800;text-align:right"></div>
<script>let s={int(seconds_left)};const e=document.getElementById('t');function f(){{const m=Math.floor(Math.max(s,0)/60),r=Math.max(s,0)%60;
e.textContent='⏱ '+(s>0?m+':'+String(r).padStart(2,'0'):'{L(lang, "Tiempo agotado: envía tu examen", "Time is up: submit your exam")}');s--;}}f();setInterval(f,1000);</script>""",
                    height=34)


def _result(exam: Exam, res: dict, lang: str) -> None:
    dom_title = {d["id"]: d["title"] for d in exam.domains}
    c = st.columns(3)
    c[0].metric(L(lang, "Resultado", "Score"), f"{res['score']} / 1000", delta=L(lang, f"se aprueba con {exam.pass_score}", f"pass mark {exam.pass_score}"),
                delta_color="off", border=True)
    c[1].metric(L(lang, "Aciertos", "Correct"), f"{res['correct']} / {res['total']}", border=True)
    c[2].metric(L(lang, "Tiempo", "Time"), f"{res.get('seconds', 0) // 60} min", border=True)
    if res["passed"]:
        st.success(L(lang, "**¡Aprobado!** ", "**Passed!** ") + (f"+{res['points']} pts. " if res.get("points") else "")
                   + L(lang, "Repite el simulacro un par de veces más y agenda el examen oficial.", "Take the mock a couple more times and book the real exam."))
    else:
        st.error(L(lang, "**Todavía no alcanzas la marca.** Revisa abajo lo que fallaste y practica esos módulos.",
                   "**Not at the pass mark yet.** Review what you missed below and practice those modules."))
    if res.get("late"):
        st.warning(L(lang, "Enviaste el examen después del tiempo límite; en el examen real no se habría contado.",
                     "You submitted after the time limit; in the real exam it would not have counted."))
    st.markdown(L(lang, "##### Por dominio", "##### By domain"))
    for dom, v in res["domains"].items():
        st.progress(v["correct"] / v["total"] if v["total"] else 0.0, text=f"{dom_title.get(dom, dom)} — {v['correct']}/{v['total']}")
    if res["wrong"]:
        st.markdown(L(lang, f"##### Para repasar ({len(res['wrong'])})", f"##### To review ({len(res['wrong'])})"))
        for qid in res["wrong"]:
            q = exam.question(qid)
            mine = res["answers"].get(qid)
            with st.expander(q.q):
                st.markdown(L(lang, "Tu respuesta: ", "Your answer: ") + (f"~~{q.options[mine]}~~" if mine is not None else L(lang, "_sin responder_", "_unanswered_")))
                st.markdown(L(lang, "Correcta: ", "Right answer: ") + f"**{q.options[q.answer]}**")
                st.markdown(q.why)
                st.caption(L(lang, "Módulo: ", "Module: ") + exam.module(q.module).title)
    if not res["passed"] or res["wrong"]:
        weak = {}
        for qid in res["wrong"]:
            weak[exam.question(qid).module] = weak.get(exam.question(qid).module, 0) + 1
        mods = [exam.module(m) for m in sorted(weak, key=weak.get, reverse=True)[:3]]
        mats = [(x["title"], x["url"]) for m in mods for x in m.materials[:2]]
        doms = [(dom_title.get(d, d), v["correct"], v["total"]) for d, v in res["domains"].items()]
        assistant_box(ai.prompt_study_plan(exam.name, res["score"], exam.pass_score, doms, [m.title for m in mods], mats, lang=lang), lang,
                      f"plan_{exam.id}", L(lang, "Plan de estudio de 7 días con IA", "7-day study plan with AI"))


def _mock(exam: Exam, tr: ExamTracker, lang: str) -> None:
    state_key, res_key = f"ex_mock_{exam.id}_{tr.learner}", f"ex_res_{exam.id}_{tr.learner}"
    run = st.session_state.get(state_key)
    if run is None:
        res = st.session_state.get(res_key)
        if res:
            _result(exam, res, lang)
            st.divider()
        st.markdown(L(lang, f"**{exam.mock_questions} preguntas · {exam.mock_minutes} minutos · se aprueba con {exam.pass_score} de 1000.** "
                            "Las preguntas se reparten por dominio igual que en el examen, y no hay retroalimentación hasta el final.",
                      f"**{exam.mock_questions} questions · {exam.mock_minutes} minutes · pass mark {exam.pass_score} of 1000.** "
                      "Questions follow the exam's domain weights, with no feedback until the end."))
        if st.button(L(lang, "Empezar simulacro", "Start mock exam") if not res else L(lang, "Nuevo simulacro", "New mock exam"),
                     key=f"ex_start_{exam.id}", type="primary"):
            seed = int(time.time())
            st.session_state[state_key] = {"qids": build_mock(exam, random.Random(seed)), "start": time.time(), "seed": seed}
            st.session_state.pop(res_key, None)
            st.rerun()
        return
    left = int(exam.mock_minutes * 60 - (time.time() - run["start"]))
    _countdown(left, lang)
    shuffled = {qid: quiz.shuffled(f"{run['seed']}:{qid}", exam.question(qid).options, exam.question(qid).answer) for qid in run["qids"]}
    with st.form(f"ex_form_{exam.id}"):
        picks = {}
        for n, qid in enumerate(run["qids"], start=1):
            q = exam.question(qid)
            opts = shuffled[qid][0]
            picks[qid] = st.radio(f"**{n}. {q.q}**", list(range(4)), format_func=lambda j, o=opts: o[j], index=None,
                                  key=f"ex_mq_{run['seed']}_{qid}")
        sent = st.form_submit_button(L(lang, "Enviar examen", "Submit exam"), type="primary")
    if sent:
        answers = {qid: (q.options.index(shuffled[qid][0][j]) if j is not None else None)
                   for qid, j in picks.items() for q in [exam.question(qid)]}
        seconds = int(time.time() - run["start"])
        res = grade(exam, run["qids"], answers)
        res.update(answers=answers, seconds=seconds, late=seconds > exam.mock_minutes * 60 + 15, points=tr.record_mock(res, seconds))
        st.session_state[res_key] = res
        st.session_state.pop(state_key, None)
        ui.fx("win" if res["passed"] else "bad")
        st.rerun()


def _history(exam: Exam, tr: ExamTracker, lang: str) -> None:
    at = tr.attempts()
    if not at:
        st.info(L(lang, "Todavía no has hecho un simulacro.", "No mock exams yet."))
        return
    df = pd.DataFrame([{"#": a["n"], L(lang, "Fecha", "Date"): a["time"][:10], L(lang, "Resultado", "Score"): a.get("score", 0),
                        L(lang, "Aciertos", "Correct"): f"{a.get('correct', 0)}/{a.get('total', 0)}",
                        L(lang, "Minutos", "Minutes"): a.get("seconds", 0) // 60,
                        L(lang, "Estado", "Status"): L(lang, "Aprobado", "Passed") if a["passed"] else L(lang, "No aprobado", "Not passed")} for a in at])
    if len(at) > 1:
        st.line_chart(df.set_index("#")[[L(lang, "Resultado", "Score")]], height=220)
    st.dataframe(df, hide_index=True, width="stretch")


# ---------------------------------------------------------------------------------------------- tab
def exams_tab(exams: list[Exam], conn, learner: str, lang: str, catalog=None, leader: bool = False) -> None:
    if not exams:
        st.info(L(lang, "Todavía no hay certificaciones. Agrega una en exams/<id>/exam.json.", "No certifications yet. Add one in exams/<id>/exam.json."))
        return
    exam = exams[0] if len(exams) == 1 else st.selectbox(L(lang, "Certificación", "Certification"), exams, key="ex_pick",
                                                           format_func=lambda e: e.name)
    tr = ExamTracker(conn, exam, learner)
    st.markdown(f"### {exam.name}")
    fam = next((f for f in catalog.families if f.id == exam.family), None) if catalog else None
    if fam:
        st.caption(L(lang, "Familia de skills: ", "Skill family: ") + fam.name + (f" · Champion: {fam.champion}" if fam.champion else ""))
    at = tr.attempts()
    weak = tr.weak_modules()
    c = st.columns(4)
    c[0].metric(L(lang, "Preparación", "Readiness"), f"{tr.readiness():.0%}", border=True)
    c[1].metric(L(lang, "Mejor simulacro", "Best mock"), f"{max(a.get('score', 0) for a in at)}" if at else "—",
                delta=L(lang, "aprobado", "passed") if tr.passed() else None, border=True)
    c[2].metric(L(lang, "Puntos", "Points"), f"{tr.total_points():,}", border=True)
    c[3].metric(L(lang, "Módulos por reforzar", "Modules to reinforce"), len(weak), border=True)
    with st.expander(L(lang, "Recursos oficiales del examen", "Official exam resources")):
        material_links(exam.links)
        st.caption(exam.disclaimer)
    modes = {"study": L(lang, "Ruta de estudio", "Study route"), "practice": L(lang, "Práctica", "Practice"),
             "mock": L(lang, "Simulacro", "Mock exam"), "history": L(lang, "Historial", "History")}
    if st.session_state.get("ex_mode") not in modes:
        st.session_state["ex_mode"] = "study"
    mode = st.segmented_control("exam_mode", list(modes), key="ex_mode", format_func=lambda m: modes[m], label_visibility="collapsed") or "study"
    if mode == "study":
        st.caption(L(lang, f"Cada módulo: lee, abre el material, resuelve los ejercicios (+{EXERCISE_POINTS} pts) y practica sus preguntas "
                           f"(+{PRACTICE_POINTS} pts). Aprobar el simulacro da +{PASS_POINTS} pts.",
                     f"Each module: read, open the material, solve the exercises (+{EXERCISE_POINTS} pts) and practice its questions "
                     f"(+{PRACTICE_POINTS} pts). Passing the mock earns +{PASS_POINTS} pts."))
        _study(exam, tr, lang, leader)
    elif mode == "practice":
        _practice(exam, tr, lang)
    elif mode == "mock":
        _mock(exam, tr, lang)
    else:
        _history(exam, tr, lang)
