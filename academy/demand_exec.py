"""Executive report of the demand (owners): two pages a leader reads in five minutes.

``brief`` turns the analysis (academy/demand.py), the trend between uploads and the bench (people at level 3+ in the team
inventory) into plain conclusions: key messages, the top practice skills against the bench and the courses, and the
recommended actions with the family champion who owns each one. ``to_pdf`` lays it out with reportlab (portrait A4). The
same brief is shown in the app above the download, so the PDF never says something the screen does not.

The report is built from what is loaded: a roles file read only for the session is never written to disk by this module.
"""

from __future__ import annotations

import io
from datetime import date
from xml.sax.saxutils import escape

from academy.demand import COLOR, SCOPE_NAME
from academy.demand_pdf import INK, LINE, MUTED, ORANGE, _bars, _lines, _share, available  # noqa: F401  (available: re-exported)
from academy.practice import OUTSIDE, Practice

RED, AMBER, GREEN = "#C4314B", "#C27C0E", "#2E7D32"
STATUS_COLOR = {"lessons": GREEN, "path": AMBER, "none": RED, "new": RED}


def _month_label(ym: str) -> str:
    y, m = ym.split("-")
    return date(int(y), int(m), 1).strftime("%b %Y")


def brief(a: dict, tr: dict | None = None, bench: dict[str, int] | None = None, catalog=None, today: date | None = None,
          top: int = 10) -> dict:
    """{"messages": [...], "skills": [rows], "actions": [rows], "kpis": [(label, value)], "upcoming": int}."""
    k, s = a["keys"], a["summary"]
    today = today or date.today()
    fams = {f.id: f for f in catalog.families} if catalog else {}
    total = s["roles"] or 0

    def champion(entry, short: bool = False) -> str:
        f = fams.get(entry.family) if entry is not None else None
        if not f:
            return "Owner"
        return f.champion or ("Vacant" if short else f"{f.name} champion (vacant)")

    def people_word(n) -> str:
        return f"{n} person" if n == 1 else f"{n} people"

    skills = []
    for r in [r for r in a["skills"] if r["_scope"] != OUTSIDE][:top]:
        e = r["_entry"]
        sid = e.skill_id if e is not None and e.skill_id else ""
        people = bench.get(sid) if bench is not None and sid else None
        skills.append({"Skill": r[k["skill"]], "Skill family": r[k["family"]], "Roles": r[k["roles"]],
                       "People at level 3+": "—" if people is None else people, "Content": r[k["cover"]], "Champion": champion(e, True), "_owner": champion(e),
                       "_gap": r[k["roles"]] - (people or 0), "_people": people, "_cover": r["_cover"], "_scope": r["_scope"]})

    messages: list[str] = []
    if total:
        messages.append(f"{s['in_practice']} of {total} roles ({s['in_practice_pct']} %) belong to the practice; "
                        f"{s['outside']} fall outside it.")
    if a["skills"]:
        lead = a["skills"][0]
        messages.append(f"The most requested skill is {lead[k['skill']]} ({lead[k['roles']]} roles, "
                        f"{round(100 * lead[k['roles']] / max(total, 1))} % of the demand).")
    trend = None
    if tr and len(tr.get("points", [])) > 1:
        p0, p1 = tr["points"][-2], tr["points"][-1]
        trend = p1["roles"] - p0["roles"]
        up = max(tr["skills"], key=lambda r: r["_delta"], default=None)
        verb = "grew" if trend > 0 else "dropped" if trend < 0 else "held steady"
        msg = f"Since {p0['date']} the demand {verb}" + (f" by {abs(trend)} roles" if trend else "") + f" ({p0['roles']} → {p1['roles']})"
        if up is not None and up["_delta"] > 0:
            msg += f"; {up[tr['keys']['skill']]} grew the most (+{up['_delta']})"
        messages.append(msg + f". New roles: {len(tr['new_roles'])} · closed or removed: {len(tr['gone_roles'])}.")
    if skills:
        covered = sum(1 for r in skills if r["_cover"] == "lessons")
        bare = [r["Skill"] for r in skills if r["_cover"] in ("none", "new")]
        messages.append(f"{covered} of the top {len(skills)} practice skills already have a course in the academy"
                        + (f"; {len(bare)} have no content yet ({', '.join(bare[:3])})." if bare else "."))
    gaps = sorted((r for r in skills if r["_people"] is not None and r["_gap"] > 0), key=lambda r: -r["_gap"])
    if bench is not None and gaps:
        g = gaps[0]
        messages.append(f"Biggest bench gap: {g['Skill']}, {g['Roles']} roles against {people_word(g['_people'])} at level 3+.")
    elif bench is None or not any(bench.values()):
        messages.append("The team inventory has no skill levels yet: load it (Reports → Skills matrix) to compare the demand with the bench.")
    matrix = [r for r in a.get("matrix", []) if r["Roles where it is a gap"]]
    if matrix:
        m = matrix[0]
        messages.append(f"Most frequent gap in the practice matrix: {m['Skill']} ({m['Skill family']}), in {m['Roles where it is a gap']} roles.")
    this_month = f"{today.year}-{today.month:02d}"
    nxt = date(today.year + (today.month == 12), today.month % 12 + 1, 1)
    window = {this_month, f"{nxt.year}-{nxt.month:02d}"}
    upcoming = sum(n for ym, n in a.get("months", []) if ym in window)
    if upcoming:
        messages.append(f"{upcoming} roles start this month or the next: the people for them must be ready now.")

    actions = []
    for r in [r for r in a["backlog"] if r["_cover"] in ("none", "new")][:3]:
        actions.append({"Action": f"Build the course for {r[k['skill']]}", "Why": f"{r[k['roles']]} roles ask for it and it has no content",
                        "Owner": champion(r["_entry"])})
    for r in gaps[:3]:
        actions.append({"Action": f"Grow the bench in {r['Skill']}: study group and certification",
                        "Why": f"{r['Roles']} roles vs {people_word(r['_people'])} at level 3+", "Owner": r["_owner"]})
    for m in matrix[:2]:
        actions.append({"Action": f"Close the matrix gap {m['Skill']}", "Why": f"gap in {m['Roles where it is a gap']} roles · {m['In the academy']}",
                        "Owner": "Owner + " + m["Skill family"] + " champion"})
    out = [r for r in a["skills"] if r["_scope"] == OUTSIDE][:3]
    if out and out[0][k["roles"]] >= max(2, round(0.05 * total)):
        actions.append({"Action": "Decide on demand outside the practice: " + ", ".join(r[k["skill"]] for r in out),
                        "Why": f"{s['outside']} roles; add to the catalog, partner or decline", "Owner": "Owner"})

    kpis = [("Roles in demand", str(total)), ("In the practice", f"{s['in_practice_pct']} %"),
            ("Change vs previous upload", "—" if trend is None else f"{trend:+d}"),
            ("Practice skills without a course", str(s["no_course"])), ("Roles starting soon", str(upcoming))]
    return {"messages": messages, "skills": skills, "actions": actions, "kpis": kpis, "upcoming": upcoming}


