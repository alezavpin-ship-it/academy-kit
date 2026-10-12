"""Rhythm in the app.

* 🎓 Learning view → «Study groups»: the learner's study sessions, the study groups of their role family (opened by its
  champion or the owners, so every group a learner sees is authorized) and the room of the groups they are in.
* 🛠️ Management view → «Rhythm»: every series (monthly review, family syncs, study groups), the meeting room and the
  management of the series, for owners, the Upskilling & learning team and the champions (their families)."""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from academy import notify, ui
from academy import rhythm as rh
from academy.access import load_access
from academy.certs import DESIRED, Certs


def _ctx(conn, catalog, packs, exams):
    owners = load_access().owners
    champions = {f.id: f.champion for f in catalog.families} if catalog else {}
    mails = notify.emails(conn)
    for f in (catalog.families if catalog else []):
        if f.champion and f.champion_email:
            mails.setdefault(f.champion, f.champion_email)
    people = {f.id: [r["Person"] for r in notify.family_team(conn, packs, exams, catalog, {f.id})] for f in (catalog.families if catalog else [])}
    return owners, champions, mails, people


def _invite(r: rh.Rhythm, s: rh.Series, ctx, me: str, key: str, label: str = "📅 Invite (.ics)") -> None:
    owners, champions, mails, people = ctx
    who = r.attendees(s, owners, champions, people.get(s.family))
    st.download_button(label, rh.ics(s, {p: mails.get(p, p if "@" in p else "") for p in who}, mails.get(s.lead, ""),
                                     f"{rh.KINDS[s.kind]} · {s.when()} · Academia - Cloud (Rhythm tab: agenda and actions)"),
                       file_name=f"{s.title[:40].replace(':', '').replace('/', '-')}.ics", mime="text/calendar", key=key, width="stretch",
                       help=f"Open it with Outlook: it adds the series with {sum(1 for p in who if mails.get(p) or '@' in p)} attendee(s) who have an e-mail.")


def _can_manage(s: rh.Series, me: str, owner: bool, families: set[str]) -> bool:
    return owner or (s.kind in (rh.WEEKLY, rh.STUDY) and s.family in families) or (s.kind == rh.STUDY and s.lead.lower() == me.lower())


def _family_ok(s: rh.Series, family: str | None) -> bool:
    """A study group for a learner of ``family``: one of that family, or one open to the whole practice (no family)."""
    return family is None or not s.family or s.family == family


def study_tab(conn, catalog, packs: list, exams: list, learner: str, family: str | None) -> None:
    """The learner's study groups: their next sessions, the groups of their family to join and the room of their groups."""
    me = learner.strip() or "me"
    r = rh.Rhythm(conn)
    if not catalog:
        st.info("Study groups are organized by role family: the catalog is not loaded yet.")
        return
    ctx = _ctx(conn, catalog, packs, exams)
    st.markdown("#### Study groups")
    fam = next((f.name for f in catalog.families if f.id == family), "")
    st.caption("Groups that prepare a certification together, with an exam date, a session per week and an agenda built from the "
               "exam's domains. They are opened by your role family's champion or the practice's owners"
               + (f": you see the groups of **{fam}** and the ones open to the whole practice." if fam else "."))
    mine = {s.id for s in r.all() if s.kind == rh.STUDY and (me.lower() in [m.lower() for m in r.members(s.id)] or s.lead.lower() == me.lower())}
    soon = r.upcoming(35, only=mine)
    st.markdown("##### My next study sessions")
    if not soon:
        st.info("No study session in the next 5 weeks. Join a group below.")
    for n, (day, s) in enumerate(soon[:8]):
        with st.container(border=True):
            a, b, c = st.columns([5, 2, 2], vertical_alignment="center")
            a.markdown(f"**{day.strftime('%a %d %b')} · {s.time}** — {s.title}  \n{s.minutes} min" + (f" · [join]({s.place})" if s.place.startswith("https://")
                                                                                                    else (f" · {s.place}" if s.place else "")))
            if b.button("Open the agenda", key=f"sg_open_{s.id}_{day}", width="stretch"):
                st.session_state["rh_room"] = s.id
                st.session_state[f"rh_day_{s.id}"] = day.isoformat()
            with c:
                _invite(r, s, ctx, me, key=f"sg_ics_{s.id}_{n}")
    _study_groups(conn, r, catalog, exams, me, family)
    _room(conn, r, catalog, packs, exams, me, False, set(), ctx, mine)


