"""Progress per learner and per pack, stored in a local SQLite file: points, ranks, badges, VBD checklists.

Scoring (same rules as the original AZP Academy):
* quiz question: 10 points if right on the first try, 5 if right after a miss; only the first correct answer scores;
* glossary quiz: 10 points per correct answer;
* value-based deliverable (VBD): 25 points the first time every "done when" criterion is ticked and it is marked done.
A lesson is complete when its 3 questions have been answered correctly at least once.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from academy.pack import Pack

VBD_POINTS = 25

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    time TEXT NOT NULL,
    pack TEXT NOT NULL,
    learner TEXT NOT NULL,
    kind TEXT NOT NULL,
    item TEXT NOT NULL DEFAULT '',
    points INTEGER NOT NULL DEFAULT 0,
    correct INTEGER NOT NULL DEFAULT 0,
    detail TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS ix_events ON events(pack, learner, kind, item);
CREATE TABLE IF NOT EXISTS vbd_checks (
    pack TEXT NOT NULL, learner TEXT NOT NULL, lesson TEXT NOT NULL, idx INTEGER NOT NULL, checked INTEGER NOT NULL,
    PRIMARY KEY (pack, learner, lesson, idx)
);
CREATE TABLE IF NOT EXISTS people (learner TEXT PRIMARY KEY, email TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS notices (
    learner TEXT NOT NULL, kind TEXT NOT NULL, ref TEXT NOT NULL, sent TEXT NOT NULL, PRIMARY KEY (learner, kind, ref)
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path: str | Path) -> sqlite3.Connection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


class Tracker:
    """All progress queries for one learner in one pack."""

    def __init__(self, conn: sqlite3.Connection, pack: Pack, learner: str):
        self.conn, self.pack, self.learner = conn, pack, (learner.strip() or "yo")

    # ------------------------------------------------------------------ writing
    def record(self, kind: str, item: str = "", points: int = 0, correct: bool = False, detail: str = "") -> None:
        with self.conn:
            self.conn.execute("INSERT INTO events(time, pack, learner, kind, item, points, correct, detail) VALUES (?,?,?,?,?,?,?,?)",
                              (_now(), self.pack.id, self.learner, kind, item, int(points), int(bool(correct)), detail))

    def answer_quiz(self, item: str, correct: bool) -> int:
        rows = self.conn.execute("SELECT correct FROM events WHERE pack=? AND learner=? AND kind='quiz' AND item=?",
                                 (self.pack.id, self.learner, item)).fetchall()
        already = any(r["correct"] for r in rows)
        pts = 0 if (already or not correct) else (10 if not rows else 5)
        self.record("quiz", item, pts, correct)
        return pts

    def set_check(self, lesson: str, idx: int, checked: bool) -> None:
        with self.conn:
            self.conn.execute("INSERT OR REPLACE INTO vbd_checks(pack, learner, lesson, idx, checked) VALUES (?,?,?,?,?)",
                              (self.pack.id, self.learner, lesson, idx, int(bool(checked))))

    def complete_vbd(self, lesson: str, evidence: str = "") -> int:
        """Mark a VBD done (all criteria must be ticked). Returns the points earned (0 if already done or not ready)."""
        les = self.pack.lesson(lesson)
        if les.vbd is None or not all(self.checks(lesson).get(i) for i in range(len(les.vbd.done_when))):
            return 0
        pts = 0 if lesson in self.vbds_done() else VBD_POINTS
        self.record("vbd", lesson, pts, True, evidence.strip())
        return pts

    # ------------------------------------------------------------------ reading
    def events(self) -> pd.DataFrame:
        return pd.read_sql_query("SELECT * FROM events WHERE pack=? AND learner=? ORDER BY id", self.conn,
                                 params=(self.pack.id, self.learner))

    def checks(self, lesson: str) -> dict[int, bool]:
        rows = self.conn.execute("SELECT idx, checked FROM vbd_checks WHERE pack=? AND learner=? AND lesson=?",
                                 (self.pack.id, self.learner, lesson)).fetchall()
        return {r["idx"]: bool(r["checked"]) for r in rows}

    def total_points(self) -> int:
        r = self.conn.execute("SELECT COALESCE(SUM(points),0) AS p FROM events WHERE pack=? AND learner=?",
                              (self.pack.id, self.learner)).fetchone()
        return int(r["p"])

    def correct_items(self, lesson: str | None = None) -> set[str]:
        """Check questions answered right at least once ("<lesson>:<n>"); only one lesson's when ``lesson`` is given."""
        ok = {r["item"] for r in self.conn.execute(
            "SELECT DISTINCT item FROM events WHERE pack=? AND learner=? AND kind='quiz' AND correct=1",
            (self.pack.id, self.learner)).fetchall()}
        return ok if lesson is None else {i for i in ok if i.rsplit(":", 1)[0] == lesson}

    def completed_lessons(self) -> set[str]:
        ok = self.correct_items()
        return {les.id for les in self.pack.lessons if all(f"{les.id}:{k}" in ok for k in range(len(les.quiz)))}

    def vbds_done(self) -> set[str]:
        return {r["item"] for r in self.conn.execute(
            "SELECT DISTINCT item FROM events WHERE pack=? AND learner=? AND kind='vbd'", (self.pack.id, self.learner)).fetchall()}

    def rank(self, points: int | None = None) -> tuple[int, int | None]:
        """(index of the current rank, points still needed for the next one or None at the top)."""
        pts = self.total_points() if points is None else points
        cur = max(i for i, r in enumerate(self.pack.ranks) if pts >= r.points)
        nxt = self.pack.ranks[cur + 1].points - pts if cur + 1 < len(self.pack.ranks) else None
        return cur, nxt

    def badges(self) -> list[tuple[str, str, bool]]:
        """(badge, how to earn it, earned?)."""
        ev = self.events()
        done, vbds = self.completed_lessons(), self.vbds_done()
        quiz = ev[ev["kind"] == "quiz"]
        first_try = int((quiz["points"] == 10).sum()) if len(quiz) else 0
        gloss = int(((ev["kind"] == "glossary") & (ev["correct"] == 1)).sum()) if len(ev) else 0
        out = [
            ("Primeros pasos", "Completa tu primera lección", len(done) >= 1),
            ("A la primera", "10 respuestas correctas al primer intento", first_try >= 10),
            ("Glosario al día", "20 respuestas correctas en el quiz del glosario", gloss >= 20),
            ("Generador de valor", "Entrega tu primer VBD", len(vbds) >= 1),
            ("Máquina de valor", "Entrega 5 VBDs", len(vbds) >= 5),
        ]
        for level in self.pack.levels:
            ids = {les.id for les in self.pack.lessons if les.level == level}
            out.append((f"Graduado: {level}", f"Completa todas las lecciones de «{level}»", bool(ids) and ids <= done))
        out.append(("Ruta completa", "Completa todas las lecciones y sus VBDs",
                    done >= {les.id for les in self.pack.lessons} and vbds >= {les.id for les in self.pack.lessons if les.vbd}))
        return out


def team(conn: sqlite3.Connection, pack: Pack) -> pd.DataFrame:
    """One row per learner of this pack: points, rank, lessons and VBDs done, last activity — for the team tab / CSV."""
    learners = [r["learner"] for r in conn.execute("SELECT DISTINCT learner FROM events WHERE pack=?", (pack.id,)).fetchall()]
    rows = []
    for name in learners:
        t = Tracker(conn, pack, name)
        pts = t.total_points()
        last = conn.execute("SELECT MAX(time) AS t FROM events WHERE pack=? AND learner=?", (pack.id, name)).fetchone()["t"]
        rows.append({"Persona": name, "Puntos": pts, "Rango": pack.ranks[t.rank(pts)[0]].name,
                     "Lecciones": f"{len(t.completed_lessons())}/{len(pack.lessons)}",
                     "VBDs": f"{len(t.vbds_done())}/{sum(1 for les in pack.lessons if les.vbd)}",
                     "Última actividad": (last or "")[:10]})
    return pd.DataFrame(rows).sort_values("Puntos", ascending=False) if rows else pd.DataFrame(
        columns=["Persona", "Puntos", "Rango", "Lecciones", "VBDs", "Última actividad"])
