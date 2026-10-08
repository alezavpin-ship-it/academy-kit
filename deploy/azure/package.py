"""Build the zip that is deployed to Azure App Service: the code and the starting content, never local or confidential data.

    python deploy/azure/package.py            ->  dist/academy-cloud.zip

Left out: the progress database and backups (data/), config/ (owners, PIN, assistant keys), roles files and their history
(confidential demand data), exports, tests, virtual environments and Windows launchers. On Azure those live in
/home/academy-data (see startup.py) and are managed from the app.
"""

from __future__ import annotations

import fnmatch
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "dist" / "academy-cloud.zip"
EXCLUDE_DIRS = {".git", ".github", ".venv", "venv", "__pycache__", ".pytest_cache", "dist", "tests", "data", "config", "export",
                ".docs_tmp", "demand_history", "content_backups"}
EXCLUDE_FILES = ["*.pyc", "*.bat", "*.db", "*.db-journal", "*.log", "content/demand_roles.csv", "content/* (old).*", "test123.txt",
                 "data/*", "~$*"]


def included(rel: Path) -> bool:
    if any(part in EXCLUDE_DIRS for part in rel.parts[:-1]) or rel.name in EXCLUDE_DIRS:
        return False
    text = rel.as_posix()
    return not any(fnmatch.fnmatch(text, p) or fnmatch.fnmatch(rel.name, p) for p in EXCLUDE_FILES)


def build(out: Path = OUT) -> list[str]:
    out.parent.mkdir(parents=True, exist_ok=True)
    names = []
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(ROOT.rglob("*")):
            rel = p.relative_to(ROOT)
            if p.is_file() and included(rel):
                z.write(p, rel.as_posix())
                names.append(rel.as_posix())
    return names


if __name__ == "__main__":
    files = build(Path(sys.argv[1]) if len(sys.argv) > 1 else OUT)
    print(f"{len(files)} files -> {OUT if len(sys.argv) < 2 else sys.argv[1]}")
