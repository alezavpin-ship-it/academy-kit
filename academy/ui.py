"""Visual layer: the shared styles, the «next step» card that opens the page and the progress bars.

Everything here is presentation only; the numbers come from the Tracker. Colors: brand orange #FF5800 on carbon #1C1C1E.
Orange surfaces carry dark text (white on #FF5800 does not reach the minimum contrast).
"""

from __future__ import annotations

import html

import streamlit as st

from academy import legal
from academy.pack import Lesson, Pack
from academy.progress import Tracker

ORANGE, CARBON = "#FF5800", "#1C1C1E"

CSS = """<style>
/* the whole app at 80 % (Streamlit sizes text and spacing in rem): more fits on the screen without the browser zoom */
html{font-size:80%}
/* a full web page, not a centered form: the content uses the whole window (up to very wide screens) */
.block-container{max-width:1920px;padding:2.25rem clamp(1.25rem,3.5vw,4rem) 4rem}
h1{font-size:clamp(2.1rem,2.6vw,3rem)!important}
div[data-testid="stMetricValue"]{font-size:clamp(1.9rem,2.2vw,2.6rem)}
div[data-testid="stTabs"] [role="tab"]{padding:.5rem .45rem}
div[data-testid="stTabs"] [role="tab"] p{font-size:.95rem;font-weight:600}
div[data-testid="stTabs"] [role="tablist"]{gap:.35rem}
.ak-tiles{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;height:100%}
.ak-tile{background:rgba(255,255,255,.08);border-radius:12px;padding:16px 18px;display:flex;flex-direction:column;justify-content:center;gap:2px}
.ak-tile b{font-size:clamp(1.7rem,2.3vw,2.6rem);line-height:1.1;font-weight:700;color:#FFFFFF}
.ak-tile span{font-size:.9rem;color:#D6D2CC!important}
.ak-tile small{font-size:.8rem;color:#FFB98F!important}
h1{letter-spacing:-.02em}h2,h3{letter-spacing:-.01em}
button[data-testid="stBaseButton-primary"],button[data-testid="stBaseButton-primary"] p{color:#1C1C1E!important;font-weight:700}
div[data-testid="stVerticalBlockBorderWrapper"]{border-radius:14px}
.st-key-ak_hero{background:#1C1C1E;border-radius:18px;padding:clamp(24px,2.6vw,44px);margin:6px 0 8px}
.st-key-ak_hero p,.st-key-ak_hero h2,.st-key-ak_hero div{color:#FFFFFF}
.ak-eyebrow{display:flex;flex-wrap:wrap;gap:8px 12px;align-items:center;font-size:1rem}
.ak-eyebrow span{color:#D6D2CC}
.ak-pill{display:inline-block;padding:6px 14px;border-radius:999px;background:#FF5800;color:#1C1C1E!important;font-size:.9rem;font-weight:700}
.ak-hero-title{margin:16px 0 10px;font-size:clamp(28px,3vw,48px);line-height:1.12;font-weight:700;letter-spacing:-.02em;color:#FFFFFF}
.ak-hero-sum{margin:0 0 10px;font-size:clamp(1rem,1.15vw,1.25rem);line-height:1.55;color:#D6D2CC!important;max-width:820px}
.ak-prog{margin:14px 0 2px}
.ak-prog-head{display:flex;flex-wrap:wrap;justify-content:space-between;align-items:baseline;gap:6px 16px;font-size:1rem;margin-bottom:8px}
.ak-prog-head b{font-size:1.05rem}
.ak-prog-head strong{font-size:1.5rem;margin-right:6px}
.ak-prog-bar{height:18px;border-radius:999px;background:rgba(128,128,128,.25);overflow:hidden}
.ak-prog-bar i{display:block;height:100%;border-radius:999px;background:#FF5800;transition:width .3s ease}
.st-key-ak_hero .ak-prog-bar{background:rgba(255,255,255,.18)}
.ak-prog-foot{font-size:.9rem;opacity:.75;margin-top:6px}
.ak-card{border:1px solid rgba(128,128,128,.25);border-radius:14px;padding:16px 20px;margin:4px 0 14px}
.ak-segs{display:flex;gap:4px}
.ak-segs i{flex:1;height:14px;border-radius:3px;background:rgba(128,128,128,.25)}
.ak-segs i.on{background:#FF5800}
.ak-points{list-style:none;margin:10px 0 6px;padding:0;display:flex;flex-direction:column;gap:12px;counter-reset:akp}
.ak-points li{display:flex;gap:14px;align-items:flex-start;line-height:1.55;counter-increment:akp;
  animation:ak-rise .45s ease-out both;animation-delay:calc(var(--i)*90ms)}
.ak-points li::before{content:counter(akp);flex:0 0 30px;height:30px;border-radius:50%;background:rgba(255,88,0,.16);
  display:flex;align-items:center;justify-content:center;font-weight:700;font-size:14px}
/* motion: things arrive, progress fills, results pop */
.st-key-ak_hero{animation:ak-rise .5s ease-out both}
.ak-prog-bar i{transform-origin:left center;animation:ak-fill .9s cubic-bezier(.2,.8,.2,1) both}
.ak-segs i.on{animation:ak-pop .45s ease-out both}
.ak-card{animation:ak-rise .4s ease-out both}
div[data-testid="stTabs"] [role="tabpanel"]{animation:ak-fade .3s ease-out both}
div[data-testid="stAlert"]{animation:ak-rise .3s ease-out both}
button[data-testid="stBaseButton-primary"]{transition:transform .15s ease,box-shadow .15s ease}
button[data-testid="stBaseButton-primary"]:hover{transform:translateY(-1px);box-shadow:0 6px 16px rgba(255,88,0,.28)}
button[data-testid="stBaseButton-primary"]:active{transform:translateY(0) scale(.98)}
.ak-confetti{position:fixed;inset:0;pointer-events:none;overflow:hidden;z-index:999990}
.ak-confetti i{position:absolute;top:-16px;left:var(--x);width:9px;height:15px;border-radius:2px;background:var(--c);
  animation:ak-fall var(--t) cubic-bezier(.3,.6,.5,1) var(--d) both}
@keyframes ak-rise{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}
@keyframes ak-fade{from{opacity:0}to{opacity:1}}
@keyframes ak-fill{from{transform:scaleX(0)}to{transform:scaleX(1)}}
@keyframes ak-pop{0%{transform:scaleY(.4);opacity:.3}60%{transform:scaleY(1.5)}100%{transform:none;opacity:1}}
@keyframes ak-fall{0%{transform:translate3d(0,0,0) rotate(0);opacity:1}85%{opacity:1}
  100%{transform:translate3d(var(--dx),105vh,0) rotate(var(--r));opacity:0}}
.ak-legal{margin:28px 0 4px;padding-top:14px;border-top:1px solid rgba(128,128,128,.25);font-size:13px;opacity:.8;text-align:center}
@media (prefers-reduced-motion: reduce){
  .st-key-ak_hero,.ak-prog-bar i,.ak-segs i.on,.ak-card,.ak-points li,div[data-testid="stAlert"],
  div[data-testid="stTabs"] [role="tabpanel"]{animation:none!important}
  .ak-prog-bar i,button[data-testid="stBaseButton-primary"]{transition:none}
  .ak-confetti{display:none}}
</style>"""

