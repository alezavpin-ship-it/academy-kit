"""Study material: a bank of external training content (videos, playlists, pages) the practice recommends, by theme.

It is not a course: it is reading / watching material that champions can promote to a skill's learning path when it fits.
One CSV per practice, editable in Excel, in the content workbook (tab StudyMaterial) or in the app's edit mode:

    catalog/study_material.csv      (or the file named by ACADEMY_STUDY)

    Title, Url, Source, Category, Theme, Kind, Level, SkillId, Notes

* Kind = video (one YouTube video, it plays inside the app) | playlist | search (a search inside the author's channel, for
  a theme) | page (any other link).
* SkillId (optional) ties the item to a skill of the catalog; «Add to the learning path» copies it there as a class.

``from_page`` builds rows from a web page saved from the browser (File → Save as… → HTML): every YouTube link becomes a
row, with the nearest heading above it as the theme. It is how a full catalog such as John Savill's video index is
imported without typing it.
"""

from __future__ import annotations

import csv
import html
import io
import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
STUDY_FILE = ROOT / "catalog" / "study_material.csv"
COLUMNS = ["Title", "Url", "Source", "Category", "Theme", "Kind", "Level", "SkillId", "Notes", "Families"]
KINDS = ["video", "playlist", "search", "page"]
LEVELS = ["basic", "intermediate", "advanced"]
SAVILL = "John Savill's Technical Training"
SAVILL_INDEX = "https://www.azadvertizer.net/savill.html"
SAVILL_CHANNEL = "https://www.youtube.com/@NTFAQGuy"


@dataclass(frozen=True)
class Item:
    title: str
    url: str
    source: str = ""
    category: str = ""
    theme: str = ""
    kind: str = "video"
    level: str = ""
    skill_id: str = ""
    notes: str = ""
    families: str = ""  # role family ids separated by ";"; empty = the family of its SkillId, or every family

    def row(self) -> list[str]:
        return [self.title, self.url, self.source, self.category, self.theme, self.kind, self.level, self.skill_id, self.notes, self.families]

    def for_family(self, family: str | None, catalog=None) -> bool:
        """Shown to a learner of ``family``: tagged with it (Families, or the family of its skill), or practice-wide."""
        from academy.news import for_family

        tags = self.families
        if not tags and self.skill_id and catalog:
            tags = next((s.family for s in catalog.skills if s.id == self.skill_id), "")
        return for_family(tags, family)


def study_path() -> Path:
    from academy import workspace

    return Path(os.environ.get("ACADEMY_STUDY") or workspace.root() / "catalog" / "study_material.csv")


def _text(v) -> str:
    return "" if v is None else str(v).strip()


def parse(raw: bytes) -> tuple[list[Item], list[str]]:
    text = raw.decode("utf-8-sig", errors="replace")
    first = text.split("\n", 1)[0]
    rows = list(csv.DictReader(io.StringIO(text, newline=""), delimiter=";" if first.count(";") > first.count(",") else ","))
    if rows and not {"Title", "Url"} <= set(rows[0]):
        return [], [f"Missing columns: Title and Url are required ({', '.join(COLUMNS)})."]
    out, problems, seen = [], [], set()
    for n, r in enumerate(rows, start=2):
        title, url = _text(r.get("Title")), _text(r.get("Url"))
        if not title and not url:
            continue
        kind = _text(r.get("Kind")).lower() or "video"
        if not title or not url.startswith("https://"):
            problems.append(f"[study row {n}] needs a Title and an https:// Url.")
            continue
        if kind not in KINDS:
            problems.append(f"[study row {n}] Kind must be one of: {', '.join(KINDS)}.")
            continue
        if url in seen:
            continue  # the same link twice: kept once
        seen.add(url)
        out.append(Item(title, url, _text(r.get("Source")), _text(r.get("Category")), _text(r.get("Theme")), kind,
                        _text(r.get("Level")).lower(), _text(r.get("SkillId")), _text(r.get("Notes")),
                        "; ".join(x.strip() for x in _text(r.get("Families")).replace(",", ";").split(";") if x.strip())))
    return out, problems


