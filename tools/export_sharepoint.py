"""Export the content (pack + skills catalog) as CSV files ready to load into SharePoint lists for the Power Apps version.

    python tools/export_sharepoint.py packs/cloud-security          -> export/sharepoint/*.csv

One CSV per list; the columns match INTEGRACION_POWERAPPS.md. Files are UTF-8 with BOM so Excel opens accents correctly.
"""

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from academy.catalog import load_catalog  # noqa: E402
from academy.pack import load_pack  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def tables(pack, catalog) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    if catalog:
        out["Familias"] = [{"Title": f.name, "FamilyId": f.id, "GapVolume": f.gap_volume, "RoleImpact": f.role_impact, "Champion": f.champion,
                            "ChampionEmail": f.champion_email}
                           for f in catalog.by_gap()]
        out["Skills"] = [{"Title": s.name, "SkillId": s.id, "FamilyId": s.family, "Severity": s.severity, "TargetLevel": s.target,
                          "ImpactedRoles": s.impacted_roles} for s in catalog.skills]
    out["Lecciones"] = [{
        "Title": les.title, "LessonId": les.id, "PackId": pack.id, "Level": les.level, "SortOrder": i + 1, "Summary": les.summary,
        "KeyPoints": "\n".join(les.points), "PracticeLabel": les.practice.get("label", ""), "PracticeUrl": les.practice.get("url", ""),
        "CatalogSkills": ";".join(les.catalog_skills),
        "VbdDeliverable": les.vbd.deliverable if les.vbd else "", "VbdDoneWhen": "\n".join(les.vbd.done_when) if les.vbd else "",
        "VbdValue": les.vbd.value if les.vbd else "", "VbdWhereLabel": (les.vbd.where or {}).get("label", "") if les.vbd else "",
        "VbdWhereUrl": (les.vbd.where or {}).get("url", "") if les.vbd else ""} for i, les in enumerate(pack.lessons)]
    out["Preguntas"] = [{"Title": q.q, "QuestionId": f"{les.id}:{k}", "LessonId": les.id, "SortOrder": k + 1, "OptionA": q.options[0],
                         "OptionB": q.options[1], "OptionC": q.options[2], "OptionD": q.options[3], "AnswerLetter": "ABCD"[q.answer], "Why": q.why}
                        for les in pack.lessons for k, q in enumerate(les.quiz)]
    out["Recursos"] = [{"Title": r.title, "ResourceKey": r.key, "Url": r.url, "Channel": r.channel, "Lang": r.lang,
                        "Topic": pack.topics.get(r.topic, r.topic), "Why": r.why, "Kind": r.kind, "Level": r.level} for r in pack.resources.values()]
    out["LeccionRecursos"] = [{"Title": f"{les.id}:{key}", "LessonId": les.id, "ResourceKey": key, "SortOrder": i + 1,
                               "Note": les.resource_notes.get(key, "")} for les in pack.lessons for i, key in enumerate(les.resources)]
    out["Glosario"] = [{"Title": g["term"], "Category": g.get("category", ""), "Definition": g["definition"]} for g in pack.glossary]
    out["Rangos"] = [{"Title": r.name, "Points": r.points, "Emoji": r.emoji, "Color": r.color} for r in pack.ranks]
    return out


def export(pack_path, out_dir: Path | None = None, catalog=None) -> list[Path]:
    pack = load_pack(pack_path)
    out_dir = out_dir or ROOT / "export" / "sharepoint"
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for name, rows in tables(pack, catalog if catalog is not None else load_catalog()).items():
        path = out_dir / f"{name}.csv"
        with path.open("w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]) if rows else ["Title"])
            w.writeheader()
            w.writerows(rows)
        written.append(path)
    return written


if __name__ == "__main__":
    for p in export(sys.argv[1] if len(sys.argv) > 1 else "cloud-security"):
        print(p)
