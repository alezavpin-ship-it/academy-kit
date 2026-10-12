"""The «Demanda» tab (owners and champions): what the role requests ask for, what belongs to the practice, what has a course."""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from academy import demand, demand_exec, demand_pdf
from academy.catalog import load_materials
from academy.practice import load_practice


@st.cache_data(show_spinner=False)
def _rows(path: str, stamp: int) -> list[dict]:
    return demand.load(path)


@st.cache_data(show_spinner=False)
def _report_pdf(signature: tuple, lang: str, now: str, _a: dict, _practice, _tr: dict) -> bytes | None:
    """The PDF for the current data (None without reportlab); rebuilt only when a roles file, the practice or the content changes."""
    return demand_pdf.to_pdf(_a, _practice, now, _tr) if demand_pdf.available() else None


@st.cache_data(show_spinner=False)
def _exec_pdf(signature: tuple, now: str, source: str, bench_key: tuple, _a: dict, _practice, _b: dict, _tr: dict) -> bytes | None:
    return demand_exec.to_pdf(_a, _practice, _b, source, now, _tr) if demand_pdf.available() else None


def _bench(conn, a: dict) -> dict[str, int] | None:
    """People at level 3+ in the team inventory for the demanded practice skills (None without the database)."""
    if conn is None:
        return None
    from academy.inventory import Inventory

    ids = [r["_entry"].skill_id for r in a["skills"] if r["_scope"] != "outside" and r.get("_entry") is not None and r["_entry"].skill_id]
    try:
        return Inventory(conn).coverage(ids)
    except Exception:  # an inventory not created yet
        return None


def _executive(a: dict, practice, tr: dict, catalog, conn, source: str, now: str, stamp: str, signature: tuple, col) -> None:
    """Owners: the executive summary on screen and as a two-page PDF."""
    bench = _bench(conn, a)
    b = demand_exec.brief(a, tr, bench, catalog)
    pdf = _exec_pdf(signature, now, source, tuple(sorted((bench or {}).items())), a, practice, b, tr)
    if pdf:
        col.download_button("Executive report (PDF)", pdf, file_name=f"demand_executive_report_{stamp}.pdf", mime="application/pdf",
                            key="dm_exec", width="stretch", type="primary", help="Two pages for the leadership: key messages, top skills "
                            "against the bench and the courses, recommended actions with their owner, trend.")
    with st.expander("📌 Executive summary (owners)", expanded=False):
        for m in b["messages"]:
            st.markdown(f"- {m}")
        if b["actions"]:
            st.markdown("**Recommended actions**")
            st.dataframe(pd.DataFrame(b["actions"]), hide_index=True, width="stretch")


def _signature() -> tuple:
    from academy import content_xlsx as content
    from academy.catalog import catalog_path, materials_path
    from academy.practice import practice_path

    files = [f for _, f in demand.snapshots()] + [demand.demand_path(), practice_path(), catalog_path(), materials_path()] + content.pack_files()
    return tuple((str(f), f.stat().st_mtime_ns) for f in files if f.exists())


