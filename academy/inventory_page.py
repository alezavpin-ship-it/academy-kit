"""The team inventory in the app: «My skills» for each person, and the skills matrix for owners and champions."""

from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from academy import inventory as inv
from academy import ui
from academy.certs import CURRENT, DESIRED
from academy.practice import load_practice


def _skill_names(catalog) -> list[str]:
    practice = load_practice()
    return list(dict.fromkeys([s.name for s in (catalog.skills if catalog else [])] + [t.term for t in practice.skills]))


def template_buttons(catalog, key: str) -> None:
    a, b = st.columns(2)
    a.download_button("Collection template (Excel, with lists)", inv.template_xlsx(skills=_skill_names(catalog)), file_name="team_inventory_template.xlsx",
                      mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key=f"{key}_tpl_xlsx", width="stretch", type="primary")
    b.download_button("Collection template (CSV)", inv.template_csv(), file_name="team_inventory_template.csv", mime="text/csv",
                      key=f"{key}_tpl_csv", width="stretch")


def my_skills(conn, catalog, learner: str) -> None:
    """Each person keeps their own skills with the same 1-5 scale; certifications live in «My certifications»."""
    me = learner.strip() or "me"
    store = inv.Inventory(conn)
    st.markdown("Register the skills and technologies you **work with** and the ones you **want to learn**. Use the same scale as everyone, "
                "so staffing can find the right person when a role arrives.")
    st.caption(" · ".join(inv.LEVELS[n] + ": " + inv.LEVEL_HELP[n].lower() for n in inv.LEVELS))
    mine = store.skills(me)
    names = _skill_names(catalog)
    df = pd.DataFrame([{"Skill": r["Skill"], "Level": inv.LEVELS.get(r["Level"]), "Years": r["Years"], "Status": r["Status"],
                        "Evidence": r["Evidence"] or None, "Notes": r["Notes"] or None,
                        "Validated": f"✓ {r['ValidatedBy']}" if r["ValidatedBy"] else ""} for r in mine],
                      columns=["Skill", "Level", "Years", "Status", "Evidence", "Notes", "Validated"])
    df = df.astype({"Skill": "string", "Level": "string", "Status": "string", "Evidence": "string", "Notes": "string", "Validated": "string"})
    cc = st.column_config
    skill_col = cc.SelectboxColumn("Skill", options=list(dict.fromkeys(names + [r["Skill"] for r in mine])), required=True,
                                   help="Pick from the practice's skills; for any other one use «➕ Another skill» below.")
    extra = st.session_state.setdefault("inv_extra_skills", [])
    if extra:
        skill_col = cc.SelectboxColumn("Skill", options=list(dict.fromkeys(names + [r["Skill"] for r in mine] + extra)), required=True)
    ed = st.data_editor(df, num_rows="dynamic", hide_index=True, width="stretch", key=f"inv_my_{len(mine)}_{len(extra)}", column_config={
        "Skill": skill_col,
        "Level": cc.SelectboxColumn("Level", options=list(inv.LEVELS.values()), required=True),
        "Years": cc.NumberColumn("Years", min_value=0, max_value=50, step=0.5),
        "Status": cc.SelectboxColumn("Status", options=[CURRENT, DESIRED], required=True, help="current = you work with it · desired = you want to learn it"),
        "Evidence": cc.LinkColumn("Evidence", validate=r"^https://.+", help="Optional: a badge, a repo, a project page (https)"),
        "Notes": cc.TextColumn("Notes"),
        "Validated": cc.TextColumn("Validated by", disabled=True, help="Your champion validates the level; changing it removes the validation.")})
    a, b = st.columns([2, 3])
    with a.popover("➕ Another skill"):
        new = st.text_input("Skill or technology", key="inv_new_skill")
        if st.button("Add to the list", key="inv_new_add", disabled=not new.strip()):
            extra.append(new.strip())
            st.rerun()
    if b.button("Save my skills", type="primary", key="inv_my_save"):
        practice = load_practice()
        by_name = {s.name.lower(): s for s in (catalog.skills if catalog else [])}
        rows = []
        for r in ed.to_dict("records"):
            if pd.isna(r.get("Skill")) or not str(r["Skill"]).strip():
                continue
            rows.append({"Skill": str(r["Skill"]).strip(), "SkillId": inv.match(str(r["Skill"]), practice, by_name), "Level": r.get("Level") or "",
                         "Years": None if pd.isna(r.get("Years")) else r["Years"], "Status": r.get("Status") or CURRENT,
                         "Evidence": "" if pd.isna(r.get("Evidence")) else r["Evidence"], "Notes": "" if pd.isna(r.get("Notes")) else r["Notes"]})
        if any(r["Status"] == CURRENT and not inv.level_of(r["Level"]) for r in rows):
            st.error("Every skill you work with needs a Level (1 to 5).")
        else:
            store.set_skills(me, rows, by=me)
            st.session_state.pop("inv_extra_skills", None)
            ui.fx("step")
            st.toast("Skills saved.")
            st.rerun()


