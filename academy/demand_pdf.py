"""The demand analysis as a PDF (charts and tables), built with reportlab so it works offline on any computer.

``available()`` says whether reportlab is installed; ``to_pdf`` returns the file's bytes. Same content and colors as the
charts in the app (academy/demand.py).
"""

from __future__ import annotations

import io
from xml.sax.saxutils import escape

from academy.demand import COLOR, SCOPE_NAME, visible
from academy.practice import CORE, EMERGING, OUTSIDE, THIRD, Practice

INK, MUTED, LINE, ORANGE = "#1C1C1E", "#55524E", "#E4E0DB", "#FF5800"


def available() -> bool:
    try:
        import reportlab  # noqa: F401
    except ImportError:
        return False
    return True


def _bars(items: list[tuple[str, int, str]], width: float):
    """Horizontal bar chart as a reportlab Drawing. items: (label, value, scope)."""
    from reportlab.graphics.shapes import Drawing, Line, Rect, String
    from reportlab.lib.colors import HexColor

    row, label_w, pad = 15, 0.42 * width, 26
    d = Drawing(width, len(items) * row + 4)
    top = max(v for _, v, _ in items) or 1
    d.add(Line(label_w, 0, label_w, len(items) * row + 4, strokeColor=HexColor("#C9C5BF"), strokeWidth=0.6))
    for i, (label, value, scope) in enumerate(items):
        y = (len(items) - 1 - i) * row + 3
        w = max(1.5, (width - label_w - pad) * value / top)
        text = label if len(label) <= 44 else label[:43] + "…"
        d.add(String(label_w - 5, y + 2.5, text, fontName="Helvetica", fontSize=7.5, fillColor=HexColor(INK), textAnchor="end"))
        d.add(Rect(label_w, y, w, row - 5, rx=1.5, ry=1.5, fillColor=HexColor(COLOR[scope]), strokeColor=None))
        d.add(String(label_w + w + 4, y + 2.5, str(value), fontName="Helvetica-Bold", fontSize=7.5, fillColor=HexColor(INK)))
    return d


def _share(scope_roles: dict, width: float, lang: str):
    """One stacked bar with the split of roles by scope, each segment with its count and share."""
    from reportlab.graphics.shapes import Drawing, Rect, String
    from reportlab.lib.colors import HexColor

    total = sum(scope_roles.values()) or 1
    ink = {CORE: INK, EMERGING: INK, THIRD: "#FFFFFF", OUTSIDE: "#FFFFFF"}
    d = Drawing(width, 40)
    x = 0.0
    for s in (CORE, THIRD, EMERGING, OUTSIDE):
        n = scope_roles.get(s, 0)
        if not n:
            continue
        w = max(26.0, (width - 6) * n / total)
        d.add(Rect(x, 16, w, 22, fillColor=HexColor(COLOR[s]), strokeColor=None))
        d.add(String(x + w / 2, 23.5, f"{n} · {round(100 * n / total)} %", fontName="Helvetica-Bold", fontSize=8, fillColor=HexColor(ink[s]),
                     textAnchor="middle"))
        x += w + 2
    x = 0.0
    for s in (CORE, THIRD, EMERGING, OUTSIDE):  # legend: identity is never color alone
        name = SCOPE_NAME[s]
        d.add(Rect(x, 2, 7, 7, fillColor=HexColor(COLOR[s]), strokeColor=None))
        d.add(String(x + 10, 2.5, name, fontName="Helvetica", fontSize=7.5, fillColor=HexColor(MUTED)))
        x += 16 + 4.2 * len(name)
    return d