# ------------------------------------------------------------------------------------------ sound and celebration
# Short synthesized tones (Web Audio): no audio files to ship or host. (frequency Hz, seconds, waveform)
SOUNDS = {
    "ok": [(659.25, .11, "sine"), (880.0, .2, "sine")],  # right answer: two notes up
    "bad": [(233.08, .16, "triangle"), (196.0, .26, "triangle")],  # wrong answer: two soft notes down
    "step": [(783.99, .1, "sine")],  # a step marked as done
    "go": [(523.25, .08, "sine"), (659.25, .12, "sine")],  # start / continue a lesson
    "win": [(523.25, .12, "triangle"), (659.25, .12, "triangle"), (783.99, .12, "triangle"), (1046.5, .34, "triangle")],  # lesson, exam
}
_JS = """<script>(function(){try{var A=window.AudioContext||window.webkitAudioContext;if(!A)return;
var c=window.__akAudio||(window.__akAudio=new A());if(c.state==='suspended'){c.resume();}
var seq=%s,t=c.currentTime+0.03;window.__akLastSound=%s;
seq.forEach(function(n){var o=c.createOscillator(),g=c.createGain();o.type=n[2];o.frequency.value=n[0];
g.gain.setValueAtTime(0.0001,t);g.gain.exponentialRampToValueAtTime(0.16,t+0.02);g.gain.exponentialRampToValueAtTime(0.0001,t+n[1]);
o.connect(g);g.connect(c.destination);o.start(t);o.stop(t+n[1]+0.03);t+=n[1]*0.85;});}catch(e){}})();</script>"""


def fx(kind: str) -> None:
    """Queue feedback for the action that just happened: its sound and, for a win, the celebration. Played by play_fx()."""
    if kind in SOUNDS:
        st.session_state["ak_fx"] = kind


