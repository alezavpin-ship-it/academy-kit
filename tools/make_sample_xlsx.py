"""Write catalog/ejemplo_upskilling_plan.xlsx: a workbook with FICTITIOUS roles in the layout the importer expects.

    python tools/make_sample_xlsx.py

Use it to try «Mapa de skills → Importar de Excel» without touching the real (confidential) report.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from openpyxl import Workbook  # noqa: E402

from academy.catalog import CATALOG_PATH, load_catalog  # noqa: E402

HEADERS = ["Skill Family", "Unaligned / Missing Skill", "Gap Severity / Priority Band", "Impacted Roles", "Required Target Proficiency",
           "Target Champion / Action Owner"]


def build(path: Path) -> Path:
    cat = load_catalog(CATALOG_PATH)
    names = {f.id: f.name for f in cat.families}
    wb = Workbook()
    other = wb.active
    other.title = "Sheet4 editable"
    other.append(["Esta pestaña no se lee: el importador solo abre la que elijas."])
    ws = wb.create_sheet("Upskilling Plan")
    ws["A1"] = "Cloud Security Upskilling & Gap Remediation Requirement"
    ws["A4"], ws["A5"] = "Remediation Urgency", "High"
    ws["A13"] = "Mandatory Gap Remediation Backlog"
    for j, h in enumerate(HEADERS, start=1):
        ws.cell(row=15, column=j, value=h)
    for i, s in enumerate(cat.skills):
        roles = "; ".join(f"Rol de ejemplo {k + 1}" for k in range(2 + i % 4))
        fam = names[s.family]
        row = [fam, s.name, ["High", "Medium", "Low"][i % 3], roles, ["P3 - Advanced", "P2 - Intermediate"][i % 2], f"{fam} Champion"]
        for j, v in enumerate(row, start=1):
            ws.cell(row=16 + i, column=j, value=v)
    for j, h in enumerate(["Skill Family", "Gap Volume", "Role Impact Count"]):  # summary table to the right, like the report
        ws.cell(row=1, column=24 + j, value=h)
    for i, f in enumerate(x for x in cat.by_gap() if x.gap_volume is not None):
        for j, v in enumerate([f.name, f.gap_volume, f.role_impact]):
            ws.cell(row=2 + i, column=24 + j, value=v)
    wb.save(path)
    return path


if __name__ == "__main__":
    print(build(CATALOG_PATH.parent / "ejemplo_upskilling_plan.xlsx"))