def _import_box(lang: str, current: list[dict], owner: bool = False) -> None:
    path = demand.demand_path()
    with st.expander("📥 Load the roles file (CSV or Excel) · template and test data",
                     expanded=not current):
        st.markdown((f"The analysis reads **`{path}`**. You can replace that file directly (same header) or upload it here. "
                      f"Columns: {len(demand.COLUMNS)}, those of the roles report; only *Role ID*, *Role Title* and *Role Primary Skill* are mandatory."))
        c = st.columns(3)
        c[0].download_button("Empty template (CSV)", demand.to_csv([]), file_name="demand_roles_template.csv",
                             mime="text/csv", key="dm_tpl", width="stretch")
        c[1].download_button("Test CSV (48 made-up roles)", demand.to_csv(demand.sample_rows()),
                             file_name="demand_roles_sample.csv", mime="text/csv", key="dm_sample", width="stretch")
        if c[2].button("Use the test data", key="dm_use_sample", width="stretch", disabled=bool(current),
                       help="Only while there is no roles file yet. It loads two made-up weeks so the trend shows too."):
            for day, sample in demand.sample_history():
                demand.save_snapshot(sample, day)
            st.rerun()
        st.info("🔒 **Confidential data.** A roles file you upload here is **only read**: the analysis runs in memory for this session and "
                "nothing is saved. An owner can choose to save it so the academy keeps it and follows the trend week over week.")
        up = st.file_uploader("Roles file", type=["csv", "xlsx"], key="dm_up")
        if up is not None:
            rows, problems = demand.parse(up.getvalue())
            for e in problems:
                (st.warning if rows else st.error)(e)
            if rows:
                st.session_state["dm_session"] = {"name": up.name, "rows": rows, "date": demand.snapshot_date(rows)}
                a, b = st.columns([2, 3])
                b.caption(f"{len(rows)} roles read from «{up.name}» · analyzed below, not saved.")
                if owner:
                    day = a.text_input("Date of this upload (YYYY-MM-DD)", value=demand.snapshot_date(rows),
                                       key=f"dm_day_{up.name}", help=("Saved uploads are kept with their date to compare the demand week over week. "
                                                                       "An existing upload with that date is replaced."))
                    if b.button("Save it in the app (owners) to follow the trend", key="dm_save", width="stretch"):
                        try:
                            demand.save_snapshot(rows, day.strip())
                        except ValueError:
                            st.error("The date must be YYYY-MM-DD.")
                        else:
                            st.session_state.pop("dm_session", None)
                            st.rerun()
                else:
                    a.caption("Only an owner can save a roles file in the app.")
        snaps = demand.snapshots()
        if snaps:
            st.caption("Saved uploads: " + " · ".join(d for d, _ in snaps)
                       + f" (folder `{demand.history_dir()}`; delete a file there to remove that upload).")