def rhythm_tab(conn, catalog, packs: list, exams: list, learner: str, owner: bool, families: set[str] | None = None) -> None:
    me = learner.strip() or "me"
    families = set(families or set())
    r = rh.Rhythm(conn)
    if not catalog:
        st.info("The rhythm is organized by role family: load the skills catalog first.")
        return
    ctx = _ctx(conn, catalog, packs, exams)
    owners, champions, mails, people = ctx
    if owner:
        families = {f.id for f in catalog.families}
    st.markdown("#### Rhythm")
    st.caption("The meetings that keep the upskilling alive: the monthly review (owner lead and champions), the weekly family sync and the "
               "study groups for certifications. Every agenda is built from the academy's data and every meeting closes with actions.")
    mine = {s.id for s in r.all() if me.lower() in [p.lower() for p in r.attendees(s, owners, champions, people.get(s.family))]}
    if owner:
        mine |= {s.id for s in r.all()}
    soon = r.upcoming(35, only=mine)
    st.markdown("##### My next sessions")
    if not soon:
        st.info("No sessions in the next 5 weeks." + (" Create the recommended rhythm below." if owner else " Join a study group below."))
    for n, (day, s) in enumerate(soon[:8]):
        with st.container(border=True):
            a, b, c = st.columns([5, 2, 2], vertical_alignment="center")
            a.markdown(f"**{day.strftime('%a %d %b')} · {s.time}** — {s.title}  \n"
                       f"<span class='ak-pill'>{rh.KINDS[s.kind]}</span> {s.minutes} min" + (f" · [join]({s.place})" if s.place.startswith("https://") else
                                                                                         (f" · {s.place}" if s.place else "")), unsafe_allow_html=True)
            if b.button("Open the agenda", key=f"rh_open_{s.id}_{day}", width="stretch"):
                st.session_state["rh_room"] = s.id
                st.session_state[f"rh_day_{s.id}"] = day.isoformat()
            with c:
                _invite(r, s, ctx, me, key=f"rh_ics_{s.id}_{n}")
    _study_groups(conn, r, catalog, exams, me)
    _room(conn, r, catalog, packs, exams, me, owner, families, ctx, mine)
    if owner or families:
        _manage(conn, r, catalog, exams, me, owner, families, ctx)


