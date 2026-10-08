"""Screens of the certification register: each learner's own list, and what owners / champions run."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from academy import ui
from academy.catalog import VENDORS
from academy.certs import CURRENT, DESIRABLE, DESIRED, RECORD_COLUMNS, REQUIRED, REQUIREMENT_COLUMNS, Certs
from academy.i18n import L

DATE = r"^\d{4}-\d{2}-\d{2}$"


def _status_names(lang: str) -> dict[str, str]:
    return {CURRENT: L(lang, "actual", "current"), DESIRED: L(lang, "deseable", "desired")}


def _level_names(lang: str) -> dict[str, str]:
    return {REQUIRED: L(lang, "requerida", "required"), DESIRABLE: L(lang, "deseable", "desirable")}


def _records_editor(rows: list[dict], lang: str, key: str) -> list[dict]:
    """Editable table of one person's certifications. Returns the rows as the register stores them."""
    names = _status_names(lang)
    df = pd.DataFrame([{"Code": r["Code"], "Name": r["Name"], "Vendor": r["Vendor"], "Status": names[r["Status"]], "Obtained": r["Obtained"],
                        "Expires": r["Expires"], "CredentialUrl": r["CredentialUrl"]} for r in rows],
                      columns=["Code", "Name", "Vendor", "Status", "Obtained", "Expires", "CredentialUrl"]).astype("string")
    ed = st.data_editor(df, num_rows="dynamic", hide_index=True, width="stretch", key=key, column_config={
        "Code": st.column_config.TextColumn(L(lang, "Código", "Code"), required=True, help="AZ-500, SC-200, CISSP…"),
        "Name": st.column_config.TextColumn(L(lang, "Certificación", "Certification")),
        "Vendor": st.column_config.SelectboxColumn("Vendor", options=[v for v in VENDORS if v != "Vendor-neutral"] + ["ISC2", "ISACA", "CompTIA", "PMI", "Otro"]),
        "Status": st.column_config.SelectboxColumn(L(lang, "Estado", "Status"), options=list(names.values()), required=True, default=names[CURRENT],
                                                   help=L(lang, "actual = ya la tienes · deseable = la quieres obtener", "current = you hold it · desired = you are aiming for it")),
        "Obtained": st.column_config.TextColumn(L(lang, "Obtenida (AAAA-MM-DD)", "Obtained (YYYY-MM-DD)"), validate=DATE),
        "Expires": st.column_config.TextColumn(L(lang, "Vence (AAAA-MM-DD)", "Expires (YYYY-MM-DD)"), validate=DATE),
        "CredentialUrl": st.column_config.LinkColumn(L(lang, "Enlace de la credencial", "Credential link"), validate=r"^https://.+")})
    out = []
    for r in ed.to_dict("records"):
        if pd.notna(r.get("Code")) and str(r["Code"]).strip():
            out.append({k: ("" if pd.isna(r.get(k)) else str(r[k]).strip()) for k in ("Code", "Name", "Vendor", "Status", "Obtained", "Expires", "CredentialUrl")})
    return out