def demand_tab(catalog, packs: list, lang: str, owner: bool = False, conn=None) -> None:
    path = demand.demand_path()
    demand.sync_history()  # a roles file replaced by hand becomes one more dated upload
    rows = _rows(str(path), path.stat().st_mtime_ns) if path.exists() else []
    practice = load_practice()
    st.markdown(f"Which skills, technologies and roles are being requested, which belong to the **{practice.name or '—'}** practice and which already have a course in the academy.")
    _import_box(lang, rows, owner)
    session = st.session_state.get("dm_session")
    if session:  # a file read in this session only: analyzed, not saved
        c = st.columns([5, 1])
        c[0].warning(f"Showing «{session['name']}» ({len(session['rows'])} roles, {session['date']}): read in memory for this session, **not saved**.")
        if c[1].button("Close it", key="dm_close", width="stretch"):
            st.session_state.pop("dm_session", None)
            st.rerun()
        rows = session["rows"]
    if not practice.skills:
        st.warning("The practice is not defined yet: fill in the Practica, PracticaSkills and PracticaRoles tables of the content file.")
    if not rows:
        st.info("There is no roles file yet. Load one or use the test data.")
        return
    a = demand.analyze(rows, practice, catalog, packs, load_materials(), lang)
    k, s = a["keys"], a["summary"]
    m = st.columns(6)
    for col, (label, value) in zip(m, (("Roles", s["roles"]),
                                        ("In the practice", f"{s['in_practice_pct']} %"),
                                        ("Outside the practice", s["outside"]),
                                        ("Clients", s["clients"]), ("Distinct skills", s["skills"]),
                                        ("Practice skills without a course", s["no_course"]))):
        col.metric(label, value, border=True)
    stamp, now = datetime.now().strftime("%Y-%m-%d"), datetime.now().strftime("%Y-%m-%d %H:%M")
    history = [(day, _rows(str(f), f.stat().st_mtime_ns)) for day, f in demand.snapshots()]
    if session:  # the file read for this session is compared with the saved uploads (it replaces a saved one of the same date)
        history = sorted([h for h in history if h[0] != session["date"]] + [(session["date"], rows)], key=lambda h: h[0])
    tr = demand.trend(history, practice, lang)
    d = st.columns(4 if owner else 3)
    sig = _signature() + ((("session", session["name"], session["date"], len(rows)),) if session else ())
    if owner:
        source = (f"«{session['name']}» ({session['date']}), read for this session only, not saved" if session
                  else f"saved upload of {history[-1][0]}" if history else "roles file")
        _executive(a, practice, tr, catalog, conn, source, now[:13] + ":00", stamp, sig, d[3])
    pdf = _report_pdf(sig, lang, now[:13] + ":00", a, practice, tr)  # rebuilt when the data changes, or once an hour
    if pdf:
        d[0].download_button("Detailed report (PDF)", pdf,
                             file_name=f"demand_analysis_{stamp}.pdf", mime="application/pdf", key="dm_pdf",
                             width="stretch", type="secondary" if owner else "primary")
    else:
        d[0].button("Detailed report (PDF)", disabled=True, key="dm_pdf_off", width="stretch",
                    help="The PDF component is missing: close the app, double-click «Install components.bat» (in the app folder) and open it again.")
    d[1].download_button("Requested skills (CSV)",
                         pd.DataFrame(demand.visible(a["skills"])).to_csv(index=False).encode("utf-8-sig"),
                         file_name=f"requested_skills_{stamp}.csv", mime="text/csv", key="dm_csv", width="stretch")
    d[2].download_button("New skills for the catalog (CSV)", demand.catalog_suggestions(a),
                         file_name="suggested_skills.csv", mime="text/csv", key="dm_sug", width="stretch",
                         help="Practice skills in demand that are not in the catalog, with the columns of the Skills tab of the content workbook: copy the rows and paste them at the end of that tab.")
    ch = demand.charts(a)
    st.markdown(f"<style>{demand.CHART_CSS}</style>" + ch["share"] + demand.legend(lang), unsafe_allow_html=True)
    tabs = st.tabs(["Skills", "Trend", "Roles and primary skill",
                    "Outside the practice", "Demand against courses",
                    "Other views", "Practice definition", "Gaps per role (matrix)"])
    css = ""  # the chart styles were written once, above
    with tabs[0]:
        st.markdown(css + ch["skills"], unsafe_allow_html=True)
        st.dataframe(pd.DataFrame(demand.visible(a["skills"])), hide_index=True, width="stretch")
    with tabs[1]:
        if len(tr["dates"]) < 2:
            st.info(f"There is a single upload ({', '.join(tr['dates']) or '—'}). The trend shows once you save the next one (for example, next week's).")
        else:
            tc, tk = demand.trend_charts(tr), tr["keys"]
            st.markdown(f"**{len(tr['dates'])} uploads**, from {tr['dates'][0]} to {tr['dates'][-1]}. Changes compare the latest with the previous one.")
            st.markdown(tc["lines"] + demand.legend(lang), unsafe_allow_html=True)
            c1, c2 = st.columns(2)
            c1.markdown(tc["up"] or "_No skill grew._", unsafe_allow_html=True)
            c2.markdown(tc["down"] or "_No skill dropped._", unsafe_allow_html=True)
            st.markdown("**Most requested skills in every upload**")
            st.dataframe(pd.DataFrame(demand.visible(tr["skills"])), hide_index=True, width="stretch")
            n1, n2 = st.columns(2)
            n1.markdown(f"**New roles since the previous upload ({len(tr['new_roles'])})**")
            n1.dataframe(pd.DataFrame(tr["new_roles"]), hide_index=True, width="stretch")
            n2.markdown(f"**Roles no longer in the file ({len(tr['gone_roles'])})**")
            n2.dataframe(pd.DataFrame(tr["gone_roles"]), hide_index=True, width="stretch")
            if tr["new_skills"]:
                st.caption("Skills appearing for the first time: " + ", ".join(tr["new_skills"][:40]))
    with tabs[2]:
        c1, c2 = st.columns(2)
        c1.markdown(css + ch["titles"], unsafe_allow_html=True)
        c2.markdown(css + ch["primary"], unsafe_allow_html=True)
        st.markdown("**Role title and primary skill**")
        st.dataframe(pd.DataFrame(demand.visible(a["combos"])), hide_index=True, width="stretch")
    with tabs[3]:
        st.caption("What is requested and is not in PracticaSkills or PracticaRoles. If something does belong to the practice, add it there (or as an alias).")
        st.markdown(css + ch["outside"], unsafe_allow_html=True)
        st.markdown(f"**Roles outside the practice ({len(a['outside_roles'])})**")
        st.dataframe(pd.DataFrame(a["outside_roles"]), hide_index=True, width="stretch")
    with tabs[4]:
        st.caption(("Practice skills in demand, crossed with the academy's content. \"Has a course\" = it has lessons; "
                     "\"Learning path only\" = vendor classes but no lessons of our own; \"Not in the catalog\" = it has to be added to Skills."))
        st.markdown(css + ch["backlog"], unsafe_allow_html=True)
        st.dataframe(pd.DataFrame(demand.visible(a["backlog"])), hide_index=True, width="stretch")
    with tabs[5]:
        names = {"Skill Category": "Skill category", "Client": "Client",
                 "Industry Level 1": "Industry", "Role Country/Territory": "Country",
                 "Role Status": "Role status", "Role Market Unit": "Market unit",
                 "Role Career Level From": "Career level"}
        cols = st.columns(3)
        for i, (name, items) in enumerate(a["by"].items()):
            if items:
                cols[i % 3].markdown(f"**{names.get(name, name)}**")
                cols[i % 3].dataframe(pd.DataFrame(items, columns=[names.get(name, name), "Roles"]), hide_index=True, width="stretch")
        if a["months"]:
            st.markdown("**Roles by start month**")
            st.bar_chart(pd.DataFrame(a["months"], columns=["Month", "Roles"]).set_index("Month"), color="#eb6834")
    with tabs[6]:
        st.markdown(practice.description or "—")
        st.caption("Owners edit it with ✏️ Edit mode at the top of this tab, or in the content workbook (tabs Practice, PracticeSkills and "
                   "PracticeRoles). Another practice (for example ServiceNow) uses the same academy by changing those tables and the skills catalog.")
        st.dataframe(pd.DataFrame([{"Term": t.term, "Aliases": "; ".join(t.aliases), "SkillId": t.skill_id, "FamilyId": t.family, "Vendor": t.vendor,
                                    "Scope": t.scope} for t in practice.skills]), hide_index=True, width="stretch")
        st.dataframe(pd.DataFrame([{"RoleTitle": r.title, "Aliases": "; ".join(r.aliases), "Scope": r.scope} for r in practice.roles]),
                     hide_index=True, width="stretch")
    with tabs[7]:
        st.markdown("**Gaps per role, from the file's «Matrix cross-skills Practice» column**: for every role, the practice capabilities it "
                    "matches and the ones the team lacks, counted across roles and crossed with the academy's content.")
        if a.get("matrix"):
            st.dataframe(pd.DataFrame(a["matrix"]), hide_index=True, width="stretch")
        else:
            st.info("This file has no «Matrix cross-skills Practice» column (or it is empty).")


