"""Demand results for one role family: what the market asks of the family, against the family's own skill tree.

Built for the family's career path lead (champion). From the same analysis the Demand team runs (demand.analyze) and the
learning structure of the practice (academy/paths.py):

* gaps        - the family's gap volume and roles affected (skills catalog), and its skills with a gap (severity, target,
                roles with the gap);
* demand      - each skill the role requests ask for that belongs to the family: roles, as primary skill, and where it
                stands in the family's tree (in a learning path with courses / in the tree without courses / not in the tree);
* tree        - each skill of the family's tree (active learning paths): its path, the courses it has, its gap and how
                many roles of the current demand ask for it (a tree skill nobody asks for is worth a look);
* matrix      - the skills the requests list as gaps or aligned for the family (column «Matrix cross-skills Practice»).
"""

from __future__ import annotations

import io

IN_TREE, NO_COURSES, NOT_IN_TREE, SWITCHED_OFF = "In your tree", "In your tree, no courses yet", "Not in your tree", "In the catalog, switched off"


def _norm(s: str) -> str:
    return " ".join(str(s or "").lower().split())


def tree(structure, catalog, materials: dict, family: str) -> dict[str, dict]:
    """The family's skill tree: {skill id: {skill, path, vendor, courses}} for the active skills of its active learning paths."""
    from academy.family_path import REQUIRED, status_of

    out = {}
    for p in structure.paths_of(family):
        for sk in structure.skills_of(p.id, catalog):
            out[sk.id] = {"skill": sk, "path": p.name, "vendor": structure.vendor_name(p.vendor),
                          "courses": sum(1 for m in materials.get(sk.id, []) if status_of(m) == REQUIRED)}
    return out


def results(a: dict, catalog, structure, materials: dict, family: str) -> dict:
    """The demand results of ``family`` from an analysis ``a`` (demand.analyze)."""
    fam = next(f for f in catalog.families if f.id == family)
    mine = tree(structure, catalog, materials, family)
    by_id = {s.id: s for s in catalog.skills}
    by_name = {_norm(s.name): s for s in catalog.skills if s.family == family}
    asked: dict[str, int] = {}  # catalog skill id -> roles asking for it

    def where(sid: str) -> tuple[str, str, int]:
        if sid in mine:
            t = mine[sid]
            return (IN_TREE if t["courses"] else NO_COURSES), t["path"], t["courses"]
        if sid in by_id and by_id[sid].family == family:
            return SWITCHED_OFF, "—", 0
        return NOT_IN_TREE, "—", 0

    demand_rows = []
    for r in a.get("skills", []):
        e = r.get("_entry")
        if r.get("_scope") == "outside" or e is None:
            continue
        sid = e.skill_id if e.skill_id in by_id else ""
        fam_of = e.family or (by_id[sid].family if sid else "")
        if fam_of != family:
            continue
        status, path, courses = where(sid) if sid else (NOT_IN_TREE, "—", 0)
        roles = r["Roles"]
        if sid:
            asked[sid] = asked.get(sid, 0) + roles
        sk = by_id.get(sid)
        demand_rows.append({"Skill": r["Skill"], "Roles": roles, "As primary skill": r["As primary skill"], "Vendor": e.vendor or "—",
                            "Your skill tree": status, "Learning path": path, "Required courses": courses,
                            "Gap severity": (sk.severity if sk else "") or "—", "Roles with the gap": (sk.impacted_roles if sk else None) or 0,
                            "_status": status})
    tree_rows = []
    for sid, t in mine.items():
        sk = t["skill"]
        tree_rows.append({"Skill": sk.name, "Learning path": t["path"], "Vendor": t["vendor"], "Required courses": t["courses"],
                          "Roles asking for it now": asked.get(sid, 0), "Gap severity": sk.severity or "—", "Target level": sk.target or "—",
                          "Roles with the gap": sk.impacted_roles or 0})
    tree_rows.sort(key=lambda r: (-r["Roles asking for it now"], -r["Roles with the gap"], r["Skill"]))
    gap_rows = [{"Skill": s.name, "Gap severity": s.severity or "—", "Target level": s.target or "—", "Roles with the gap": s.impacted_roles or 0,
                 "Your skill tree": where(s.id)[0]} for s in catalog.in_family(family) if s.impacted_roles or s.severity]
    order = {"High": 0, "Medium": 1, "Low": 2}
    gap_rows.sort(key=lambda r: (order.get(r["Gap severity"], 3), -r["Roles with the gap"], r["Skill"]))
    matrix_rows = []
    for r in a.get("matrix", []):
        if _norm(r["Role family"]) != _norm(fam.name):
            continue
        sk = by_name.get(_norm(r["Skill"]))
        matrix_rows.append({"Skill": r["Skill"], "Roles where it is a gap": r["Roles where it is a gap"],
                            "Roles where it is aligned": r["Roles where it is aligned"],
                            "Your skill tree": where(sk.id)[0] if sk else NOT_IN_TREE})
    roles_asking = max([r["Roles"] for r in demand_rows], default=0)
    summary = {"Gap volume": fam.gap_volume or 0, "Roles affected": fam.role_impact or 0,
               "Demanded skills of the family": len(demand_rows),
               "Covered by your tree": sum(1 for r in demand_rows if r["_status"] == IN_TREE),
               "In your tree without courses": sum(1 for r in demand_rows if r["_status"] in (NO_COURSES, SWITCHED_OFF)),
               "Not in your tree": sum(1 for r in demand_rows if r["_status"] == NOT_IN_TREE),
               "Skills in your tree": len(mine), "Most requested skill (roles)": roles_asking}
    return {"family": fam, "summary": summary, "demand": demand_rows, "tree": tree_rows, "gaps": gap_rows, "matrix": matrix_rows,
            "roles": a.get("rows", 0)}


