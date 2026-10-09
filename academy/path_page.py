"""The Learning route tab, in the structure the practice runs:

    Role family -> Vendor -> Learning path (with its certification) -> Skill -> Module -> Course

A learner sees their family (People.Families, the first one) and the learning paths of their job role (People.CourseRole,
set by owners and champions); they can switch to all the paths of the family or look at another family. Each course
opens where it lives (SharePoint, Percipio, Workday MyLearning, the vendor's site, a repo or a file of the academy) and is
marked done here.

The family's champion (and the owners) get «🧭 Manage the learning paths of …»: job roles, learning paths, skills,
courses and certifications, each one switched on and off without deleting it.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from academy import paths as pathmod
from academy import ui
from academy.catalog import load_materials
from academy.route import ITEM_POINTS, RouteTracker, family_route

LEVEL_ICON = {"required": "🔴 required", "desirable": "🟡 desirable", "off": "⚪ off"}


def _person(learner: str):
    from academy import people

    return people.find([p for p in people.load() if p.active], learner)


def route_tab(catalog, conn, learner: str, lang: str = "en", manage: set[str] | None = None) -> None:
    if not catalog or not catalog.families:
        st.info("The role families are not loaded yet. An owner loads them in ✏️ Edit mode or with the content workbook.")
        return
    materials = load_materials()
    structure = pathmod.load()
    person = _person(learner)
    mine = [f for f in (person.families if person else ()) if any(x.id == f for x in catalog.families)]
    fams = {f.id: f.name for f in catalog.families}
    order = mine + [f for f in fams if f not in mine]
    st.markdown("Your learning path follows the practice's structure: **role family → vendor → learning path → skill → module → "
                "course**. Open each course where it lives (SharePoint, Percipio, Workday, the vendor's site, a repo…), complete it "
                "and mark it here.")
    c = st.columns([2, 2])
    fid = c[0].selectbox("Role family", order, key="rt_family", format_func=lambda k: fams[k] + ("  · yours" if k in mine else ""))
    role = structure.role_of(fid, person.course_role) if person and fid in mine else None
    roles = structure.roles_of(fid)
    view = None
    if roles:
        opts = ["*"] + [r.id for r in roles]
        names = {"*": "All job roles", **{r.id: r.name for r in roles}}
        default = role.id if role else "*"
        if st.session_state.get(f"rt_role_{fid}") not in opts:
            st.session_state[f"rt_role_{fid}"] = default
        view = c[1].selectbox("Job role", opts, key=f"rt_role_{fid}", format_func=lambda k: names[k] + ("  · yours" if role and k == role.id else ""),
                              help="Your job role is set by your champion; pick another one to look at its path.")
        view = None if view == "*" else view
    elif person and person.course_role and fid in mine:
        c[1].caption(f"Job role: **{person.course_role}** (not defined in this family yet: you see every path)")
    if fid in (manage or set()):
        manage_paths(catalog, conn, fid, structure, learner)
        structure = pathmod.load()
    route = family_route(catalog, materials, structure, fid, view)
    tr = RouteTracker(conn, learner)
    done = tr.done()
    got, total = tr.progress(route)
    nxt = tr.next_step(route)
    m = st.columns(4)
    m[0].metric("Courses completed", f"{got} / {total}", border=True)
    m[1].metric("Learning paths", len(route.paths), border=True)
    m[2].metric("Route points", f"{tr.total_points():,}", border=True)
    m[3].metric("Next course", nxt.skill if nxt else ("✅" if total else "—"), border=True)
    st.progress(got / total if total else 0.0)
    _certs(conn, learner, fid, view, structure)
    fb = st.session_state.pop("rt_fb", None)
    if fb is not None:
        st.toast("Course completed!" + (f" +{fb} pts" if fb else ""))
    if not route.paths:
        st.info("This family has no active learning paths for this job role yet. Its champion adds them in «🧭 Manage the learning paths».")
        return
    vendors = list(dict.fromkeys(structure.vendor_name(p.vendor) for p in route.paths))
    vendor = "*"
    if len(vendors) > 1:
        vendor = st.segmented_control("Vendor", ["*"] + vendors, default="*", key=f"rt_vendor_{fid}",
                                      format_func=lambda v: "All" if v == "*" else v) or "*"
    by_path: dict[str, list] = {}
    for stp in route.steps:
        by_path.setdefault(stp.path, []).append(stp)
    for path in route.paths:
        vname = structure.vendor_name(path.vendor)
        if vendor != "*" and vname != vendor:
            continue
        steps = by_path.get(path.id, [])
        n_done = sum(1 for s in steps if s.key in done)
        head = f"🧭 {path.name}" + ("" if vname.lower() in path.name.lower() else f" · {vname}") + (f" · 🏅 {path.cert}" if path.cert else "") \
            + f" — {n_done}/{len(steps)} courses"
        with st.expander(head, expanded=bool(nxt and nxt.path == path.id) or len(route.paths) == 1):
            if path.description:
                st.caption(path.description)
            if not steps:
                st.caption("No required courses yet.")
            _path_body(catalog, path, steps, done, nxt, tr, structure, materials)
    if nxt:
        from academy import assistant as ai
        from academy.exam_page import assistant_box

        target = next((s.target for s in catalog.skills if s.id == nxt.skill_id), "")
        assistant_box(ai.prompt_step_coach(route.family, nxt.skill, nxt.title, nxt.provider, target, lang=lang), lang, f"coach_{nxt.key}",
                      "Get ready for your next step with the AI tutor")
    if route.uncovered:
        st.caption("Skills without required courses yet: " + ", ".join(route.uncovered) + ".")


def _path_body(catalog, path, steps, done, nxt, tr, structure, materials) -> None:
    from academy.family_page import download_step

    for sk in structure.skills_of(path.id, catalog):
        mine = [s for s in steps if s.skill_id == sk.id]
        extra = [m for m in materials.get(sk.id, []) if str(m.get("status") or "") == "optional"]
        if not mine and not extra:
            continue
        st.markdown(f"##### {sk.name}")
        st.caption(f"{sum(s.key in done for s in mine)} / {len(mine)} courses" + (f" · {sk.category}" if sk.category else ""))
        modules: dict[str, list] = {}
        for s in mine:
            modules.setdefault(s.module or pathmod.DEFAULT_MODULE, []).append(s)
        for module, items in modules.items():
            if len(modules) > 1 or module != pathmod.DEFAULT_MODULE:
                st.markdown(f"**📦 {module}**")
            for stp in items:
                ok = stp.key in done
                with st.container(border=True):
                    a, b, c = st.columns([5, 2, 2])
                    icon = pathmod.KIND_ICON.get(stp.kind, "🎓")
                    a.markdown(f"{'✅' if ok else '🟠' if nxt and stp.key == nxt.key else '○'} {icon} **{stp.number}. {stp.title}**")
                    a.caption(" · ".join(x for x in (stp.kind, stp.location, stp.provider, f"{stp.minutes} min" if stp.minutes else "") if x))
                    if not download_step(stp.url, stp.title, f"rt_dl_{stp.key}", b):
                        b.link_button("Open ↗", stp.url, width="stretch")
                    if ok:
                        ev = done[stp.key]
                        c.caption("Completed" + (f" · [evidence]({ev})" if ev.startswith("https://") else ""))
                    else:
                        with c.popover(f"Done (+{ITEM_POINTS})", width="stretch"):
                            with st.form(f"rt_form_{stp.key}", border=False, enter_to_submit=False):
                                ev = st.text_input("Link to your achievement (optional)", key=f"rt_ev_{stp.key}", placeholder="https://…")
                                if st.form_submit_button("Mark as completed", type="primary", key=f"rt_done_{stp.key}"):
                                    st.session_state["rt_fb"] = tr.complete(stp, ev)
                                    ui.fx("step")
                                    st.rerun()
        if extra:
            with st.expander(f"Optional material for {sk.name} ({len(extra)})"):
                from academy.exam_page import material_links

                material_links(extra)


def _certs(conn, learner: str, fid: str, role: str | None, structure) -> None:
    """The certifications the family asks for (for the job role in view), with the ones the person holds."""
    from academy.certs import CURRENT, DESIRED, REQUIRED, Certs

    c = Certs(conn)
    reqs = c.requirements({fid}, role)
    if not reqs:
        return
    mine = {r["Code"]: r["Status"] for r in c.records(learner.strip() or "me")}
    chips = []
    for r in reqs:
        state = "✅" if mine.get(r["Code"]) == CURRENT else "🎯" if mine.get(r["Code"]) == DESIRED else ("🔴" if r["Level"] == REQUIRED else "🟡")
        chips.append(f"{state} **{r['Code']}** {r['Name']}".strip())
    st.markdown("**Certifications of this path** — " + " · ".join(chips))
    st.caption("✅ you hold it · 🎯 you are aiming for it · 🔴 required · 🟡 desirable. Register yours in the Certifications tab.")


# ------------------------------------------------------------------------------------------------ the champion's panel
def manage_paths(catalog, conn, fid: str, structure, who: str) -> None:
    """Job roles, learning paths, skills, courses and certifications of one family: on / off, order, roles, certification."""
    from academy.family_page import manage_family

    fam = next(f for f in catalog.families if f.id == fid)
    with st.expander(f"🧭 Manage the learning paths of {fam.name} (champion)"):
        st.caption("Switch anything on or off without deleting it. Learners see the active learning paths of their job role, the active "
                   "skills in them and the required courses; optional courses are shown as recommended material.")
        t = st.tabs(["Job roles", "Learning paths", "Skills", "Courses", "Certifications"])
        with t[0]:
            _roles_editor(structure, fid, catalog)
        with t[1]:
            _paths_editor(structure, fid, catalog)
        with t[2]:
            _skills_editor(structure, fid, catalog)
        with t[3]:
            manage_family(catalog, fid, who, embedded=True)
        with t[4]:
            _certs_editor(conn, structure, fid)


def _saved(structure) -> None:
    from academy import content_sync

    pathmod.save(structure)
    content_sync.refresh()
    st.cache_data.clear()
    ui.fx("ok")
    st.toast("Saved.")
    st.rerun()


def _yes(v) -> bool:
    return bool(v) and not (isinstance(v, float) and pd.isna(v))


def _roles_editor(structure, fid: str, catalog) -> None:
    rows = [{"RoleId": r.id, "Name": r.name, "Description": r.description, "Active": r.active} for r in structure.roles_of(fid, active_only=False)]
    with st.form(f"pm_roles_{fid}_{len(rows)}", border=False, enter_to_submit=False):
        ed = st.data_editor(pd.DataFrame(rows, columns=["RoleId", "Name", "Description", "Active"]).astype({"RoleId": "string", "Name": "string",
                                                                                                         "Description": "string"}),
                            num_rows="dynamic", hide_index=True, width="stretch", key=f"pm_roles_ed_{fid}_{len(rows)}",
                            column_config={"RoleId": st.column_config.TextColumn("RoleId", help="Short id; made from the name when empty"),
                                           "Name": st.column_config.TextColumn("Job role", required=True),
                                           "Active": st.column_config.CheckboxColumn("Active", default=True)})
        save = st.form_submit_button("💾 Save the job roles", type="primary", key=f"pm_roles_save_{fid}")
    if save:
        new = []
        for r in ed.to_dict("records"):
            name = "" if pd.isna(r["Name"]) else str(r["Name"]).strip()
            if name:
                rid = ("" if pd.isna(r["RoleId"]) else str(r["RoleId"]).strip()) or pathmod.slug(name)
                new.append(pathmod.JobRole(rid, fid, name, "" if pd.isna(r["Description"]) else str(r["Description"]), _yes(r["Active"])))
        if len({r.id for r in new}) < len(new):
            st.error("A RoleId is repeated.")
            return
        _saved(pathmod.Structure(structure.vendors, [r for r in structure.roles if r.family != fid] + new, structure.paths, structure.skills))


def _paths_editor(structure, fid: str, catalog) -> None:
    roles = structure.roles_of(fid, active_only=False)
    vendors = [v.id for v in structure.vendors]
    rows = [{"PathId": p.id, "Name": p.name, "Vendor": p.vendor, "Certification": p.cert, "Job roles": list(p.roles), "Order": p.order or None,
             "Active": p.active, "Description": p.description} for p in structure.paths_of(fid, active_only=False)]
    df = pd.DataFrame(rows, columns=["PathId", "Name", "Vendor", "Certification", "Job roles", "Order", "Active", "Description"])
    for col in ("PathId", "Name", "Vendor", "Certification", "Description"):
        df[col] = df[col].astype("string")
    df["Order"] = pd.to_numeric(df["Order"], errors="coerce").astype("Int64")
    st.caption("A learning path groups the skills of one vendor towards a goal, usually a certification (e.g. AZ-900). Job roles empty = "
               "every role of the family. New vendors: add them in ✏️ Edit mode → Vendors (or type the id here; it is created).")
    with st.form(f"pm_paths_{fid}_{len(rows)}", border=False, enter_to_submit=False):
        ed = st.data_editor(df, num_rows="dynamic", hide_index=True, width="stretch", key=f"pm_paths_ed_{fid}_{len(rows)}", column_config={
            "PathId": st.column_config.TextColumn("PathId", help="Short id; made from the name when empty"),
            "Name": st.column_config.TextColumn("Learning path", required=True),
            "Vendor": st.column_config.SelectboxColumn("Vendor", options=list(dict.fromkeys(vendors + ["MSFT", "CISCO", "AWS", "GCP"])), required=True),
            "Certification": st.column_config.TextColumn("Certification", help="Exam code, e.g. AZ-900 (optional)"),
            "Job roles": st.column_config.MultiselectColumn("Job roles", options=[r.id for r in roles], help="Empty = every role")
            if hasattr(st.column_config, "MultiselectColumn") else st.column_config.ListColumn("Job roles"),
            "Order": st.column_config.NumberColumn("Order", min_value=1, step=1),
            "Active": st.column_config.CheckboxColumn("Active", default=True)})
        save = st.form_submit_button("💾 Save the learning paths", type="primary", key=f"pm_paths_save_{fid}")
    if save:
        new, vend = [], list(structure.vendors)
        for r in ed.to_dict("records"):
            name = "" if pd.isna(r["Name"]) else str(r["Name"]).strip()
            if not name:
                continue
            vid = ("" if pd.isna(r["Vendor"]) else str(r["Vendor"]).strip().upper()) or "OTHER"
            if not any(v.id == vid for v in vend):
                vend.append(pathmod.Vendor(vid, vid))
            pid = ("" if pd.isna(r["PathId"]) else str(r["PathId"]).strip()) or f"{fid}-{pathmod.slug(name)}"
            jr = r["Job roles"] if isinstance(r["Job roles"], (list, tuple)) else []
            new.append(pathmod.LearningPath(pid, fid, vid, name, "" if pd.isna(r["Certification"]) else str(r["Certification"]).strip().upper(),
                                            tuple(jr), 0 if pd.isna(r["Order"]) else int(r["Order"]), _yes(r["Active"]),
                                            "" if pd.isna(r["Description"]) else str(r["Description"])))
        others = [p for p in structure.paths if p.family != fid]
        if len({p.id for p in new + others}) < len(new + others):
            st.error("A PathId is repeated (ids are unique in the practice).")
            return
        out = pathmod.Structure(vend, structure.roles, others + new, structure.skills)
        errs = pathmod.validate(out, catalog)
        if errs:
            st.error("\n\n".join(errs[:10]))
            return
        _saved(out)


def _skills_editor(structure, fid: str, catalog) -> None:
    paths = structure.paths_of(fid, active_only=False)
    names = {p.id: p.name for p in paths}
    rows = [{"SkillId": s.id, "Skill": s.name, "Learning path": names.get(structure.place(s.id).path, structure.place(s.id).path),
             "Order": structure.place(s.id).order or None, "Active": structure.place(s.id).active} for s in catalog.in_family(fid)]
    df = pd.DataFrame(rows, columns=["SkillId", "Skill", "Learning path", "Order", "Active"])
    df["Order"] = pd.to_numeric(df["Order"], errors="coerce").astype("Int64")
    st.caption("Place each skill of the family in a learning path, in order. New skills are added in ✏️ Edit mode → Skills.")
    with st.form(f"pm_skills_{fid}_{len(rows)}", border=False, enter_to_submit=False):
        ed = st.data_editor(df, hide_index=True, width="stretch", key=f"pm_skills_ed_{fid}", disabled=["SkillId", "Skill"], column_config={
            "Learning path": st.column_config.SelectboxColumn("Learning path", options=list(names.values()), required=True),
            "Order": st.column_config.NumberColumn("Order", min_value=1, step=1),
            "Active": st.column_config.CheckboxColumn("Active")})
        save = st.form_submit_button("💾 Save the skills", type="primary", key=f"pm_skills_save_{fid}")
    if save:
        by_name = {v: k for k, v in names.items()}
        skills = dict(structure.skills)
        for r in ed.to_dict("records"):
            skills[r["SkillId"]] = pathmod.Placement(by_name.get(r["Learning path"], structure.place(r["SkillId"]).path),
                                                     0 if pd.isna(r["Order"]) else int(r["Order"]), _yes(r["Active"]))
        _saved(pathmod.Structure(structure.vendors, structure.roles, structure.paths, skills))


def _certs_editor(conn, structure, fid: str) -> None:
    from academy.certs import Certs

    c = Certs(conn)
    roles = structure.roles_of(fid, active_only=False)
    cur = c.requirements({fid}, include_off=True)
    df = pd.DataFrame([{"Code": r["Code"], "Name": r["Name"], "Vendor": r["Vendor"],
                        "Job roles": [x.strip() for x in r["Roles"].split(";") if x.strip()], "Level": r["Level"], "Url": r["Url"]} for r in cur],
                      columns=["Code", "Name", "Vendor", "Job roles", "Level", "Url"])
    for col in ("Code", "Name", "Vendor", "Level", "Url"):
        df[col] = df[col].astype("string")
    st.caption("The certifications this family asks for, per job role (empty = every role). Level off keeps it in the plan without asking for it.")
    with st.form(f"pm_certs_{fid}_{len(cur)}", border=False, enter_to_submit=False):
        ed = st.data_editor(df, num_rows="dynamic", hide_index=True, width="stretch", key=f"pm_certs_ed_{fid}_{len(cur)}", column_config={
            "Code": st.column_config.TextColumn("Code", required=True, help="AZ-500, SC-200, CCNA…"),
            "Name": st.column_config.TextColumn("Certification"),
            "Vendor": st.column_config.SelectboxColumn("Vendor", options=[v.name for v in structure.vendors] or ["Microsoft"]),
            "Job roles": st.column_config.MultiselectColumn("Job roles", options=[r.id for r in roles], help="Empty = every role")
            if hasattr(st.column_config, "MultiselectColumn") else st.column_config.ListColumn("Job roles"),
            "Level": st.column_config.SelectboxColumn("Level", options=["required", "desirable", "off"], required=True, default="desirable"),
            "Url": st.column_config.LinkColumn("Official page", validate=r"^https://.+")})
        save = st.form_submit_button("💾 Save the certifications", type="primary", key=f"pm_certs_save_{fid}")
    if save:
        rows = []
        for r in ed.to_dict("records"):
            if pd.isna(r["Code"]) or not str(r["Code"]).strip():
                continue
            jr = r["Job roles"] if isinstance(r["Job roles"], (list, tuple)) else []
            rows.append({"Code": str(r["Code"]), "Name": "" if pd.isna(r["Name"]) else str(r["Name"]), "Vendor": "" if pd.isna(r["Vendor"]) else str(r["Vendor"]),
                         "Roles": "; ".join(jr), "Level": "" if pd.isna(r["Level"]) else str(r["Level"]), "Url": "" if pd.isna(r["Url"]) else str(r["Url"])})
        c.set_requirements(fid, rows)
        ui.fx("ok")
        st.toast("Certifications saved.")
        st.rerun()


# ------------------------------------------------------------------------------------------------ the dashboard
def hero(catalog, conn, learner: str, pack, tracker) -> None:
    """The first thing on the page: the next course of the person's learning path, their progress, certifications and rank."""
    import html

    from academy.certs import CURRENT, REQUIRED, Certs

    person = _person(learner)
    structure = pathmod.load() if catalog else None
    fam = next((f for f in (person.families if person else ()) if catalog and any(x.id == f for x in catalog.families)), None)
    route = None
    if catalog and fam:
        role = structure.role_of(fam, person.course_role) if person else None
        route = family_route(catalog, load_materials(), structure, fam, role.id if role else None)
    rt = RouteTracker(conn, learner)
    done = rt.done()
    got, total = (rt.progress(route) if route else (0, 0))
    nxt = rt.next_step(route) if route else None
    certs = Certs(conn)
    reqs = certs.requirements({fam}, (structure.role_of(fam, person.course_role).id if person and structure.role_of(fam, person.course_role) else None)) \
        if fam else []
    held = {r["Code"] for r in certs.records(learner.strip() or "me") if r["Status"] == CURRENT}
    need = [r["Code"] for r in reqs if r["Level"] == REQUIRED]
    pts = tracker.total_points() + rt.total_points()
    cur, to_go = tracker.rank(pts)
    to_next = f"{to_go} to reach {pack.ranks[cur + 1].name}" if to_go is not None else "top rank"
    tiles = "".join(f'<div class="ak-tile"><b>{html.escape(str(v))}</b><span>{html.escape(k)}</span><small>{html.escape(note)}</small></div>'
                    for k, v, note in (("Courses completed", f"{got} / {total}", ""),
                                       ("Required certifications", f"{sum(1 for c in need if c in held)} / {len(need)}", ", ".join(need[:3])),
                                       ("Points", f"{pts:,}", to_next),
                                       ("Rank", pack.ranks[cur].name, "")))
    fam_name = next((f.name for f in catalog.families if f.id == fam), "") if catalog and fam else ""
    with st.container(key="ak_hero"):
        left, right = st.columns([3, 2], gap="large")
        with right:
            st.markdown(f'<div class="ak-tiles">{tiles}</div>', unsafe_allow_html=True)
        with left:
            if route is None:
                st.markdown(f'<div class="ak-eyebrow"><b class="ak-pill">Getting started</b></div>'
                            f'<h2 class="ak-hero-title">{html.escape(pack.title)}</h2>'
                            '<p class="ak-hero-sum">Your role family and job role are set by your champion in People. Meanwhile, explore the '
                            'learning paths of every family in the Learning route tab.</p>', unsafe_allow_html=True)
            elif nxt is None:
                st.markdown(f'<div class="ak-eyebrow"><b class="ak-pill">{"Path complete" if total else "Getting ready"}</b>'
                            f'<span>{html.escape(fam_name)}</span></div>'
                            f'<h2 class="ak-hero-title">{"You completed every course of your path." if total else "Your path has no courses yet."}</h2>'
                            '<p class="ak-hero-sum">Prepare your certifications and help others in the Forum.</p>', unsafe_allow_html=True)
            else:
                st.markdown(f'<div class="ak-eyebrow"><b class="ak-pill">Your next course</b>'
                            f'<span>{html.escape(fam_name)} · {html.escape(nxt.path_name)} · {html.escape(nxt.skill)}</span></div>'
                            f'<h2 class="ak-hero-title">{html.escape(nxt.title)}</h2>'
                            f'<p class="ak-hero-sum">{html.escape(" · ".join(x for x in (nxt.module, nxt.kind, nxt.location, nxt.provider, f"{nxt.minutes} min" if nxt.minutes else "") if x))}</p>',
                            unsafe_allow_html=True)
                if str(nxt.url).startswith("https://"):
                    st.link_button("Open the course ↗", nxt.url, type="primary")
        pct = 100 * got / total if total else 0
        st.markdown(ui.bar_html(pct, "Your learning path", f"· {got} of {total} courses completed",
                                f"{total - got} courses left" if total - got else ("Path complete" if total else "")), unsafe_allow_html=True)

