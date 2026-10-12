"""Study material in the app: the second section of Knowledge exchange and a section of the Video library."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import streamlit as st

from academy import content_sync, study, ui
from academy.catalog import load_materials, save_materials


def _filters(items: list[study.Item], key: str) -> list[study.Item]:
    cats = list(dict.fromkeys(i.category for i in items if i.category))
    c = st.columns([2, 2, 3])
    cat = c[0].selectbox("Category", ["All"] + cats, index=(cats.index("Microsoft") + 1) if "Microsoft" in cats else 0, key=f"{key}_cat")
    pool = [i for i in items if cat == "All" or i.category == cat]
    themes = list(dict.fromkeys(i.theme for i in pool if i.theme))
    theme = c[1].selectbox("Theme", ["All"] + themes, key=f"{key}_theme")
    find = c[2].text_input("Search", key=f"{key}_find", placeholder="Key Vault, Sentinel, AZ-500…")
    return [i for i in pool if (theme == "All" or i.theme == theme)
            and (not find.strip() or find.strip().lower() in f"{i.title} {i.theme} {i.notes} {i.source}".lower())]


def _embed(url: str) -> str | None:
    q = urlparse(url)
    vid = parse_qs(q.query).get("v", [""])[0] if "youtube.com" in q.netloc else q.path.strip("/") if "youtu.be" in q.netloc else ""
    return f"https://www.youtube-nocookie.com/embed/{vid}" if vid else None


def study_bank(catalog, leader: bool, key: str = "sm", player: bool = False, family: str | None = None) -> None:
    """The bank: filters, the list grouped by theme with a link to the source, an optional player, and (leaders) the tools.
    ``family``: only the items of that role family and the ones for the whole practice."""
    everything = study.load()
    items = [i for i in everything if i.for_family(family, catalog)]
    st.markdown("#### Study material")
    st.caption("Training content the practice recommends, by theme: open it on the author's site. Champions can promote any item to a "
               "skill's learning path. Kinds: ▶ video · ☰ playlist · 🔎 search in the author's channel · ↗ page.")
    if not items:
        st.info("No study material yet. An owner can import it below or with ✏️ Edit mode.")
    shown = _filters(items, key) if items else []
    icon = {"video": "▶", "playlist": "☰", "search": "🔎", "page": "↗"}
    if items:
        st.caption(f"{len(shown)} of {len(items)} items")
    if player:
        videos = [i for i in shown if i.kind == "video" and _embed(i.url)]
        if videos:
            pick = st.selectbox("Watch here", range(len(videos)), key=f"{key}_play", format_func=lambda n: f"▶ {videos[n].title} — {videos[n].theme}")
            st.iframe(_embed(videos[pick].url), width=640, height=362) if hasattr(st, "iframe") else st.video(videos[pick].url)
    by_theme: dict[str, list[study.Item]] = {}
    for i in shown:
        by_theme.setdefault(i.theme or "Other", []).append(i)
    for theme, group in by_theme.items():
        with st.expander(f"{theme} ({len(group)})", expanded=len(by_theme) <= 3):
            for i in group:
                a, b = st.columns([5, 1])
                meta = " · ".join(x for x in (i.source, i.level, i.notes) if x)
                a.markdown(f"{icon.get(i.kind, '↗')} **{_md(i.title)}**  \n{_md(meta)}")
                b.link_button("Open ↗", i.url, width="stretch")
    if leader:
        _tools(everything, shown, catalog, key)  # imports merge into the whole bank, never into a filtered view


def _md(text: str) -> str:
    return "".join("\\" + ch if ch in "[]()*_`#<>|~" else ch for ch in text)


def _tools(items: list[study.Item], shown: list[study.Item], catalog, key: str) -> None:
    with st.expander("⚙️ Study material tools", expanded=True):
        st.markdown("**Add to a learning path**: the chosen items become classes of a skill's route (videos as reference, playlists as steps).")
        if catalog and shown:
            names = {s.id: f"{s.name} ({next((f.name for f in catalog.families if f.id == s.family), s.family)})" for s in catalog.skills}
            c = st.columns([3, 2])
            picks = c[0].multiselect("Items", range(len(shown)), format_func=lambda n: shown[n].title, key=f"{key}_pick")
            default = next((shown[n].skill_id for n in picks if shown[n].skill_id in names), None)
            skill = c[1].selectbox("Skill", list(names), index=list(names).index(default) if default else 0, format_func=lambda k: names[k],
                                   key=f"{key}_skill_{default}")
            if st.button("Add to the learning path", key=f"{key}_add", disabled=not picks, type="primary"):
                mats = load_materials()
                have = {m.get("url") for m in mats.get(skill, [])}
                new = [study.as_class(shown[n]) for n in picks if shown[n].url not in have]
                mats.setdefault(skill, []).extend(new)
                save_materials(mats)
                content_sync.refresh()
                st.cache_data.clear()
                ui.fx("step")
                st.toast(f"{len(new)} item(s) added to {names[skill]}.")
        st.markdown("**Import** a CSV with the same columns, or a web page saved from the browser (File → Save as… → HTML): every YouTube "
                    f"link of the page becomes an item, with the heading above it as the theme. For John Savill's full index, open "
                    f"{study.SAVILL_INDEX}, save it and upload it here.")
        up = st.file_uploader("CSV or saved page (.html)", type=["csv", "html", "htm"], key=f"{key}_up")
        if up is not None:
            raw = up.getvalue()
            if up.name.lower().endswith((".html", ".htm")):
                source = st.text_input("Source", value=study.SAVILL, key=f"{key}_src")
                new, problems = study.from_page(raw, source.strip() or "External", "Microsoft"), []
            else:
                new, problems = study.parse(raw)
            merged = study.merge(items, new)
            st.caption(f"{len(new)} item(s) in the file · {len(merged) - len(items)} new for the bank")
            if problems:
                st.error("\n\n".join(problems[:20]))
            elif st.button("Add them to the study material", key=f"{key}_imp", type="primary", disabled=len(merged) == len(items)):
                study.save(merged)
                content_sync.refresh()
                st.cache_data.clear()
                ui.fx("ok")
                st.rerun()
        st.download_button("Download the study material (CSV)", study.to_csv(items), file_name="study_material.csv", mime="text/csv",
                           key=f"{key}_csv")
