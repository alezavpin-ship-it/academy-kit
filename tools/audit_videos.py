"""Audit every YouTube resource of a pack with YouTube's oEmbed service (needs internet).

For each video it reports: OK (title/channel match), CAMBIÓ (exists but YouTube shows another title or channel — update the
pack) or CAÍDO (removed/private — replace it). Run it before publishing a pack and every few months.

    python tools/audit_videos.py packs/cloud-security
    python tools/audit_videos.py packs/cloud-security --fix   # writes the current title/channel and today's date
"""

import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from academy.pack import PACKS_DIR  # noqa: E402
from academy.videos import embed_src, oembed  # noqa: E402


def main(target: str, fix: bool = False) -> int:
    p = Path(target)
    if not p.exists():
        p = PACKS_DIR / target
    if p.is_dir():
        p = p / "pack.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    bad = 0
    for key, r in data["resources"].items():
        if r.get("kind", "video") == "link" or not embed_src(r["url"]):
            continue
        info = oembed(r["url"])
        if info is None:
            print(f"CAÍDO   {key}: {r['url']}")
            bad += 1
            continue
        same = info["title"] == r["title"] and info["channel"] == r["channel"]
        print(f"{'OK     ' if same else 'CAMBIÓ '} {key}: {info['title']} — {info['channel']}")
        if not same:
            bad += 1
        if fix:
            r["title"], r["channel"], r["verified"] = info["title"], info["channel"], date.today().isoformat()
    if fix:
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print("\nPaquete actualizado con los títulos y canales actuales (los CAÍDOS hay que reemplazarlos a mano).")
    print(f"\n{bad} video(s) por revisar." if bad else "\nTodos los videos verificados.")
    return 1 if bad else 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1], "--fix" in sys.argv))
