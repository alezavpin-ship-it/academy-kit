"""Content packs: one JSON file per subject (Cloud Security, IT, onboarding…). The engine never hard-codes content.

A pack holds: meta (title, language, ranks), levels, optional roles, lessons (points, practice, 3-question quiz,
videos), glossary, topics and the resource catalog. ``load_pack`` parses it into dataclasses
and ``validate`` returns the list of problems (empty = valid). The full format is documented in FORMATO_PACK.md.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

from academy.videos import embed_src


def packs_dir() -> Path:
    """packs/ of the practice in use (ACADEMY_PACKS names another folder)."""
    import os

    from academy import workspace

    return Path(os.environ.get("ACADEMY_PACKS") or workspace.root() / "packs")

PACKS_DIR = Path(__file__).resolve().parents[1] / "packs"


@dataclass(frozen=True)
class Rank:
    name: str
    points: int
    emoji: str = "⭐"
    color: str = "#FF5800"
    image: str = ""  # optional file in the pack's assets/ folder (png/webp/jpg)


@dataclass(frozen=True)
class Question:
    q: str
    options: list[str]
    answer: int  # index of the correct option
    why: str  # explanation shown after a correct answer


@dataclass(frozen=True)
class Lesson:
    id: str
    level: str
    title: str
    summary: str
    points: list[str]
    quiz: list[Question]
    practice: dict = field(default_factory=dict)  # {"label": ..., "url": ...}
    skills: list[str] = field(default_factory=list)
    resources: list[str] = field(default_factory=list)  # keys of Pack.resources, most relevant first
    resource_notes: dict = field(default_factory=dict)  # key -> why this resource matters for THIS lesson
    catalog_skills: list[str] = field(default_factory=list)  # ids from catalog/skills.json that this lesson builds


@dataclass(frozen=True)
class Resource:
    key: str
    title: str  # the title the platform shows (verified)
    url: str
    channel: str  # who publishes it
    lang: str  # "es" | "en" | ...
    topic: str
    why: str  # what it explains, in one line
    kind: str = "video"  # "video" | "playlist" | "link"
    level: str = "basic"
    who: str = ""  # the expert speaking, when it's not the channel owner
    verified: str = ""  # date of the last oEmbed check (YYYY-MM-DD)


@dataclass
class Pack:
    id: str
    title: str
    subtitle: str
    language: str
    version: str
    disclaimer: str
    ranks: list[Rank]
    levels: list[str]
    lessons: list[Lesson]
    glossary: list[dict]
    topics: dict[str, str]
    resources: dict[str, Resource]
    roles: dict[str, list[str]] = field(default_factory=dict)
    folder: Path | None = None

    def lesson(self, lesson_id: str) -> Lesson:
        for les in self.lessons:
            if les.id == lesson_id:
                return les
        raise KeyError(lesson_id)

    def by_level(self) -> dict[str, list[Lesson]]:
        out: dict[str, list[Lesson]] = {lv: [] for lv in self.levels}
        for les in self.lessons:
            out.setdefault(les.level, []).append(les)
        return out

    def for_lesson(self, lesson_id: str) -> list[tuple[Resource, str]]:
        """(resource, why-for-this-lesson) pairs in display order."""
        les = self.lesson(lesson_id)
        return [(self.resources[k], les.resource_notes.get(k) or self.resources[k].why) for k in les.resources if k in self.resources]

    def by_topic(self, topic: str) -> list[Resource]:
        return [r for r in self.resources.values() if r.topic == topic]

    def lessons_for_role(self, role: str) -> set[str]:
        skills = set(self.roles.get(role, []))
        return {les.id for les in self.lessons if skills & set(les.skills)}

    def lessons_in_scope(self, role: str | None = None) -> list[Lesson]:
        """The lessons a learner of ``role`` has to take, in pack order (every lesson without a role, or for a role with none)."""
        ids = self.lessons_for_role(role) if role else set()
        return [les for les in self.lessons if les.id in ids] if ids else list(self.lessons)

    def asset(self, name: str) -> Path | None:
        if not name or self.folder is None:
            return None
        p = self.folder / "assets" / name
        return p if p.exists() else None


def _parse(data: dict, folder: Path | None = None) -> Pack:
    meta = data["meta"]
    lessons = []
    for x in data["lessons"]:
        quiz = [Question(q["q"], list(q["options"]), int(q["answer"]), q["why"]) for q in x["quiz"]]
        lessons.append(Lesson(x["id"], x["level"], x["title"], x["summary"], list(x["points"]), quiz,
                              x.get("practice", {}), list(x.get("skills", [])), list(x.get("resources", [])),
                              dict(x.get("resource_notes", {})), list(x.get("catalog_skills", []))))
    resources = {k: Resource(k, r["title"], r["url"], r["channel"], r.get("lang", meta.get("language", "en")),
                             r.get("topic", ""), r.get("why", ""), r.get("kind", "video"), r.get("level", "basic"),
                             r.get("who", ""), r.get("verified", ""))
                 for k, r in data.get("resources", {}).items()}
    return Pack(meta["id"], meta["title"], meta.get("subtitle", ""), meta.get("language", "en"), meta.get("version", "1.0"),
                meta.get("disclaimer", ""), [Rank(**r) for r in meta["ranks"]], list(data["levels"]), lessons,
                list(data.get("glossary", [])), dict(data.get("topics", {})), resources, dict(data.get("roles", {})), folder)


def load_pack(path: str | Path, lang: str | None = None) -> Pack:
    """Load packs/<name>/pack.json (pass the folder, the json file or just the pack name). ``lang`` is ignored: English only."""
    p = Path(path)
    if not p.exists():
        p = packs_dir() / str(path)
    if p.is_dir():
        p = p / "pack.json"
    return _parse(json.loads(p.read_text(encoding="utf-8")), p.parent)


def available_packs() -> list[str]:
    root = packs_dir()
    return sorted(d.name for d in root.iterdir() if (d / "pack.json").exists() and not d.name.startswith("_")) if root.is_dir() else []


def role_notes(pack: Pack) -> list[str]:
    """Lessons outside every course role: shown to people without a role, hidden from those with one (not an error)."""
    if not pack.roles:
        return []
    skills = {s for v in pack.roles.values() for s in v}
    out = [les.title for les in pack.lessons if not set(les.skills) & skills]
    return [f"{len(out)} lesson(s) are in no course role ({', '.join(out[:6])}{'…' if len(out) > 6 else ''}): people with a course role "
            "will not see them. Add their skills to a role in the Roles sheet if they should."] if out else []


def validate(pack: Pack, catalog=None) -> list[str]:
    """Every rule the methodology asks for. Returns human-readable problems; an empty list means the pack is valid.

    Pass the skills catalog (academy.catalog.load_catalog()) to also check each lesson's ``catalog_skills``.
    """
    errs: list[str] = []
    known = catalog.skill_ids() if catalog else None
    for les in pack.lessons:
        for sid in les.catalog_skills if known is not None else []:
            if sid not in known:
                errs.append(f"[{les.id}] catalog skill '{sid}' does not exist in catalog/skills.json.")
    ids = [les.id for les in pack.lessons]
    if len(ids) != len(set(ids)):
        errs.append("There are repeated lesson ids.")
    if [r.points for r in pack.ranks] != sorted(r.points for r in pack.ranks) or not pack.ranks or pack.ranks[0].points != 0:
        errs.append("Ranks must be in order of points and the first one must start at 0.")
    for les in pack.lessons:
        tag = f"[{les.id}]"
        if les.level not in pack.levels:
            errs.append(f"{tag} level '{les.level}' is not in 'levels'.")
        if not (les.title and les.summary):
            errs.append(f"{tag} title or summary is missing.")
        if len(les.points) < 3:
            errs.append(f"{tag} needs at least 3 key points.")
        if len(les.quiz) != 3:
            errs.append(f"{tag} needs exactly 3 questions.")
        for i, q in enumerate(les.quiz):
            if len(q.options) != 4 or len(set(q.options)) != 4:
                errs.append(f"{tag} question {i + 1}: needs 4 distinct options.")
            if not 0 <= q.answer < len(q.options):
                errs.append(f"{tag} question {i + 1}: 'answer' out of range.")
            if not q.why:
                errs.append(f"{tag} question {i + 1}: the explanation ('why') is missing.")
        missing = [k for k in les.resources if k not in pack.resources]
        if missing:
            errs.append(f"{tag} unknown resources: {', '.join(missing)}.")
        res = [pack.resources[k] for k in les.resources if k in pack.resources]
        if sum(r.kind != "link" for r in res) < 2:
            errs.append(f"{tag} needs at least 2 videos.")
        if len({r.channel for r in res}) < 2:
            errs.append(f"{tag} the videos must come from at least 2 different channels.")
        for k in les.resource_notes:
            if k not in les.resources:
                errs.append(f"{tag} note for '{k}', which is not in its resources.")
        # a lesson whose skills are in no course role is allowed: learners with a role do not see it (see role_notes)
    for k, r in pack.resources.items():
        if urlparse(r.url).scheme != "https":
            errs.append(f"[resource {k}] the URL must be https.")
        if r.kind in ("video", "playlist") and not embed_src(r.url):
            errs.append(f"[resource {k}] is not an embeddable YouTube video/playlist; use kind='link'.")
        if not (r.title and r.channel and r.why):
            errs.append(f"[resource {k}] title, channel or 'why' is missing.")
        if r.topic and r.topic not in pack.topics:
            errs.append(f"[resource {k}] topic '{r.topic}' is not in 'topics'.")
    urls = [r.url for r in pack.resources.values()]
    if len(urls) != len(set(urls)):
        errs.append("There are repeated resource URLs.")
    terms = [g["term"].lower() for g in pack.glossary]
    if len(terms) != len(set(terms)):
        errs.append("There are repeated glossary terms.")
    if pack.glossary and len(terms) < 8:
        errs.append("The glossary needs at least 8 terms so the quiz has distractors.")
    return errs