# ---------------------------------------------------------------------------------------------- study groups
def _study_groups(conn, r: rh.Rhythm, catalog, exams, me: str, family: str | None = None) -> None:
    st.markdown("##### Study groups to join")
    today = date.today()
    groups = [s for s in r.all() if s.kind == rh.STUDY and (rh._day(s.end) or today) >= today and _family_ok(s, family)]
    wanted = {c["Code"] for c in Certs(conn).records(me) if c["Status"] == DESIRED}
    if not groups:
        st.caption("No study group is running." + (f" You aim for {', '.join(sorted(wanted))}: ask your champion to open a group." if wanted else ""))
        return
    missing = wanted - {g.cert for g in groups}
    if missing:
        st.caption(f"No group yet for {', '.join(sorted(missing))} (in your desired certifications): ask your champion to open one.")
    cols = st.columns(3, gap="medium")
    for n, g in enumerate(sorted(groups, key=lambda g: (g.cert not in wanted, g.end))):
        members = r.members(g.id)
        inside = me.lower() in [m.lower() for m in members] or g.lead.lower() == me.lower()
        left = (rh._day(g.end) - today).days if rh._day(g.end) else None
        with cols[n % 3].container(border=True):
            st.markdown(f"**{g.cert}**" + (" · ⭐ in your goals" if g.cert in wanted else ""))
            st.caption(f"{g.title}  \nExam {g.end}" + (f" · {left} days" if left is not None else "") + f"  \n{g.when()}  \nLead: {g.lead or '—'} · "
                       f"{len(members)} member(s)")
            if inside:
                if g.lead.lower() != me.lower() and st.button("Leave the group", key=f"rh_leave_{g.id}", width="stretch"):
                    r.leave(g.id, me)
                    st.rerun()
                st.caption("✓ You are in this group.")
            elif g.open:
                if st.button("Join the group", key=f"rh_join_{g.id}", type="primary", width="stretch"):
                    r.join(g.id, me)
                    ui.fx("step")
                    st.toast(f"You joined the {g.cert} study group. Download the invite from «My next sessions».")
                    st.rerun()
            else:
                st.caption("Closed group: ask the lead to add you.")


# ---------------------------------------------------------------------------------------------- meeting room
def _room(conn, r: rh.Rhythm, catalog, packs, exams, me: str, owner: bool, families: set[str], ctx, mine: set[int]) -> None:
    series = [s for s in r.all() if s.id in mine]
    if not series:
        return
    st.markdown("##### Meeting room")
    ids = [s.id for s in series]
    if st.session_state.get("rh_room") not in ids:
        st.session_state["rh_room"] = ids[0]
    names = {s.id: f"{s.title} · {rh.KINDS[s.kind]}" for s in series}
    c1, c2 = st.columns([3, 1])
    sid = c1.selectbox("Meeting", ids, format_func=lambda i: names[i], key="rh_room")
    s = r.get(sid)
    today = date.today()
    days = rh.occurrences(s, today - timedelta(days=45), today + timedelta(days=60))
    if not days:
        st.caption("This series has no session in this period (check its start and, for a study group, its exam date).")
        return
    default = next((d for d in days if d >= today), days[-1])
    choices = [d.isoformat() for d in days]
    if st.session_state.get(f"rh_day_{sid}") not in choices:
        st.session_state[f"rh_day_{sid}"] = default.isoformat()
    day = date.fromisoformat(c2.selectbox("Session", choices, key=f"rh_day_{sid}", format_func=lambda d: date.fromisoformat(d).strftime("%a %d %b %Y")))
    with st.container(border=True):
        st.markdown(f"**{s.title}** · {day.strftime('%A %d %B %Y')} · {s.time} · {s.minutes} min")
        items = rh.agenda(conn, s, day, packs, exams, catalog)
        text = [f"{s.title} — {day.isoformat()} {s.time}", ""]
        for n, (head, lines) in enumerate(items, start=1):
            st.markdown(f"**{n}. {head}**")
            st.markdown("\n".join(f"- {x}" for x in lines))
            text += [f"{n}. {head}"] + [f"   - {x}" for x in lines] + [""]
        st.download_button("Download the agenda (text, to paste in Teams or Outlook)", "\n".join(text).encode("utf-8"),
                           file_name=f"agenda_{day.isoformat()}.txt", mime="text/plain", key=f"rh_agenda_{sid}_{day}")
    st.markdown("**Actions**")
    acts = r.actions(sid)
    if acts:
        df = pd.DataFrame([{"Done": bool(a["done"]), "Action": a["text"], "Owner": a["owner"], "Due": a["due"], "From": a["meeting"], "_id": a["id"]} for a in acts])
        with st.form(f"rh_acts_form_{sid}_{len(acts)}", border=False, enter_to_submit=False):
            ed = st.data_editor(df.drop(columns=["_id"]), hide_index=True, width="stretch", key=f"rh_acts_{sid}_{len(acts)}",
                                disabled=["Action", "Owner", "Due", "From"], column_config={"Done": st.column_config.CheckboxColumn("Done")})
            save_acts = st.form_submit_button("Save the actions", key=f"rh_acts_save_{sid}")
        changed = [(a, bool(row["Done"])) for a, row in zip(acts, ed.to_dict("records")) if bool(a["done"]) != bool(row["Done"])]
        if save_acts and changed:
            for a, done in changed:
                r.set_done(a["id"], done)
            st.rerun()
    owners, champions, mails, people = ctx
    who = r.attendees(s, owners, champions, people.get(s.family))
    with st.form(f"rh_new_act_{sid}", clear_on_submit=True, border=False):
        a, b, c, d = st.columns([4, 2, 2, 1], vertical_alignment="bottom")
        what = a.text_input("New action", placeholder="What will be done")
        owner_ = b.selectbox("Owner", [""] + who, format_func=lambda x: x or "—")
        due = c.date_input("Due", value=None, min_value=today - timedelta(days=30))
        if d.form_submit_button("Add", width="stretch") and what.strip():
            r.add_action(sid, day.isoformat(), what, owner_, due.isoformat() if due else "", by=me)
            st.rerun()


