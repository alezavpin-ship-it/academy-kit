"""The status and follow-up report (Reports tab) as a PDF, built with reportlab so it works offline on any computer.

Same numbers as the tab and the Excel export (academy/report.py): indicators, who is keeping up with the career path,
each family's state, the people who need follow-up and the certifications. ``to_pdf(rep)`` returns the file's bytes.
"""

from __future__ import annotations

import io
from xml.sax.saxutils import escape

from academy import report
from academy.demand_pdf import INK, LINE, MUTED, ORANGE, available  # noqa: F401  (available is re-exported for the page)

# a person's state on the career path (worst first); every bar also carries its name and number, never color alone
PATH_COLOR = {report.BEHIND: "#FF5800", report.AT_RISK: "#F2A541", report.NOT_STARTED: "#9A958F", report.GOING: "#2A78D6",
              report.DONE: "#1BAF7A"}
LATE = {report.BEHIND, report.AT_RISK}


def _bars(items: list[tuple[str, int, str]], width: float):
    """Horizontal bars as a reportlab Drawing. items: (label, value, color)."""
    from reportlab.graphics.shapes import Drawing, Line, Rect, String
    from reportlab.lib.colors import HexColor

    row, label_w, pad = 16, 0.36 * width, 30
    d = Drawing(width, len(items) * row + 4)
    top = max((v for _, v, _ in items), default=1) or 1
    d.add(Line(label_w, 0, label_w, len(items) * row + 4, strokeColor=HexColor("#C9C5BF"), strokeWidth=0.6))
    for i, (label, value, color) in enumerate(items):
        y = (len(items) - 1 - i) * row + 3
        w = max(1.5, (width - label_w - pad) * value / top) if value else 0
        text = label if len(label) <= 40 else label[:39] + "…"
        d.add(String(label_w - 5, y + 3, text, fontName="Helvetica", fontSize=8, fillColor=HexColor(INK), textAnchor="end"))
        if w:
            d.add(Rect(label_w, y, w, row - 5, rx=1.5, ry=1.5, fillColor=HexColor(color), strokeColor=None))
        d.add(String(label_w + w + 4, y + 3, str(value), fontName="Helvetica-Bold", fontSize=8, fillColor=HexColor(INK)))
    return d


def _widths(cols: list[str], rows: list[dict], width: float) -> list[float]:
    """Column widths in points: no header word is ever split; long text columns give up room first."""
    from reportlab.pdfbase.pdfmetrics import stringWidth

    pad = 9
    def word(text, font: str) -> float:
        return max((stringWidth(w, font, 7.5) for w in str(text).split()), default=8)

    mins = [max(word(c, "Helvetica-Bold"), *(word("—" if r[c] is None else r[c], "Helvetica") for r in rows)) + pad for c in cols]
    want = [max(m, min(160, max(stringWidth("—" if r[c] is None else str(r[c]), "Helvetica", 7.5) for r in rows) + pad)) for m, c in zip(mins, cols)]
    if sum(want) <= width:
        return [w * width / sum(want) for w in want]
    if sum(mins) >= width:
        return [m * width / sum(mins) for m in mins]
    room, extra = width - sum(mins), [w - m for w, m in zip(want, mins)]
    return [m + room * e / sum(extra) for m, e in zip(mins, extra)]


# the family status in the PDF: who leads it, the gap, the people and how far they are (the Excel has every column)
BRIEF = ["Role family", "Champion", "Gap volume", "People",
         "Active", "Need follow-up", "Lesson progress",
         "Route progress", "Mock exams passed", "Forum: waiting",
         "Last activity", "Status"]


def _only(rows: list[dict], lang: str, keep: list[str]) -> list[dict]:
    names = keep
    return [{k: v for k, v in r.items() if k in names or k.startswith("_")} for r in rows]


def _num(text) -> int:
    """'40 %' -> 40; '—' -> 0."""
    try:
        return int(str(text).split()[0])
    except (ValueError, IndexError):
        return 0


