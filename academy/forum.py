"""Discussion forum: learners ask, the subject-matter experts (SMEs) of the skill family answer.

* Every question belongs to a skill family (and optionally to one of its skills).
* Anyone can reply. A reply from an SME, the family's champion or an owner carries that badge, and the question counts
  as answered once it has one of those (or once an answer is marked as accepted).
* The forum is run by owners (every family) and by each champion (their own families): they name the SMEs of the
  family, mark the accepted answer, pin, close or reopen a question and hide what does not belong.
* Hidden posts are kept in the database (never deleted), so a moderation decision can be reviewed or undone.

Pure logic over the same SQLite file as the progress; the screen lives in academy/forum_page.py.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS forum_questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT, time TEXT NOT NULL, author TEXT NOT NULL, family TEXT NOT NULL,
    skill TEXT NOT NULL DEFAULT '', title TEXT NOT NULL, body TEXT NOT NULL DEFAULT '',
    closed INTEGER NOT NULL DEFAULT 0, pinned INTEGER NOT NULL DEFAULT 0, hidden INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS forum_answers (
    id INTEGER PRIMARY KEY AUTOINCREMENT, question INTEGER NOT NULL, time TEXT NOT NULL, author TEXT NOT NULL,
    body TEXT NOT NULL, role TEXT NOT NULL DEFAULT '', accepted INTEGER NOT NULL DEFAULT 0, hidden INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_forum_answers ON forum_answers(question);
CREATE TABLE IF NOT EXISTS forum_smes (family TEXT NOT NULL, person TEXT NOT NULL, PRIMARY KEY (family, person));
"""
OWNER, CHAMPION, SME = "owner", "champion", "sme"  # the role an answer was written with ('' = a fellow learner)
MAX_TITLE, MAX_BODY = 160, 4000


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _norm(s: str) -> str:
    return (s or "").strip().lower()


@dataclass
class Answer:
    id: int
    question: int
    time: str
    author: str
    body: str
    role: str = ""
    accepted: bool = False
    hidden: bool = False


@dataclass
class Question:
    id: int
    time: str
    author: str
    family: str
    skill: str
    title: str
    body: str
    closed: bool = False
    pinned: bool = False
    hidden: bool = False
    answers: list[Answer] = field(default_factory=list)

    def visible_answers(self) -> list[Answer]:
        return [a for a in self.answers if not a.hidden]

    @property
    def answered(self) -> bool:
        """It has an accepted answer, or one written by an SME, the champion or an owner."""
        return any(a.accepted or a.role for a in self.visible_answers())

    @property
    def last_activity(self) -> str:
        return max([self.time] + [a.time for a in self.visible_answers()])