def to_csv(items: list[Item]) -> bytes:
    buf = io.StringIO(newline="")
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(COLUMNS)
    w.writerows(i.row() for i in items)
    return buf.getvalue().encode("utf-8-sig")


def load(path: str | Path | None = None) -> list[Item]:
    p = Path(path) if path else study_path()
    return parse(p.read_bytes())[0] if p.exists() else []


def save(items: list[Item], path: str | Path | None = None) -> Path:
    p = Path(path) if path else study_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(to_csv(items))
    return p


def merge(old: list[Item], new: list[Item]) -> list[Item]:
    """The old list plus the new links (a link already in the list keeps its row: what the team edited wins)."""
    have = {i.url for i in old}
    return old + [i for i in new if i.url not in have]


def youtube(url: str) -> bool:
    return bool(re.match(r"^https://(www\.)?(youtube\.com/(watch|playlist|shorts|embed)|youtu\.be/)", url))


# ------------------------------------------------------------------------------------------------ import from a saved page
def from_page(raw: bytes, source: str = SAVILL, category: str = "Microsoft") -> list[Item]:
    """Every YouTube link of an HTML page, with its text as the title and the nearest heading above as the theme."""
    text = raw.decode("utf-8", errors="replace")
    tokens = re.finditer(r"(?is)<h([1-4])[^>]*>(.*?)</h\1>|<a\s[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", text)
    theme, out, seen = "", [], set()
    for m in tokens:
        if m.group(1):
            theme = _clean(m.group(2))
            continue
        url, title = html.unescape(m.group(3)).strip(), _clean(m.group(4))
        if url.startswith("//"):
            url = "https:" + url
        url = url.replace("http://", "https://", 1)
        if not youtube(url) or url in seen:
            continue
        seen.add(url)
        kind = "playlist" if "playlist?list=" in url else "video"
        out.append(Item(title or url, url, source, category, theme, kind))
    return out


def _clean(fragment: str) -> str:
    t = html.unescape(re.sub(r"(?s)<[^>]+>", " ", fragment or ""))
    return re.sub(r"\s+", " ", t).strip()


# ------------------------------------------------------------------------------------------------ into a learning path
def as_class(item: Item) -> dict:
    """The item as an entry of catalog/materials.json (a video is reference material; a playlist counts as a course step)."""
    kind = {"playlist": "course", "video": "video", "search": "video", "page": "doc"}.get(item.kind, "video")
    return {"title": item.title, "url": item.url, "kind": kind, "provider": item.source or "External"}


