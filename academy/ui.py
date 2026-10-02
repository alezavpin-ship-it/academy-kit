"""Visual layer: the shared styles, the «next step» card that opens the page and the progress bars.

Everything here is presentation only; the numbers come from the Tracker. Colors: brand orange #FF5800 on carbon #1C1C1E.
Orange surfaces carry dark text (white on #FF5800 does not reach the minimum contrast).
"""

from __future__ import annotations

import html

import streamlit as st

from academy.i18n import L
from academy.pack import Lesson, Pack
from academy.progress import Tracker

ORANGE, CARBON = "#FF5800", "#1C1C1E"

CSS = """<style>
.block-container{max-width:1240px;padding-top:2.5rem}
h1{letter-spacing:-.02em}h2,h3{letter-spacing:-.01em}
button[data-testid="stBaseButton-primary"],button[data-testid="stBaseButton-primary"] p{color:#1C1C1E!important;font-weight:700}
div[data-testid="stTabs"] button[role="tab"] p{font-size:15px;font-weight:600}
div[data-testid="stVerticalBlockBorderWrapper"]{border-radius:14px}
.st-key-ak_hero{background:#1C1C1E;border-radius:16px;padding:28px 32px 26px;margin:6px 0 4px}
.st-key-ak_hero p,.st-key-ak_hero h2,.st-key-ak_hero div{color:#FFFFFF}
.ak-eyebrow{display:flex;flex-wrap:wrap;gap:8px 12px;align-items:center;font-size:14px}
.ak-eyebrow span{color:#D6D2CC}
.ak-pill{display:inline-block;padding:5px 12px;border-radius:999px;background:#FF5800;color:#1C1C1E!important;font-size:13px;font-weight:700}
.ak-hero-title{margin:14px 0 8px;font-size:clamp(24px,3.2vw,34px);line-height:1.15;font-weight:700;letter-spacing:-.02em;color:#FFFFFF}
.ak-hero-sum{margin:0 0 6px;font-size:16px;line-height:1.55;color:#D6D2CC!important;max-width:680px}
.ak-prog{margin:14px 0 2px}
.ak-prog-head{display:flex;flex-wrap:wrap;justify-content:space-between;align-items:baseline;gap:6px 16px;font-size:14px;margin-bottom:8px}
.ak-prog-head b{font-size:15px}
.ak-prog-head strong{font-size:20px;margin-right:6px}
.ak-prog-bar{height:14px;border-radius:999px;background:rgba(128,128,128,.25);overflow:hidden}
.ak-prog-bar i{display:block;height:100%;border-radius:999px;background:#FF5800;transition:width .3s ease}
.st-key-ak_hero .ak-prog-bar{background:rgba(255,255,255,.18)}
.ak-prog-foot{font-size:13px;opacity:.75;margin-top:6px}
.ak-card{border:1px solid rgba(128,128,128,.25);border-radius:14px;padding:16px 20px;margin:4px 0 14px}
.ak-segs{display:flex;gap:4px}
.ak-segs i{flex:1;height:10px;border-radius:3px;background:rgba(128,128,128,.25)}
.ak-segs i.on{background:#FF5800}
@media (prefers-reduced-motion: reduce){.ak-prog-bar i{transition:none}}
</style>"""


def inject_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def next_lesson(pack: Pack, tr: Tracker, role: str | None = None) -> Lesson | None:
    """The first lesson still open, in pack order; the ones recommended for the chosen role go first."""
    done = tr.completed_lessons()
    todo = [x for x in pack.lessons if x.id not in done]
    if not todo:
        return None
    rec = pack.lessons_for_role(role) if role else set()
    return next((x for x in todo if x.id in rec), todo[0])


