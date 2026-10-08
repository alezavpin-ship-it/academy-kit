"""Academia - Cloud on Azure App Service (Linux, Python). Startup command of the Web App:

    python deploy/azure/startup.py

App Service runs the app from a temporary copy that is replaced on every deploy and restart. Everything the academy
writes (progress database, content workbook, catalog, people, courses, saved roles files, backups) therefore lives in
/home/academy-data, the persistent storage of the Web App, and the app's folders point there.

* First start: the folders shipped with the code are copied to /home/academy-data.
* Later deploys: only files that do not exist there yet are added (new courses, templates). What the team edited in the
  app is never overwritten. To take a shipped file again, delete it in /home/academy-data and restart.

Written in Python (not a shell script) so it works the same when the repository was saved on Windows (CRLF line ends).
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[2]
FOLDERS = ("data", "config", "catalog", "content", "packs", "exams", "export")


def link_folders(app_dir: Path, data_dir: Path) -> list[str]:
    """Point the app's writable folders at the persistent storage. Returns the files added to the storage this time."""
    added = []
    data_dir.mkdir(parents=True, exist_ok=True)
    for name in FOLDERS:
        here, kept = app_dir / name, data_dir / name
        if here.is_symlink():
            continue  # already linked (a restart without a new deploy)
        kept.mkdir(parents=True, exist_ok=True)
        if here.is_dir():
            for src in here.rglob("*"):
                dest = kept / src.relative_to(here)
                if src.is_file() and not dest.exists():  # only new files: never overwrite what the team changed
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dest)
                    added.append(str(dest.relative_to(data_dir)))
            shutil.rmtree(here)
        elif here.exists():
            here.unlink()
        here.symlink_to(kept, target_is_directory=True)
    return added


def main() -> None:
    data_dir = Path(os.environ.get("ACADEMY_DATA", "/home/academy-data"))
    added = link_folders(APP_DIR, data_dir)
    print(f"Academia - Cloud: data folder {data_dir} ({len(added)} new file(s) from this deploy)", flush=True)
    os.chdir(APP_DIR)
    port = os.environ.get("PORT") or os.environ.get("WEBSITES_PORT") or "8000"
    # config.toml keeps a laptop safe (127.0.0.1 only); on App Service the app listens on the port the platform gives it.
    args = [sys.executable, "-m", "streamlit", "run", str(APP_DIR / "app.py"), "--server.address", "0.0.0.0", "--server.port", port,
            "--server.headless", "true", "--browser.gatherUsageStats", "false"]
    os.execv(sys.executable, args)


if __name__ == "__main__":
    main()