def visible(rows: list[dict]) -> list[dict]:
    return [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows]


def to_xlsx(res: dict, source: str = "") -> bytes:
    """The family's results as a workbook (summary, demand vs tree, tree, gaps, matrix) to send to its lead."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = "Summary"
    ws.append([f"Demand results · {res['family'].name}"])
    ws["A1"].font = Font(bold=True, size=14)
    if source:
        ws.append([f"Source: {source} · {res['roles']} roles"])
    ws.append([])
    for k, v in res["summary"].items():
        ws.append([k, v])
    ws.column_dimensions["A"].width = 36
    for name, rows in (("Demand vs your tree", res["demand"]), ("Your skill tree", res["tree"]), ("Gaps", res["gaps"]),
                       ("Gaps per role (matrix)", res["matrix"])):
        sh = wb.create_sheet(name[:31])
        rows = visible(rows)
        if not rows:
            sh.append(["Nothing to show."])
            continue
        sh.append(list(rows[0]))
        for c in sh[1]:
            c.font, c.fill = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor="FF5800")
        for r in rows:
            sh.append(list(r.values()))
        for i, col in enumerate(rows[0], start=1):
            sh.column_dimensions[get_column_letter(i)].width = max(12, min(48, len(col) + 4, max(len(str(r[col])) for r in rows) + 2))
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def message(res: dict) -> str:
    """A short text for the lead (the body of the e-mail that goes with the workbook)."""
    s, f = res["summary"], res["family"]
    top = [r["Skill"] for r in res["demand"] if r["_status"] == NOT_IN_TREE][:5]
    bare = [r["Skill"] for r in res["demand"] if r["_status"] in (NO_COURSES, SWITCHED_OFF)][:5]
    lines = [f"Hi {f.champion or 'team'},", "",
             f"These are the demand results of {f.name}: {s['Demanded skills of the family']} skills of the family are requested by the "
             f"roles we receive; your tree covers {s['Covered by your tree']} of them with courses.",
             f"Gap volume {s['Gap volume']} · roles affected {s['Roles affected']}."]
    if top:
        lines.append("Requested and not in your tree: " + ", ".join(top) + ".")
    if bare:
        lines.append("In your tree without courses: " + ", ".join(bare) + ".")
    lines += ["", "Open Academia - Cloud → 🔍 Demand → Demand results for the detail (the workbook is attached)."]
    return "\n".join(lines)