# ---------------------------------------------------------------------------------------------- results by role family
def family_results_tab(catalog, packs: list, lang: str, families: set[str], team: bool = False) -> None:
    """🔍 Demand → Demand results: one role family's gaps, roles affected and demanded skills against its own skill tree.

    ``families``: the families the person may open (a champion: theirs; the Demand team and owners: all). ``team``: the
    Demand team, who send each family's results to its career path lead."""
    import urllib.parse
    import zipfile

    from academy import demand_family as dfam
    from academy import paths as pathmod

    if not catalog or not catalog.families:
        st.info("The role families are not loaded yet.")
        return
    path = demand.demand_path()
    rows = _rows(str(path), path.stat().st_mtime_ns) if path.exists() else []
    source = f"saved upload of {demand.snapshots()[-1][0]}" if demand.snapshots() else "saved roles file"
    session = st.session_state.get("dm_session") if team else None
    if session:  # the Demand team's file of this session (not saved) is what they are looking at
        rows, source = session["rows"], f"«{session['name']}» ({session['date']}), this session only"
    if not rows:
        st.info("The Demand team has not published a demand analysis yet: the results appear here when they save a roles file.")
        return
    fams = [f for f in catalog.by_gap() if f.id in families]
    if not fams:
        st.info("You do not lead a role family yet.")
        return
    materials = load_materials()
    a = demand.analyze(rows, load_practice(), catalog, packs, materials, lang)
    structure = pathmod.load()
    st.caption(f"What the roles we receive ask of a role family, against the family's own skill tree (its learning paths). Source: {source} · "
               f"{len(rows)} roles.")
    fid = st.selectbox("Role family", [f.id for f in fams], key="dr_family",
                       format_func=lambda k: next(f.name + (f" · lead: {f.champion}" if f.champion else "") for f in fams if f.id == k))
    res = dfam.results(a, catalog, structure, materials, fid)
    s = res["summary"]
    keys = list(s)
    for row in (keys[:4], keys[4:]):
        for col, k in zip(st.columns(4), row):
            col.metric(k, s[k], border=True)
    fam = res["family"]
    stamp = datetime.now().strftime("%Y-%m-%d")
    c = st.columns(3 if team else 1)
    c[0].download_button("📊 Download the results (Excel)", dfam.to_xlsx(res, source), key="dr_xlsx", width="stretch", type="primary",
                         file_name=f"demand_results_{fid}_{stamp}.xlsx",
                         mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    if team:
        to = fam.champion_email or ""
        mail = "mailto:" + urllib.parse.quote(to) + "?" + urllib.parse.urlencode(
            {"subject": f"Demand results · {fam.name} · {stamp}", "body": dfam.message(res)}, quote_via=urllib.parse.quote)
        c[1].link_button(f"✉️ Send to {fam.champion or 'the lead'}", mail, width="stretch", disabled=not to,
                         help="Opens Outlook with a summary for the family's lead; attach the Excel you just downloaded." if to
                         else "This family has no lead e-mail yet (People → champion, or Families → ChampionEmail).")
        buf = __import__("io").BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for f in fams:
                z.writestr(f"demand_results_{f.id}_{stamp}.xlsx", dfam.to_xlsx(dfam.results(a, catalog, structure, materials, f.id), source))
        c[2].download_button("🗂 Every family's results (.zip)", buf.getvalue(), key="dr_zip", width="stretch",
                             file_name=f"demand_results_{stamp}.zip", mime="application/zip")
    t = st.tabs(["Demand vs your skill tree", "Your skill tree", "Gaps and roles affected", "Gaps per role (matrix)"])
    colors = {dfam.IN_TREE: "🟢", dfam.NO_COURSES: "🟡", dfam.SWITCHED_OFF: "🟡", dfam.NOT_IN_TREE: "🔴"}

    def table(rows_: list[dict], empty: str) -> None:
        if not rows_:
            st.info(empty)
            return
        df = pd.DataFrame(dfam.visible(rows_))
        if "Your skill tree" in df:
            df["Your skill tree"] = [f"{colors.get(v, '')} {v}" for v in df["Your skill tree"]]
        st.dataframe(df, hide_index=True, width="stretch")

    with t[0]:
        st.caption("🟢 in a learning path with required courses · 🟡 in your tree without courses (or switched off) · 🔴 requested and "
                   "not in your tree: a candidate for a new skill or learning path.")
        table(res["demand"], "No skill of this family appears in the current demand.")
    with t[1]:
        st.caption("Your family's skills in its active learning paths, most requested first. A skill nobody asks for now may still be "
                   "foundational: check it before switching it off.")
        table(res["tree"], "The family has no active learning path yet.")
    with t[2]:
        st.caption(f"From the skills catalog (the team's gap report): gap volume {fam.gap_volume or 0}, {fam.role_impact or 0} roles affected.")
        table(res["gaps"], "No gap recorded for this family's skills.")
    with t[3]:
        st.caption("The skills the role requests list for this family in «Matrix cross-skills Practice».")
        table(res["matrix"], "The requests do not name this family in their practice matrix.")
