"""The «Demanda» tab (owners and champions): what the role requests ask for, what belongs to the practice, what has a course."""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from academy import demand, demand_pdf
from academy.catalog import load_materials
from academy.i18n import L
from academy.practice import load_practice


@st.cache_data(show_spinner=False)
def _rows(path: str, stamp: int) -> list[dict]:
    return demand.load(path)


@st.cache_data(show_spinner=False)
def _reports(signature: tuple, lang: str, now: str, _a: dict, _practice, _tr: dict) -> tuple[bytes | None, bytes]:
    """(PDF or None, HTML) for the current data; rebuilt only when a roles file, the practice or the content changes."""
    pdf = demand_pdf.to_pdf(_a, _practice, now, _tr) if demand_pdf.available() else None
    return pdf, demand.to_html(_a, _practice, now, _tr).encode("utf-8")


def _signature() -> tuple:
    from academy import content_xlsx as content
    from academy.catalog import catalog_path, materials_path
    from academy.practice import practice_path

    files = [f for _, f in demand.snapshots()] + [demand.demand_path(), practice_path(), catalog_path(), materials_path()] + content.pack_files()
    return tuple((str(f), f.stat().st_mtime_ns) for f in files if f.exists())


def _import_box(lang: str, current: list[dict]) -> None:
    path = demand.demand_path()
    with st.expander(L(lang, "📥 Cargar el archivo de roles (CSV o Excel) · plantilla y datos de prueba", "📥 Load the roles file (CSV or Excel) · template and test data"),
                     expanded=not current):
        st.markdown(L(lang, f"El análisis lee **`{path}`**. Puedes reemplazar ese archivo directamente (mismo encabezado) o subirlo aquí. "
                            f"Columnas: {len(demand.COLUMNS)}, las del reporte de roles; solo son obligatorias *Role ID*, *Role Title* y *Role Primary Skill*.",
                      f"The analysis reads **`{path}`**. You can replace that file directly (same header) or upload it here. "
                      f"Columns: {len(demand.COLUMNS)}, those of the roles report; only *Role ID*, *Role Title* and *Role Primary Skill* are mandatory."))
        c = st.columns(3)
        c[0].download_button(L(lang, "Plantilla vacía (CSV)", "Empty template (CSV)"), demand.to_csv([]), file_name="demanda_roles_plantilla.csv",
                             mime="text/csv", key="dm_tpl", width="stretch")
        c[1].download_button(L(lang, "CSV de prueba (48 roles ficticios)", "Test CSV (48 made-up roles)"), demand.to_csv(demand.sample_rows()),
                             file_name="demanda_roles_ejemplo.csv", mime="text/csv", key="dm_sample", width="stretch")
        if c[2].button(L(lang, "Usar los datos de prueba", "Use the test data"), key="dm_use_sample", width="stretch", disabled=bool(current),
                       help=L(lang, "Solo cuando todavía no hay archivo de roles. Carga dos semanas ficticias para ver también la tendencia.",
                              "Only while there is no roles file yet. It loads two made-up weeks so the trend shows too.")):
            for day, sample in demand.sample_history():
                demand.save_snapshot(sample, day)
            st.rerun()
        up = st.file_uploader(L(lang, "Archivo de roles", "Roles file"), type=["csv", "xlsx"], key="dm_up")
        if up is not None:
            rows, problems = demand.parse(up.getvalue())
            for e in problems:
                (st.warning if rows else st.error)(e)
            if rows:
                a, b = st.columns([2, 3])
                day = a.text_input(L(lang, "Fecha de esta carga (AAAA-MM-DD)", "Date of this upload (YYYY-MM-DD)"), value=demand.snapshot_date(rows),
                                   key=f"dm_day_{up.name}", help=L(lang, "Cada carga se guarda con su fecha para comparar la demanda semana a semana. "
                                                                         "Si ya hay una carga con esa fecha, se reemplaza.",
                                                                   "Every upload is kept with its date to compare the demand week over week. "
                                                                   "An existing upload with that date is replaced."))
                b.caption(L(lang, f"{len(rows)} roles leídos.", f"{len(rows)} roles read."))
                if b.button(L(lang, "Guardar esta carga", "Save this upload"), type="primary", key="dm_save", width="stretch"):
                    try:
                        demand.save_snapshot(rows, day.strip())
                    except ValueError:
                        st.error(L(lang, "La fecha debe ser AAAA-MM-DD.", "The date must be YYYY-MM-DD."))
                    else:
                        st.rerun()
        snaps = demand.snapshots()
        if snaps:
            st.caption(L(lang, "Cargas guardadas: ", "Saved uploads: ") + " · ".join(d for d, _ in snaps)
                       + L(lang, f" (carpeta `{demand.history_dir()}`; borra un archivo ahí para quitar esa carga).",
                           f" (folder `{demand.history_dir()}`; delete a file there to remove that upload)."))


