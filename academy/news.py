"""Security news: the sources each practice follows and the latest items they publish.

The sources live in ONE CSV per practice, editable in Excel, in the content workbook (tab NewsSources) or in the app's
edit mode:

    catalog/news_sources.csv      (or the file named by ACADEMY_NEWS)

    Name, Category, Url, FeedUrl, Splash, Enabled, Description

* ``Url``      the site people open (always shown);
* ``FeedUrl``  its RSS / Atom feed, when it has one: the latest items are read from it. Without a feed (or when it does
               not answer) the card shows the site's own preview (title, description and image of the page);
* ``Splash``   yes = its latest item is the news shown when the academy opens (the first enabled one is used);
* ``Enabled``  no = kept in the list but not shown.

Reading is best effort and never blocks the academy: short timeouts, several sources at once, and the last good reading
is kept in data/news_cache.json so the bank still shows something offline. Everything read from the internet is shown
as plain text (tags removed) and only https links and images are used.
"""

from __future__ import annotations

import csv
import html
import io
import json
import os
import re
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCES_FILE = ROOT / "catalog" / "news_sources.csv"
CACHE_FILE = ROOT / "data" / "news_cache.json"
COLUMNS = ["Name", "Category", "Url", "FeedUrl", "Splash", "Enabled", "Description", "Families"]
CATEGORIES = ["Microsoft", "Cloud providers", "Security vendors", "Frameworks and standards", "Government advisories"]
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AcademiaCloud/1.0 (+news reader)"
TIMEOUT = 5
MAX_BYTES = 3_000_000


@dataclass(frozen=True)
class Source:
    name: str
    category: str
    url: str
    feed: str = ""
    splash: bool = False
    enabled: bool = True
    description: str = ""
    families: str = ""  # role family ids separated by ";" whose learners see it; empty = every family

    def for_family(self, family: str | None) -> bool:
        return for_family(self.families, family)


@dataclass
class Item:
    title: str
    link: str
    summary: str = ""
    published: str = ""  # YYYY-MM-DD when known
    image: str = ""
    source: str = ""
    kind: str = "item"  # item = an article from the feed; page = the site's own preview


@dataclass
class Reading:
    source: str
    items: list[Item] = field(default_factory=list)
    fetched: str = ""
    ok: bool = False
    error: str = ""


# ------------------------------------------------------------------------------------------------ sources (CSV)
def sources_path() -> Path:
    from academy import workspace

    return Path(os.environ.get("ACADEMY_NEWS") or workspace.root() / "catalog" / "news_sources.csv")


def _yes(v) -> bool:
    return str(v or "").strip().lower() in ("yes", "y", "true", "1", "si", "sí")


def parse_sources(raw: bytes) -> tuple[list[Source], list[str]]:
    """Sources from the CSV (comma or semicolon) and the problems found."""
    text = raw.decode("utf-8-sig", errors="replace")
    first = text.split("\n", 1)[0]
    rows = list(csv.DictReader(io.StringIO(text, newline=""), delimiter=";" if first.count(";") > first.count(",") else ","))
    problems, out = [], []
    if rows and not {"Name", "Url"} <= set(rows[0]):
        return [], [f"Missing columns: Name and Url are required ({', '.join(COLUMNS)})."]
    for n, r in enumerate(rows, start=2):
        name, url = (r.get("Name") or "").strip(), (r.get("Url") or "").strip()
        if not name and not url:
            continue
        feed = (r.get("FeedUrl") or "").strip()
        if not name or not url.startswith("https://") or (feed and not feed.startswith("https://")):
            problems.append(f"[news row {n}] needs a Name and https addresses (Url, FeedUrl).")
            continue
        out.append(Source(name, (r.get("Category") or "").strip(), url, feed, _yes(r.get("Splash")),
                          r.get("Enabled") in (None, "") or _yes(r.get("Enabled")), (r.get("Description") or "").strip(),
                          _fams(r.get("Families"))))
    names = [s.name.lower() for s in out]
    if len(names) != len(set(names)):
        problems.append("There are repeated news sources (Name).")
    return out, problems


