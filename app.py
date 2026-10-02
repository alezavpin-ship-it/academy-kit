"""Academy Kit - run with:  streamlit run app.py

Pick the content pack in the sidebar (folder packs/<name>/pack.json). Progress is saved per person in data/academy.db.
Set ACADEMY_PACK to start on a given pack and ACADEMY_DB to store progress elsewhere.
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

from academy import page  # noqa: E402
from academy import legal  # noqa: E402
from academy import notify  # noqa: E402
from academy.access import load_access, save_access  # noqa: E402
from academy.catalog import load_catalog  # noqa: E402
from academy.exam import available_exams, load_exam  # noqa: E402
from academy.i18n import T  # noqa: E402
from academy.pack import available_packs, load_pack  # noqa: E402
from academy.progress import connect  # noqa: E402

st.set_page_config(page_title="Academia - Cloud", page_icon="🎓", layout="wide")

# Company logo (optional): drop the official file in assets/ as logo.svg / logo.png (and logo_icon.* for the collapsed sidebar).
_logo = next((p for p in (ROOT / "assets" / f"logo{e}" for e in (".svg", ".png", ".webp")) if p.exists()), None)
if _logo:
    _icon = next((p for p in (ROOT / "assets" / f"logo_icon{e}" for e in (".svg", ".png", ".webp")) if p.exists()), None)
    st.logo(str(_logo), size="large", icon_image=str(_icon) if _icon else None)


@st.cache_resource
def _conn(path: str):
    return connect(path)


@st.cache_data
def _pack(name: str, lang: str = "en"):
    return load_pack(name, lang)


@st.cache_data
def _exam(name: str, lang: str = "en"):
    return load_exam(name, lang)


legal.guard()  # the copyright notice is fixed; the app does not open if it was altered

packs = available_packs()
if not packs:
    st.error("No packs in packs/. Copy packs/_plantilla to packs/<your-topic> and fill in pack.json. · "
             "No hay paquetes en packs/. Copia packs/_plantilla a packs/<tu-tema> y llena pack.json.")
    st.stop()
default = os.environ.get("ACADEMY_PACK", packs[0])
with st.sidebar:
    lang = st.radio("Language / Idioma", ["en", "es"], horizontal=True, key="ak_lang", format_func=lambda x: "Español" if x == "es" else "English")  # English first = default
    name = st.selectbox(T("pack", lang), packs, index=packs.index(default) if default in packs else 0, key="ak_pack",
                        format_func=lambda n: _pack(n, lang).title)
    pack = _pack(name, lang)
    learner = st.text_input(T("who", lang), value=st.query_params.get("u", "yo"), key="ak_learner", help=T("who_help", lang))
    role = None
    if pack.roles:
        opts = [""] + list(pack.roles)
        if st.session_state.get("ak_role") not in opts:  # role names are translated with the pack
            st.session_state.pop("ak_role", None)
        role = st.selectbox(T("role", lang), opts, key="ak_role", format_func=lambda r: r or T("any_role", lang)) or None

    email = st.text_input(T("email", lang), key="ak_email", help=T("email_help", lang), placeholder="nombre@empresa.com" if lang == "es" else "name@company.com")

conn = _conn(os.environ.get("ACADEMY_DB", str(ROOT / "data" / "academy.db")))
who = learner.strip() or "yo"
if email.strip() and "@" in email and notify.emails(conn).get(who) != email.strip():
    notify.set_email(conn, who, email)
email = email.strip() or notify.emails(conn).get(who, "")
catalog = load_catalog()

# Views: end user by default; owners, leaders and champions can switch on the owner view (see academy/access.py).
acc = load_access()
owner, families = False, set()
is_owner = acc.is_owner(who, email)
mine = acc.champion_families(who, email, catalog)
with st.sidebar:
    if not acc.configured:
        st.divider()
        st.caption(T("claim", lang))
        if st.button(T("claim_btn", lang), key="ak_claim"):
            acc.owners = [email or who]
            save_access(acc)
            st.rerun()
    elif is_owner or mine:
        st.divider()
        on = st.toggle(T("view_owner" if is_owner else "view_champion", lang), value=True, key="ak_owner_view",
                       help=T("view_owner_help" if is_owner else "view_champion_help", lang))
        if on and acc.has_pin():
            pin = st.text_input(T("pin", lang), type="password", key="ak_owner_pin")
            on = bool(pin) and acc.check_pin(pin)
            if pin and not on:
                st.caption(T("pin_bad", lang))
        owner, families = on and is_owner, (mine if on and not is_owner else set())

with st.sidebar:
    st.divider()
    st.caption(legal.notice(lang))

page.render(pack, conn, learner, lang, role, catalog=catalog, packs=[_pack(n, lang) for n in packs],
            exams=[_exam(n, lang) for n in available_exams()], owner=owner, families=families)