def my_certs(conn, catalog, learner: str, lang: str) -> None:
    """The learner's own register: what they hold and what they are aiming for."""
    c = Certs(conn)
    me = learner.strip() or "yo"
    mine = c.records(me)
    st.markdown(L(lang, "Registra las certificaciones que **ya tienes** y las que **quieres obtener**. Tu champion las ve para planear la "
                        "formación de la familia y puede sugerirte certificaciones deseables.",
                  "Register the certifications you **already hold** and the ones you **want to get**. Your champion sees them to plan the "
                  "family's training and may suggest desired certifications."))
    m = st.columns(3)
    m[0].metric(L(lang, "Actuales", "Current"), sum(r["Status"] == CURRENT for r in mine), border=True)
    m[1].metric(L(lang, "Deseables", "Desired"), sum(r["Status"] == DESIRED for r in mine), border=True)
    reqs = c.requirements()
    have = {r["Code"] for r in mine}
    m[2].metric(L(lang, "Requeridas por las familias que te faltan", "Required by the families and missing"),
                len({r["Code"] for r in reqs if r["Level"] == REQUIRED} - {r["Code"] for r in mine if r["Status"] == CURRENT}), border=True)
    if reqs:
        fams = {f.id: f.name for f in catalog.families} if catalog else {}
        level = _level_names(lang)
        options = {r["Code"]: f"{r['Code']} · {r['Name']} — {fams.get(r['FamilyId'], r['FamilyId'])} ({level[r['Level']]})" for r in reqs if r["Code"] not in have}
        if options:
            pick = st.multiselect(L(lang, "Certificaciones que piden las familias de skills: agrégalas como deseables",
                                    "Certifications the skill families ask for: add them as desired"), list(options), format_func=lambda k: options[k],
                                  key="ce_pick")
            if st.button(L(lang, "Agregar a mis deseables", "Add to my desired ones"), key="ce_pick_add", disabled=not pick):
                by_code = {r["Code"]: r for r in reqs}
                c.set_records(me, mine + [{"Code": k, "Name": by_code[k]["Name"], "Vendor": by_code[k]["Vendor"], "Status": DESIRED} for k in pick], me)
                ui.fx("step")
                st.rerun()
    rows = _records_editor(mine, lang, f"ce_mine_{len(mine)}")
    a, b = st.columns(2)
    if a.button(L(lang, "Guardar mis certificaciones", "Save my certifications"), type="primary", key="ce_save", width="stretch"):
        try:
            c.set_records(me, rows, me)
        except ValueError as e:
            st.error(L(lang, f"Fecha no válida: {e}. Usa AAAA-MM-DD.", f"Invalid date: {e}. Use YYYY-MM-DD."))
        else:
            ui.fx("ok")
            st.toast(L(lang, "Certificaciones guardadas.", "Certifications saved."))
            st.rerun()
    b.download_button(L(lang, "Descargar mis certificaciones (CSV)", "Download my certifications (CSV)"), c.records_csv(me),
                      file_name=L(lang, "mis_certificaciones.csv", "my_certifications.csv"), mime="text/csv", key="ce_my_csv", width="stretch")
    with st.expander(L(lang, "Importar mis certificaciones desde un CSV", "Import my certifications from a CSV")):
        st.caption(L(lang, "Columnas: ", "Columns: ") + ", ".join(RECORD_COLUMNS) + L(lang, ". Status = current o desired. Reemplaza tu lista.",
                                                                                      ". Status = current or desired. It replaces your list."))
        up = st.file_uploader("CSV", type=["csv"], key="ce_my_up", label_visibility="collapsed")
        if up is not None:
            data, problems = Certs.parse_records(up.getvalue(), only_learner=me)
            if problems:
                st.error("\n\n".join(problems[:20]))
            elif st.button(L(lang, f"Importar {sum(len(v) for v in data.values())} certificación(es)", f"Import {sum(len(v) for v in data.values())} certification(s)"),
                           key="ce_my_imp", type="primary"):
                c.set_records(me, data.get(me, []), me)
                ui.fx("ok")
                st.rerun()


