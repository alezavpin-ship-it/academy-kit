"""Screens of the certification register: each learner's own list, and what owners / champions run."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from academy import ui
from academy.catalog import VENDORS
from academy.certs import CURRENT, DESIRABLE, DESIRED, RECORD_COLUMNS, REQUIRED, REQUIREMENT_COLUMNS, Certs

DATE = r"^\d{4}-\d{2}-\d{2}$"


def _status_names(lang: str) -> dict[str, str]:
    return {CURRENT: "current", DESIRED: "desired"}


def _level_names(lang: str) -> dict[str, str]:
    return {REQUIRED: "required", DESIRABLE: "desirable"}


def _records_editor(rows: list[dict], lang: str, key: str) -> list[dict]:
    """Editable table of one person's certifications. Returns the rows as the register stores them."""
    names = _status_names(lang)
    df = pd.DataFrame([{"Code": r["Code"], "Name": r["Name"], "Vendor": r["Vendor"], "Status": names[r["Status"]], "Obtained": r["Obtained"],
                        "Expires": r["Expires"], "CredentialUrl": r["CredentialUrl"]} for r in rows],
                      columns=["Code", "Name", "Vendor", "Status", "Obtained", "Expires", "CredentialUrl"]).astype("string")
    ed = st.data_editor(df, num_rows="dynamic", hide_index=True, width="stretch", key=key, column_config={
        "Code": st.column_config.TextColumn("Code", required=True, help="AZ-500, SC-200, CISSP…"),
        "Name": st.column_config.TextColumn("Certification"),
        "Vendor": st.column_config.SelectboxColumn("Vendor", options=[v for v in VENDORS if v != "Vendor-neutral"] + ["ISC2", "ISACA", "CompTIA", "PMI", "Otro"]),
        "Status": st.column_config.SelectboxColumn("Status", options=list(names.values()), required=True, default=names[CURRENT],
                                                   help="current = you hold it · desired = you are aiming for it"),
        "Obtained": st.column_config.TextColumn("Obtained (YYYY-MM-DD)", validate=DATE),
        "Expires": st.column_config.TextColumn("Expires (YYYY-MM-DD)", validate=DATE),
        "CredentialUrl": st.column_config.LinkColumn("Credential link", validate=r"^https://.+")})
    out = []
    for r in ed.to_dict("records"):
        if pd.notna(r.get("Code")) and str(r["Code"]).strip():
            out.append({k: ("" if pd.isna(r.get(k)) else str(r[k]).strip()) for k in ("Code", "Name", "Vendor", "Status", "Obtained", "Expires", "CredentialUrl")})
    return out


def my_certs(conn, catalog, learner: str, lang: str) -> None:
    """The learner's own register: what they hold and what they are aiming for."""
    c = Certs(conn)
    me = learner.strip() or "me"
    mine = c.records(me)
    st.markdown(("Register the certifications you **already hold** and the ones you **want to get**. Your champion sees them to plan the "
                  "family's training and may suggest desired certifications."))
    m = st.columns(3)
    m[0].metric("Current", sum(r["Status"] == CURRENT for r in mine), border=True)
    m[1].metric("Desired", sum(r["Status"] == DESIRED for r in mine), border=True)
    from academy import paths as pathmod

    reqs = c.asked(None, pathmod.load(catalog) if catalog else None)  # the families' requirements and their paths' certifications
    have = {r["Code"] for r in mine}
    m[2].metric("Required by the families and missing",
                len({r["Code"] for r in reqs if r["Level"] == REQUIRED} - {r["Code"] for r in mine if r["Status"] == CURRENT}), border=True)
    if reqs:
        fams = {f.id: f.name for f in catalog.families} if catalog else {}
        level = _level_names(lang)
        options = {r["Code"]: f"{r['Code']} · {r['Name']} — {fams.get(r['FamilyId'], r['FamilyId'])} ({level[r['Level']]})" for r in reqs if r["Code"] not in have}
        if options:
            pick = st.multiselect("Certifications the role families ask for: add them as desired", list(options), format_func=lambda k: options[k],
                                  key="ce_pick")
            if st.button("Add to my desired ones", key="ce_pick_add", disabled=not pick):
                by_code = {r["Code"]: r for r in reqs}
                c.set_records(me, mine + [{"Code": k, "Name": by_code[k]["Name"], "Vendor": by_code[k]["Vendor"], "Status": DESIRED} for k in pick], me)
                ui.fx("step")
                st.rerun()
    with st.form(f"ce_mine_form_{len(mine)}", border=False, enter_to_submit=False):
        rows = _records_editor(mine, lang, f"ce_mine_{len(mine)}")
        save_mine = st.form_submit_button("Save my certifications", type="primary", key="ce_save")
    a, b = st.columns(2)
    if save_mine:
        try:
            c.set_records(me, rows, me)
        except ValueError as e:
            st.error(f"Invalid date: {e}. Use YYYY-MM-DD.")
        else:
            ui.fx("ok")
            st.toast("Certifications saved.")
            st.rerun()
    b.download_button("Download my certifications (CSV)", c.records_csv(me),
                      file_name="my_certifications.csv", mime="text/csv", key="ce_my_csv", width="stretch")
    with st.expander("Import my certifications from a CSV"):
        st.caption("Columns: " + ", ".join(RECORD_COLUMNS) + ". Status = current or desired. It replaces your list.")
        up = st.file_uploader("CSV", type=["csv"], key="ce_my_up", label_visibility="collapsed")
        if up is not None:
            data, problems = Certs.parse_records(up.getvalue(), only_learner=me)
            if problems:
                st.error("\n\n".join(problems[:20]))
            elif st.button(f"Import {sum(len(v) for v in data.values())} certification(s)",
                           key="ce_my_imp", type="primary"):
                c.set_records(me, data.get(me, []), me)
                ui.fx("ok")
                st.rerun()


