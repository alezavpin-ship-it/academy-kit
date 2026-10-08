"""Academia - Cloud on Azure App Service (Linux, Python). Startup command of the Web App:

    python deploy/azure/startup.py

App Service runs the app from a temporary copy that is replaced on every deploy and restart. Everything the academy
writes (progress database, content workbook, catalog, people, courses, saved roles files, backups) therefore lives in
/home/academy-data, the persistent storage of the Web App, and the app's folders point there.

* First start: the folders shipped with the code are copied to /home/academy-data.
* Later deploys: only files that do not exist there yet are added (new courses, templates). What the team edited in the
  app is never overwritten. To take a shipped file again, delete it in /home/academy-data and restart.
* ACADEMY_OWNERS (optional app setting): the app's owners, set from the Azure portal without editing files, for example
  "a.person@company.com; Perla Marmolejo <perla.m@company.com>" (up to 3). On every start they become the owners in
  /home/academy-data/catalog/people.csv; anyone else listed as owner there steps down to learner (or champion).

Written in Python (not a shell script) so it works the same when the repository was saved on Windows (CRLF line ends).
"""

from __future__ import annotations

import os
import re
import shutil
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[2]
FOLDERS = ("data", "config", "catalog", "content", "packs", "exams", "export", "practices")


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


def apply_owners(app_dir: Path, data_dir: Path, spec: str) -> str:
    """Make the people of ``spec`` (e-mails, optionally «Name <e-mail>», separated by ; , or new lines) the app's owners."""
    if str(app_dir) not in sys.path:
        sys.path.insert(0, str(app_dir))
    from academy import people

    path = data_dir / "catalog" / "people.csv"
    directory = people.load(path)
    wanted = []
    for item in re.split(r"[;,\n]+", spec or ""):
        m = re.match(r"^\s*(.*?)\s*<\s*([^>]+?)\s*>\s*$", item)
        name, email = (m.group(1), m.group(2)) if m else ("", item.strip())
        if "@" not in email:
            continue
        known = people.find(directory, "", email)
        wanted.append((name or (known.name if known else email.split("@")[0].replace(".", " ").title()), email))
    if not wanted:
        return "ACADEMY_OWNERS has no e-mail address: owners unchanged."
    new, problems = people.set_owners(directory, wanted)
    if problems:
        return "ACADEMY_OWNERS ignored: " + " ".join(problems)
    people.save(new, path)
    return "Owners from ACADEMY_OWNERS: " + ", ".join(e for _, e in wanted)


def main() -> None:
    data_dir = Path(os.environ.get("ACADEMY_DATA", "/home/academy-data"))
    added = link_folders(APP_DIR, data_dir)
    print(f"Academia - Cloud: data folder {data_dir} ({len(added)} new file(s) from this deploy)", flush=True)
    if os.environ.get("ACADEMY_OWNERS", "").strip():
        try:
            print("Academia - Cloud: " + apply_owners(APP_DIR, data_dir, os.environ["ACADEMY_OWNERS"]), flush=True)
        except Exception as e:  # never keep the app from starting
            print(f"Academia - Cloud: ACADEMY_OWNERS not applied ({e})", flush=True)
    os.chdir(APP_DIR)
    port = os.environ.get("PORT") or os.environ.get("WEBSITES_PORT") or "8000"
    # config.toml keeps a laptop safe (127.0.0.1 only); on App Service the app listens on the port the platform gives it.
    args = [sys.executable, "-m", "streamlit", "run", str(APP_DIR / "app.py"), "--server.address", "0.0.0.0", "--server.port", port,
            "--server.headless", "true", "--browser.gatherUsageStats", "false"]
    os.execv(sys.executable, args)


if __name__ == "__main__":
    main()
