"""The news in the app: the window shown when the academy opens, and the «Knowledge exchange» tab (a reading bank)."""

from __future__ import annotations

import streamlit as st

from academy import news

SPLASH_IMAGE_WIDTH = 480  # a medium image: big enough to recognize, small enough to keep the window short


@st.cache_data(ttl=3600, show_spinner=False)
def _latest(sources: tuple, limit: int = 5) -> dict:
    """Readings for these sources, cached for an hour (the CSV's content is part of the key)."""
    return {k: news.asdict(v) for k, v in news.latest([news.Source(*s) for s in sources], limit).items()}


@st.cache_data(ttl=3600, show_spinner=False)
def _cover(link: str, image: str) -> str:
    return news.cover_image(news.Item("", link, image=image))


def _key(sources: list[news.Source]) -> tuple:
    return tuple((s.name, s.category, s.url, s.feed, s.splash, s.enabled, s.description) for s in sources)


def _md(text: str) -> str:
    """Plain text safe inside Markdown (a title with brackets or asterisks cannot become a link or a style)."""
    return "".join("\\" + ch if ch in "[]()*_`#<>|~" else ch for ch in text)


def _url(link: str) -> str:
    return link.replace(" ", "%20").replace("(", "%28").replace(")", "%29")


# ---------------------------------------------------------------------------------------------- opening window
def splash() -> None:
    """Once per session: the latest item of the splash source in a window that closes with «Continue»."""
    if st.session_state.get("news_seen"):
        return
    st.session_state["news_seen"] = True  # whatever happens, it is shown only once
    src = news.splash_source(news.load_sources())
    if src is None or not hasattr(st, "dialog"):
        return
    with st.spinner("Loading the latest security news…"):
        reading = _latest(_key([src]), 1).get(src.name) or {}
    items = reading.get("items") or []
    if not items:
        return
    item = items[0]

    @st.dialog(f"Latest from {src.name}", width="large")
    def window() -> None:
        meta = " · ".join(x for x in (item.get("published", ""), item.get("source", "")) if x)
        st.markdown(f"### {_md(item['title'])}")
        if meta:
            st.caption(meta)
        image = _cover(item["link"], item.get("image", ""))
        left, right = st.columns([5, 4], gap="medium") if image else (st.container(), None)
        if image:
            with right:
                st.image(image, width=SPLASH_IMAGE_WIDTH)
        with left:
            st.markdown(_md(news.clean(item.get("summary", ""), 520)) or "_No summary available._")
        a, b, c = st.columns([2, 2, 2])
        a.link_button("Read the full article ↗", item["link"], type="primary", width="stretch")
        if src.url != item["link"]:
            b.link_button(f"More on {src.name} ↗", src.url, width="stretch")
        if c.button("Continue to the academy", key="news_close", width="stretch"):
            st.rerun()
        st.caption("Third-party content: it opens on the publisher's site. This window shows once per session.")

    window()


# ---------------------------------------------------------------------------------------------- Knowledge exchange
def knowledge_tab(lang: str = "en", catalog=None, leader: bool = False) -> None:
    """Two sections: the latest news of the practice's sources, and the study material (training content by theme)."""
    part = st.segmented_control("Knowledge exchange", ["📰 News", "📚 Study material"], default="📰 News", key="kx_part",
                                label_visibility="collapsed") or "📰 News"
    if part == "📚 Study material":
        from academy.study_page import study_bank

        study_bank(catalog, leader, key="kx_sm")
        return
    sources = [s for s in news.load_sources() if s.enabled]
    st.markdown("#### Knowledge exchange")
    st.caption("A reading bank of security news from the sources this practice follows: Microsoft, cloud providers, security vendors, "
               "frameworks and standards. Open any item to read it on the publisher's site.")
    if not sources:
        st.info("No news sources yet. An owner can add them with ✏️ Edit mode (or in catalog/news_sources.csv).")
        return
    cats = list(dict.fromkeys([c for c in news.CATEGORIES if any(s.category == c for s in sources)] + [s.category for s in sources if s.category]))
    top = st.columns([6, 1])
    pick = top[0].segmented_control("Category", ["All"] + cats, default="All", key="kx_cat", label_visibility="collapsed") or "All"
    if top[1].button("↻ Refresh", key="kx_refresh", width="stretch", help="Read the sources again (they are cached for an hour)."):
        _latest.clear()
        _cover.clear()
    shown = [s for s in sources if pick == "All" or s.category == pick]
    with st.spinner("Reading the sources…"):
        readings = _latest(_key(shown), 4)
    cols = st.columns(3, gap="medium")
    for n, src in enumerate(shown):
        r = readings.get(src.name) or {}
        items = r.get("items") or []
        with cols[n % 3].container(border=True):
            st.markdown(f"**{_md(src.name)}**")
            st.caption(" · ".join(x for x in (src.category, ("updated " + r["fetched"][:10]) if r.get("fetched") else "",
                                              "saved copy" if items and not r.get("ok") else "") if x))
            first = items[0] if items else None
            if first and first.get("image"):
                st.image(first["image"], width="stretch")
            if not items:
                st.markdown(_md(src.description) or "—")
                st.caption("Could not read the latest items right now.")
            for it in items:
                when = f" · {it['published']}" if it.get("published") else ""
                st.markdown(f"[{_md(it['title'])}]({_url(it['link'])}){when}")
                if it is first and it.get("summary"):
                    st.caption(news.clean(it["summary"], 220))
            st.link_button(f"Open {src.name} ↗", src.url, width="stretch")
