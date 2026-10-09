"""The champion's panel in the Learning route: run the family's path (classes on / off, order, own decks) with a table or a CSV."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from academy import content_sync, family_path as fp, ui
from academy.catalog import load_materials, save_materials, validate_materials

PROVIDERS = ["Microsoft Learn", "Workday Learning", "Champion", "AWS Skill Builder", "Google Cloud Skills Boost", "Cisco Networking Academy",
             "IBM SkillsBuild", "Anthropic Academy", "John Savill's Technical Training", "SharePoint"]


def _save(fid: str, new: dict, catalog) -> bool:
    mats = fp.replace(fid, new, catalog)
    errs = validate_materials({k: v for k, v in mats.items() if k in new}, catalog)
    if errs:
        st.error("Nothing was saved:\n\n" + "\n\n".join(errs[:15]))
        return False
    save_materials(mats)
    fp.refresh(catalog, mats)  # the family CSV files
    content_sync.refresh()  # the content workbook
    st.cache_data.clear()
    ui.fx("ok")
    return True


def manage_family(catalog, fid: str, who: str, embedded: bool = False) -> None:
    """The courses of the family's skills (on / off, module, order, location, own files), as a table or as the family CSV.
    ``embedded``: drawn inside the champion's panel of the learning paths (no expander of its own)."""
    fam = next(f for f in catalog.families if f.id == fid)
    skills = {s.id: s.name for s in catalog.in_family(fid)}
    by_name = {v: k for k, v in skills.items()}
    import contextlib

    box = contextlib.nullcontext() if embedded else st.expander(f"🧭 Manage the career path of {fam.name} (champion)", expanded=False)
    with box:
        st.caption("Switch classes on and off for the learners of this family: **required** classes form the path and count for progress, "
                   "**optional** ones are recommended material, **off** keeps them in your plan but hidden. Use Microsoft Learn, the vendor's "
                   "free training, Workday Learning, a SharePoint deck or a file you upload here (your own PowerPoint).")
        rows = fp.rows(fid, catalog, load_materials())
        from academy.paths import LOCATIONS, location_of

        df = pd.DataFrame([{"Skill": r["Skill"], "Module": r["Module"] or None, "Class": r["Class"] or None, "Title": r["Title"], "Url": r["Url"],
                            "Kind": r["Kind"] or None, "Location": r["Location"] or location_of({"url": r["Url"]}), "Provider": r["Provider"] or None,
                            "Status": r["Status"], "Minutes": r["Minutes"] or None, "Notes": r["Notes"] or None}
                           for r in rows], columns=["Skill", "Module", "Class", "Title", "Url", "Kind", "Location", "Provider", "Status", "Minutes", "Notes"])
        for col in ("Class", "Minutes"):
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
        for col in ("Skill", "Module", "Title", "Url", "Kind", "Location", "Provider", "Status", "Notes"):
            df[col] = df[col].astype("string")
        providers = list(dict.fromkeys(PROVIDERS + [r["Provider"] for r in rows if r["Provider"]]))
        with st.form(f"fp_form_{fid}_{len(rows)}", border=False, enter_to_submit=False):
            ed = st.data_editor(df, num_rows="dynamic", hide_index=True, width="stretch", key=f"fp_ed_{fid}_{len(rows)}", column_config={
                "Skill": st.column_config.SelectboxColumn("Skill", options=list(by_name), required=True),
                "Module": st.column_config.TextColumn("Module", help="Groups the courses of a skill (e.g. Identity basics); empty = Core"),
                "Class": st.column_config.NumberColumn("Class", min_value=1, step=1, help="Order of the required classes inside the skill: 1, 2, 3…"),
                "Title": st.column_config.TextColumn("Title", required=True, width="medium"),
                "Url": st.column_config.TextColumn("Url", required=True, help="https://… or file:… for a file uploaded below", width="medium"),
                "Kind": st.column_config.SelectboxColumn("Kind", options=fp.KINDS, required=True),
                "Location": st.column_config.SelectboxColumn("Where it lives", options=LOCATIONS),
                "Provider": st.column_config.SelectboxColumn("Provider", options=providers),
                "Status": st.column_config.SelectboxColumn("Status", options=fp.STATUSES, required=True, default=fp.REQUIRED,
                                                           help="required = part of the path · optional = recommended · off = hidden"),
                "Minutes": st.column_config.NumberColumn("Minutes", min_value=0, step=5),
                "Notes": st.column_config.TextColumn("Notes")})
            save_path = st.form_submit_button("💾 Save the courses", key=f"fp_save_{fid}", type="primary")
        c = st.columns(3)
        n_req = sum(1 for s in ed["Status"].tolist() if s == fp.REQUIRED)
        c[0].metric("Required classes", n_req, border=True)
        c[1].metric("Optional", sum(1 for s in ed["Status"].tolist() if s == fp.OPTIONAL), border=True)
        c[2].metric("Off", sum(1 for s in ed["Status"].tolist() if s == fp.OFF), border=True)
        if save_path:
            table = [{"SkillId": by_name.get(r["Skill"], ""), "Class": "" if pd.isna(r["Class"]) else int(r["Class"]),
                      **{k: ("" if pd.isna(r[k]) else str(r[k])) for k in ("Module", "Title", "Url", "Kind", "Location", "Provider", "Status", "Notes")},
                      "Minutes": "" if pd.isna(r["Minutes"]) else int(r["Minutes"])}
                     for r in ed.to_dict("records") if pd.notna(r.get("Title")) and pd.notna(r.get("Url"))]
            new, problems = fp.parse(fp.to_csv(table), fid, catalog)
            if problems:
                st.error("Nothing was saved:\n\n" + "\n\n".join(problems[:15]))
            elif _save(fid, new, catalog):
                st.toast("Career path saved: learners see it now.")
                st.rerun()
        st.markdown("**Add your own material** (PowerPoint, PDF, Word, Excel, video): it becomes a class that learners download.")
        u = st.columns([3, 2, 2])
        up = u[0].file_uploader("File", type=fp.FILE_TYPES, key=f"fp_file_{fid}", label_visibility="collapsed")
        skill = u[1].selectbox("For the skill", list(skills), format_func=lambda k: skills[k], key=f"fp_fskill_{fid}")
        status = u[2].selectbox("Status", fp.STATUSES, key=f"fp_fstatus_{fid}")
        if up is not None and st.button(f"Add «{up.name}» to the path", key=f"fp_fadd_{fid}"):
            try:
                url = fp.save_file(fid, up.name, up.getvalue())
            except ValueError as e:
                st.error(str(e))
            else:
                mats = load_materials()
                kind = "deck" if up.name.lower().endswith((".ppt", ".pptx")) else ("video" if up.name.lower().endswith(".mp4") else "doc")
                items = [m for m in mats.get(skill, []) if m.get("url") != url]
                order = max([int(m.get("order") or 0) for m in items] + [0]) + 1
                items.append({"title": up.name.rsplit(".", 1)[0], "url": url, "kind": kind, "provider": "Champion", "status": status,
                              "order": order, "notes": f"Uploaded by {who}"})
                if _save(fid, {**{s: mats.get(s, []) for s in skills}, skill: items}, catalog):
                    st.toast("File added to the path.")
                    st.rerun()
        st.markdown(f"**The family's CSV**: `content/families/{fid}.csv` — edit it in Excel and reopen the app, or download / upload it here.")
        d = st.columns(2)
        d[0].download_button("Download this family's path (CSV)", fp.export(fid, catalog), file_name=f"{fid}.csv", mime="text/csv",
                             key=f"fp_csv_{fid}", width="stretch")
        csv_up = d[1].file_uploader("Upload the family's path (CSV)", type=["csv"], key=f"fp_up_{fid}", label_visibility="collapsed")
        if csv_up is not None:
            new, problems = fp.parse(csv_up.getvalue(), fid, catalog)
            if problems:
                st.error("\n\n".join(problems[:20]))
            elif st.button(f"Replace the path of {fam.name} with this file ({sum(map(len, new.values()))} items)", key=f"fp_imp_{fid}", type="primary"):
                if _save(fid, new, catalog):
                    st.rerun()


def download_step(url: str, title: str, key: str, container) -> bool:
    """A class that is an uploaded file: a download button instead of a link. Returns False for web links."""
    path = fp.file_path(url)
    if path is None:
        if str(url).startswith("file:"):
            container.caption("File not found in this computer's academy folder.")
            return True
        return False
    container.download_button(f"⬇ Download {path.suffix.upper().lstrip('.')}", path.read_bytes(), file_name=path.name, key=key, width="stretch")
    return True
