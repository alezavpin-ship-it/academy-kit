"""The academy content as one file.

    python tools/content.py export                      -> content/academia_contenido.csv (the file the app reads)
    python tools/content.py export contenido.xlsx       -> the same content as an Excel workbook, one sheet per table
    python tools/content.py check  archivo.csv|xlsx     -> lists the problems, changes nothing
    python tools/content.py import archivo.csv|xlsx     -> checks it and, if it is right, replaces the app's content (with a backup)
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from academy import content_sync, content_xlsx as content  # noqa: E402


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in ("export", "check", "import") or (argv[0] != "export" and len(argv) < 2):
        print(__doc__)
        return 2
    if argv[0] == "export":
        if len(argv) == 1:
            print(content_sync.refresh())
            return 0
        out = Path(argv[1])
        out.write_bytes(content.export_bytes() if out.suffix.lower() == ".xlsx" else content.csv_bytes(content.export_csv()))
        print(f"OK -> {out}")
        return 0
    result = content.read(Path(argv[1]))
    for row in result["summary"]:
        print(row)
    print(f"Skill families: {result.get('families', 0)} · skills: {result.get('skills', 0)} · learning paths: {result.get('learning_paths', 0)}")
    if result["problems"]:
        print(f"\n{len(result['problems'])} problem(s); nothing was saved:")
        for e in result["problems"]:
            print(" -", e)
        return 1
    if argv[0] == "import":
        for f in content.apply(result):
            print("saved", f)
        print(content_sync.refresh())
    else:
        print("OK: no problems")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
