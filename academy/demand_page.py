"""The «Demanda» tab (owners and champions): what the role requests ask for, what belongs to the practice, what has a course."""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from academy import demand, demand_pdf
from academy.catalog import load_materials
from academy.practice import load_practice


@st.cache_data(show_spinner=False)
def _rows(path: str, stamp: int) -> list[dict]:
    return demand.load(path)


@st.cache_data(show_spinner=False)
def _report_pdf(signature: tuple, lang: str, now: str, _a: dict, _practice, _tr: dict) -> bytes | None:
    """The PDF for the current data (None without reportlab); rebuilt only when a roles file, the practice or the content changes."""
    return demand_pdf.to_pdf(_a, _practice, now, _tr) if demand_pdf.available() else None


def _signature() -> tuple:
    from academy import content_xlsx as content
    from academy.catalog import catalog_path, materials_path
    from academy.practice import practice_path

    files = [f for _, f in demand.snapshots()] + [demand.demand_path(), practice_path(), catalog_path(), materials_path()] + content.pack_files()
    return tuple((str(f), f.stat().st_mtime_ns) for f in files if f.exists())


def _import_box(lang: str, current: list[dict]) -> None:
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
        up = st.file_uploader("Roles file", type=["csv", "xlsx"], key="dm_up")
        if up is not None:
            rows, problems = demand.parse(up.getvalue())
            for e in problems:
                (st.warning if rows else st.error)(e)
            if rows:
                a, b = st.columns([2, 3])
                day = a.text_input("Date of this upload (YYYY-MM-DD)", value=demand.snapshot_date(rows),
                                   key=f"dm_day_{up.name}", help=("Every upload is kept with its date to compare the demand week over week. "
                                                                   "An existing upload with that date is replaced."))
                b.caption(f"{len(rows)} roles read.")
                if b.button("Save this upload", type="primary", key="dm_save", width="stretch"):
                    try:
                        demand.save_snapshot(rows, day.strip())
                    except ValueError:
                        st.error("The date must be YYYY-MM-DD.")
                    else:
                        st.rerun()
        snaps = demand.snapshots()
        if snaps:
            st.caption("Saved uploads: " + " · ".join(d for d, _ in snaps)
                       + f" (folder `{demand.history_dir()}`; delete a file there to remove that upload).")


def demand_tab(catalog, packs: list, lang: str) -> None:
    path = demand.demand_path()
    demand.sync_history()  # a roles file replaced by hand becomes one more dated upload
    rows = _rows(str(path), path.stat().st_mtime_ns) if path.exists() else []
    practice = load_practice()
    st.markdown(f"Which skills, technologies and roles are being requested, which belong to the **{practice.name or '—'}** practice and which already have a course in the academy.")
    _import_box(lang, rows)
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
    tr = demand.trend([(day, _rows(str(f), f.stat().st_mtime_ns)) for day, f in demand.snapshots()], practice, lang)
    d = st.columns(3)
    pdf = _report_pdf(_signature(), lang, now[:13] + ":00", a, practice, tr)  # rebuilt when the data changes, or once an hour
    if pdf:
        d[0].download_button("Report as PDF", pdf,
                             file_name=f"demand_analysis_{stamp}.pdf", mime="application/pdf", key="dm_pdf",
                             width="stretch", type="primary")
    else:
        d[0].button("Report as PDF", disabled=True, key="dm_pdf_off", width="stretch",
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
                    "Other views", "Practice definition"])
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
