"""YouTube helpers: parse ids, build the privacy-enhanced (youtube-nocookie) player URL, check a video with oEmbed."""

from __future__ import annotations

import json
from urllib.parse import parse_qs, quote, urlparse
from urllib.request import Request, urlopen

SIZES = {"XS": 280, "S": 400, "M": 520, "L": 720}  # player width in px (16:9), sized for the full-width page
DEFAULT_SIZE = "M"


def youtube_id(url: str) -> str | None:
    u = urlparse(url)
    host = u.netloc.lower().removeprefix("www.").removeprefix("m.")
    if host == "youtu.be":
        return u.path.strip("/") or None
    if host == "youtube.com":
        if u.path == "/watch":
            return parse_qs(u.query).get("v", [None])[0]
        parts = [p for p in u.path.split("/") if p]
        if len(parts) >= 2 and parts[0] in {"shorts", "embed", "live"}:
            return parts[1]
    return None


def playlist_id(url: str) -> str | None:
    u = urlparse(url)
    if u.netloc.lower().removeprefix("www.") == "youtube.com" and u.path == "/playlist":
        return parse_qs(u.query).get("list", [None])[0]
    return None


def embed_src(url: str) -> str | None:
    """Embeddable player URL for a video or playlist, or None if it isn't one."""
    vid = youtube_id(url)
    if vid:
        return f"https://www.youtube-nocookie.com/embed/{vid}?rel=0&modestbranding=1"
    pid = playlist_id(url)
    return f"https://www.youtube-nocookie.com/embed/videoseries?list={pid}" if pid else None


def oembed(url: str, timeout: float = 10.0) -> dict | None:
    """YouTube's own title and channel for a video (None if removed, private or unreachable)."""
    api = f"https://www.youtube.com/oembed?url={quote(url, safe='')}&format=json"
    try:
        with urlopen(Request(api, headers={"User-Agent": "academy-kit"}), timeout=timeout) as r:  # noqa: S310 - fixed https host
            data = json.loads(r.read().decode("utf-8"))
        return {"title": data.get("title", ""), "channel": data.get("author_name", "")}
    except Exception:  # noqa: BLE001
        return None