def play_fx(sound: bool = True) -> None:
    """Call once, at the end of the page: plays what fx() queued during this run (or just before a rerun)."""
    kind = st.session_state.pop("ak_fx", None)
    if kind is None:
        return
    n = st.session_state["ak_fx_n"] = st.session_state.get("ak_fx_n", 0) + 1  # makes each one a new element, so it plays again
    if kind == "win":
        colors = ["#FF5800", "#FFB414", "#1C1C1E", "#FF8A4C", "#FFFFFF"]
        bits = "".join(f'<i style="--x:{(i * 37 + 11) % 100}%;--c:{colors[i % 5]};--t:{1.6 + (i % 5) * .22:.2f}s;--d:{(i % 7) * .05:.2f}s;'
                       f'--dx:{((i * 53) % 160) - 80}px;--r:{360 + (i * 97) % 540}deg"></i>' for i in range(36))
        st.markdown(f'<div class="ak-confetti" aria-hidden="true" data-n="{n}">{bits}</div>', unsafe_allow_html=True)
    if not sound:
        return
    import json

    script = _JS % (json.dumps(SOUNDS[kind]), json.dumps(f"{kind}:{n}"))
    try:
        st.html(script, unsafe_allow_javascript=True)
    except TypeError:  # older Streamlit: run it from a component frame, on the page's own audio context
        import streamlit.components.v1 as components

        components.html(script.replace("window.", "window.parent."), height=0)


def points_html(points: list[str]) -> str:
    """The lesson's key points as a numbered list that arrives one by one."""
    items = "".join(f'<li style="--i:{i}"><span>{html.escape(p)}</span></li>' for i, p in enumerate(points))
    return f'<ol class="ak-points">{items}</ol>'


def legal_footer(lang: str) -> None:
    """The fixed copyright notice that closes every page (see academy/legal.py)."""
    legal.guard(lang)
    st.markdown(legal.footer_html(lang), unsafe_allow_html=True)


def inject_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


LEADER = "#2A78D6"  # the owner / champion tools wear blue, the learner's sections the academy's orange


def tab_rows(learner_tabs: int, label: str = "Owner tools") -> None:
    """The page's tabs in two rows: the learner's sections first, then (owner / champion view) their tools, in another color.

    One st.tabs keeps working underneath (state, deep links, tests); CSS wraps its tab list: a zero-height flex item placed
    between both groups forces the second row."""
    k = learner_tabs + 1
    st.markdown(f"""<style>
.st-key-ak_tabs [role="tablist"]{{flex-wrap:wrap;row-gap:.55rem;overflow:visible!important;width:auto!important}}
.st-key-ak_tabs [role="tablist"]>*{{order:1}}
.st-key-ak_tabs [role="tablist"]::after{{content:"";position:static!important;flex:0 0 100%;width:100%;height:0;order:2;border:0!important;background:none!important}}
.st-key-ak_tabs [role="tablist"]>[role="tab"]:nth-child(n+{k}){{order:3;border:1px solid {LEADER}66;background:{LEADER}14;border-radius:999px;
  padding:.3rem .95rem;margin-top:.15rem}}
.st-key-ak_tabs [role="tablist"]>[role="tab"]:nth-child(n+{k}) p{{color:{LEADER}!important}}
.st-key-ak_tabs [role="tablist"]>[role="tab"]:nth-child(n+{k})[aria-selected="true"]{{background:{LEADER};border-color:{LEADER}}}
.st-key-ak_tabs [role="tablist"]>[role="tab"]:nth-child(n+{k})[aria-selected="true"] p{{color:#FFFFFF!important}}
.st-key-ak_tabs [role="tablist"]>[role="tab"]:nth-child({k})::before{{content:"{label}";position:absolute;right:calc(100% + .7rem);
  white-space:nowrap;font-size:.72rem;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:{LEADER}}}
.st-key-ak_tabs [role="tablist"]>[role="tab"]:nth-child({k}){{margin-left:7.5rem;position:relative}}
.st-key-ak_tabs [role="tablist"]>[role="tab"]:nth-child(n+{k}) .react-aria-SelectionIndicator{{display:none}}
.st-key-ak_tabs [role="tablist"]+button,.st-key-ak_tabs button[aria-label*="croll"]{{display:none}}
</style>""", unsafe_allow_html=True)


def next_lesson(pack: Pack, tr: Tracker, role: str | None = None) -> Lesson | None:
    """The first lesson still open, in pack order, among the lessons of the chosen role (all lessons without a role)."""
    done = tr.completed_lessons()
    return next((x for x in pack.lessons_in_scope(role) if x.id not in done), None)