def bar_html(pct: float, title: str, right: str, foot: str = "", label: str | None = None) -> str:
    """A labelled progress bar (0..100). Screen readers get it as a progressbar with its value."""
    pct = max(0.0, min(100.0, pct))
    foot_html = f'<div class="ak-prog-foot">{html.escape(foot)}</div>' if foot else ""
    return (f'<div class="ak-prog"><div class="ak-prog-head"><b>{html.escape(title)}</b>'
            f'<span><strong>{pct:.0f} %</strong>{html.escape(right)}</span></div>'
            f'<div class="ak-prog-bar" role="progressbar" aria-label="{html.escape(label or title)}" aria-valuemin="0" aria-valuemax="100" '
            f'aria-valuenow="{pct:.0f}"><i style="width:{pct:.1f}%"></i></div>{foot_html}</div>')


def _go_to(level: str, lesson_id: str) -> None:
    st.session_state["ak_level"] = level
    st.session_state[f"ak_lesson_{level}"] = lesson_id
    st.session_state["ak_goto"] = "tab_course"


def hero(pack: Pack, tr: Tracker, lang: str, role: str | None = None) -> None:
    """The first thing on the page: what to study next, one button to get there, and the overall progress."""
    done, total = len(tr.completed_lessons()), len(pack.lessons)
    les = next_lesson(pack, tr, role)
    pct = 100 * done / total if total else 0
    left = total - done
    foot = (L(lang, f"Faltan {left} lecciones para completar la ruta", f"{left} lessons left to finish the route") if left
            else L(lang, "Ruta completa", "Route complete"))
    progress = bar_html(pct, L(lang, "Avance total de tu ruta", "Your overall progress"),
                        L(lang, f"· {done} de {total} lecciones completadas", f"· {done} of {total} lessons completed"), foot)
    with st.container(key="ak_hero"):
        if les is None:
            st.markdown(f'<div class="ak-eyebrow"><b class="ak-pill">{L(lang, "Ruta completa", "Route complete")}</b></div>'
                        f'<h2 class="ak-hero-title">{L(lang, "Completaste todas las lecciones.", "You completed every lesson.")}</h2>'
                        f'<p class="ak-hero-sum">{L(lang, "Revisa tus entregables de valor pendientes o prepara una certificación.", "Review your pending value deliverables or prepare a certification.")}</p>'
                        + progress, unsafe_allow_html=True)
            return
        n = [x.id for x in pack.lessons].index(les.id) + 1
        started = bool(tr.correct_items(les.id))
        st.markdown(f'<div class="ak-eyebrow"><b class="ak-pill">{L(lang, "Tu siguiente paso", "Your next step")}</b>'
                    f'<span>{html.escape(les.level)} · {L(lang, "Lección", "Lesson")} {n} {L(lang, "de", "of")} {total}</span></div>'
                    f'<h2 class="ak-hero-title">{html.escape(les.title)}</h2>'
                    f'<p class="ak-hero-sum">{html.escape(les.summary)}</p>', unsafe_allow_html=True)
        st.button(L(lang, "Continuar lección →", "Continue lesson →") if started else L(lang, "Empezar lección →", "Start lesson →"),
                  key="ak_hero_go", type="primary", on_click=_go_to, args=(les.level, les.id))
        st.markdown(progress, unsafe_allow_html=True)


def lesson_progress(tr: Tracker, les: Lesson, lang: str) -> None:
    """Progress inside one lesson: one segment per check question, plus one for the value deliverable (VBD)."""
    ok = tr.correct_items(les.id)
    marks = [f"{les.id}:{k}" in ok for k in range(len(les.quiz))]
    if les.vbd is not None:
        marks.append(les.id in tr.vbds_done())
    if not marks:
        return
    got, total = sum(marks), len(marks)
    segs = "".join(f'<i class="{"on" if m else ""}"></i>' for m in marks)
    title = L(lang, "Avance de esta lección", "Progress in this lesson")
    right = L(lang, f"{got} de {total} pasos", f"{got} of {total} steps")
    st.markdown(f'<div class="ak-card"><div class="ak-prog-head"><b>{title}</b><span>{right}</span></div>'
                f'<div class="ak-segs" role="progressbar" aria-label="{title}" aria-valuemin="0" aria-valuemax="{total}" '
                f'aria-valuenow="{got}">{segs}</div></div>', unsafe_allow_html=True)