def _fams(text) -> str:
    return "; ".join(x.strip() for x in str(text or "").replace(",", ";").split(";") if x.strip())


def for_family(families: str, family: str | None) -> bool:
    """Shown to a learner of ``family``: tagged with it, or not tagged with any family (practice-wide). None = everything."""
    tags = {x.strip().lower() for x in str(families or "").split(";") if x.strip()}
    return family is None or not tags or family.lower() in tags


def load_sources(path: str | Path | None = None) -> list[Source]:
    p = Path(path) if path else sources_path()
    if not p.exists():
        return []
    return parse_sources(p.read_bytes())[0]


def to_csv(sources: list[Source]) -> bytes:
    buf = io.StringIO(newline="")
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(COLUMNS)
    for s in sources:
        w.writerow([s.name, s.category, s.url, s.feed, "yes" if s.splash else "no", "yes" if s.enabled else "no", s.description, s.families])
    return buf.getvalue().encode("utf-8-sig")


def save_sources(sources: list[Source], path: str | Path | None = None) -> Path:
    p = Path(path) if path else sources_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(to_csv(sources))
    return p


def splash_source(sources: list[Source]) -> Source | None:
    return next((s for s in sources if s.enabled and s.splash), None)


# ------------------------------------------------------------------------------------------------ reading
def clean(text: str, limit: int = 0) -> str:
    """Plain text: no tags, entities decoded, spaces collapsed; cut at a word when ``limit`` is given."""
    t = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", text or "")
    t = html.unescape(re.sub(r"(?s)<[^>]+>", " ", t))
    t = re.sub(r"\s+", " ", t).strip()
    if limit and len(t) > limit:
        t = t[:limit].rsplit(" ", 1)[0].rstrip(",.;:") + "…"
    return t


def _https(url: str) -> str:
    url = html.unescape((url or "").strip())
    return url if url.startswith("https://") else ""


def _date(text: str) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    try:
        return parsedate_to_datetime(text).date().isoformat()  # RSS: Tue, 07 Oct 2026 16:00:00 +0000
    except (TypeError, ValueError, IndexError):
        pass
    m = re.match(r"(\d{4}-\d{2}-\d{2})", text)  # Atom / ISO 8601
    return m.group(1) if m else ""


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _image_in(el, body: str) -> str:
    for child in el.iter():
        name = _local(child.tag)
        if name in ("content", "thumbnail") and child.get("url") and (child.get("medium") in (None, "image") or "image" in (child.get("type") or "image")):
            if _https(child.get("url")):
                return _https(child.get("url"))
        if name == "enclosure" and (child.get("type") or "").startswith("image") and _https(child.get("url")):
            return _https(child.get("url"))
    m = re.search(r"""<img[^>]+src=["']([^"']+)["']""", body or "", re.I)
    return _https(m.group(1)) if m else ""


def parse_feed(raw: bytes, source: str = "", limit: int = 5) -> list[Item]:
    """The newest items of an RSS 2.0 or Atom feed."""
    root = ET.fromstring(raw)
    entries = [e for e in root.iter() if _local(e.tag) in ("item", "entry")]
    out = []
    for e in entries:
        kids = {}
        for c in e:
            kids.setdefault(_local(c.tag), c)
        title = clean("".join(kids["title"].itertext())) if "title" in kids else ""
        link = ""
        for c in e:
            if _local(c.tag) == "link":
                href = c.get("href")
                if href and c.get("rel", "alternate") == "alternate":
                    link = href
                    break
                if not href and (c.text or "").strip():
                    link = c.text.strip()
                    break
        body = ""
        for name in ("encoded", "content", "description", "summary"):
            if name in kids:
                body = "".join(kids[name].itertext()) or (kids[name].text or "")
                if body.strip():
                    break
        summary = ""
        for name in ("description", "summary", "encoded", "content"):
            if name in kids:
                summary = clean("".join(kids[name].itertext()), 420)
                if summary:
                    break
        when = next((kids[n].text for n in ("pubdate", "published", "updated", "date") if n in kids and kids[n].text), "")
        if title and _https(link):
            out.append(Item(title, _https(link), summary, _date(when), _image_in(e, body), source))
    out.sort(key=lambda i: i.published, reverse=True)
    return out[:limit]


