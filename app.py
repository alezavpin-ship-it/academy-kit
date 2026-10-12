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
from academy import content_sync, english, family_path, identity, notify, people, workspace  # noqa: E402
from academy import legal  # noqa: E402
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
def _pack(practice: str, name: str):  # the practice is part of the key: each practice has its own courses
    return load_pack(name)


@st.cache_data
def _exam(practice: str, name: str):
    return load_exam(name)


legal.guard()  # the copyright notice is fixed; the app does not open if it was altered

# The academy is English only: files of earlier two-language versions are converted once (with a backup).
if english.migrate():
    st.cache_data.clear()
acc = load_access()
directory = [x for x in people.load() if x.active]  # the people directory (catalog/people.csv), global to every practice
me = identity.signed_in(getattr(st.context, "headers", None))  # on Azure: the person Microsoft Entra ID signed in
with st.sidebar:
    if me:
        person = people.find(directory, "", me.email)
        learner = person.name if person else me.name
        st.caption(f"Signed in as **{learner}** ({me.email})")
    elif directory:
        names = [x.name for x in directory] + ["Someone else…"]
        asked = st.query_params.get("u", "")
        pick = st.selectbox("Who are you?", names, index=names.index(asked) if asked in names else 0, key="ak_person",
                            help="The names of the people directory (Team → ✏️ Edit mode → People, or catalog/people.csv). "
                                 "Your role (owner, champion, SME) and your practice come with your name.")
        learner = st.text_input(T("who"), value=asked or "me", key="ak_learner", help=T("who_help")) if pick == names[-1] else pick
    else:
        learner = st.text_input(T("who"), value=st.query_params.get("u", "me"), key="ak_learner", help=T("who_help"))
    if not me:
        person = people.find(directory, learner)
    by_name = "" if me else (learner.strip() or "me")  # signed in with Entra ID: roles go by the account's e-mail only
    known_email = me.email if me else (person.email if person else "")

    # The practice: everyone works in their own; global owners pick any active practice.
    first = workspace.default_id()
    active = [x for x in workspace.load() if x.active] or workspace.load()[:1]
    global_owner = people.is_global_owner(directory, by_name, known_email) or acc.is_owner(by_name, known_email)
    mine_practice = people.practice_of(person, first)
    if global_owner and len(active) > 1:
        ids = [x.id for x in active]
        if st.session_state.get("ak_practice_next") in ids:  # a practice just created: open it
            st.session_state["ak_practice"] = st.session_state.pop("ak_practice_next")
        if st.session_state.get("ak_practice") not in ids:
            st.session_state["ak_practice"] = mine_practice if mine_practice in ids else ids[0]
        pid = st.selectbox(T("practice_label"), ids, key="ak_practice", format_func=lambda i: next(x.name for x in active if x.id == i),
                           help="Each practice has its own courses, role families, people and content. As a global owner you can open any of them.")
    else:
        pid = mine_practice
        name_of = next((x.name for x in workspace.load() if x.id == pid), "")
        if name_of and len(workspace.load()) > 1:
            st.caption(f"{T('practice_label')}: **{name_of}**")
pid = workspace.use(pid)

# The content file (content/academy_content.xlsx) is where courses, videos, learning paths and skills are edited:
# when it changed since the last run it is checked and, if it is right, applied before anything is shown.
_sync = content_sync.sync()
if _sync["status"] == "none":  # first run: write the file from what the app already holds
    content_sync.refresh()
    _sync = content_sync.sync()
st.session_state["ak_content_sync"] = _sync
if _sync["status"] == "applied":
    st.cache_data.clear()
if english.practice_titles():  # courses are named after the practice («… Practice», not «… Academy»)
    content_sync.refresh()
    st.cache_data.clear()
# Each family's career path is also a CSV (content/families/<family>.csv) its champion may edit in Excel.
_fam = family_path.sync(load_catalog())
st.session_state["ak_family_sync"] = _fam
if _fam["applied"]:
    content_sync.refresh()
    st.cache_data.clear()

packs = available_packs()
if not packs:
    st.error("This practice has no course yet (packs/ is empty). Copy packs/_template to packs/<your-topic> and fill in pack.json.")
    st.stop()