def certs_admin(conn, catalog, lang: str, admin_fams: set[str], who: str, roster: list[str]) -> None:
    """Owners / champions: what each family asks for, and anyone's register (to correct it or set desired certifications)."""
    c = Certs(conn)
    fams = {f.id: f.name for f in catalog.families if f.id in admin_fams}
    level = _level_names(lang)
    st.markdown(L(lang, "##### Certificaciones que pide cada familia de skills", "##### Certifications each skill family asks for"))
    if not c.requirements() and st.button(L(lang, "Cargar sugerencias de certificaciones Microsoft (como deseables, editables)",
                                            "Load suggested Microsoft certifications (as desirable, editable)"), key="ce_sug"):
        n = c.load_suggested(set(fams))
        st.toast(L(lang, f"{n} certificaciones sugeridas agregadas.", f"{n} suggested certifications added."))
        st.rerun()
    fam = st.selectbox(L(lang, "Familia de skills", "Skill family"), list(fams), format_func=lambda k: fams[k], key="ce_fam")
    if fam:
        cur = c.requirements({fam})
        df = pd.DataFrame([{"Code": r["Code"], "Name": r["Name"], "Vendor": r["Vendor"], "Level": level[r["Level"]], "Url": r["Url"]} for r in cur],
                          columns=["Code", "Name", "Vendor", "Level", "Url"]).astype("string")
        ed = st.data_editor(df, num_rows="dynamic", hide_index=True, width="stretch", key=f"ce_req_{fam}_{len(cur)}", column_config={
            "Code": st.column_config.TextColumn(L(lang, "Código", "Code"), required=True),
            "Name": st.column_config.TextColumn(L(lang, "Certificación", "Certification")),
            "Vendor": st.column_config.TextColumn("Vendor"),
            "Level": st.column_config.SelectboxColumn(L(lang, "Nivel", "Level"), options=list(level.values()), required=True, default=level[DESIRABLE]),
            "Url": st.column_config.LinkColumn(L(lang, "Página oficial", "Official page"), validate=r"^https://.+")})
        if st.button(L(lang, "Guardar certificaciones de la familia", "Save the family's certifications"), type="primary", key="ce_req_save"):
            c.set_requirements(fam, [{k: ("" if pd.isna(r.get(k)) else str(r[k]).strip()) for k in ("Code", "Name", "Vendor", "Level", "Url")}
                                     for r in ed.to_dict("records")])
            st.toast(L(lang, "Guardado.", "Saved."))
            st.rerun()
    a, b = st.columns(2)
    a.download_button(L(lang, "Exportar requisitos (CSV)", "Export requirements (CSV)"), c.requirements_csv(set(fams)),
                      file_name=L(lang, "certificaciones_por_familia.csv", "certifications_by_family.csv"), mime="text/csv", key="ce_req_csv", width="stretch")
    with b.popover(L(lang, "Importar requisitos (CSV)", "Import requirements (CSV)"), width="stretch"):
        st.caption(L(lang, "Columnas: ", "Columns: ") + ", ".join(REQUIREMENT_COLUMNS) + L(lang, ". Level = required o desirable. Reemplaza los de las familias del archivo.",
                                                                                           ". Level = required or desirable. It replaces those of the families in the file."))
        up = st.file_uploader("CSV", type=["csv"], key="ce_req_up", label_visibility="collapsed")
        if up is not None:
            data, problems = Certs.parse_requirements(up.getvalue(), {f.id for f in catalog.families}, set(fams))
            if problems:
                st.error("\n\n".join(problems[:20]))
            elif st.button(L(lang, "Aplicar", "Apply"), key="ce_req_imp", type="primary"):
                for k, rows in data.items():
                    c.set_requirements(k, rows)
                st.rerun()

    st.markdown(L(lang, "##### Registro de certificaciones de las personas", "##### People's certification register"))
    st.caption(L(lang, "Corrige el registro de alguien o colócale certificaciones deseables. Cada cambio queda con tu nombre.",
                 "Correct someone's register or set desired certifications for them. Every change is saved under your name."))
    people = list(dict.fromkeys(roster + c.learners()))
    p = st.columns([2, 2])
    person = p[0].selectbox(L(lang, "Persona", "Person"), [""] + people, key="ce_person", format_func=lambda k: k or L(lang, "(elige)", "(choose)"))
    new = p[1].text_input(L(lang, "…o escribe un nombre nuevo", "…or type a new name"), key="ce_person_new").strip()
    person = new or person
    if person:
        theirs = c.records(person)
        rows = _records_editor(theirs, lang, f"ce_adm_{person}_{len(theirs)}")
        if st.button(L(lang, f"Guardar certificaciones de {person}", f"Save {person}'s certifications"), type="primary", key="ce_adm_save"):
            try:
                c.set_records(person, rows, who)
            except ValueError as e:
                st.error(L(lang, f"Fecha no válida: {e}. Usa AAAA-MM-DD.", f"Invalid date: {e}. Use YYYY-MM-DD."))
            else:
                st.toast(L(lang, "Guardado.", "Saved."))
                st.rerun()
    a, b = st.columns(2)
    a.download_button(L(lang, "Exportar el registro completo (CSV)", "Export the whole register (CSV)"), c.records_csv(),
                      file_name=L(lang, "certificaciones_equipo.csv", "team_certifications.csv"), mime="text/csv", key="ce_all_csv", width="stretch")
    with b.popover(L(lang, "Importar registro (CSV)", "Import register (CSV)"), width="stretch"):
        st.caption(L(lang, "Columnas: ", "Columns: ") + ", ".join(RECORD_COLUMNS) + L(lang, ". Reemplaza las certificaciones de las personas que vienen en el archivo; las demás no cambian.",
                                                                                      ". It replaces the certifications of the people in the file; everyone else is untouched."))
        up = st.file_uploader("CSV", type=["csv"], key="ce_all_up", label_visibility="collapsed")
        if up is not None:
            data, problems = Certs.parse_records(up.getvalue())
            if problems:
                st.error("\n\n".join(problems[:20]))
            elif st.button(L(lang, f"Aplicar a {len(data)} persona(s)", f"Apply to {len(data)} people"), key="ce_all_imp", type="primary"):
                for k, rows in data.items():
                    c.set_records(k, rows, who)
                st.rerun()