def to_pdf(rep: dict) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    lang, s = rep["lang"], rep["summary"]
    t = report.titles(lang)
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

    def table(rows: list[dict], flag=None):
        """``flag(row) -> bool`` marks the rows that need attention with an orange edge (and bold last column)."""
        shown = report.visible(rows)
        if not shown:
            return Paragraph(escape(t["empty"]), st["meta"])
        cols = list(shown[0])
        cell = (lambda v: Paragraph(escape("—" if v is None else str(v)), st["cell"]))
        data = [[Paragraph(escape(str(c)), st["head"]) for c in cols]] + [[cell(r[c]) for c in cols] for r in shown]
        tb = Table(data, colWidths=_widths(cols, shown, width), repeatRows=1)
        style = [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(INK)), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                 ("LINEBELOW", (0, 1), (-1, -1), 0.4, colors.HexColor(LINE)), ("TOPPADDING", (0, 0), (-1, -1), 3),
                 ("BOTTOMPADDING", (0, 0), (-1, -1), 3), ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4)]
        for i, r in enumerate(rows, start=1):
            if flag and flag(r):
                style += [("LINEBEFORE", (0, i), (0, i), 3, colors.HexColor(ORANGE)), ("FONTNAME", (-1, i), (-1, i), "Helvetica-Bold")]
        tb.setStyle(TableStyle(style))
        return tb

    def pair(left: list, right: list):
        tb = Table([[left, right]], colWidths=[width / 2, width / 2])
        tb.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 12)]))
        return tb

    certs = rep.get("certs") or {}
    cs = certs.get("summary") or {}
    kp = [(t["families"], s["families"]), (t["on_track"], s["on_track"]), (t["no_champion"], s["no_champion"]),
          (t["active_people"], s["people"]), (t["behind"], s.get("behind", 0)), (t["not_started"], s.get("not_started", 0)),
          ("Current certifications", cs.get("current", 0))]
    kpis = Table([[[Paragraph(escape(str(v)), st["kpi"]), Paragraph(escape(n), st["kpil"])] for n, v in kp]], colWidths=[width / len(kp)] * len(kp))
    kpis.setStyle(TableStyle([("BOX", (i, 0), (i, 0), 0.6, colors.HexColor(LINE)) for i in range(len(kp))]
                             + [("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7), ("LEFTPADDING", (0, 0), (-1, -1), 8)]))
    half = width / 2 - 14
    names = dict(report.PATH)
    people = rep.get("people", [])
    by_state = [(names[k], sum(1 for p in people if p["_path"] == k), PATH_COLOR[k]) for k in report.PATH_ORDER]
    status = rep["status"]
    fam_key = next(iter(status[0])) if status else ""
    lessons_key, steps_key = "Lesson progress", "Route progress"
    progress = [(r[fam_key], max(_num(r.get(lessons_key)), _num(r.get(steps_key))), ORANGE) for r in status]
    rule = Table([[""]], colWidths=[52], rowHeights=[4])
    rule.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(ORANGE))]))
    rule.hAlign = "LEFT"
    story = [rule, Spacer(1, 8), Paragraph(escape(t["report"]), st["h1"]),
             Paragraph(escape(f"Academia - Cloud · {t['generated']}: {rep['generated']} · {t['rules']}"), st["meta"]),
             Spacer(1, 10), kpis, Spacer(1, 6),
             pair([Paragraph(escape("People by career path status"), st["h3"]),
                   _bars(by_state, half) if people else Paragraph(escape(t["empty"]), st["meta"])],
                  [Paragraph(escape("Progress by family (best of lessons or route, %)"), st["h3"]),
                   _bars(progress, half) if progress else Paragraph("—", st["meta"])]),
             Paragraph(escape(t["status"]), st["h2"]),
             Paragraph(escape("The content columns (skills, lessons, steps, certifications) are in the report's Excel."), st["meta"]),
             Spacer(1, 4), table(_only(status, lang, BRIEF), lambda r: r["_state"] != report.ON_TRACK),
             PageBreak(),
             Paragraph(escape(t["people"]), st["h2"]),
             Paragraph(escape("One row per person, whoever is not keeping up first. The status is the worst across their families."), st["meta"]),
             Spacer(1, 4), table(people, lambda r: r["_path"] in LATE),
             Paragraph(escape(t["followup"]), st["h2"]),
             table([r for r in rep["followup"] if r["_late"]], lambda r: True) if any(r["_late"] for r in rep["followup"])
             else Paragraph(escape("Nobody needs follow-up today."), st["meta"]),
             PageBreak(),
             Paragraph(escape(t["paths"]), st["h2"]), table(rep.get("paths", []), lambda r: r["_path"] in LATE)]
    if certs.get("families") or certs.get("people") or certs.get("expiring"):
        story += [PageBreak()]
        for key, part in (("certs_fam", "families"), ("certs_people", "people"), ("certs_exp", "expiring")):
            if certs.get(part):
                story += [KeepTogether([Paragraph(escape(t[key]), st["h2"]), table(certs[part])])]

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(colors.HexColor(MUTED))
        canvas.drawString(margin, 8 * mm, f"Academia - Cloud · {t['report']}")
        canvas.drawRightString(page[0] - margin, 8 * mm, f"{'Page'} {doc.page}")
        canvas.restoreState()

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=page, leftMargin=margin, rightMargin=margin, topMargin=12 * mm, bottomMargin=14 * mm,
                            title=t["report"], author="Academia - Cloud")
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()
