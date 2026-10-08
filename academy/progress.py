"""Progress per learner and per pack, stored in a local SQLite file: points, ranks and badges.

Scoring (same rules as the original AZP Academy):
* quiz question: 10 points if right on the first try, 5 if right after a miss; only the first correct answer scores;
* glossary quiz: 10 points per correct answer.
A lesson is complete when its 3 questions have been answered correctly at least once.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from academy.pack import Pack

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
        self.conn, self.pack, self.learner = conn, pack, (learner.strip() or "me")

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

    # ------------------------------------------------------------------ reading
    def events(self) -> pd.DataFrame:
        return pd.read_sql_query("SELECT * FROM events WHERE pack=? AND learner=? ORDER BY id", self.conn,
                                 params=(self.pack.id, self.learner))

    def total_points(self) -> int:
        r = self.conn.execute("SELECT COALESCE(SUM(points),0) AS p FROM events WHERE pack=? AND learner=? AND kind<>'vbd'",
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

    def rank(self, points: int | None = None) -> tuple[int, int | None]:
        """(index of the current rank, points still needed for the next one or None at the top)."""
        pts = self.total_points() if points is None else points
        cur = max(i for i, r in enumerate(self.pack.ranks) if pts >= r.points)
        nxt = self.pack.ranks[cur + 1].points - pts if cur + 1 < len(self.pack.ranks) else None
        return cur, nxt

    def badges(self, lang: str = "es") -> list[tuple[str, str, bool]]:
        """(badge, how to earn it, earned?)."""
        ev = self.events()
        done = self.completed_lessons()
        quiz = ev[ev["kind"] == "quiz"]
        first_try = int((quiz["points"] == 10).sum()) if len(quiz) else 0
        gloss = int(((ev["kind"] == "glossary") & (ev["correct"] == 1)).sum()) if len(ev) else 0
        names = ([("First steps", "Complete your first lesson"), ("First try", "10 correct answers on the first attempt"),
                 ("Glossary up to date", "20 correct answers in the glossary quiz"),
                 ("Glossary master", "60 correct answers in the glossary quiz")])
        earned = [len(done) >= 1, first_try >= 10, gloss >= 20, gloss >= 60]
        out = [(n, how, ok) for (n, how), ok in zip(names, earned)]
        for level in self.pack.levels:
            ids = {les.id for les in self.pack.lessons if les.level == level}
            out.append((f"Graduate: {level}", f"Complete every lesson of \"{level}\"", bool(ids) and ids <= done))
        out.append(("Full route",
                    "Complete every lesson",
                    bool(self.pack.lessons) and done >= {les.id for les in self.pack.lessons}))
        return out


def team(conn: sqlite3.Connection, pack: Pack) -> pd.DataFrame:
    """One row per learner of this pack: points, rank, lessons done, last activity — for the team tab / CSV."""
    learners = [r["learner"] for r in conn.execute("SELECT DISTINCT learner FROM events WHERE pack=?", (pack.id,)).fetchall()]
    rows = []
    for name in learners:
        t = Tracker(conn, pack, name)
        pts = t.total_points()
        last = conn.execute("SELECT MAX(time) AS t FROM events WHERE pack=? AND learner=?", (pack.id, name)).fetchone()["t"]
        rows.append({"Person": name, "Points": pts, "Rank": pack.ranks[t.rank(pts)[0]].name,
                     "Lessons": f"{len(t.completed_lessons())}/{len(pack.lessons)}",
                     "Last activity": (last or "")[:10]})
    return pd.DataFrame(rows).sort_values("Points", ascending=False) if rows else pd.DataFrame(
        columns=["Person", "Points", "Rank", "Lessons", "Last activity"])