class Forum:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        conn.executescript(SCHEMA)

    # ------------------------------------------------------------------ who is who
    def smes(self, family: str | None = None) -> dict[str, list[str]]:
        """family id -> the people named as its subject-matter experts (names or e-mails, as typed in the sidebar)."""
        out: dict[str, list[str]] = {}
        for r in self.conn.execute("SELECT family, person FROM forum_smes ORDER BY family, person"):
            if family is None or r["family"] == family:
                out.setdefault(r["family"], []).append(r["person"])
        return out

    def set_smes(self, family: str, people: list[str]) -> None:
        clean = list(dict.fromkeys(p.strip() for p in people if p and p.strip()))
        with self.conn:
            self.conn.execute("DELETE FROM forum_smes WHERE family=?", (family,))
            self.conn.executemany("INSERT INTO forum_smes(family, person) VALUES (?,?)", [(family, p) for p in clean])

    def sme_families(self, learner: str, email: str = "") -> set[str]:
        me = {_norm(learner), _norm(email)} - {""}
        return {fam for fam, people in self.smes().items() if me & {_norm(p) for p in people}}

    def role_in(self, family: str, learner: str, email: str = "", owner: bool = False, champion_of: set[str] | None = None) -> str:
        """The badge this person answers with in a family: owner, champion, sme or '' (a fellow learner)."""
        if owner:
            return OWNER
        if family in (champion_of or set()):
            return CHAMPION
        return SME if family in self.sme_families(learner, email) else ""

    # ------------------------------------------------------------------ writing
    def ask(self, author: str, family: str, title: str, body: str = "", skill: str = "") -> int:
        title, body = " ".join(title.split())[:MAX_TITLE], body.strip()[:MAX_BODY]
        if not title or not family or not author.strip():
            raise ValueError("A question needs an author, a skill family and a title.")
        with self.conn:
            cur = self.conn.execute("INSERT INTO forum_questions(time, author, family, skill, title, body) VALUES (?,?,?,?,?,?)",
                                    (_now(), author.strip(), family, skill, title, body))
        return int(cur.lastrowid)

    def answer(self, question: int, author: str, body: str, role: str = "") -> int:
        body = body.strip()[:MAX_BODY]
        q = self.get(question)
        if not body or not author.strip() or q is None or q.closed or q.hidden:
            raise ValueError("The answer is empty or the question is closed.")
        with self.conn:
            cur = self.conn.execute("INSERT INTO forum_answers(question, time, author, body, role) VALUES (?,?,?,?,?)",
                                    (question, _now(), author.strip(), body, role))
        return int(cur.lastrowid)

    def accept(self, answer: int, accepted: bool = True) -> None:
        """Mark the answer that solved the question (one per question)."""
        row = self.conn.execute("SELECT question FROM forum_answers WHERE id=?", (answer,)).fetchone()
        if row is None:
            return
        with self.conn:
            self.conn.execute("UPDATE forum_answers SET accepted=0 WHERE question=?", (row["question"],))
            if accepted:
                self.conn.execute("UPDATE forum_answers SET accepted=1 WHERE id=?", (answer,))

    def _flag(self, table: str, column: str, row_id: int, value: bool) -> None:
        with self.conn:
            self.conn.execute(f"UPDATE {table} SET {column}=? WHERE id=?", (int(value), row_id))  # noqa: S608 - fixed names below

    def close(self, question: int, closed: bool = True) -> None:
        self._flag("forum_questions", "closed", question, closed)

    def pin(self, question: int, pinned: bool = True) -> None:
        self._flag("forum_questions", "pinned", question, pinned)

    def hide_question(self, question: int, hidden: bool = True) -> None:
        self._flag("forum_questions", "hidden", question, hidden)

    def hide_answer(self, answer: int, hidden: bool = True) -> None:
        self._flag("forum_answers", "hidden", answer, hidden)

    # ------------------------------------------------------------------ reading
    def _question(self, r, answers: dict[int, list[Answer]]) -> Question:
        return Question(r["id"], r["time"], r["author"], r["family"], r["skill"], r["title"], r["body"], bool(r["closed"]), bool(r["pinned"]),
                        bool(r["hidden"]), answers.get(r["id"], []))

    def _answers(self) -> dict[int, list[Answer]]:
        out: dict[int, list[Answer]] = {}
        for a in self.conn.execute("SELECT * FROM forum_answers ORDER BY accepted DESC, id"):
            out.setdefault(a["question"], []).append(Answer(a["id"], a["question"], a["time"], a["author"], a["body"], a["role"],
                                                            bool(a["accepted"]), bool(a["hidden"])))
        return out

    def get(self, question: int) -> Question | None:
        r = self.conn.execute("SELECT * FROM forum_questions WHERE id=?", (question,)).fetchone()
        return self._question(r, self._answers()) if r else None

    def questions(self, families: set[str] | None = None, include_hidden: bool = False) -> list[Question]:
        """Pinned first, then the ones with the most recent activity. ``families``: only these (None = all)."""
        answers = self._answers()
        out = [self._question(r, answers) for r in self.conn.execute("SELECT * FROM forum_questions")]
        out = [q for q in out if (include_hidden or not q.hidden) and (families is None or q.family in families)]
        out.sort(key=lambda q: q.last_activity, reverse=True)
        out.sort(key=lambda q: not q.pinned)
        return out

    def waiting(self, families: set[str] | None = None) -> list[Question]:
        """Open questions still without an answer from an SME, the champion or an owner."""
        return [q for q in self.questions(families) if not q.answered and not q.closed]

    def counts(self) -> dict[str, dict[str, int]]:
        """family id -> {"questions", "waiting"}: what the status report shows per family."""
        out: dict[str, dict[str, int]] = {}
        for q in self.questions():
            c = out.setdefault(q.family, {"questions": 0, "waiting": 0})
            c["questions"] += 1
            c["waiting"] += not q.answered and not q.closed
        return out

    def rows(self, families: set[str] | None = None) -> list[dict]:
        """Flat export (one row per question or answer) for a CSV."""
        out = []
        for q in self.questions(families, include_hidden=True):
            out.append({"QuestionId": q.id, "Type": "question", "Time": q.time, "Author": q.author, "Family": q.family, "Skill": q.skill,
                        "Title": q.title, "Text": q.body, "Role": "", "Accepted": "", "Closed": int(q.closed), "Hidden": int(q.hidden)})
            for a in q.answers:
                out.append({"QuestionId": q.id, "Type": "answer", "Time": a.time, "Author": a.author, "Family": q.family, "Skill": q.skill,
                            "Title": q.title, "Text": a.body, "Role": a.role, "Accepted": int(a.accepted), "Closed": "", "Hidden": int(a.hidden)})
        return out