# ------------------------------------------------------------------------------------------------ the starting list
def savill_seed() -> list[Item]:
    """John Savill's Technical Training, as a starting point for a Microsoft Cloud Security practice.

    Six videos are exact links already checked for the courses of the academy; the rest are searches inside his channel by
    theme (they always open his current videos on that theme). The full index (every video) is imported from his index page
    saved as HTML (see ``from_page``)."""
    s, cat = SAVILL, "Microsoft"

    def video(title, vid, theme, level, skill, notes=""):
        return Item(title, f"https://www.youtube.com/watch?v={vid}", s, cat, theme, "video", level, skill, notes)

    def search(title, query, theme, level, skill="", notes=""):
        return Item(title, f"{SAVILL_CHANNEL}/search?query={quote(query)}", s, cat, theme, "search", level, skill,
                    notes or "Opens the videos of his channel on this theme.")

    return [
        Item("John Savill's video index (by theme)", SAVILL_INDEX, s, cat, "Index", "page", "", "",
             "The complete, organized list of his videos. Save it as HTML and import it here to load every video."),
        Item("John Savill's Technical Training (YouTube channel)", SAVILL_CHANNEL, s, cat, "Index", "page", "", ""),
        # exact videos, already used by the courses of the academy
        video("Differences Between Cloud Service Categories - AZ-900 Certification Course", "IqQC1EOQqeU", "Cloud fundamentals", "basic", "microsoft-azure-security"),
        video("Functionality of Microsoft Defender for Cloud - AZ-900 Certification Course", "eWcoMi_nQt4", "Security operations", "basic", "defender-for-cloud"),
        video("Azure Key Vault Deep Dive (AZ-500)", "kP7KpfToMkg", "Data protection", "intermediate", "encryption-key-vault-hsm"),
        video("Azure Storage and Disk Encryption Deep Dive", "EOXgzTqceok", "Data protection", "intermediate", "encryption-key-vault-hsm"),
        video("Azure AD Privileged Identity Management (PIM) - AZ-500, SC-300 Deep Dive Topic", "gccgIkR8_a0", "Identity", "intermediate", "pim-pam"),
        video("Azure Virtual Network and PaaS Network Controls", "MnARPRQ2kvk", "Networking", "intermediate", "azure-network-controls"),
        # learning series
        search("Azure Master Class", "Azure Master Class", "Azure Master Class", "intermediate", "microsoft-azure-security",
               "His complete Azure course, module by module."),
        # certification study crams
        *[search(f"{code} study cram", f"{code} study cram", "Certification study cram", level, skill)
          for code, level, skill in (("AZ-900", "basic", "microsoft-azure-security"), ("SC-900", "basic", "microsoft-azure-security"),
                                     ("AI-900", "basic", "azure-ai-security"), ("AZ-104", "intermediate", "cloud-hybrid-infrastructure"),
                                     ("AZ-500", "intermediate", "microsoft-azure-security"), ("SC-300", "intermediate", "microsoft-entra-id"),
                                     ("AZ-700", "intermediate", "azure-network-controls"), ("AI-102", "intermediate", "azure-ai-security"),
                                     ("AZ-305", "advanced", "security-architecture"), ("SC-100", "advanced", "security-architecture"))],
        # themes of the practice
        *[search(title, query, theme, level, skill) for title, query, theme, level, skill in (
            ("Microsoft Entra ID", "Entra ID", "Identity", "basic", "microsoft-entra-id"),
            ("Conditional Access", "Conditional Access", "Identity", "intermediate", "conditional-access"),
            ("Managed identities", "managed identities", "Identity", "intermediate", "microsoft-entra-id"),
            ("Identity governance and access reviews", "Entra ID Governance", "Identity", "advanced", "identity-governance"),
            ("Azure RBAC", "Azure RBAC", "Governance", "basic", "microsoft-azure-security"),
            ("Azure Policy", "Azure Policy", "Governance", "intermediate", "microsoft-azure-security"),
            ("Azure landing zones", "landing zone", "Governance", "advanced", "security-architecture"),
            ("Zero Trust", "Zero Trust", "Architecture", "intermediate", "zero-trust"),
            ("Azure Firewall", "Azure Firewall", "Networking", "intermediate", "azure-network-controls"),
            ("Network security groups", "network security groups", "Networking", "basic", "azure-network-controls"),
            ("Private Link and private endpoints", "private endpoint", "Networking", "intermediate", "azure-network-controls"),
            ("Azure Front Door and WAF", "Front Door", "Networking", "intermediate", "azure-network-controls"),
            ("Azure Bastion", "Azure Bastion", "Networking", "basic", "azure-network-controls"),
            ("Microsoft Defender for Cloud", "Defender for Cloud", "Security operations", "intermediate", "defender-for-cloud"),
            ("Microsoft Sentinel", "Sentinel", "Security operations", "intermediate", "microsoft-sentinel"),
            ("KQL (Kusto Query Language)", "KQL", "Security operations", "intermediate", "microsoft-sentinel"),
            ("Azure Monitor and Log Analytics", "Log Analytics", "Monitoring", "basic", "production-support"),
            ("Microsoft Purview", "Purview", "Data protection", "intermediate", "microsoft-purview"),
            ("Azure Storage security", "storage security", "Data protection", "intermediate", "encryption-key-vault-hsm"),
            ("Containers and AKS security", "AKS", "Containers", "intermediate", "container-security"),
            ("Infrastructure as code (Bicep / ARM)", "Bicep", "DevOps", "intermediate", "infrastructure-as-code-security"),
            ("GitHub Actions and Azure DevOps", "GitHub Actions", "DevOps", "intermediate", "azure-devops-github-actions"),
            ("Azure OpenAI and AI services", "Azure OpenAI", "AI", "intermediate", "azure-ai-security"),
            ("Backup and disaster recovery", "Azure Backup", "Resiliency", "basic", "cloud-hybrid-infrastructure"),
        )],
    ]