def path_certs_note(c: Certs, fam: str, structure=None) -> None:
    """The certifications the family's learning paths prepare: asked of everyone in the family unless listed here."""
    from academy import paths as pathmod

    structure = structure if structure is not None else pathmod.load()
    written = {r["Code"] for r in c.requirements({fam}, include_off=True)}
    extra = [p for p in structure.certs_of(fam) if p.cert not in written]
    if extra:
        st.caption("Also asked by its learning paths (required for everyone in the family; add the code here to make it desirable or "
                   "off): " + ", ".join(f"**{p.cert}** ({p.name})" for p in extra) + ".")


def certs_admin(conn, catalog, lang: str, admin_fams: set[str], who: str, roster: list[str]) -> None:
    """Owners / champions: what each family asks for, and anyone's register (to correct it or set desired certifications)."""
    c = Certs(conn)
    fams = {f.id: f.name for f in catalog.families if f.id in admin_fams}
    level = _level_names(lang)
    st.markdown("##### Certifications each role family asks for")
    if not c.requirements() and st.button("Load suggested Microsoft certifications (as desirable, editable)", key="ce_sug"):
        n = c.load_suggested(set(fams))
        st.toast(f"{n} suggested certifications added.")
        st.rerun()
    fam = st.selectbox("Role family", list(fams), format_func=lambda k: fams[k], key="ce_fam")
    if fam:
        cur = c.requirements({fam})
        path_certs_note(c, fam)
        df = pd.DataFrame([{"Code": r["Code"], "Name": r["Name"], "Vendor": r["Vendor"], "Level": level[r["Level"]], "Url": r["Url"]} for r in cur],
                          columns=["Code", "Name", "Vendor", "Level", "Url"]).astype("string")
        with st.form(f"ce_req_form_{fam}_{len(cur)}", border=False, enter_to_submit=False):
            ed = st.data_editor(df, num_rows="dynamic", hide_index=True, width="stretch", key=f"ce_req_{fam}_{len(cur)}", column_config={
                "Code": st.column_config.TextColumn("Code", required=True),
                "Name": st.column_config.TextColumn("Certification"),
                "Vendor": st.column_config.TextColumn("Vendor"),
                "Level": st.column_config.SelectboxColumn("Level", options=list(level.values()), required=True, default=level[DESIRABLE]),
                "Url": st.column_config.LinkColumn("Official page", validate=r"^https://.+")})
            save_req = st.form_submit_button("Save the family's certifications", type="primary", key="ce_req_save")
        if save_req:
            c.set_requirements(fam, [{k: ("" if pd.isna(r.get(k)) else str(r[k]).strip()) for k in ("Code", "Name", "Vendor", "Level", "Url")}
                                     for r in ed.to_dict("records")])
            st.toast("Saved.")
            st.rerun()
    a, b = st.columns(2)
    a.download_button("Export requirements (CSV)", c.requirements_csv(set(fams)),
                      file_name="certifications_by_family.csv", mime="text/csv", key="ce_req_csv", width="stretch")
    with b.popover("Import requirements (CSV)", width="stretch"):
        st.caption("Columns: " + ", ".join(REQUIREMENT_COLUMNS) + ". Level = required or desirable. It replaces those of the families in the file.")
        up = st.file_uploader("CSV", type=["csv"], key="ce_req_up", label_visibility="collapsed")
        if up is not None:
            data, problems = Certs.parse_requirements(up.getvalue(), {f.id for f in catalog.families}, set(fams))
            if problems:
                st.error("\n\n".join(problems[:20]))
            elif st.button("Apply", key="ce_req_imp", type="primary"):
                for k, rows in data.items():
                    c.set_requirements(k, rows)
                st.rerun()

    st.markdown("##### People's certification register")
    st.caption("Correct someone's register or set desired certifications for them. Every change is saved under your name.")
    people = list(dict.fromkeys(roster + c.learners()))
    p = st.columns([2, 2])
    person = p[0].selectbox("Person", [""] + people, key="ce_person", format_func=lambda k: k or "(choose)")
    new = p[1].text_input("…or type a new name", key="ce_person_new").strip()
    person = new or person
    if person:
        theirs = c.records(person)
        with st.form(f"ce_adm_form_{person}_{len(theirs)}", border=False, enter_to_submit=False):
            rows = _records_editor(theirs, lang, f"ce_adm_{person}_{len(theirs)}")
            save_theirs = st.form_submit_button(f"Save {person}'s certifications", type="primary", key="ce_adm_save")
        if save_theirs:
            try:
                c.set_records(person, rows, who)
            except ValueError as e:
                st.error(f"Invalid date: {e}. Use YYYY-MM-DD.")
            else:
                st.toast("Saved.")
                st.rerun()
    a, b = st.columns(2)
    a.download_button("Export the whole register (CSV)", c.records_csv(),
                      file_name="team_certifications.csv", mime="text/csv", key="ce_all_csv", width="stretch")
    with b.popover("Import register (CSV)", width="stretch"):
        st.caption("Columns: " + ", ".join(RECORD_COLUMNS) + ". It replaces the certifications of the people in the file; everyone else is untouched.")
        up = st.file_uploader("CSV", type=["csv"], key="ce_all_up", label_visibility="collapsed")
        if up is not None:
            data, problems = Certs.parse_records(up.getvalue())
            if problems:
                st.error("\n\n".join(problems[:20]))
            elif st.button(f"Apply to {len(data)} people", key="ce_all_imp", type="primary"):
                for k, rows in data.items():
                    c.set_records(k, rows, who)
                st.rerun()