def skills_matrix(conn, catalog, who: str, owner: bool, people: set[str] | None = None) -> None:
    """Owners and champions: the team's skills matrix, «who can take this role?», validation and the collection file."""
    store = inv.Inventory(conn)
    st.markdown("#### Team skills matrix")
    st.caption("Levels 1-5 per person and skill (✓ = validated by a champion). Collect it once with the template, then each person keeps it "
               "up to date in Certifications → My skills.")
    cols, rows = store.matrix(catalog, people)
    m = st.columns(3)
    m[0].metric("People in the inventory", len(rows), border=True)
    m[1].metric("Distinct skills", len(cols), border=True)
    validated = sum(1 for r in store.skills() if r["ValidatedBy"] and (people is None or r["Person"] in people))
    m[2].metric("Validated levels", validated, border=True)
    with st.expander("📥 Collect the team's certifications and skills (template and import)", expanded=not rows):
        st.markdown("Send the template to the team (or turn it into a Microsoft Form with the same columns). One row per certification or "
                    "skill; the example rows show the expected shape. Importing replaces the inventory of the people in the file.")
        template_buttons(catalog, "inv")
        if owner:
            up = st.file_uploader("Import the filled-in file (Excel or CSV)", type=["xlsx", "csv"], key="inv_up")
            if up is not None:
                parsed = inv.parse(up.getvalue(), load_practice(), catalog)
                certs_n, skills_n = sum(len(v) for v in parsed["certs"].values()), sum(len(v) for v in parsed["skills"].values())
                st.caption(f"{len(parsed['people'])} people · {certs_n} certifications · {skills_n} skills")
                if parsed["problems"]:
                    st.error(f"{len(parsed['problems'])} problem(s): fix them in the file and upload it again; nothing was saved.")
                    st.code("\n".join(parsed["problems"][:40]), language=None, wrap_lines=True)
                elif st.button("Import into the academy", type="primary", key="inv_apply"):
                    store.apply(parsed, by=who)
                    ui.fx("step")
                    st.toast(f"Inventory updated for {len(parsed['people'])} people.")
                    st.rerun()
        st.download_button("Download the current inventory (CSV, same columns)", store.export_csv(), file_name=f"team_inventory_{date.today()}.csv",
                           mime="text/csv", key="inv_export")
    if not rows:
        st.info("The inventory is empty: send the collection template to the team, or ask each person to fill in Certifications → My skills.")
        return
    st.markdown("##### Who can take this role?")
    c1, c2 = st.columns([3, 1])
    wanted = c1.multiselect("Skills the role asks for", cols, key="inv_find", placeholder="Pick one or more skills")
    level = c2.select_slider("Minimum level", options=[1, 2, 3, 4, 5], value=3, key="inv_find_lvl")
    if wanted:
        found = store.who_has(wanted, level, catalog)
        found = [r for r in found if people is None or r["Person"] in people]
        if found:
            st.dataframe(pd.DataFrame([{k: v for k, v in r.items() if not k.startswith("_")} for r in found]), hide_index=True, width="stretch")
        else:
            st.warning("Nobody has all of them at that level yet: a candidate for a study group or a course.")
    st.markdown("##### Matrix")
    st.dataframe(pd.DataFrame(rows, columns=["Person"] + cols).fillna(""), hide_index=True, width="stretch")
    st.markdown("##### Validate a person's levels")
    names = [r["Person"] for r in rows]
    person = st.selectbox("Person", names, key="inv_val_person")
    recs = [r for r in store.skills(person) if r["Status"] == CURRENT]
    vdf = pd.DataFrame([{"Skill": r["Skill"], "Level": inv.LEVELS.get(r["Level"], ""), "Years": r["Years"], "Validated": bool(r["ValidatedBy"]),
                         "By": r["ValidatedBy"]} for r in recs])
    ved = st.data_editor(vdf, hide_index=True, width="stretch", key=f"inv_val_{person}", disabled=["Skill", "Level", "Years", "By"],
                         column_config={"Validated": st.column_config.CheckboxColumn("Validated", help="You confirm the level after a conversation or evidence.")})
    if st.button("Save validation", key="inv_val_save"):
        for before, after in zip(recs, ved.to_dict("records")):
            if bool(before["ValidatedBy"]) != bool(after["Validated"]):
                store.validate(person, before["Skill"], who, bool(after["Validated"]))
        st.toast("Validation saved.")
        st.rerun()