def _lines(points: list[dict], width: float, lang: str, height: float = 150):
    """Roles per upload, one line per scope, with the value and the name at the end of each line."""
    from reportlab.graphics.shapes import Circle, Drawing, Line, PolyLine, String
    from reportlab.lib.colors import HexColor

    left, right, bottom, topm = 26, 150, 16, 8
    top_v = max(max(p[s] for s in (CORE, THIRD, EMERGING, OUTSIDE)) for p in points) or 1
    step = (width - left - right) / (len(points) - 1)
    d = Drawing(width, height)

    def xy(i: int, v: float) -> tuple[float, float]:
        return left + i * step, bottom + (height - bottom - topm) * v / top_v

    for v in sorted({0, top_v // 2, top_v}):
        y = xy(0, v)[1]
        d.add(Line(left, y, width - right, y, strokeColor=HexColor(LINE), strokeWidth=0.5))
        d.add(String(left - 4, y - 2.5, str(v), fontName="Helvetica", fontSize=7, fillColor=HexColor(MUTED), textAnchor="end"))
    for i, p in enumerate(points):
        d.add(String(xy(i, 0)[0], 3, p["date"], fontName="Helvetica", fontSize=7, fillColor=HexColor(MUTED), textAnchor="middle"))
    used: list[float] = []
    for s in (CORE, THIRD, EMERGING, OUTSIDE):
        pts = [xy(i, p[s]) for i, p in enumerate(points)]
        d.add(PolyLine([c for pt in pts for c in pt], strokeColor=HexColor(COLOR[s]), strokeWidth=1.6))
        for x, y in pts:
            d.add(Circle(x, y, 2.6, fillColor=HexColor(COLOR[s]), strokeColor=HexColor("#FFFFFF"), strokeWidth=1))
        ly = pts[-1][1] - 2.5
        while any(abs(ly - u) < 9 for u in used):
            ly -= 9
        used.append(ly)
        d.add(String(pts[-1][0] + 7, ly, f"{SCOPE_NAME[s]}: {points[-1][s]}", fontName="Helvetica", fontSize=7.5, fillColor=HexColor(INK)))
    return d


def to_pdf(a: dict, practice: Practice, generated: str = "", tr: dict | None = None) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    lang, k, s = a["lang"], a["keys"], a["summary"]
    page = landscape(A4)
    margin = 14 * mm
    width = page[0] - 2 * margin
    base = ParagraphStyle("base", fontName="Helvetica", fontSize=8.5, leading=11.5, textColor=colors.HexColor(INK))
    st = {"h1": ParagraphStyle("h1", parent=base, fontName="Helvetica-Bold", fontSize=19, leading=23),
          "h2": ParagraphStyle("h2", parent=base, fontName="Helvetica-Bold", fontSize=13, leading=16, spaceBefore=12, spaceAfter=6),
          "h3": ParagraphStyle("h3", parent=base, fontName="Helvetica-Bold", fontSize=9.5, leading=12, spaceAfter=4),
          "meta": ParagraphStyle("meta", parent=base, fontSize=8, textColor=colors.HexColor(MUTED)),
          "cell": ParagraphStyle("cell", parent=base, fontSize=7.5, leading=9.5),
          "head": ParagraphStyle("head", parent=base, fontName="Helvetica-Bold", fontSize=7.5, leading=9.5, textColor=colors.white),
          "kpi": ParagraphStyle("kpi", parent=base, fontName="Helvetica-Bold", fontSize=16, leading=19),
          "kpil": ParagraphStyle("kpil", parent=base, fontSize=7.5, textColor=colors.HexColor(MUTED))}

    def table(rows: list[dict], limit: int | None = None, weights: list[float] | None = None):
        rows = visible(rows)[:limit]
        if not rows:
            return Paragraph("—", base)
        cols = list(rows[0])
        data = [[Paragraph(escape(str(c)), st["head"]) for c in cols]] + [[Paragraph(escape(str(r[c])), st["cell"]) for c in cols] for r in rows]
        weights = weights or [max(len(str(c)), *(min(len(str(r[c])), 42) for r in rows)) + 2 for c in cols]
        t = Table(data, colWidths=[width * w / sum(weights) for w in weights], repeatRows=1)
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(INK)), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                               ("LINEBELOW", (0, 1), (-1, -1), 0.4, colors.HexColor(LINE)), ("TOPPADDING", (0, 0), (-1, -1), 3),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 3), ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4)]))
        return t

    def chart(title: str, items: list[tuple[str, int, str]], w: float):
        return [Paragraph(escape(title), st["h3"]), _bars(items, w) if items else Paragraph("—", base)]

    def pair(left: list, right: list):
        t = Table([[left, right]], colWidths=[width / 2, width / 2])
        t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 10)]))
        return t

    kp = [("Roles", s["roles"]), ("In the practice", f"{s['in_practice']} · {s['in_practice_pct']} %"),
          ("Outside the practice", s["outside"]), ("Clients", s["clients"]),
          ("Distinct skills", s["skills"]), ("Practice skills without a course", s["no_course"])]
    kpis = Table([[[Paragraph(escape(str(v)), st["kpi"]), Paragraph(escape(n), st["kpil"])] for n, v in kp]], colWidths=[width / len(kp)] * len(kp))
    kpis.setStyle(TableStyle([("BOX", (i, 0), (i, 0), 0.6, colors.HexColor(LINE)) for i in range(len(kp))]
                             + [("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7), ("LEFTPADDING", (0, 0), (-1, -1), 8)]))
    top, half = 15, width / 2 - 12
    skills = [(r[k["skill"]], r[k["roles"]], r["_scope"]) for r in a["skills"][:top]]
    primary = [(r[k["pskill"]], r[k["roles"]], r["_scope"]) for r in a["primary"][:top]]
    titles = [(r[k["title"]], r[k["roles"]], r["_scope"]) for r in a["titles"][:top]]
    outside = [(r[k["skill"]], r[k["roles"]], OUTSIDE) for r in a["skills"] if r["_scope"] == OUTSIDE][:top]
    backlog = [(r[k["skill"]], r[k["roles"]], r["_scope"]) for r in a["backlog"][:top]]
    rule = Table([[""]], colWidths=[52], rowHeights=[4])
    rule.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(ORANGE))]))
    rule.hAlign = "LEFT"
    story = [rule, Spacer(1, 8),
             Paragraph(escape(f"{'Role demand analysis'} · {practice.name}"), st["h1"]),
             Paragraph(escape(f"Academia - Cloud · {'Generated'}: {generated} · "
                              + "Counts are roles: a skill counts once per role that asks for it."), st["meta"]),
             Spacer(1, 10), kpis,
             Paragraph(escape("How much of the demand belongs to our practice?"), st["h2"]),
             _share(a["scope_roles"], width, lang),
             Paragraph(escape("What is being requested"), st["h2"]),
             pair(chart(f"Top {top} most requested skills (roles that ask for each)", skills, half),
                  chart("Most requested primary skills", primary, half)),
             PageBreak(),
             pair(chart("Most requested role titles", titles, half),
                  chart("Most requested skills outside the practice", outside, half)),
             PageBreak(),
             Paragraph(escape("Demand against existing courses"), st["h2"]),
             Paragraph(escape("Practice skills in demand that still have no lessons in the academy: the courses to build, most requested first."), st["meta"]),
             Spacer(1, 6), KeepTogether(chart("Practice skills in demand without a course", backlog, width * 0.62)),
             PageBreak()]
    if tr and len(tr["dates"]) > 1:
        tk = tr["keys"]
        up = sorted((r for r in tr["skills"] if r["_delta"] > 0), key=lambda r: -r["_delta"])[:10]
        down = sorted((r for r in tr["skills"] if r["_delta"] < 0), key=lambda r: r["_delta"])[:10]
        story += [Paragraph(escape(f"{'Demand trend'} · {tr['dates'][0]} → {tr['dates'][-1]}"), st["h2"]),
                  Paragraph(escape("Roles per upload, by scope"), st["h3"]), _lines(tr["points"], width * 0.8, lang),
                  Spacer(1, 10),
                  pair(chart("Skills growing the most (more roles than in the previous upload)",
                             [(r[tk["skill"]], r["_delta"], r["_scope"]) for r in up], half),
                       chart("Skills dropping the most (fewer roles than in the previous upload)",
                             [(r[tk["skill"]], -r["_delta"], r["_scope"]) for r in down], half)),
                  PageBreak(),
                  Paragraph(escape("Most requested skills in every upload"), st["h2"]), table(tr["skills"]),
                  Paragraph(escape(f"New roles since the previous upload ({len(tr['new_roles'])})"), st["h2"]),
                  table(tr["new_roles"]),
                  Paragraph(escape(f"Roles no longer in the file ({len(tr['gone_roles'])})"), st["h2"]),
                  table(tr["gone_roles"]), PageBreak()]
    story += [
             Paragraph(escape("Courses to build (detail)"), st["h2"]), table(a["backlog"]),
             Paragraph(escape("Requested skills"), st["h2"]), table(a["skills"]),
             Paragraph(escape("Role titles"), st["h2"]), table(a["titles"]),
             Paragraph(escape("Role title and primary skill"), st["h2"]), table(a["combos"]),
             Paragraph(escape("Roles outside the practice"), st["h2"]), table(a["outside_roles"])]

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(colors.HexColor(MUTED))
        canvas.drawString(margin, 8 * mm, f"Academia - Cloud · {practice.name}")
        canvas.drawRightString(page[0] - margin, 8 * mm, f"{'Page'} {doc.page}")
        canvas.restoreState()

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=page, leftMargin=margin, rightMargin=margin, topMargin=12 * mm, bottomMargin=14 * mm,
                            title=f"{'Demand analysis'} · {practice.name}", author="Academia - Cloud")
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()
