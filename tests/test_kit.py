"""Academy Kit: pack rules, scoring, VBD flow, team view and the Streamlit page end to end."""

import json
import random
from pathlib import Path

import pytest

from academy import quiz
from academy import catalog as catmod
from academy.catalog import (catalog_from_tables, load_catalog, parse_grid, parse_text, read_xlsx, save_catalog, sheet_names,
                             validate_catalog)
from academy.pack import available_packs, load_pack, validate
from academy.progress import VBD_POINTS, Tracker, connect, team  # noqa: F401
from academy.videos import embed_src, playlist_id, youtube_id

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def pack():
    return load_pack("cloud-security")


@pytest.fixture
def conn(tmp_path):
    return connect(tmp_path / "t.db")


def test_every_shipped_pack_is_valid():
    assert "cloud-security" in available_packs() and "_plantilla" not in available_packs()
    for name in available_packs():
        assert validate(load_pack(name)) == [], name


def test_template_has_the_same_shape():
    tpl = load_pack(ROOT / "packs" / "_plantilla")
    assert tpl.lessons and tpl.lessons[0].vbd and len(tpl.lessons[0].quiz) == 3


def test_validator_catches_broken_content(pack, tmp_path):
    data = json.loads((ROOT / "packs" / "cloud-security" / "pack.json").read_text(encoding="utf-8"))
    data["lessons"][0]["quiz"] = data["lessons"][0]["quiz"][:2]
    data["lessons"][1]["resources"] = data["lessons"][1]["resources"][:1]
    data["lessons"][2]["vbd"]["done_when"] = ["solo uno"]
    data["resources"]["x"] = {"title": "t", "url": "http://example.com", "channel": "c", "why": "w", "kind": "video", "topic": "nope"}
    (tmp_path / "pack.json").write_text(json.dumps(data), encoding="utf-8")
    errs = " | ".join(validate(load_pack(tmp_path)))
    for needle in ("exactamente 3 preguntas", "al menos 2 videos", "3 criterios", "https", "embebible", "tema 'nope'"):
        assert needle in errs, needle


def test_youtube_parsing():
    assert youtube_id("https://youtu.be/abc") == "abc"
    assert youtube_id("https://www.youtube.com/shorts/xyz") == "xyz"
    assert youtube_id("https://www.youtube.com/watch?v=q1&t=3") == "q1"
    assert playlist_id("https://www.youtube.com/playlist?list=PL1") == "PL1"
    assert "youtube-nocookie.com/embed/q1" in embed_src("https://www.youtube.com/watch?v=q1")
    assert embed_src("https://example.com") is None


def test_quiz_scoring_and_completion(pack, conn):
    t = Tracker(conn, pack, "ana")
    les = pack.lessons[0]
    assert t.answer_quiz(f"{les.id}:0", False) == 0
    assert t.answer_quiz(f"{les.id}:0", True) == 5
    assert t.answer_quiz(f"{les.id}:0", True) == 0
    assert t.answer_quiz(f"{les.id}:1", True) == 10
    assert les.id not in t.completed_lessons()
    t.answer_quiz(f"{les.id}:2", True)
    assert les.id in t.completed_lessons() and t.total_points() == 25
    assert Tracker(conn, pack, "luis").total_points() == 0  # progress is per person


def test_vbd_needs_every_criterion(pack, conn):
    t = Tracker(conn, pack, "ana")
    les = pack.lessons[0]
    assert t.complete_vbd(les.id) == 0
    for i in range(len(les.vbd.done_when) - 1):
        t.set_check(les.id, i, True)
    assert t.complete_vbd(les.id) == 0
    t.set_check(les.id, len(les.vbd.done_when) - 1, True)
    assert t.complete_vbd(les.id, "https://wiki/raci") == VBD_POINTS
    assert t.complete_vbd(les.id) == 0 and les.id in t.vbds_done()
    assert any(n == "Generador de valor" and ok for n, _, ok in t.badges())


def test_ranks_and_team(pack, conn):
    t = Tracker(conn, pack, "ana")
    assert t.rank(0) == (0, 100) and t.rank(1000)[1] is None
    t.record("glossary", "MFA", 10, True)
    df = team(conn, pack)
    assert list(df["Persona"]) == ["ana"] and df["Puntos"].iloc[0] == 10


def test_role_filter(pack):
    soc = pack.lessons_for_role("Analista de seguridad (SOC)")
    assert {"r1", "r2", "r3"} <= soc and "d3" not in soc


def test_glossary_question_has_one_right_answer(pack):
    rng = random.Random(3)
    for _ in range(200):
        g = quiz.glossary_question(pack.glossary, rng)
        assert len(set(g["options"])) == 4 and 0 <= g["correct"] < 4