# ---------------------------------------------------------------------------------------------- management
def _manage(conn, r: rh.Rhythm, catalog, exams, me: str, owner: bool, families: set[str], ctx) -> None:
    with st.expander("⚙️ Manage the rhythm and open study groups", expanded=True):
        fams = [f for f in catalog.families if f.id in families]
        if owner:
            missing = not any(s.kind == rh.MONTHLY for s in r.all(None)) or any(not any(s.kind == rh.WEEKLY and s.family == f.id for s in r.all(None)) for f in fams)
            if missing and st.button("Create the recommended rhythm (monthly review + a sync per family)", type="primary", key="rh_std"):
                n = len(r.standard(fams, me))
                st.toast(f"{n} series created. Adjust days and times in the table below.")
                st.rerun()
        elif fams:
            for f in fams:
                if not any(s.kind == rh.WEEKLY and s.family == f.id for s in r.all(None)) and st.button(f"Create the weekly sync of {f.name}", key=f"rh_mk_{f.id}"):
                    r.create(rh.WEEKLY, f"{f.name}: family sync", family=f.id, lead=me, weekday=3, time="09:30", minutes=30)
                    st.rerun()
        st.markdown("**New study group**")
        codes = sorted({c["Code"] for c in Certs(conn).requirements(families)} | {e.code.upper() for e in exams} |
                       {c["Code"] for c in Certs(conn).records() if c["Status"] == DESIRED})
        fam_names = {"": "Whole practice (every family)", **{f.id: f.name for f in catalog.families}}
        fam_opts = ([""] if owner else []) + [f.id for f in catalog.families if f.id in families]
        with st.form("rh_new_group", clear_on_submit=True):
            group_family = st.selectbox("Role family", fam_opts, format_func=lambda k: fam_names[k], key="rh_g_family",
                                        help="Learners see the study groups of their own role family and the ones open to the whole practice.")
            a, b, c = st.columns(3)
            code = a.selectbox("Certification", codes + ["Other…"], key="rh_g_code")
            other = a.text_input("Other certification code", placeholder="e.g. SC-401", key="rh_g_other")
            exam_day = b.date_input("Exam date", value=date.today() + timedelta(weeks=8), min_value=date.today() + timedelta(days=7), key="rh_g_exam")
            weekday = b.selectbox("Day", list(range(7)), index=2, format_func=lambda i: rh.WEEKDAYS[i], key="rh_g_wd")
            time_ = c.text_input("Time (HH:MM)", value="17:00", key="rh_g_time")
            minutes = c.number_input("Minutes", 30, 180, 60, 15, key="rh_g_min")
            place = st.text_input("Teams link or room (optional)", key="rh_g_place")
            open_ = st.checkbox("Anyone can join", value=True, key="rh_g_open")
            if st.form_submit_button("Open the study group", type="primary"):
                cert = (other.strip() if code == "Other…" else code).upper()
                try:
                    sid = r.create(rh.STUDY, f"{cert} study group", cert=cert, lead=me, family=group_family or "", weekday=weekday, time=time_.strip(), minutes=int(minutes),
                                   end=exam_day.isoformat(), place=place, open=open_, start=date.today().isoformat())
                    r.join(sid, me)
                    st.toast(f"{cert} study group opened: {rh.session_number(r.get(sid), date.today())[1]} sessions until the exam.")
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))
        mine = [s for s in r.all(None) if _can_manage(s, me, owner, families)]
        if not mine:
            return
        st.markdown("**Series**")
        fam_of = {f.id: f.name for f in catalog.families}
        df = pd.DataFrame([{"Title": s.title, "Kind": rh.KINDS[s.kind], "Family": fam_of.get(s.family, "Whole practice" if s.kind != rh.WEEKLY else s.family), "Lead": s.lead, "Day": rh.WEEKDAYS[s.weekday],
                            "Week of month": rh.WEEKS.get(s.week, "first") if s.kind == rh.MONTHLY else "", "Time": s.time, "Minutes": s.minutes,
                            "Every (weeks)": s.every, "Exam date": s.end, "Place": s.place, "Active": s.active} for s in mine])
        cc = st.column_config
        with st.form(f"rh_series_form_{len(mine)}", border=False, enter_to_submit=False):
            ed = st.data_editor(df, hide_index=True, width="stretch", key=f"rh_series_{len(mine)}", disabled=["Kind", "Family"], column_config={
                "Day": cc.SelectboxColumn("Day", options=rh.WEEKDAYS, required=True),
                "Week of month": cc.SelectboxColumn("Week of month", options=["", *rh.WEEKS.values()], help="Monthly review only"),
                "Minutes": cc.NumberColumn("Minutes", min_value=15, max_value=240, step=15),
                "Every (weeks)": cc.NumberColumn("Every (weeks)", min_value=1, max_value=4, step=1, help="2 = every other week"),
                "Lead": cc.SelectboxColumn("Lead", options=list(dict.fromkeys([s.lead for s in mine] + list(ctx[0]) + [c for c in ctx[1].values() if c]))),
                "Active": cc.CheckboxColumn("Active")})
            save_series = st.form_submit_button("Save the series", key="rh_series_save", type="primary")
        a, b = st.columns([1, 2])
        if save_series:
            week_of = {v: k for k, v in rh.WEEKS.items()}
            try:
                for s, row in zip(mine, ed.to_dict("records")):
                    r.update(s.id, title=row["Title"], lead=row["Lead"] or "", weekday=rh.WEEKDAYS.index(row["Day"]), week=week_of.get(row["Week of month"] or "first", 1),
                             time=str(row["Time"]).strip(), minutes=int(row["Minutes"]), every=int(row["Every (weeks)"]), end=row["Exam date"] or "",
                             place=row["Place"] or "", active=bool(row["Active"]))
                st.toast("Series saved.")
                st.rerun()
            except ValueError as e:
                st.error(str(e))
        pick = b.selectbox("Invitation for", [s.id for s in mine], format_func=lambda i: next(s.title for s in mine if s.id == i), key="rh_inv_pick")
        _invite(r, r.get(pick), ctx, me, key="rh_inv_dl", label="📅 Download the invitation for everyone in it (.ics)")
        with st.popover("🗑 Delete a series"):
            gone = st.selectbox("Series", [s.id for s in mine], format_func=lambda i: next(s.title for s in mine if s.id == i), key="rh_del_pick")
            if st.button("Delete it with its actions", key="rh_del"):
                r.delete(gone)
                st.rerun()
