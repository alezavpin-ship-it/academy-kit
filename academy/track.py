"""Progress line: one medal per rank (the pack's illustration or its emoji), the current one glowing, plus a bar."""

from __future__ import annotations

import base64
import html

from academy.pack import Pack

CSS = """<style>
.ak-track{display:flex;align-items:flex-end;gap:4px;padding:14px 10px 6px;border:1px solid rgba(128,128,128,.25);border-radius:16px}
.ak-lv{flex:1;text-align:center;min-width:0}
.ak-medal{position:relative;width:100%;max-width:120px;aspect-ratio:1;margin:0 auto;border-radius:50%;border:4px solid var(--ring);
  box-sizing:border-box;background:var(--bg);display:flex;align-items:center;justify-content:center;font-size:clamp(26px,4vw,48px);
  animation:ak-float 3.4s ease-in-out infinite;animation-delay:var(--d)}
.ak-medal img{position:absolute;inset:0;width:100%;height:100%;border-radius:50%;object-fit:cover}
.ak-now .ak-medal{animation:ak-float 2.6s ease-in-out infinite,ak-glow 2.2s ease-in-out infinite}
.ak-next .ak-medal{filter:grayscale(1);opacity:.45}
.ak-nm{font-weight:700;font-size:14px;margin-top:6px}.ak-pt{font-size:12px;opacity:.7}
.ak-now .ak-nm{color:#FF5800}.ak-done .ak-nm{color:#00E676}.ak-next .ak-nm{opacity:.55}
.ak-ar{color:#FF5800;font-size:20px;padding-bottom:46px}
.ak-bar{height:9px;border-radius:99px;background:rgba(128,128,128,.22);margin:10px 8px 4px;position:relative;overflow:hidden}
.ak-bar i{position:absolute;left:0;top:0;bottom:0;border-radius:99px;background:linear-gradient(90deg,#FFB414,#FF5800)}
.ak-note{font-size:13px;opacity:.8;margin:0 8px 6px}
@keyframes ak-float{0%,100%{transform:translateY(0)}50%{transform:translateY(-5px)}}
@keyframes ak-glow{0%,100%{box-shadow:0 0 0 0 rgba(255,88,0,0)}50%{box-shadow:0 0 16px 4px rgba(255,88,0,.5)}}
@media (prefers-reduced-motion: reduce){.ak-medal{animation:none!important}}
</style>"""

_MIME = {".png": "image/png", ".webp": "image/webp", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".svg": "image/svg+xml"}


def _img(pack: Pack, name: str) -> str:
    p = pack.asset(name)
    if p is None:
        return ""
    return f'<img src="data:{_MIME.get(p.suffix.lower(), "image/png")};base64,{base64.b64encode(p.read_bytes()).decode()}" alt="">'


def position(pack: Pack, points: int) -> float:
    """0..1 along the line, linear between rank thresholds."""
    ths = [r.points for r in pack.ranks]
    if points >= ths[-1]:
        return 1.0
    for i in range(len(ths) - 1):
        if points < ths[i + 1]:
            return (i + (max(points, 0) - ths[i]) / (ths[i + 1] - ths[i])) / (len(ths) - 1)
    return 1.0


def track_html(pack: Pack, points: int, note: str) -> str:
    cur = max(i for i, r in enumerate(pack.ranks) if points >= r.points)
    cells = []
    for i, r in enumerate(pack.ranks):
        state = "now" if i == cur else ("done" if i < cur else "next")
        inner = _img(pack, r.image) or html.escape(r.emoji)
        cells.append(f'<div class="ak-lv ak-{state}"><div class="ak-medal" style="--ring:{r.color};--bg:{r.color}22;--d:-{i * 0.7:.1f}s">'
                     f'{inner}</div><div class="ak-nm">{"✓ " if state == "done" else ""}{html.escape(r.name)}</div>'
                     f'<div class="ak-pt">{r.points:,}+ pts</div></div>' + ('<div class="ak-ar">➜</div>' if i < len(pack.ranks) - 1 else ""))
    return (CSS + f'<div class="ak-track">{"".join(cells)}</div>'
            f'<div class="ak-bar"><i style="width:{position(pack, points) * 100:.1f}%"></i></div><div class="ak-note">{html.escape(note)}</div>')