def bar_html(pct: float, title: str, right: str, foot: str = "", label: str | None = None) -> str:
    """A labelled progress bar (0..100). Screen readers get it as a progressbar with its value."""
    pct = max(0.0, min(100.0, pct))
    foot_html = f'<div class="ak-prog-foot">{html.escape(foot)}</div>' if foot else ""
    return (f'<div class="ak-prog"><div class="ak-prog-head"><b>{html.escape(title)}</b>'
            f'<span><strong>{pct:.0f} %</strong>{html.escape(right)}</span></div>'
            f'<div class="ak-prog-bar" role="progressbar" aria-label="{html.escape(label or title)}" aria-valuemin="0" aria-valuemax="100" '
            f'aria-valuenow="{pct:.0f}"><i style="width:{pct:.1f}%"></i></div>{foot_html}</div>')


def _go_to(level: str, lesson_id: str) -> None:
    fx("go")
    st.session_state["ak_level"] = level
    st.session_state[f"ak_lesson_{level}"] = lesson_id
    st.session_state["ak_goto"] = "tab_course"


def hero(pack: Pack, tr: Tracker, lang: str, role: str | None = None) -> None:
    """The first thing on the page: what to study next, one button to get there, and the progress — of the chosen role's
    lessons when a role is picked in the sidebar, of every lesson otherwise."""
    scope = pack.lessons_in_scope(role)
    ids = {x.id for x in scope}
    done, total = len(tr.completed_lessons() & ids), len(scope)
    les = next_lesson(pack, tr, role)
    pct = 100 * done / total if total else 0
    left = total - done
    who = f"the {role} route" if role and len(scope) < len(pack.lessons) else "the route"
    foot = f"{left} lessons left to finish {who}" if left else ("Route complete" if who == "the route" else f"{role} route complete")
    progress = bar_html(pct, f"Your progress as {role}" if role else "Your overall progress",
                        f"· {done} of {total} lessons completed", foot)
    pts = tr.total_points()
    cur, need = tr.rank(pts)
    to_next = (f"{need} to reach {pack.ranks[cur + 1].name}" if need is not None
               else "top rank")
    right_q = len({i for i in tr.correct_items() if i.rsplit(":", 1)[0] in ids})
    total_q = sum(len(x.quiz) for x in scope)
    tiles = "".join(f'<div class="ak-tile"><b>{html.escape(str(v))}</b><span>{html.escape(k)}</span><small>{html.escape(note)}</small></div>'
                    for k, v, note in (("Lessons completed", f"{done} / {total}", ""),
                                       ("Questions answered right", f"{right_q} / {total_q}", ""),
                                       ("Points", f"{pts:,}", to_next),
                                       ("Rank", pack.ranks[cur].name, "")))
    with st.container(key="ak_hero"):
        left, right = st.columns([3, 2], gap="large")
        with right:
            st.markdown(f'<div class="ak-tiles">{tiles}</div>', unsafe_allow_html=True)
        with left:
            if les is None:
                st.markdown(f'<div class="ak-eyebrow"><b class="ak-pill">{"Route complete"}</b></div>'
                            f'<h2 class="ak-hero-title">{"You completed every lesson of your role." if role else "You completed every lesson."}</h2>'
                            f'<p class="ak-hero-sum">{"Review the glossary or prepare a certification."}</p>',
                            unsafe_allow_html=True)
            else:
                n = [x.id for x in scope].index(les.id) + 1
                started = bool(tr.correct_items(les.id))
                st.markdown(f'<div class="ak-eyebrow"><b class="ak-pill">{"Your next step"}</b>'
                            f'<span>{html.escape(les.level)} · {"Lesson"} {n} {"of"} {total}</span></div>'
                            f'<h2 class="ak-hero-title">{html.escape(les.title)}</h2>'
                            f'<p class="ak-hero-sum">{html.escape(les.summary)}</p>', unsafe_allow_html=True)
                st.button("Continue lesson →" if started else "Start lesson →",
                          key="ak_hero_go", type="primary", on_click=_go_to, args=(les.level, les.id))
        st.markdown(progress, unsafe_allow_html=True)


def lesson_progress(tr: Tracker, les: Lesson, lang: str) -> None:
    """Progress inside one lesson: one segment per check question."""
    ok = tr.correct_items(les.id)
    marks = [f"{les.id}:{k}" in ok for k in range(len(les.quiz))]
    if not marks:
        return
    got, total = sum(marks), len(marks)
    segs = "".join(f'<i class="{"on" if m else ""}"></i>' for m in marks)
    title = "Progress in this lesson"
    right = f"{got} of {total} steps"
    st.markdown(f'<div class="ak-card"><div class="ak-prog-head"><b>{title}</b><span>{right}</span></div>'
                f'<div class="ak-segs" role="progressbar" aria-label="{title}" aria-valuemin="0" aria-valuemax="{total}" '
                f'aria-valuenow="{got}">{segs}</div></div>', unsafe_allow_html=True)