def test_shuffle_is_stable():
    opts, ci = quiz.shuffled("f1:0", ["a", "b", "c", "d"], 2)
    assert opts[ci] == "c" and quiz.shuffled("f1:0", ["a", "b", "c", "d"], 2) == (opts, ci)


def _run(tmp_path, monkeypatch, owners=("yo",), **state):
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("ACADEMY_ACCESS", str(tmp_path / "access.json"))
    monkeypatch.setenv("ACADEMY_ASSISTANT", str(tmp_path / "assistant.json"))
    if owners is not None and not (tmp_path / "access.json").exists():
        (tmp_path / "access.json").write_text(json.dumps({"owners": list(owners)}), encoding="utf-8")

    monkeypatch.setenv("ACADEMY_DB", str(tmp_path / "app.db"))
    monkeypatch.setenv("ACADEMY_CATALOG", str(tmp_path / "skills.json"))  # never let a test overwrite the real catalog
    if not (tmp_path / "skills.json").exists():
        (tmp_path / "skills.json").write_text(catmod.CATALOG_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    state.setdefault("ak_lang", "es")  # the app opens in English; these tests read the Spanish texts
    for k, v in state.items():
        if v is not None:  # None = leave the app's own default
            at.session_state[k] = v
    return at.run()


def test_app_renders_and_scores(tmp_path, monkeypatch):
    at = _run(tmp_path, monkeypatch)
    assert not at.exception
    assert any("Videos de esta lección" in m.value for m in at.markdown)
    assert any("Entregable de valor" in m.value for m in at.markdown)
    pack = load_pack("cloud-security")
    les = pack.lessons[0]
    opts, ci = quiz.shuffled(f"{les.id}:0", les.quiz[0].options, les.quiz[0].answer)
    at.radio(key=f"ak_q_yo_{les.id}:0").set_value(ci).run()
    at.button(key=f"ak_check_{les.id}:0").click().run()
    assert not at.exception and any("Correcto" in s.value for s in at.success)
    at.selectbox(key=f"ak_vid_{les.id}").set_value(1).run()  # change video without losing the answer
    assert not at.exception and any("Correcto" in s.value for s in at.success)
    for i in range(len(les.vbd.done_when)):
        at.checkbox(key=f"ak_vbd_yo_{les.id}_{i}").check().run()
    at.button(key=f"ak_vbd_btn_{les.id}").click().run()
    assert not at.exception
    assert les.id in Tracker(connect(tmp_path / "app.db"), pack, "yo").vbds_done()


def test_app_other_tabs_and_english(tmp_path, monkeypatch):
    at = _run(tmp_path, monkeypatch)
    at.radio(key=f"ak_gq_pick_{at.session_state['ak_gq_n']}").set_value(0).run()
    at.button(key="ak_gq_check").click().run()
    assert not at.exception
    for topic in ("fundamentos", "identidad", "referencias"):
        at.selectbox(key="ak_lib_topic").set_value(topic).run()
        assert not at.exception
    at.toggle(key="ak_lib_es").set_value(True).run()
    at.selectbox(key="ak_role").set_value("DevOps / SRE").run()
    assert not at.exception
    at.radio(key="ak_lang").set_value("en").run()
    assert not at.exception and any("Videos for this lesson" in m.value for m in at.markdown)


def test_catalog_is_valid_and_lessons_point_to_it(pack):
    cat = load_catalog()
    assert validate_catalog(cat) == [] and len(cat.skills) == 34
    assert validate(pack, cat) == []
    assert cat.by_gap()[0].name == "Microsoft 365 Security" and cat.by_gap()[-1].gap_volume is None
    assert len(cat.families) == 9
    cov = cat.coverage([pack])
    assert any(t == "Contenedores y Kubernetes" for _, t in cov["container-security"]) and cov["exchange-online"] == []


def test_validator_catches_unknown_catalog_skill(tmp_path):
    data = json.loads((ROOT / "packs" / "cloud-security" / "pack.json").read_text(encoding="utf-8"))
    data["lessons"][0]["catalog_skills"] = ["no-existe"]
    (tmp_path / "pack.json").write_text(json.dumps(data), encoding="utf-8")
    assert any("no-existe" in e for e in validate(load_pack(tmp_path), load_catalog()))


def test_skills_tab_renders(tmp_path, monkeypatch):
    at = _run(tmp_path, monkeypatch)
    assert not at.exception
    assert any("Microsoft 365 Security" in m.value for m in at.markdown)
    assert any("por asignar" in m.value for m in at.markdown)


def _sample(tmp_path):
    import importlib.util

    spec = importlib.util.spec_from_file_location("make_sample_xlsx", ROOT / "tools" / "make_sample_xlsx.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.build(tmp_path / "plan.xlsx")


def test_import_reads_only_the_chosen_sheet(tmp_path):
    path = _sample(tmp_path)
    assert sheet_names(path) == ["Sheet4 editable", "Upskilling Plan"]
    assert parse_grid(read_xlsx(path, "Sheet4 editable"))[0] is None  # no table there: clear error, no crash
    cat, rep = parse_grid(read_xlsx(path, "Upskilling Plan"))
    assert rep["families"] == 9 and rep["skills"] == 34 and rep["header_row"] == 15 and rep["summary"]
    assert validate_catalog(cat) == []
    m365 = next(f for f in cat.families if f.name == "Microsoft 365 Security")
    assert (m365.gap_volume, m365.role_impact, m365.champion) == (194, 97, "Microsoft 365 Security Champion")
    iam = next(f for f in cat.families if f.name == "Identity & Access Management")
    assert iam.gap_volume and iam.role_impact  # not in the summary table: computed from the impacted roles
    sk = next(s for s in cat.skills if s.id == "microsoft-365-security")
    assert sk.severity == "High" and sk.target == "P3 - Advanced" and sk.impacted_roles == 2 and sk.roles == []
    kept, _ = parse_grid(read_xlsx(path, "Upskilling Plan"), keep_roles=True)
    assert next(s for s in kept.skills if s.id == "microsoft-365-security").roles == ["Rol de ejemplo 1", "Rol de ejemplo 2"]


def test_import_keeps_assigned_champions_and_round_trips(tmp_path):
    path = _sample(tmp_path)
    first, _ = parse_grid(read_xlsx(path, "Upskilling Plan"))
    prev2 = type(first)([type(f)(f.id, f.name, f.gap_volume, f.role_impact, "Ana") for f in first.families], first.skills)
    again2, _ = parse_grid(read_xlsx(path, "Upskilling Plan"), previous=prev2)
    assert {f.champion for f in again2.families} == {"Ana"}
    out = save_catalog(again2, tmp_path / "c.json", source="test", updated="2026-10-01")
    back = load_catalog(out)
    assert [s.id for s in back.skills] == [s.id for s in again2.skills] and back.families[0].champion == "Ana"


def test_pasted_table_and_manual_tables():
    text = "Skill Family\tUnaligned / Missing Skill\tGap Severity / Priority Band\nMicrosoft 365 Security\tExchange Online\tHigh\n\tDefender for Office 365\tmedium\n"
    cat, rep = parse_grid(parse_text(text))
    assert [s.name for s in cat.skills] == ["Exchange Online", "Defender for Office 365"]  # blank family = same as the row above
    assert cat.skills[1].severity == "Medium" and cat.families[0].gap_volume is None and "roles" in rep["missing_columns"]
    assert parse_grid(parse_text("hola\tmundo"))[0] is None
    man = catalog_from_tables([{"name": "Zero Trust y red", "gap": 5, "impact": float("nan"), "champion": "Luis"}, {"name": None}],
                              [{"family": "Zero Trust y red", "name": "Zero Trust", "severity": "High", "target": "P3 - Advanced", "impact": 3},
                               {"family": "No existe", "name": "Otra"}])
    assert man.families[0].role_impact is None and man.skills[0].id == "zero-trust"
    assert any("No existe".lower().replace(" ", "-") in e for e in validate_catalog(man))


def test_skills_tab_modes_render_and_save(tmp_path, monkeypatch):
    at = _run(tmp_path, monkeypatch, ak_sk_mode="edit")
    assert not at.exception
    at.button(key="ak_sk_save_edit").click().run()
    assert not at.exception and len(load_catalog(tmp_path / "skills.json").skills) == 34
    at = _run(tmp_path, monkeypatch, ak_sk_mode="paste")
    at.text_area(key="ak_sk_text").set_value("Skill Family\tMissing Skill\nRedes\tAzure Firewall").run()
    assert not at.exception and any("1 familias" in s.value for s in at.success)
    at.button(key="ak_sk_save_paste").click().run()
    assert not at.exception and [s.name for s in load_catalog(tmp_path / "skills.json").skills] == ["Azure Firewall"]
    assert not _run(tmp_path, monkeypatch, ak_sk_mode="import").exception


def test_sharepoint_export(tmp_path, pack):
    import csv
    import importlib.util

    spec = importlib.util.spec_from_file_location("export_sharepoint", ROOT / "tools" / "export_sharepoint.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    files = {p.stem: p for p in mod.export("cloud-security", tmp_path)}
    assert set(files) == {"Familias", "Skills", "Lecciones", "Preguntas", "Recursos", "LeccionRecursos", "Glosario", "Rangos"}
    rows = {k: list(csv.DictReader(p.open(encoding="utf-8-sig"))) for k, p in files.items()}
    assert len(rows["Lecciones"]) == 12 and len(rows["Preguntas"]) == 36 and len(rows["Skills"]) == 34 and len(rows["Familias"]) == 9
    q = rows["Preguntas"][0]
    assert q[f"Option{q['AnswerLetter']}"] == pack.lessons[0].quiz[0].options[pack.lessons[0].quiz[0].answer]
    assert {r["LessonId"] for r in rows["LeccionRecursos"]} == {les.id for les in pack.lessons}


# ---------------------------------------------------------------------------------------------- certifications
@pytest.fixture
def exam():
    from academy.exam import load_exam

    return load_exam("ai-901")


def test_exam_pack_is_valid(exam):
    from academy.catalog import load_materials, validate_materials
    from academy.exam import available_exams, quota, validate_exam

    assert "ai-901" in available_exams()
    assert validate_exam(exam, load_catalog()) == []
    assert quota(exam) == {"concepts": 11, "foundry": 14} and len(exam.questions) == 35
    assert validate_materials(load_materials(catmod.CATALOG_PATH.parent / "materials.json"), load_catalog()) == []


def test_mock_is_weighted_and_graded(exam):
    from academy.exam import build_mock, grade

    qids = build_mock(exam, random.Random(1))
    assert len(qids) == len(set(qids)) == 25
    assert sum(exam.domain_of(exam.question(q)) == "concepts" for q in qids) == 11
    assert {exam.question(q).module for q in qids} == {m.id for m in exam.modules}  # every module shows up
    assert qids != build_mock(exam, random.Random(2))
    perfect = grade(exam, qids, {q: exam.question(q).answer for q in qids})
    assert perfect["score"] == 1000 and perfect["passed"] and perfect["wrong"] == []
    answers = {q: (exam.question(q).answer if i < 17 else None) for i, q in enumerate(qids)}
    res = grade(exam, qids, answers)
    assert res["score"] == 680 and not res["passed"] and res["unanswered"] == 8 and len(res["wrong"]) == 8
    assert grade(exam, qids, {q: (exam.question(q).answer if i < 18 else None) for i, q in enumerate(qids)})["passed"]  # 720


def test_exam_tracker_points_and_readiness(exam, conn):
    from academy.exam import EXERCISE_POINTS, PASS_POINTS, PRACTICE_POINTS, ExamTracker, build_mock, check_match, check_order, grade

    t = ExamTracker(conn, exam, "ana")
    q = exam.questions[0]
    assert t.answer_practice(q.id, False) == 0 and t.answer_practice(q.id, True) == PRACTICE_POINTS and t.answer_practice(q.id, True) == 0
    order = next(e for e in exam.exercises() if e.type == "order")
    match = next(e for e in exam.exercises() if e.type == "match")
    assert check_order(order, order.steps) and not check_order(order, order.steps[::-1])
    assert all(check_match(match, dict(match.pairs))) and not all(check_match(match, {p[0]: match.pairs[0][1] for p in match.pairs}))
    assert t.complete_exercise(order.id) == EXERCISE_POINTS and t.complete_exercise(order.id) == 0
    assert 0 < t.readiness() < 0.1 and t.weak_modules()[0][1] == 0
    qids = build_mock(exam, random.Random(3))
    assert t.record_mock(grade(exam, qids, {}), 60) == 0 and not t.passed()
    ok = grade(exam, qids, {x: exam.question(x).answer for x in qids})
    assert t.record_mock(ok, 900) == PASS_POINTS and t.record_mock(ok, 900) == 0 and t.passed()
    assert [a["score"] for a in t.attempts()] == [0, 1000, 1000]
    assert t.total_points() == PRACTICE_POINTS + EXERCISE_POINTS + PASS_POINTS
    assert ExamTracker(conn, exam, "luis").total_points() == 0


# ---------------------------------------------------------------------------------------------- notices
def _backdate(conn, learner, days):
    from datetime import datetime, timedelta, timezone

    conn.execute("UPDATE events SET time=? WHERE learner=?", ((datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds"), learner))
    conn.commit()


def test_notices_rules_and_champion_copy(pack, exam, conn):
    from academy import notify
    from academy.exam import ExamTracker, build_mock, grade

    cat = load_catalog()
    fams = [type(f)(f.id, f.name, f.gap_volume, f.role_impact, f"Champ {i}", f"champ{i}@x.com") for i, f in enumerate(cat.families)]
    cat = type(cat)(fams, cat.skills)
    args = (conn, [pack], [exam], cat)
    assert notify.pending(*args) == []
    Tracker(conn, pack, "ana@x.com").answer_quiz("f1:0", True)
    assert notify.pending(*args) == []  # active today, nothing to say
    _backdate(conn, "ana@x.com", 6)
    (n,) = notify.pending(*args)
    assert n.kind == "inactive" and "6 días" in n.subject and n.to == "ana@x.com" and n.cc and n.champions
    assert "El modelo de responsabilidad compartida" in n.body and n.champions[0] in n.body
    assert notify.mailto(n).startswith("mailto:ana%40x.com?cc=") and "subject=No%20has%20tomado" in notify.mailto(n)
    notify.mark_sent(conn, n)
    assert notify.pending(*args) == [] and len(notify.pending(*args, include_sent=True)) == 1
    # stalled: came back (activity without points) but no progress for a week
    _backdate(conn, "ana@x.com", 9)
    Tracker(conn, pack, "ana@x.com").answer_quiz("f1:1", False)
    assert [x.kind for x in notify.pending(*args)] == ["stalled"]
    # finishing the course and passing the mock: congratulations with the owner family's champion in copy
    t = Tracker(conn, pack, "luis")
    for les in pack.lessons:
        for k in range(3):
            t.answer_quiz(f"{les.id}:{k}", True)
    qids = build_mock(exam, random.Random(1))
    ExamTracker(conn, exam, "luis").record_mock(grade(exam, qids, {q: exam.question(q).answer for q in qids}), 600)
    notify.set_email(conn, "luis", "luis@x.com")
    mine = {x.kind: x for x in notify.pending(*args, learner="luis")}
    assert set(mine) == {"course_done", "exam_passed"} and mine["course_done"].to == "luis@x.com"
    assert "AI-901" in mine["exam_passed"].subject and "1000 de 1000" in mine["exam_passed"].body
    ai = next(f for f in cat.families if f.id == exam.family)
    assert mine["exam_passed"].cc == [ai.champion_email]
    assert notify.owner_families(pack, cat)[0].name == "Cloud & Network Security"
    assert notify.queue_rows(list(mine.values()))[0]["To"] == "luis@x.com"


def test_certification_tab_and_notices_render(tmp_path, monkeypatch):
    at = _run(tmp_path, monkeypatch, ex_mode="study")
    assert not at.exception and any("AI-901" in m.value for m in at.markdown)
    at = _run(tmp_path, monkeypatch, ex_mode="practice")
    assert not at.exception
    at = _run(tmp_path, monkeypatch, ex_mode="mock")
    at.button(key="ex_start_ai-901").click().run()
    assert not at.exception and len([r for r in at.radio if str(r.key).startswith("ex_mq_")]) == 25
    assert not _run(tmp_path, monkeypatch, ex_mode="history").exception


# ---------------------------------------------------------------------------------------------- views
def test_access_rules(tmp_path):
    from academy.access import Access, load_access, save_access

    acc = Access(owners=["Ana@x.com", "luis"])
    assert acc.is_leader("ana@x.com") and acc.is_leader("pepe", "ANA@x.com") and acc.is_leader(" Luis ") and not acc.is_leader("pepe")
    cat = load_catalog()
    fams = [type(f)(f.id, f.name, f.gap_volume, f.role_impact, "Carla", "carla@x.com") if i == 0 else f for i, f in enumerate(cat.families)]
    led = type(cat)(fams, cat.skills)
    assert acc.is_leader("carla", catalog=led) and not acc.is_leader("carla", catalog=cat) and not acc.is_owner("carla")
    assert acc.champion_families("x", "CARLA@x.com", led) == {fams[0].id} and acc.champion_families("pepe", catalog=led) == set()
    assert acc.check_pin("anything") and not acc.has_pin()
    acc.set_pin("2468")
    back = load_access(save_access(acc, tmp_path / "a.json"))
    assert back.owners == ["Ana@x.com", "luis"] and back.has_pin() and back.check_pin("2468") and not back.check_pin("0000")
    assert "2468" not in (tmp_path / "a.json").read_text(encoding="utf-8")
    assert not load_access(tmp_path / "missing.json").configured


def _tab_labels(at):
    return [t.label for t in at.tabs]


def test_end_user_does_not_see_team_measurements(tmp_path, monkeypatch):
    at = _run(tmp_path, monkeypatch, owners=("jefa",))  # "yo" is not an owner
    assert not at.exception
    assert not any("Equipo" in x for x in _tab_labels(at)) and len(_tab_labels(at)) == 7
    assert not any("Avisos por enviar" in m.value for m in at.markdown)
    assert not any(m.label in ("Brecha", "Roles afectados") for m in at.metric)
    assert any("Microsoft 365 Security" in m.value for m in at.markdown)  # the map itself stays visible
    assert not any(str(b.key).startswith("ak_sk_save") for b in at.button) and "ak_owner_view" not in [t.key for t in at.toggle]


def test_owner_view_and_switch_to_end_user(tmp_path, monkeypatch):
    at = _run(tmp_path, monkeypatch)  # "yo" is an owner
    assert any("Equipo" in x for x in _tab_labels(at)) and len(_tab_labels(at)) == 8
    assert any(m.label == "Brecha" for m in at.metric) and any("Avisos por enviar" in m.value for m in at.markdown)
    at.toggle(key="ak_owner_view").set_value(False).run()  # preview what an end user sees
    assert not at.exception and len(_tab_labels(at)) == 7 and not any(m.label == "Brecha" for m in at.metric)


def test_first_owner_claim_and_pin(tmp_path, monkeypatch):
    from academy.access import load_access, save_access

    at = _run(tmp_path, monkeypatch, owners=None)  # nothing configured yet
    assert len(_tab_labels(at)) == 7
    at.button(key="ak_claim").click().run()
    assert not at.exception and load_access(tmp_path / "access.json").owners == ["yo"] and len(_tab_labels(at)) == 8
    acc = load_access(tmp_path / "access.json")
    acc.set_pin("2468")
    save_access(acc, tmp_path / "access.json")
    at = _run(tmp_path, monkeypatch, owners=None)
    assert len(_tab_labels(at)) == 7  # owner, but the PIN has not been typed
    at.text_input(key="ak_owner_pin").set_value("1111").run()
    assert len(_tab_labels(at)) == 7
    at.text_input(key="ak_owner_pin").set_value("2468").run()
    assert not at.exception and len(_tab_labels(at)) == 8


def test_champion_sees_only_their_family(tmp_path, monkeypatch, pack, exam, conn):
    from academy import notify

    cat = load_catalog()
    net = "cloud-network-security"
    Tracker(conn, pack, "ana").answer_quiz("d2:0", True)   # d2 = Zero Trust / red -> Cloud & Network Security
    Tracker(conn, pack, "luis").answer_quiz("d3:0", True)  # d3 = contenedores -> Application Security & DevSecOps
    rows = notify.family_team(conn, [pack], [exam], cat, {net})
    assert [r["Persona"] for r in rows] == ["ana"] and rows[0]["Lecciones de la familia"].startswith("0/")
    assert notify.family_team(conn, [pack], [exam], cat, {"microsoft-365-security"}) == []
    from academy.exam import ExamTracker

    ExamTracker(conn, exam, "sol").answer_practice(exam.questions[0].id, True)
    assert [r["Persona"] for r in notify.family_team(conn, [pack], [exam], cat, {exam.family})] == ["sol"]

    # in the app: a champion (not an owner) gets the team tab scoped to the family and gap numbers only for it
    data = json.loads(catmod.CATALOG_PATH.read_text(encoding="utf-8"))
    for f in data["families"]:
        if f["id"] == net:
            f["champion"] = "yo"
    (tmp_path / "skills.json").write_text(json.dumps(data), encoding="utf-8")
    at = _run(tmp_path, monkeypatch, owners=("jefa",))
    assert not at.exception and len(_tab_labels(at)) == 8
    assert any("Mi familia" in m.value and "Cloud & Network Security" in m.value for m in at.markdown)
    assert not any("Acceso" in e.label for e in at.expander) and not any(str(b.key).startswith("ak_sk_save") for b in at.button)
    assert [m.value for m in at.metric if m.label == "Brecha"] == ["98"]  # only their own family's number


# ---------------------------------------------------------------------------------------------- learning route
def test_route_follows_vendor_training(conn):
    from academy.catalog import load_materials
    from academy.route import ITEM_POINTS, RouteTracker, build_routes

    cat = load_catalog()
    routes = {r.family_id: r for r in build_routes(cat, load_materials(catmod.CATALOG_PATH.parent / "materials.json"))}
    assert list(routes)[0] == "microsoft-365-security"  # biggest gap first
    iam = routes["identity-access-management"]
    assert iam.steps and all("learn.microsoft.com" in s.url and s.provider == "Microsoft Learn" for s in iam.steps) and not iam.uncovered
    ai = routes["ai-security-governance"]
    claude = [s for s in ai.steps if s.skill_id == "claude-code-security"]
    assert claude and claude[0].provider == "Anthropic Academy"  # non-Microsoft skill: the vendor's own path
    assert all(s.kind in ("module", "path", "course", "lab", "tutorial") for r in routes.values() for s in r.steps)
    assert "Zero Trust" in routes["cloud-network-security"].extras  # the guidance center is reference, not a step
    t = RouteTracker(conn, "ana")
    first = t.next_step(iam)
    assert t.progress(iam) == (0, len(iam.steps)) and first == iam.steps[0]
    assert t.complete(first, "https://learn.microsoft.com/users/ana/achievements/x") == ITEM_POINTS and t.complete(first) == 0
    assert t.progress(iam) == (1, len(iam.steps)) and t.next_step(iam) == iam.steps[1] and t.total_points() == ITEM_POINTS
    assert RouteTracker(conn, "luis").progress(iam)[0] == 0


def test_route_tab_marks_a_step(tmp_path, monkeypatch):
    from academy.route import RouteTracker, build_routes

    (tmp_path / "materials.json").write_text((catmod.CATALOG_PATH.parent / "materials.json").read_text(encoding="utf-8"), encoding="utf-8")
    at = _run(tmp_path, monkeypatch, owners=("jefa",))
    assert not at.exception and _tab_labels(at)[0].endswith("Ruta de aprendizaje")
    done = [b for b in at.button if str(b.key).startswith("rt_done_")]
    assert done
    done[0].click().run()
    assert not at.exception
    assert len(RouteTracker(connect(tmp_path / "app.db"), "yo").done()) == 1


def test_family_lead_adds_a_workday_course(tmp_path, monkeypatch):
    """A champion adds a course of the company portal for a skill of their family; it becomes a step of the route."""
    from academy.catalog import load_materials
    from academy.route import build_routes

    data = json.loads(catmod.CATALOG_PATH.read_text(encoding="utf-8"))
    for f in data["families"]:
        if f["id"] == "technical-delivery-leadership":
            f["champion"] = "yo"
    (tmp_path / "skills.json").write_text(json.dumps(data), encoding="utf-8")
    base = json.loads((catmod.CATALOG_PATH.parent / "materials.json").read_text(encoding="utf-8"))
    base["stakeholder-governance"] = [{"title": "Stakeholder Management Essentials", "url": "https://wd5.myworkday.com/empresa/learning/course/123",
                                       "provider": "Workday Learning", "kind": "course", "verified": "2026-10-01"}]
    (tmp_path / "materials.json").write_text(json.dumps(base), encoding="utf-8")
    at = _run(tmp_path, monkeypatch, owners=("jefa",))
    assert not at.exception and any("Cursos de mi familia" in e.label for e in at.expander)
    at.button(key="ak_fam_courses_save").click().run()  # saving keeps the family's rows and every other family's material
    assert not at.exception
    saved = load_materials(tmp_path / "materials.json")
    assert saved["stakeholder-governance"][0]["provider"] == "Workday Learning" and "microsoft-sentinel" in saved
    route = next(r for r in build_routes(load_catalog(tmp_path / "skills.json"), saved) if r.family_id == "technical-delivery-leadership")
    step = next(s for s in route.steps if s.skill_id == "stakeholder-governance")
    assert step.provider == "Workday Learning" and "Stakeholder Governance" not in route.uncovered


# ---------------------------------------------------------------------------------------------- AI assistant
def test_assistant_config_modes_and_prompts(tmp_path, monkeypatch, exam):
    from academy import assistant as ai

    cfg = ai.load_assistant(tmp_path / "none.json")
    assert cfg.name == "Amethyst" and cfg.mode == "handoff" and cfg.enabled
    cfg.api_url, cfg.url = "https://gw.example/chat/completions", "https://amethyst.example"
    assert cfg.mode == "handoff"  # an endpoint without a key is still copy-and-open
    monkeypatch.setenv("AMETHYST_API_KEY", "k-123")
    assert cfg.mode == "api"
    back = ai.load_assistant(ai.save_assistant(cfg, tmp_path / "a.json"))
    assert back.api_url == cfg.api_url and "k-123" not in (tmp_path / "a.json").read_text(encoding="utf-8")  # the key never touches disk
    q = exam.questions[0]
    p = ai.prompt_explain(q.q, q.options, q.options[q.answer], q.why, q.options[0], exam.name)
    assert q.q in p and q.options[q.answer] in p and "AI-901" in p
    plan = ai.prompt_study_plan(exam.name, 560, 700, [("Conceptos", 6, 11)], ["Módulo X"], [("Curso", "https://learn.microsoft.com/x")])
    assert "560 de 1000" in plan and "6 de 11" in plan and "https://learn.microsoft.com/x" in plan and "7 días" in plan
    assert "Workday" not in plan and "brecha" not in plan.lower()  # only the learner's own result and study content
    assert "ORIGINALES" in ai.prompt_draft_questions(exam.name, "m", ["a", "b", "c"]) and "P3" in ai.prompt_step_coach("F", "S", "T", "Microsoft Learn", "P3 - Advanced")


def test_assistant_api_call_and_errors(monkeypatch):
    import io

    from academy import assistant as ai

    cfg = ai.AssistantConfig(api_url="https://gw.example/chat/completions", model="m1", auth_header="api-key")
    assert ai.ask(cfg, "hola")[0] is False  # no key
    monkeypatch.setenv("AMETHYST_API_KEY", "k-123")
    seen = {}

    class Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake(req, timeout=0):
        seen["headers"], seen["body"], seen["url"] = dict(req.header_items()), json.loads(req.data), req.full_url
        return Resp(json.dumps({"choices": [{"message": {"content": " listo "}}]}).encode())

    monkeypatch.setattr(ai.urllib.request, "urlopen", fake)
    assert ai.ask(cfg, "hola") == (True, "listo")
    assert seen["headers"]["Api-key"] == "k-123" and seen["body"]["model"] == "m1" and seen["body"]["messages"][1]["content"] == "hola"
    monkeypatch.setattr(ai.urllib.request, "urlopen", lambda req, timeout=0: Resp(b'{"otro": 1}'))
    assert ai.ask(cfg, "hola")[0] is False
    assert ai.ask(ai.AssistantConfig(api_url="http://inseguro"), "x") == (False, "La URL del asistente debe ser https.")


def test_assistant_shows_in_the_app(tmp_path, monkeypatch):
    (tmp_path / "materials.json").write_text((catmod.CATALOG_PATH.parent / "materials.json").read_text(encoding="utf-8"), encoding="utf-8")
    at = _run(tmp_path, monkeypatch)
    assert not at.exception
    labels = [e.label for e in at.expander]
    assert any("siguiente paso con el tutor de IA" in x for x in labels) and any("Asistente de IA (Amethyst)" in x for x in labels)
    assert any("borrador de preguntas" in x for x in labels)  # leaders only
    (tmp_path / "u").mkdir()  # a second, separate installation where "yo" is an end user
    (tmp_path / "u" / "materials.json").write_text((tmp_path / "materials.json").read_text(encoding="utf-8"), encoding="utf-8")
    at2 = _run(tmp_path / "u", monkeypatch, owners=("jefa",))
    labels2 = [e.label for e in at2.expander]
    assert any("tutor de IA" in x for x in labels2) and not any("borrador de preguntas" in x or "Asistente de IA" in x for x in labels2)


# ---------------------------------------------------------------------------------------------- languages
def test_english_pack_mirrors_the_spanish_one():
    """Same ids, levels in the same order and same answers, so progress is shared between languages."""
    es, en = load_pack("cloud-security"), load_pack("cloud-security", "en")
    assert en.language == "en" and es.language == "es" and en.id == es.id
    assert validate(en, load_catalog()) == []
    assert len(en.levels) == len(es.levels) and len(en.glossary) == len(es.glossary) and set(en.resources) == set(es.resources)
    level = dict(zip(es.levels, en.levels))
    for a, b in zip(es.lessons, en.lessons):
        assert (a.id, level[a.level], a.resources, a.skills) == (b.id, b.level, b.resources, b.skills)
        assert [(q.answer, len(q.options)) for q in a.quiz] == [(q.answer, len(q.options)) for q in b.quiz]
        assert len(a.vbd.done_when) == len(b.vbd.done_when)
    assert [sorted(v) for v in es.roles.values()] == [sorted(v) for v in en.roles.values()]
    assert load_pack("cloud-security", "fr").language == "es"  # no translation: the pack's own language


def test_english_exam_mirrors_the_spanish_one():
    from academy.exam import load_exam, validate_exam

    es, en = load_exam("ai-901"), load_exam("ai-901", "en")
    assert validate_exam(en, load_catalog()) == []
    assert [(q.id, q.module, q.answer, len(q.options)) for q in es.questions] == [(q.id, q.module, q.answer, len(q.options)) for q in en.questions]
    assert [(m.id, [(e.id, e.type, len(e.steps), len(e.pairs)) for e in m.exercises]) for m in es.modules] == \
           [(m.id, [(e.id, e.type, len(e.steps), len(e.pairs)) for e in m.exercises]) for m in en.modules]


def test_app_opens_in_english_and_can_switch_to_spanish(tmp_path, monkeypatch):
    at = _run(tmp_path, monkeypatch, ak_lang=None)
    assert not at.exception
    assert at.session_state["ak_lang"] == "en"
    text = " ".join(m.value for m in at.markdown)
    assert "Your next step" in text and "The shared responsibility model" in text and "Tu siguiente paso" not in text
    es = _run(tmp_path, monkeypatch)
    assert "Tu siguiente paso" in " ".join(m.value for m in es.markdown)


# ---------------------------------------------------------------------------------------------- copyright
def test_copyright_notice_is_fixed_and_sealed(tmp_path, monkeypatch):
    from academy import legal

    assert legal.verify()
    assert legal.notice("es") == "© 2026 Alejandro Zavala. Todos los derechos reservados."
    assert legal.notice("en") == "© 2026 Alejandro Zavala. All rights reserved."
    at = _run(tmp_path, monkeypatch)
    assert not at.exception
    assert any("© 2026 Alejandro Zavala" in m.value for m in at.markdown)  # page footer
    assert any("© 2026 Alejandro Zavala" in c.value for c in at.sidebar.caption)
    monkeypatch.setattr(legal, "OWNER", "Otra Persona")  # an edited notice: the app refuses to open
    assert not legal.verify()
    bad = _run(tmp_path, monkeypatch)
    assert any("derechos de autor" in e.value or "copyright notice" in e.value for e in bad.error)
    assert not any("Otra Persona" in m.value for m in bad.markdown)