def parse_page(raw: bytes, url: str, source: str = "") -> Item | None:
    """The page's own preview (Open Graph / Twitter card / <title>)."""
    text = raw.decode("utf-8", errors="replace")

    def meta(*names: str) -> str:
        for n in names:
            m = re.search(rf"""<meta[^>]+(?:property|name)=["']{re.escape(n)}["'][^>]*content=["']([^"']*)["']""", text, re.I) or \
                re.search(rf"""<meta[^>]+content=["']([^"']*)["'][^>]*(?:property|name)=["']{re.escape(n)}["']""", text, re.I)
            if m and m.group(1).strip():
                return m.group(1)
        return ""

    title = clean(meta("og:title", "twitter:title")) or clean((re.search(r"(?is)<title[^>]*>(.*?)</title>", text) or [None, ""])[1])
    if not title:
        return None
    return Item(title, _https(meta("og:url")) or url, clean(meta("og:description", "description", "twitter:description"), 420), "",
                _https(meta("og:image", "twitter:image")), source, "page")


def _get(url: str, timeout: float = TIMEOUT) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/atom+xml, text/html;q=0.9, */*;q=0.5"})
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 - only https addresses reach here
        return r.read(MAX_BYTES)


def offline() -> bool:
    return os.environ.get("ACADEMY_NEWS_OFFLINE", "") == "1"


def read(source: Source, limit: int = 5, fetch=_get) -> Reading:
    """The latest items of one source: its feed, or else the preview of its page."""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if offline():
        return Reading(source.name, error="offline")
    errors = []
    if source.feed:
        try:
            items = parse_feed(fetch(source.feed), source.name, limit)
            if items:
                return Reading(source.name, items, now, True)
            errors.append("the feed has no items")
        except Exception as e:  # network, format… : fall back to the page
            errors.append(f"feed: {type(e).__name__}")
    try:
        item = parse_page(fetch(source.url), source.url, source.name)
        if item:
            return Reading(source.name, [item], now, True)
        errors.append("the page has no preview")
    except Exception as e:
        errors.append(f"page: {type(e).__name__}")
    return Reading(source.name, [], now, False, "; ".join(errors))


def cover_image(item: Item, fetch=_get) -> str:
    """The article's own preview image when the feed did not carry one (one extra request, only for the splash)."""
    if item.image or offline():
        return item.image
    try:
        page = parse_page(fetch(item.link), item.link)
        return page.image if page else ""
    except Exception:
        return ""


# ------------------------------------------------------------------------------------------------ cache
def cache_path() -> Path:
    from academy import workspace

    return Path(os.environ.get("ACADEMY_NEWS_CACHE") or workspace.root() / "data" / "news_cache.json")


def _load_cache() -> dict:
    try:
        return json.loads(cache_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_cache(data: dict) -> None:
    try:
        p = cache_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass


def latest(sources: list[Source], limit: int = 5, fetch=_get) -> dict[str, Reading]:
    """{source name: reading} for the enabled sources, read in parallel; a source that fails keeps its last good reading."""
    live = [s for s in sources if s.enabled]
    if not live:
        return {}
    with ThreadPoolExecutor(max_workers=min(8, len(live))) as pool:
        got = dict(zip([s.name for s in live], pool.map(lambda s: read(s, limit, fetch), live)))
    cache = _load_cache()
    for name, r in got.items():
        if r.ok:
            cache[name] = asdict(r)
        elif name in cache:  # the last good reading, marked as such
            old = cache[name]
            got[name] = Reading(name, [Item(**i) for i in old.get("items", [])], old.get("fetched", ""), False, r.error or "cached")
    _save_cache({k: v for k, v in cache.items() if k in got})
    return got