def to_pdf(a: dict, practice: Practice, b: dict, source: str = "", generated: str = "", tr: dict | None = None) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    page, margin = A4, 15 * mm
    width = page[0] - 2 * margin
    hx = colors.HexColor
    base = ParagraphStyle("b", fontName="Helvetica", fontSize=9, leading=12.5, textColor=hx(INK))
    st = {"h1": ParagraphStyle("h1", parent=base, fontName="Helvetica-Bold", fontSize=20, leading=24),
          "h2": ParagraphStyle("h2", parent=base, fontName="Helvetica-Bold", fontSize=12.5, leading=16, spaceBefore=12, spaceAfter=5),
          "meta": ParagraphStyle("m", parent=base, fontSize=8, leading=10.5, textColor=hx(MUTED)),
          "msg": ParagraphStyle("msg", parent=base, fontSize=9.5, leading=13.5, leftIndent=10, bulletIndent=0, spaceAfter=3),
          "cell": ParagraphStyle("c", parent=base, fontSize=8, leading=10),
          "head": ParagraphStyle("hd", parent=base, fontName="Helvetica-Bold", fontSize=8, leading=10, textColor=colors.white),
          "kpi": ParagraphStyle("k", parent=base, fontName="Helvetica-Bold", fontSize=17, leading=20),
          "kpil": ParagraphStyle("kl", parent=base, fontSize=7.5, leading=9.5, textColor=hx(MUTED))}

    def grid(rows: list[dict], weights: list[float], color_col: str | None = None):
        if not rows:
            return Paragraph("—", base)
        cols = [c for c in rows[0] if not c.startswith("_")]
        data = [[Paragraph(escape(c), st["head"]) for c in cols]] + [[Paragraph(escape(str(r[c])), st["cell"]) for c in cols] for r in rows]
        t = Table(data, colWidths=[width * w / sum(weights) for w in weights], repeatRows=1)
        style = [("BACKGROUND", (0, 0), (-1, 0), hx(INK)), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                 ("LINEBELOW", (0, 1), (-1, -1), 0.4, hx(LINE)), ("TOPPADDING", (0, 0), (-1, -1), 3.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
                 ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4)]
        if color_col:  # a status dot is never the only signal: the text says it too
            ci = cols.index(color_col)
            for i, r in enumerate(rows, start=1):
                style.append(("LINEBEFORE", (ci, i), (ci, i), 3, hx(STATUS_COLOR.get(r.get("_cover"), MUTED))))
        t.setStyle(TableStyle(style))
        return t

    kp = b["kpis"]
    kpis = Table([[[Paragraph(escape(v), st["kpi"]), Paragraph(escape(n), st["kpil"])] for n, v in kp]], colWidths=[width / len(kp)] * len(kp))
    kpis.setStyle(TableStyle([("BOX", (i, 0), (i, 0), 0.6, hx(LINE)) for i in range(len(kp))]
                             + [("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7), ("LEFTPADDING", (0, 0), (-1, -1), 7)]))
    rule = Table([[""]], colWidths=[52], rowHeights=[4])
    rule.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), hx(ORANGE))]))
    rule.hAlign = "LEFT"
    story = [rule, Spacer(1, 8), Paragraph(escape(f"Executive report · Role demand · {practice.name}"), st["h1"]),
             Paragraph(escape(f"Source: {source or '—'} · Generated: {generated} · Counts are roles."), st["meta"]),
             Spacer(1, 10), kpis, Paragraph("Key messages", st["h2"])]
    story += [Paragraph(escape(m), st["msg"], bulletText="•") for m in b["messages"]]
    story += [Paragraph("How much of the demand is ours", st["h2"]), _share(a["scope_roles"], width, a["lang"]),
              Paragraph(escape(f"Top {len(b['skills'])} practice skills: demand, bench and content"), st["h2"]),
              grid(b["skills"], [27, 23, 7, 10, 15, 16], color_col="Content"),
              Paragraph("Content: green = has a course · amber = learning path only · red = no content or not in the catalog. "
                        "People at level 3+ come from the team inventory.", st["meta"]),
              PageBreak(),
              Paragraph("Recommended actions", st["h2"]),
              grid([{"#": n, **r} for n, r in enumerate(b["actions"], start=1)], [3, 34, 32, 18]) if b["actions"]
              else Paragraph("No action needed: every demanded practice skill has a course and the bench covers it.", base)]
    half = width / 2 - 10
    left, right = [], []
    if tr and len(tr.get("points", [])) > 1:
        tk = tr["keys"]
        moves = [r for r in sorted(tr["skills"], key=lambda r: -abs(r["_delta"])) if r["_delta"]][:8]
        story += [KeepTogether([Paragraph(escape(f"Trend · {tr['dates'][0]} → {tr['dates'][-1]}"), st["h2"]), _lines(tr["points"], width, a["lang"], 125)])]
        left = [Paragraph("Biggest moves since the previous upload", st["h2"]),
                _bars([(f"{r[tk['skill']]} ({r['_delta']:+d})", abs(r["_delta"]), r["_scope"]) for r in moves], half) if moves
                else Paragraph("No change.", base)]
    months = a.get("months", [])[-8:]
    if months:
        right = [Paragraph("Roles by start month", st["h2"]), _bars([(_month_label(ym), n, "core") for ym, n in months], half)]
    if left or right:
        pair = Table([[left or "", right or ""]], colWidths=[width / 2, width / 2])
        pair.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 10)]))
        story.append(KeepTogether(pair))
    story += [Spacer(1, 12), Paragraph("Confidential: built from the organization's roles report for the practice leadership. Do not forward "
                                       "outside the practice.", st["meta"])]

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(hx(MUTED))
        canvas.drawString(margin, 9 * mm, f"Academia - Cloud · {practice.name} · Confidential")
        canvas.drawRightString(page[0] - margin, 9 * mm, f"Page {doc.page}")
        canvas.restoreState()

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=page, leftMargin=margin, rightMargin=margin, topMargin=13 * mm, bottomMargin=15 * mm,
                            title=f"Executive report · Role demand · {practice.name}", author="Academia - Cloud")
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()


__all__ = ["brief", "to_pdf", "available", "COLOR", "SCOPE_NAME"]