def demand_tab(catalog, packs: list, lang: str) -> None:
    path = demand.demand_path()
    demand.sync_history()  # a roles file replaced by hand becomes one more dated upload
    rows = _rows(str(path), path.stat().st_mtime_ns) if path.exists() else []
    practice = load_practice()
    st.markdown(L(lang, f"Qué skills, tecnologías y roles se están pidiendo, cuáles son de la práctica **{practice.name or '—'}** y cuáles ya tienen curso en la academia.",
                  f"Which skills, technologies and roles are being requested, which belong to the **{practice.name or '—'}** practice and which already have a course in the academy."))
    _import_box(lang, rows)
    if not practice.skills:
        st.warning(L(lang, "La práctica no está definida todavía: llena las tablas Practica, PracticaSkills y PracticaRoles del archivo de contenido.",
                     "The practice is not defined yet: fill in the Practica, PracticaSkills and PracticaRoles tables of the content file."))
    if not rows:
        st.info(L(lang, "Todavía no hay archivo de roles. Carga uno o usa los datos de prueba.", "There is no roles file yet. Load one or use the test data."))
        return
    a = demand.analyze(rows, practice, catalog, packs, load_materials(), lang)
    k, s = a["keys"], a["summary"]
    m = st.columns(6)
    for col, (label, value) in zip(m, ((L(lang, "Roles", "Roles"), s["roles"]),
                                        (L(lang, "En la práctica", "In the practice"), f"{s['in_practice_pct']} %"),
                                        (L(lang, "Fuera de la práctica", "Outside the practice"), s["outside"]),
                                        (L(lang, "Clientes", "Clients"), s["clients"]), (L(lang, "Skills distintos", "Distinct skills"), s["skills"]),
                                        (L(lang, "Skills de la práctica sin curso", "Practice skills without a course"), s["no_course"]))):
        col.metric(label, value, border=True)
    stamp, now = datetime.now().strftime("%Y-%m-%d"), datetime.now().strftime("%Y-%m-%d %H:%M")
    tr = demand.trend([(day, _rows(str(f), f.stat().st_mtime_ns)) for day, f in demand.snapshots()], practice, lang)
    d = st.columns(4)
    pdf, page = _reports(_signature(), lang, now[:13] + ":00", a, practice, tr)  # rebuilt when the data changes, or once an hour
    if pdf:
        d[0].download_button(L(lang, "Reporte en PDF", "Report as PDF"), pdf,
                             file_name=L(lang, f"analisis_demanda_{stamp}.pdf", f"demand_analysis_{stamp}.pdf"), mime="application/pdf", key="dm_pdf",
                             width="stretch", type="primary")
    else:
        d[0].button(L(lang, "Reporte en PDF", "Report as PDF"), disabled=True, key="dm_pdf_off", width="stretch",
                    help=L(lang, "Falta el componente de PDF: cierra la app, haz doble clic en «Instalar componentes.bat» (en la carpeta de la app) y vuelve a abrirla.",
                           "The PDF component is missing: close the app, double-click «Instalar componentes.bat» (in the app folder) and open it again."))
    d[3].download_button(L(lang, "Reporte con gráficos (HTML)", "Report with charts (HTML)"), page,
                         file_name=L(lang, f"analisis_demanda_{stamp}.html", f"demand_analysis_{stamp}.html"), mime="text/html", key="dm_html", width="stretch")
    d[1].download_button(L(lang, "Skills solicitados (CSV)", "Requested skills (CSV)"),
                         pd.DataFrame(demand.visible(a["skills"])).to_csv(index=False).encode("utf-8-sig"),
                         file_name=L(lang, f"skills_solicitados_{stamp}.csv", f"requested_skills_{stamp}.csv"), mime="text/csv", key="dm_csv", width="stretch")
    d[2].download_button(L(lang, "Skills nuevos para el catálogo (CSV)", "New skills for the catalog (CSV)"), demand.catalog_suggestions(a),
                         file_name="skills_sugeridos.csv", mime="text/csv", key="dm_sug", width="stretch",
                         help=L(lang, "Skills de la práctica con demanda que no están en el catálogo, como filas de la tabla Skills listas para pegar en el archivo de contenido.",
                                "Practice skills in demand that are not in the catalog, as Skills rows ready to paste into the content file."))
    ch = demand.charts(a)
    st.markdown(f"<style>{demand.CHART_CSS}</style>" + ch["share"] + demand.legend(lang), unsafe_allow_html=True)
    tabs = st.tabs([L(lang, "Skills", "Skills"), L(lang, "Tendencia", "Trend"), L(lang, "Roles y skill primario", "Roles and primary skill"),
                    L(lang, "Fuera de la práctica", "Outside the practice"), L(lang, "Demanda contra cursos", "Demand against courses"),
                    L(lang, "Otras vistas", "Other views"), L(lang, "Definición de la práctica", "Practice definition")])
    css = ""  # the chart styles were written once, above
    with tabs[0]:
        st.markdown(css + ch["skills"], unsafe_allow_html=True)
        st.dataframe(pd.DataFrame(demand.visible(a["skills"])), hide_index=True, width="stretch")
    with tabs[1]:
        if len(tr["dates"]) < 2:
            st.info(L(lang, f"Hay una sola carga ({', '.join(tr['dates']) or '—'}). La tendencia aparece cuando guardes la siguiente (por ejemplo, la de la próxima semana).",
                      f"There is a single upload ({', '.join(tr['dates']) or '—'}). The trend shows once you save the next one (for example, next week's)."))
        else:
            tc, tk = demand.trend_charts(tr), tr["keys"]
            st.markdown(L(lang, f"**{len(tr['dates'])} cargas**, de {tr['dates'][0]} a {tr['dates'][-1]}. Los cambios comparan la última con la anterior.",
                          f"**{len(tr['dates'])} uploads**, from {tr['dates'][0]} to {tr['dates'][-1]}. Changes compare the latest with the previous one."))
            st.markdown(tc["lines"] + demand.legend(lang), unsafe_allow_html=True)
            c1, c2 = st.columns(2)
            c1.markdown(tc["up"] or L(lang, "_Ningún skill creció._", "_No skill grew._"), unsafe_allow_html=True)
            c2.markdown(tc["down"] or L(lang, "_Ningún skill bajó._", "_No skill dropped._"), unsafe_allow_html=True)
            st.markdown(L(lang, "**Skills más solicitados en cada carga**", "**Most requested skills in every upload**"))
            st.dataframe(pd.DataFrame(demand.visible(tr["skills"])), hide_index=True, width="stretch")
            n1, n2 = st.columns(2)
            n1.markdown(L(lang, f"**Roles nuevos desde la carga anterior ({len(tr['new_roles'])})**", f"**New roles since the previous upload ({len(tr['new_roles'])})**"))
            n1.dataframe(pd.DataFrame(tr["new_roles"]), hide_index=True, width="stretch")
            n2.markdown(L(lang, f"**Roles que ya no vienen en el archivo ({len(tr['gone_roles'])})**", f"**Roles no longer in the file ({len(tr['gone_roles'])})**"))
            n2.dataframe(pd.DataFrame(tr["gone_roles"]), hide_index=True, width="stretch")
            if tr["new_skills"]:
                st.caption(L(lang, "Skills que aparecen por primera vez: ", "Skills appearing for the first time: ") + ", ".join(tr["new_skills"][:40]))
    with tabs[2]:
        c1, c2 = st.columns(2)
        c1.markdown(css + ch["titles"], unsafe_allow_html=True)
        c2.markdown(css + ch["primary"], unsafe_allow_html=True)
        st.markdown(L(lang, "**Título de rol y skill primario**", "**Role title and primary skill**"))
        st.dataframe(pd.DataFrame(demand.visible(a["combos"])), hide_index=True, width="stretch")
    with tabs[3]:
        st.caption(L(lang, "Lo que se pide y no aparece en PracticaSkills ni en PracticaRoles. Si algo sí es de la práctica, agrégalo ahí (o como alias).",
                     "What is requested and is not in PracticaSkills or PracticaRoles. If something does belong to the practice, add it there (or as an alias)."))
        st.markdown(css + ch["outside"], unsafe_allow_html=True)
        st.markdown(L(lang, f"**Roles fuera de la práctica ({len(a['outside_roles'])})**", f"**Roles outside the practice ({len(a['outside_roles'])})**"))
        st.dataframe(pd.DataFrame(a["outside_roles"]), hide_index=True, width="stretch")
    with tabs[4]:
        st.caption(L(lang, "Skills de la práctica que se piden, cruzados con el contenido de la academia. «Con curso» = tiene lecciones; "
                           "«Solo learning path» = tiene clases del fabricante pero no lecciones propias; «No está en el catálogo» = hay que agregarlo en Skills.",
                     "Practice skills in demand, crossed with the academy's content. \"Has a course\" = it has lessons; "
                     "\"Learning path only\" = vendor classes but no lessons of our own; \"Not in the catalog\" = it has to be added to Skills."))
        st.markdown(css + ch["backlog"], unsafe_allow_html=True)
        st.dataframe(pd.DataFrame(demand.visible(a["backlog"])), hide_index=True, width="stretch")
    with tabs[5]:
        names = {"Skill Category": L(lang, "Categoría de skill", "Skill category"), "Client": L(lang, "Cliente", "Client"),
                 "Industry Level 1": L(lang, "Industria", "Industry"), "Role Country/Territory": L(lang, "País", "Country"),
                 "Role Status": L(lang, "Estado del rol", "Role status"), "Role Market Unit": "Market unit",
                 "Role Career Level From": L(lang, "Nivel de carrera", "Career level")}
        cols = st.columns(3)
        for i, (name, items) in enumerate(a["by"].items()):
            if items:
                cols[i % 3].markdown(f"**{names.get(name, name)}**")
                cols[i % 3].dataframe(pd.DataFrame(items, columns=[names.get(name, name), "Roles"]), hide_index=True, width="stretch")
        if a["months"]:
            st.markdown(L(lang, "**Roles por mes de inicio**", "**Roles by start month**"))
            st.bar_chart(pd.DataFrame(a["months"], columns=[L(lang, "Mes", "Month"), "Roles"]).set_index(L(lang, "Mes", "Month")), color="#eb6834")
    with tabs[6]:
        st.markdown(practice.description or "—")
        st.caption(L(lang, "Se edita en el archivo de contenido: tablas Practica, PracticaSkills y PracticaRoles. Otra práctica (por ejemplo ServiceNow) "
                           "usa la misma academia cambiando esas tablas y el catálogo de skills.",
                     "Edited in the content file: tables Practica, PracticaSkills and PracticaRoles. Another practice (for example ServiceNow) "
                     "uses the same academy by changing those tables and the skills catalog."))
        st.dataframe(pd.DataFrame([{"Term": t.term, "Aliases": "; ".join(t.aliases), "SkillId": t.skill_id, "FamilyId": t.family, "Vendor": t.vendor,
                                    "Scope": t.scope} for t in practice.skills]), hide_index=True, width="stretch")
        st.dataframe(pd.DataFrame([{"RoleTitle": r.title, "Aliases": "; ".join(r.aliases), "Scope": r.scope} for r in practice.roles]),
                     hide_index=True, width="stretch")