default = os.environ.get("ACADEMY_PACK", packs[0])
with st.sidebar:
    if len(packs) > 1 or st.session_state.get("ak_pack") not in (None, *packs):
        if st.session_state.get("ak_pack") not in packs:
            st.session_state.pop("ak_pack", None)
        name = st.selectbox(T("pack"), packs, index=packs.index(default) if default in packs else 0, key="ak_pack",
                            format_func=lambda n: _pack(pid, n).title)
    else:
        name = packs[0]
    pack = _pack(pid, name)
    # The course role (what the person learns) is set by the practice's owners and champions in People / the roster
    role = person.course_role if person and person.course_role in pack.roles else None  # a role without lessons yet: every lesson
    if person and person.course_role:
        st.caption(f"{T('role')}: **{person.course_role}**")

    st.toggle("Sounds", value=True, key="ak_sound",
              help="A short sound when you answer, finish a step or complete a lesson.")
    if me:  # the e-mail is the signed-in account: nobody can type someone else's
        email = me.email
    else:
        email = st.text_input(T("email"), key="ak_email", help=T("email_help"), placeholder="name@company.com") or (person.email if person else "")

conn = _conn(os.environ.get("ACADEMY_DB", str(ROOT / "data" / "academy.db")))
who = learner.strip() or "me"
if email.strip() and "@" in email and notify.emails(conn).get(who) != email.strip():
    notify.set_email(conn, who, email)
email = email.strip() or notify.emails(conn).get(who, "")
catalog = load_catalog()

# Two views: 🎓 Learning (everyone) and 🛠️ Management (the tools each person is responsible for, see page.manage_access):
# owners of the practice, champions (their role families) and the people holding a responsibility in People (Demand;
# Upskilling & learning — while nobody holds one, the owners do).
by_name = "" if me else who  # signed in with Entra ID: roles go by the account's e-mail only, never by a typed name
is_owner = acc.is_owner(by_name, email) or people.is_owner(directory, by_name, email, practice=pid)
mine = acc.champion_families(by_name, email, catalog) | people.families_of(directory, by_name, email)
duties = people.duties_of(directory, by_name, email, pid, first, is_owner)
can_manage = page.has_management(is_owner, mine, duties)
view, unlocked = page.LEARNING_VIEW, True
with st.sidebar:
    if not acc.configured and not any(x.role == people.OWNER for x in directory):
        st.divider()
        st.caption(T("claim"))
        if st.button(T("claim_btn"), key="ak_claim"):
            acc.owners = [email or who]
            save_access(acc)
            st.rerun()
    elif not can_manage and me and not any(x.role == people.OWNER for x in directory) and not acc.owners:
        st.divider()
        st.caption(f"No owners yet: the Azure admin lists them in the app setting ACADEMY_OWNERS (your e-mail: {email}).")
    if can_manage:
        st.divider()
        if st.session_state.get("ak_view") not in page.VIEWS:
            st.session_state["ak_view"] = page.LEARNING_VIEW
        view = st.segmented_control("View", list(page.VIEWS), key="ak_view", format_func=page.VIEWS.get, width="stretch",
                                    help="🎓 Learning: the academy as every learner sees it. 🛠️ Management: the tools you are "
                                         "responsible for (learning paths, team, reports, demand, rhythm, administration).") or page.LEARNING_VIEW
        if acc.has_pin():
            pin = st.text_input(T("pin"), type="password", key="ak_owner_pin")
            unlocked = bool(pin) and acc.check_pin(pin)
            if pin and not unlocked:
                st.caption(T("pin_bad"))
            if view == page.MANAGE_VIEW and not unlocked:
                st.caption("Type the PIN to open the Management view.")
                view = page.LEARNING_VIEW
        if view == page.MANAGE_VIEW:
            st.caption("You manage: " + ", ".join(T(k) for k, v in page.manage_access(is_owner, mine, duties).items() if v))

owner = is_owner and unlocked
page.render(pack, conn, learner, "en", role, catalog=catalog, packs=[_pack(pid, n) for n in packs],
            exams=[_exam(pid, n) for n in available_exams()], owner=owner, families=mine if unlocked else set(), email=email,
            global_owner=owner and (people.is_global_owner(directory, by_name, email) or acc.is_owner(by_name, email)),
            view=view, duties=duties if unlocked else set())

with st.sidebar:
    st.divider()
    st.caption(legal.notice("en"))
