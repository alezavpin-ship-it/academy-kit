"""Learning route based on the vendor's own training.

Rule of the academy: a Microsoft skill follows Microsoft Learn; a skill of another vendor follows that vendor's official
learning/career path (for example Anthropic Academy for Claude Code). For every skill family, the route is the ordered
list of those items (learning paths, modules, courses, labs) attached to its skills in catalog/materials.json. The
learner opens each one on the vendor's site, comes back and marks it done (optionally pasting the link of the
achievement from their profile as evidence). Reference material (docs, guides, videos) is shown as a complement and
does not count as a step.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

ROUTE_PACK = "learn"  # value of events.pack for route activity
ITEM_POINTS = 15
LEARN_HOST = "learn.microsoft.com"
# what counts as a step of the route (things you complete on the vendor's site), in the order they are best taken
STEP_KINDS = ["module", "path", "course", "lab", "tutorial"]


def is_learn(material: dict) -> bool:
    return LEARN_HOST in str(material.get("url", "")) or str(material.get("provider", "")).lower() == "microsoft learn"


@dataclass(frozen=True)
class Step:
    skill_id: str
    skill: str
    title: str
    url: str
    kind: str
    provider: str = "Microsoft Learn"
    vendor: str = ""  # technology / vendor of the skill (Microsoft, AWS, Cisco…)
    number: int = 0  # class number inside the skill's path: class 1, class 2…
    category: str = ""

    @property
    def key(self) -> str:
        return f"{self.skill_id}|{self.url}"


@dataclass
class FamilyRoute:
    family_id: str
    family: str
    steps: list[Step]  # the classes to complete, ordered by vendor, skill and class number
    extras: dict[str, list[dict]]  # skill name -> reference material that is not a step (docs, guides, videos)
    uncovered: list[str]  # skills of the family without any training step yet

    def vendors(self) -> list[str]:
        return list(dict.fromkeys(s.vendor for s in self.steps))


def class_order(items: list[dict]) -> list[dict]:
    """The steps of one skill in class order: the ``order`` written by the content owner (class 1, class 2…); the ones
    without a number follow, vendor's own training first and from the smallest unit to the largest."""
    mine = [m for m in items if m.get("kind") in STEP_KINDS and m.get("provider")]

    def key(m: dict):
        try:
            n = int(m.get("order") or 0)
        except (TypeError, ValueError):
            n = 0
        return (n <= 0, n, not is_learn(m), STEP_KINDS.index(m["kind"]))

    return sorted(mine, key=key)


def build_routes(catalog, materials: dict[str, list[dict]]) -> list[FamilyRoute]:
    """One route per family (biggest gap first). Inside a family: Microsoft first, then the other vendors; inside a vendor
    its skills; inside a skill its classes in order (any mix of sources: Microsoft Learn, the vendor's free training,
    the company's own portal)."""
    from academy.catalog import vendor_of

    out = []
    for fam in catalog.by_gap():
        steps, extras, uncovered = [], {}, []
        skills = [(vendor_of(s, materials), s) for s in catalog.in_family(fam.id)]
        vendors = list(dict.fromkeys(v for v, _ in skills))
        vendors.sort(key=lambda v: (v != "Microsoft", v == "Vendor-neutral"))  # stable: keeps catalog order otherwise
        for vendor in vendors:
            for _, s in [x for x in skills if x[0] == vendor]:
                items = materials.get(s.id, [])
                mine = class_order(items)
                steps += [Step(s.id, s.name, m["title"], m["url"], m["kind"], m["provider"], vendor, n, s.category)
                          for n, m in enumerate(mine, start=1)]
                rest = [m for m in items if m not in mine]
                if rest:
                    extras[s.name] = rest
                if not mine:
                    uncovered.append(s.name)
        out.append(FamilyRoute(fam.id, fam.name, steps, extras, uncovered))
    return out


class RouteTracker:
    def __init__(self, conn: sqlite3.Connection, learner: str):
        self.conn, self.learner = conn, (learner.strip() or "yo")

    def done(self) -> dict[str, str]:
        """step key -> evidence link ('' if none)."""
        return {r["item"]: r["detail"] for r in self.conn.execute(
            "SELECT item, detail FROM events WHERE pack=? AND learner=? AND kind='learn_item' ORDER BY id", (ROUTE_PACK, self.learner))}

    def complete(self, step: Step, evidence: str = "") -> int:
        """Mark a Microsoft Learn item as done. Points only the first time."""
        pts = 0 if step.key in self.done() else ITEM_POINTS
        with self.conn:
            self.conn.execute("INSERT INTO events(time, pack, learner, kind, item, points, correct, detail) VALUES (?,?,?,?,?,?,?,?)",
                              (datetime.now(timezone.utc).isoformat(timespec="seconds"), ROUTE_PACK, self.learner, "learn_item", step.key,
                               pts, 1, evidence.strip()))
        return pts

    def progress(self, route: FamilyRoute) -> tuple[int, int]:
        done = self.done()
        return sum(1 for s in route.steps if s.key in done), len(route.steps)

    def next_step(self, route: FamilyRoute) -> Step | None:
        done = self.done()
        return next((s for s in route.steps if s.key not in done), None)

    def total_points(self) -> int:
        r = self.conn.execute("SELECT COALESCE(SUM(points),0) AS p FROM events WHERE pack=? AND learner=?", (ROUTE_PACK, self.learner)).fetchone()
        return int(r["p"])
