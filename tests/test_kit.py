"""Academy Kit: pack rules, scoring, team view, content workbook, edit mode, reports and the Streamlit page end to end."""

import json
import random
import re
from pathlib import Path

import pytest

from academy import quiz
from academy import catalog as catmod
from academy.catalog import (catalog_from_tables, load_catalog, parse_grid, parse_text, read_xlsx, save_catalog, sheet_names,
                             validate_catalog)
from academy.pack import available_packs, load_pack, validate
from academy.progress import Tracker, connect, team  # noqa: F401
from academy.videos import embed_src, playlist_id, youtube_id

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _family_files(tmp_path, monkeypatch):
    """The family CSV files of every test go to its own folder, never to content/families."""
    monkeypatch.setenv("ACADEMY_FAMILIES", str(tmp_path / "families"))
    monkeypatch.setenv("ACADEMY_FAMILIES_STATE", str(tmp_path / "families_state.json"))
    from academy import english

    monkeypatch.setattr(english, "practice_titles", lambda root=None: False)  # never rename the real course files in a test


@pytest.fixture
def pack():
    return load_pack("cloud-security")


@pytest.fixture
def conn(tmp_path):
    return connect(tmp_path / "t.db")


def test_every_shipped_pack_is_valid():
    assert "cloud-security" in available_packs() and "_template" not in available_packs()
    for name in available_packs():
        assert validate(load_pack(name)) == [], name


def test_template_has_the_same_shape():
    tpl = load_pack(ROOT / "packs" / "_template")
    assert tpl.lessons and len(tpl.lessons[0].quiz) == 3 and tpl.language == "en"


def test_validator_catches_broken_content(pack, tmp_path):
    data = json.loads((ROOT / "packs" / "cloud-security" / "pack.json").read_text(encoding="utf-8"))
    data["lessons"][0]["quiz"] = data["lessons"][0]["quiz"][:2]
    data["lessons"][1]["resources"] = data["lessons"][1]["resources"][:1]
    data["resources"]["x"] = {"title": "t", "url": "http://example.com", "channel": "c", "why": "w", "kind": "video", "topic": "nope"}
    (tmp_path / "pack.json").write_text(json.dumps(data), encoding="utf-8")
    errs = " | ".join(validate(load_pack(tmp_path)))
    for needle in ("exactly 3 questions", "at least 2 videos", "https", "embeddable", "topic 'nope'"):
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


def test_retired_value_deliverables_do_not_count(pack, conn):
    t = Tracker(conn, pack, "ana")
    t.record("vbd", pack.lessons[0].id, 25, True)  # a row written by an earlier version
    assert t.total_points() == 0 and all("VBD" not in how for _, how, _ in t.badges())
    assert not hasattr(pack.lessons[0], "vbd")


def test_ranks_and_team(pack, conn):
    t = Tracker(conn, pack, "ana")
    assert t.rank(0) == (0, 100) and t.rank(1000)[1] is None
    t.record("glossary", "MFA", 10, True)
    df = team(conn, pack)
    assert list(df["Person"]) == ["ana"] and df["Points"].iloc[0] == 10


def test_role_filter(pack):
    soc = pack.lessons_for_role("Security analyst (SOC)")
    assert {"r1", "r2", "r3"} <= soc and "d3" not in soc


def test_glossary_question_has_one_right_answer(pack):
    rng = random.Random(3)
    for _ in range(200):
        g = quiz.glossary_question(pack.glossary, rng)
        assert len(set(g["options"])) == 4 and 0 <= g["correct"] < 4


def test_shuffle_is_stable():
    opts, ci = quiz.shuffled("f1:0", ["a", "b", "c", "d"], 2)
    assert opts[ci] == "c" and quiz.shuffled("f1:0", ["a", "b", "c", "d"], 2) == (opts, ci)


def _run(tmp_path, monkeypatch, owners=("me",), **state):
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("ACADEMY_ACCESS", str(tmp_path / "access.json"))
    monkeypatch.setenv("ACADEMY_ASSISTANT", str(tmp_path / "assistant.json"))
    if owners is not None and not (tmp_path / "access.json").exists():
        (tmp_path / "access.json").write_text(json.dumps({"owners": list(owners)}), encoding="utf-8")

    monkeypatch.setenv("ACADEMY_DB", str(tmp_path / "app.db"))
    monkeypatch.setenv("ACADEMY_CONTENT", str(tmp_path / "content.xlsx"))  # never let a test read or rewrite the real content file
    monkeypatch.setenv("ACADEMY_DEMAND", str(tmp_path / "demand_roles.csv"))
    if not (tmp_path / "practice.json").exists():
        (tmp_path / "practice.json").write_text((ROOT / "catalog" / "practice.json").read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setenv("ACADEMY_CONTENT_STATE", str(tmp_path / "content_state.json"))
    monkeypatch.setenv("ACADEMY_NEWS_OFFLINE", "1")  # tests never go to the internet
    monkeypatch.setenv("ACADEMY_PEOPLE", str(tmp_path / "people.csv"))  # no directory unless a test writes one
    monkeypatch.setenv("ACADEMY_STUDY", str(tmp_path / "study_material.csv"))
    if not (tmp_path / "study_material.csv").exists():
        (tmp_path / "study_material.csv").write_bytes((ROOT / "catalog" / "study_material.csv").read_bytes())
    monkeypatch.setenv("ACADEMY_NEWS_CACHE", str(tmp_path / "news_cache.json"))
    monkeypatch.setenv("ACADEMY_NEWS", str(tmp_path / "news_sources.csv"))
    if not (tmp_path / "news_sources.csv").exists():
        (tmp_path / "news_sources.csv").write_bytes((ROOT / "catalog" / "news_sources.csv").read_bytes())
    monkeypatch.setenv("ACADEMY_CATALOG", str(tmp_path / "skills.json"))  # never let a test overwrite the real catalog
    if not (tmp_path / "skills.json").exists():
        (tmp_path / "skills.json").write_text(catmod.CATALOG_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    state.setdefault("ak_cert_view", "prep")  # the Certifications tab opens on «my certifications»; most tests look at the exam prep
    for k, v in state.items():
        if v is not None:  # None = leave the app's own default
            at.session_state[k] = v
    return at.run()


def test_app_renders_and_scores(tmp_path, monkeypatch):
    """The Course tab (lessons with quizzes) was retired: the dashboard and the Learning route follow the learning paths."""
    at = _run(tmp_path, monkeypatch)
    assert not at.exception
    assert not any(x.endswith("· Course") for x in _tab_labels(at)) and _tab_labels(at)[0].endswith("Learning route")
    assert not any("deliverable" in m.value.lower() for m in at.markdown)  # value deliverables were retired
    assert any("Your learning path" in m.value for m in at.markdown)


def test_app_other_tabs(tmp_path, monkeypatch):
    at = _run(tmp_path, monkeypatch, kx_part="📖 Glossary")  # glossary and video library live in Knowledge exchange
    at.radio(key=f"ak_gq_pick_{at.session_state['ak_gq_n']}").set_value(0).run()
    at.button(key="ak_gq_check").click().run()
    assert not at.exception
    at.session_state["kx_part"] = "🎬 Video library"
    at.run()
    for topic in ("fundamentals", "identity", "references"):
        at.selectbox(key="ak_lib_topic").set_value(topic).run()
        assert not at.exception
    assert not any(s.key == "ak_role" for s in at.selectbox)  # the course role comes from the roster, not from a choice
    assert not any(r.key == "ak_lang" for r in at.radio)  # no language switch: English only


def test_catalog_is_valid_and_lessons_point_to_it(pack):
    cat = load_catalog()
    assert validate_catalog(cat) == [] and len(cat.skills) == 34
    assert validate(pack, cat) == []
    assert cat.by_gap()[0].name == "Microsoft 365 Security" and cat.by_gap()[-1].gap_volume is None
    assert len(cat.families) == 9
    cov = cat.coverage([pack])
    assert any(t == 'Containers and Kubernetes' for _, t in cov["container-security"]) and cov["exchange-online"] == []


def test_validator_catches_unknown_catalog_skill(tmp_path):
    data = json.loads((ROOT / "packs" / "cloud-security" / "pack.json").read_text(encoding="utf-8"))
    data["lessons"][0]["catalog_skills"] = ["no-existe"]
    (tmp_path / "pack.json").write_text(json.dumps(data), encoding="utf-8")
    assert any("no-existe" in e for e in validate(load_pack(tmp_path), load_catalog()))


def test_skills_tab_renders(tmp_path, monkeypatch):
    at = _run(tmp_path, monkeypatch, ak_view="demand")  # the skills map lives in the 🔍 Demand view
    assert not at.exception
    assert any("Microsoft 365 Security" in m.value for m in at.markdown)
    assert any("to be assigned" in m.value for m in at.markdown)


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
    assert next(s for s in kept.skills if s.id == "microsoft-365-security").roles == ["Sample role 1", "Sample role 2"]


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
    at = _run(tmp_path, monkeypatch, ak_sk_mode="paste", ak_view="demand")
    at.text_area(key="ak_sk_text").set_value("Skill Family\tMissing Skill\nRedes\tAzure Firewall").run()
    assert not at.exception and any("1 families" in s.value for s in at.success)
    at.button(key="ak_sk_save_paste").click().run()
    assert not at.exception and [s.name for s in load_catalog(tmp_path / "skills.json").skills] == ["Azure Firewall"]
    assert not _run(tmp_path, monkeypatch, ak_sk_mode="import", ak_view="demand").exception


def test_sharepoint_export(tmp_path, pack):
    import csv
    import importlib.util

    spec = importlib.util.spec_from_file_location("export_sharepoint", ROOT / "tools" / "export_sharepoint.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    files = {p.stem: p for p in mod.export("cloud-security", tmp_path)}
    assert set(files) == {"Families", "Skills", "Lessons", "Questions", "Resources", "LessonResources", "Glossary", "Ranks"}
    rows = {k: list(csv.DictReader(p.open(encoding="utf-8-sig"))) for k, p in files.items()}
    assert len(rows["Lessons"]) == 12 and len(rows["Questions"]) == 36 and len(rows["Skills"]) == 34 and len(rows["Families"]) == 9
    q = rows["Questions"][0]
    assert q[f"Option{q['AnswerLetter']}"] == pack.lessons[0].quiz[0].options[pack.lessons[0].quiz[0].answer]
    assert {r["LessonId"] for r in rows["LessonResources"]} == {les.id for les in pack.lessons}


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
    assert n.kind == "inactive" and "6 days" in n.subject and n.to == "ana@x.com" and n.cc and n.champions
    assert 'The shared responsibility model' in n.body and n.champions[0] in n.body
    assert notify.mailto(n).startswith("mailto:ana%40x.com?cc=") and "subject=You%20have%20not%20taken" in notify.mailto(n)
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
    assert "AI-901" in mine["exam_passed"].subject and "1000 out of 1000" in mine["exam_passed"].body
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
    """The page's own tabs ("1 · …"), not the tabs inside a section."""
    return [t.label for t in at.tabs if re.match(r"^\d+ · ", t.label)]


LEARNING_TABS = ["1 · Learning route", "2 · Progress", "3 · Forum", "4 · Study groups", "5 · Knowledge exchange"]
MANAGE_TABS = ["1 · Learning paths", "2 · Team", "3 · Reports", "4 · Certifications", "5 · Rhythm", "6 · Knowledge exchange",
               "7 · Administration"]
DEMAND_TABS = ["1 · Demand analysis", "2 · Demand results", "3 · Skills map"]


def test_end_user_does_not_see_team_measurements(tmp_path, monkeypatch):
    at = _run(tmp_path, monkeypatch, owners=("jefa",), ak_view="manage")  # "me" is not an owner: asking for Management changes nothing
    assert not at.exception
    assert _tab_labels(at) == LEARNING_TABS
    assert not any("Notices to send" in m.value for m in at.markdown)
    assert not any(m.label in ("Gap", "Roles affected") for m in at.metric)
    assert not any(str(b.key).startswith("ak_sk_save") for b in at.button) and "ak_view" not in [x.key for x in at.segmented_control]
    assert not any(str(t.key).startswith("ed_on_") for t in at.toggle)  # no edit mode in the learning view


def test_learning_and_management_views_are_separate(tmp_path, monkeypatch):
    at = _run(tmp_path, monkeypatch)  # "me" is an owner: the Learning view first, the same as every learner
    assert not at.exception and _tab_labels(at) == LEARNING_TABS and "ak_view" in [x.key for x in at.segmented_control]
    assert not any(m.label == "Gap" for m in at.metric) and not any("Notices to send" in m.value for m in at.markdown)
    assert not any("Manage the learning paths" in e.label for e in at.expander)  # the learner's route has no management panel
    at = _run(tmp_path, monkeypatch, ak_view="manage")  # owner without anyone holding Demand / Learning: every tool
    assert not at.exception and _tab_labels(at) == MANAGE_TABS
    assert not any(m.label == "Gap" for m in at.metric) and any("Notices to send" in m.value for m in at.markdown)
    assert any("Manage the learning paths" in e.label for e in at.expander) and not any("Your learning path" in m.value for m in at.markdown)
    at = _run(tmp_path, monkeypatch, ak_view="demand")  # 🔍 Demand: the analysis, each family's results and the skills map
    assert not at.exception and _tab_labels(at) == DEMAND_TABS and any(m.label == "Gap" for m in at.metric)


def test_responsibilities_decide_who_sees_demand_and_learning(tmp_path, monkeypatch):
    from academy import people

    d = [people.Person("Ana", "ana@x.com", "owner"), people.Person("Perla", "perla@x.com", "learner", duties=("learning",)),
         people.Person("Sergio", "sergio@x.com", "learner", duties=("demand",)),
         people.Person("Cam", "cam@x.com", "champion", ("identity-access-management",)), people.Person("Lu", "lu@x.com", "learner")]
    raw = people.to_csv(d)
    assert people.parse(raw) == (d, []) and b"Responsibilities" in raw.splitlines()[0]
    assert people.parse(b"Person,Responsibilities\nX,Upskilling & learning; Demand\n")[0][0].duties == ("learning", "demand")
    assert people.parse(b"Person,Responsibilities\nX,payroll\n")[1]
    assert people.duties_of(d, "Perla", "", "main", "main", False) == {"learning"}
    assert people.duties_of(d, "Ana", "", "main", "main", True) == set()  # both are held: the owner keeps Administration only
    assert people.duties_of(d, "Ana", "", "ppm", "main", True) == {"demand", "learning"}  # nobody holds them in PPM: the owner does
    moved = people.set_responsible(d, "demand", ["Sergio", "Lu"], "main", "main")
    assert [p.name for p in people.responsible(moved, "demand", "main", "main")] == ["Sergio", "Lu"]
    people.save(d, tmp_path / "people.csv")
    tabs = {}
    for who in ("Ana", "Perla", "Sergio", "Cam", "Lu"):
        at = _run(tmp_path, monkeypatch, owners=None, ak_person=who, ak_view="manage")
        assert not at.exception, who
        tabs[who] = [x.split(" · ", 1)[1] for x in _tab_labels(at)]
    assert tabs["Ana"] == ["Learning paths", "Certifications", "Rhythm", "Administration"]
    assert tabs["Perla"] == ["Team", "Reports", "Certifications", "Rhythm", "Knowledge exchange"]
    assert tabs["Sergio"] == [x.split(" · ", 1)[1] for x in LEARNING_TABS]  # Demand only: no Management view…
    assert tabs["Cam"] == ["Learning paths", "Team", "Rhythm"]
    views, dtabs = {}, {}
    for who in ("Ana", "Perla", "Sergio", "Cam", "Lu"):
        at = _run(tmp_path, monkeypatch, owners=None, ak_person=who, ak_view="demand")
        assert not at.exception, who
        views[who] = next((list(x.options) for x in at.segmented_control if x.key == "ak_view"), [])
        dtabs[who] = [x.split(" · ", 1)[1] for x in _tab_labels(at)]
    assert views == {"Ana": ["Learning", "Management", "Demand"], "Perla": ["Learning", "Management"], "Sergio": ["Learning", "Demand"],
                     "Cam": ["Learning", "Management", "Demand"], "Lu": []}  # (the leading emoji is drawn as the option's icon)
    assert dtabs["Sergio"] == ["Demand analysis", "Demand results", "Skills map"]  # …its own 🔍 Demand view
    assert dtabs["Ana"] == ["Demand results", "Skills map"] and dtabs["Cam"] == ["Demand results"]  # owner; career path lead
    assert dtabs["Perla"] == [x.split(" · ", 1)[1] for x in LEARNING_TABS]  # not in the Demand team: back to Learning
    assert tabs["Lu"] == [x.split(" · ", 1)[1] for x in LEARNING_TABS]  # a learner: the Learning view only


def test_first_owner_claim_and_pin(tmp_path, monkeypatch):
    from academy.access import load_access, save_access

    at = _run(tmp_path, monkeypatch, owners=None, ak_view="manage")  # nothing configured yet
    assert _tab_labels(at) == LEARNING_TABS
    at.button(key="ak_claim").click().run()
    assert not at.exception and load_access(tmp_path / "access.json").owners == ["me"] and _tab_labels(at) == MANAGE_TABS
    acc = load_access(tmp_path / "access.json")
    acc.set_pin("2468")
    save_access(acc, tmp_path / "access.json")
    at = _run(tmp_path, monkeypatch, owners=None, ak_view="manage")
    assert _tab_labels(at) == LEARNING_TABS  # owner, but the PIN has not been typed
    at.text_input(key="ak_owner_pin").set_value("1111").run()
    assert _tab_labels(at) == LEARNING_TABS
    at.text_input(key="ak_owner_pin").set_value("2468").run()
    assert not at.exception and _tab_labels(at) == MANAGE_TABS


def test_champion_sees_only_their_family(tmp_path, monkeypatch, pack, exam, conn):
    from academy import notify

    cat = load_catalog()
    net = "cloud-network-security"
    Tracker(conn, pack, "ana").answer_quiz("d2:0", True)   # d2 = Zero Trust / red -> Cloud & Network Security
    Tracker(conn, pack, "luis").answer_quiz("d3:0", True)  # d3 = contenedores -> Application Security & DevSecOps
    rows = notify.family_team(conn, [pack], [exam], cat, {net})
    assert [r["Person"] for r in rows] == ["ana"] and rows[0]["Family lessons"].startswith("0/")
    assert notify.family_team(conn, [pack], [exam], cat, {"microsoft-365-security"}) == []
    from academy.exam import ExamTracker

    ExamTracker(conn, exam, "sol").answer_practice(exam.questions[0].id, True)
    assert [r["Person"] for r in notify.family_team(conn, [pack], [exam], cat, {exam.family})] == ["sol"]

    # in the app: a champion (not an owner) gets the team tab scoped to the family and gap numbers only for it
    data = json.loads(catmod.CATALOG_PATH.read_text(encoding="utf-8"))
    for f in data["families"]:
        if f["id"] == net:
            f["champion"] = "me"
    (tmp_path / "skills.json").write_text(json.dumps(data), encoding="utf-8")
    at = _run(tmp_path, monkeypatch, owners=("jefa",), ak_view="manage")
    assert not at.exception and [x.split(" · ", 1)[1] for x in _tab_labels(at)] == ["Learning paths", "Team", "Rhythm"]
    assert any("My family" in m.value and "Cloud & Network Security" in m.value for m in at.markdown)
    assert not any("Access" in e.label for e in at.expander) and not any(str(b.key).startswith("ak_sk_save") for b in at.button)
    assert any("Manage the learning paths of Cloud & Network Security" in e.label for e in at.expander)
    assert not any(m.label == "Gap" for m in at.metric)  # the skills map is the owners'; reports, the Upskilling & learning team's


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
    from academy.route import RouteTracker

    (tmp_path / "materials.json").write_text((catmod.CATALOG_PATH.parent / "materials.json").read_text(encoding="utf-8"), encoding="utf-8")
    at = _run(tmp_path, monkeypatch, owners=("jefa",))
    assert not at.exception and _tab_labels(at)[0].endswith("Learning route")
    done = [b for b in at.button if str(b.key).startswith("rt_done_")]
    assert done
    done[0].click().run()
    assert not at.exception
    assert len(RouteTracker(connect(tmp_path / "app.db"), "me").done()) == 1


def test_family_lead_adds_a_workday_course(tmp_path, monkeypatch):
    """A champion runs their family's path: a Workday course becomes a class, another one is switched off, their own deck is
    uploaded; learners see only the required classes and download the deck."""
    from academy import family_path as fp
    from academy.catalog import load_materials
    from academy.route import build_routes

    data = json.loads(catmod.CATALOG_PATH.read_text(encoding="utf-8"))
    for f in data["families"]:
        if f["id"] == "technical-delivery-leadership":
            f["champion"] = "me"
    (tmp_path / "skills.json").write_text(json.dumps(data), encoding="utf-8")
    base = json.loads((catmod.CATALOG_PATH.parent / "materials.json").read_text(encoding="utf-8"))
    (tmp_path / "materials.json").write_text(json.dumps(base), encoding="utf-8")
    at = _run(tmp_path, monkeypatch, owners=("jefa",))
    assert not at.exception and not any("Manage the learning paths" in e.label for e in at.expander)  # the Learning view
    at = _run(tmp_path, monkeypatch, owners=("jefa",), ak_view="manage")
    assert not at.exception and any("Manage the learning paths of Technical Delivery Leadership" in e.label for e in at.expander)
    assert [o for o in at.selectbox(key="mg_family").options] == ["Technical Delivery Leadership"]  # only their family
    cat = load_catalog(tmp_path / "skills.json")
    fid = "technical-delivery-leadership"
    rows = fp.rows(fid, cat, load_materials(tmp_path / "materials.json"))
    first = next(r for r in rows if r["Status"] == fp.REQUIRED)
    rows = [dict(r, Status=fp.OFF) if r is first else r for r in rows]
    rows.append({"SkillId": "stakeholder-governance", "Class": 1, "Title": "Stakeholder Management Essentials",
                 "Url": "https://wd5.myworkday.com/empresa/learning/course/123", "Kind": "course", "Provider": "Workday Learning", "Status": "required"})
    deck = fp.save_file(fid, "Kickoff deck.pptx", b"PK fake pptx")
    assert deck == f"file:{fid}/Kickoff deck.pptx" and fp.file_path(deck).read_bytes() == b"PK fake pptx"
    rows.append({"Skill": "Stakeholder Governance", "Class": 2, "Title": "Our kickoff deck", "Url": deck, "Kind": "deck", "Status": "required"})
    new, problems = fp.parse(fp.to_csv(rows), fid, cat)
    assert problems == []
    mats = fp.replace(fid, new, cat, load_materials(tmp_path / "materials.json"))
    assert "microsoft-sentinel" in mats  # other families untouched
    route = next(r for r in build_routes(cat, mats) if r.family_id == fid)
    assert first["Title"] not in [s.title for s in route.steps]  # switched off: hidden from learners
    sg = [s.title for s in route.steps if s.skill_id == "stakeholder-governance"]
    assert sg == ["Stakeholder Management Essentials", "Our kickoff deck"] and "Stakeholder Governance" not in route.uncovered
    bad = fp.parse(b"SkillId,Title,Url,Status\nmicrosoft-sentinel,X,https://x,required\nstakeholder-governance,Y,ftp://y,maybe\n", fid, cat)[1]
    assert len(bad) == 2  # another family's skill; a bad link / status
    with pytest.raises(ValueError):
        fp.save_file(fid, "script.exe", b"x")
    assert fp.file_path("file:../../etc/passwd") is None


def test_family_csv_files_sync_both_ways(tmp_path, monkeypatch):
    from academy import family_path as fp
    from academy.catalog import load_materials

    import shutil

    for name in ("materials.json", "skills.json"):
        shutil.copy(catmod.CATALOG_PATH.parent / name, tmp_path / name)
    monkeypatch.setenv("ACADEMY_CATALOG", str(tmp_path / "skills.json"))  # materials.json is read next to it
    cat = load_catalog()
    assert fp.sync(cat) == {"applied": [], "problems": {}}  # first run writes one file per family
    files = sorted(p.stem for p in (tmp_path / "families").glob("*.csv"))
    assert files == sorted(f.id for f in cat.families)
    path = tmp_path / "families" / "identity-access-management.csv"
    text = path.read_text(encoding="utf-8-sig").replace(",required,", ",off,", 1)
    path.write_text(text, encoding="utf-8-sig")
    out = fp.sync(cat)
    assert out["applied"] == ["identity-access-management"]
    assert any(m.get("status") == "off" for s in cat.in_family("identity-access-management") for m in load_materials().get(s.id, []))
    path.write_text(text.replace("https://", "ftp://", 1), encoding="utf-8-sig")
    out = fp.sync(cat)
    assert out["problems"] and path.read_text(encoding="utf-8-sig").count("ftp://") == 1  # a broken edit is reported and left for the champion


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
    plan = ai.prompt_study_plan(exam.name, 560, 700, [("Concepts", 6, 11)], ["Module X"], [("Course", "https://learn.microsoft.com/x")])
    assert "560 out of 1000" in plan and "6 of 11" in plan and "https://learn.microsoft.com/x" in plan and "7-day" in plan
    assert "Workday" not in plan and "gap" not in plan.lower()  # only the learner's own result and study content
    assert "ORIGINAL" in ai.prompt_draft_questions(exam.name, "m", ["a", "b", "c"]) and "P3" in ai.prompt_step_coach("F", "S", "T", "Microsoft Learn", "P3 - Advanced")


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
    assert ai.ask(ai.AssistantConfig(api_url="http://inseguro"), "x") == (False, "The assistant URL must be https.")


def test_assistant_shows_in_the_app(tmp_path, monkeypatch):
    (tmp_path / "materials.json").write_text((catmod.CATALOG_PATH.parent / "materials.json").read_text(encoding="utf-8"), encoding="utf-8")
    at = _run(tmp_path, monkeypatch)
    assert not at.exception and any("next step with the AI tutor" in e.label for e in at.expander)
    at = _run(tmp_path, monkeypatch, ak_view="manage", mg_admin_part="👑 People and access", mg_cert_part="📝 Exam preparation (AI drafts)")
    labels = [e.label for e in at.expander]
    assert any("AI assistant (Amethyst)" in x for x in labels) and any("draft new questions" in x for x in labels)  # leaders only
    (tmp_path / "u").mkdir()  # a second, separate installation where "me" is an end user
    (tmp_path / "u" / "materials.json").write_text((tmp_path / "materials.json").read_text(encoding="utf-8"), encoding="utf-8")
    at2 = _run(tmp_path / "u", monkeypatch, owners=("jefa",))
    labels2 = [e.label for e in at2.expander]
    assert any("AI tutor" in x for x in labels2) and not any("draft new questions" in x or "AI assistant" in x for x in labels2)


# ---------------------------------------------------------------------------------------------- English only
def test_everything_is_english_only():
    """One file per course and exam, in English, with English videos only."""
    from academy.exam import load_exam

    pack = load_pack("cloud-security")
    assert pack.language == "en" and all(r.lang == "en" for r in pack.resources.values())
    assert not list((ROOT / "packs" / "cloud-security").glob("pack.*.json")) and not list((ROOT / "exams" / "ai-901").glob("exam.*.json"))
    assert load_exam("ai-901").questions and validate(pack, load_catalog()) == []
    assert all(r.level in ("basic", "intermediate", "advanced") for r in pack.resources.values())


def test_english_migration_keeps_progress_and_backs_up(tmp_path):
    from academy import english

    folder = tmp_path / "packs" / "demo"
    folder.mkdir(parents=True)
    en = json.loads((ROOT / "packs" / "cloud-security" / "pack.json").read_text(encoding="utf-8"))
    es = json.loads(json.dumps(en))
    es["meta"]["language"] = "es"
    en["resources"]["spanish"] = dict(next(iter(en["resources"].values())), lang="es", url="https://www.youtube.com/watch?v=es1", level="básico")
    en["lessons"][0]["resources"].append("spanish")
    (folder / "pack.json").write_text(json.dumps(es), encoding="utf-8")
    (folder / "pack.en.json").write_text(json.dumps(en), encoding="utf-8")
    (tmp_path / "content").mkdir()
    (tmp_path / "content" / "demanda_roles.csv").write_text("x", encoding="utf-8")
    assert english.migrate(tmp_path) is True
    out = json.loads((folder / "pack.json").read_text(encoding="utf-8"))
    assert out["meta"]["language"] == "en" and "spanish" not in out["resources"] and "spanish" not in out["lessons"][0]["resources"]
    assert [x["id"] for x in out["lessons"]] == [x["id"] for x in es["lessons"]]  # same lesson ids: progress is kept
    assert not (folder / "pack.en.json").exists() and (tmp_path / "content" / "demand_roles.csv").exists()
    assert list((tmp_path / "data" / "content_backups").glob("*-english/packs/demo/pack.json"))
    assert english.migrate(tmp_path) is False  # nothing left to convert
    (folder / "pack.en.json").write_text(json.dumps(dict(out, meta=dict(out["meta"], title="older"))), encoding="utf-8")
    assert english.migrate(tmp_path) and json.loads((folder / "pack.json").read_text(encoding="utf-8"))["meta"]["title"] != "older"  # English main file wins


def test_app_is_english_without_a_language_switch(tmp_path, monkeypatch):
    at = _run(tmp_path, monkeypatch)
    assert not at.exception and "ak_lang" not in at.session_state
    text = " ".join(m.value for m in at.markdown)
    assert "Your learning path" in text and "Tu siguiente paso" not in text


# ---------------------------------------------------------------------------------------------- reports, sound, motion
def _seed_family_activity(tmp_path):
    from datetime import datetime, timedelta, timezone

    pack, cat = load_pack("cloud-security"), load_catalog()
    conn = connect(tmp_path / "rep.db")
    now = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)
    fam_of = {s.id: s.family for s in cat.skills}
    les = next(x for x in pack.lessons if x.catalog_skills)
    fam = fam_of[les.catalog_skills[0]]
    for who, days, n in (("ana", 1, 3), ("carla", 12, 1)):
        for k in range(n):
            conn.execute("INSERT INTO events(time, pack, learner, kind, item, points, correct, detail) VALUES (?,?,?,?,?,?,?,?)",
                         ((now - timedelta(days=days)).isoformat(timespec="seconds"), pack.id, who, "quiz", f"{les.id}:{k}", 10, 1, ""))
    conn.commit()
    return conn, pack, cat, now, fam


def test_family_report_status_and_followup(tmp_path):
    from academy import report

    conn, pack, cat, now, fam = _seed_family_activity(tmp_path)
    rep = report.build(conn, [pack], [], cat, "en", now=now)
    assert len(rep["status"]) == len(cat.families) and rep["summary"]["people"] == 2
    people = {r["Person"]: r for r in rep["followup"] if r["Role family"] == next(f.name for f in cat.families if f.id == fam)}
    assert people["carla"]["_late"] and people["carla"]["Days idle"] == 12 and not people["ana"]["_late"]
    assert rep["followup"][0]["Person"] == "carla"  # whoever needs follow-up comes first
    assert all(not k.startswith("_") for r in report.visible(rep["status"]) for k in r)
    only = report.build(conn, [pack], [], cat, "en", only={fam}, now=now)  # what a champion gets: their family only
    assert len(only["status"]) == 1 and {r["Role family"] for r in only["followup"]} == {only["status"][0]["Role family"]}


def test_family_report_exports(tmp_path):
    import io

    from openpyxl import load_workbook

    from academy import report

    conn, pack, cat, now, _ = _seed_family_activity(tmp_path)
    rep = report.build(conn, [pack], [], cat, "en", now=now)
    wb = load_workbook(io.BytesIO(report.to_xlsx(rep)))
    assert wb.sheetnames[0] == "Status by family" and len(wb.sheetnames) == 4 and wb.worksheets[0].max_row == 4 + len(cat.families)
    assert [c.value for c in wb["Follow-up by person"][4]][:3] == ["Role family", "Champion", "Person"]
    assert [c.value for c in wb["Progress by person"][4]][0] == "Person"
    from academy import report_pdf

    pdf = report_pdf.to_pdf(rep)
    assert pdf.startswith(b"%PDF") and len(pdf) > 3000
    assert not hasattr(report, "to_html")  # the HTML report was retired: PDF only


def test_owner_sees_the_report_and_sounds_can_be_turned_off(tmp_path, monkeypatch):
    at = _run(tmp_path, monkeypatch, ak_view="manage")
    assert not at.exception
    assert any("Status and follow-up report" in m.value for m in at.markdown)
    assert at.session_state["ak_sound"] is True
    from academy import ui

    assert set(ui.SOUNDS) == {"ok", "bad", "step", "go", "win"} and "ak-points" in ui.points_html(["a <b>"]) and "<b>" not in ui.points_html(["a <b>"])


# ---------------------------------------------------------------------------------------------- content file (CSV / Excel)
def _content_sandbox(tmp_path, monkeypatch):
    """A copy of packs/ and catalog/ so the tests can import content without touching the real files."""
    import shutil

    from academy import content_xlsx as content

    packs = tmp_path / "packs"
    shutil.copytree(ROOT / "packs", packs)
    for name in ("skills.json", "materials.json", "practice.json"):
        shutil.copy(ROOT / "catalog" / name, tmp_path / name)
    monkeypatch.setenv("ACADEMY_CATALOG", str(tmp_path / "skills.json"))
    monkeypatch.setenv("ACADEMY_CONTENT", str(tmp_path / "content" / "academy_content.xlsx"))
    monkeypatch.setenv("ACADEMY_CONTENT_STATE", str(tmp_path / "content_state.json"))
    shutil.copy(ROOT / "catalog" / "news_sources.csv", tmp_path / "news_sources.csv")
    for name, env in (("people.csv", "ACADEMY_PEOPLE"), ("study_material.csv", "ACADEMY_STUDY")):
        shutil.copy(ROOT / "catalog" / name, tmp_path / name)
        monkeypatch.setenv(env, str(tmp_path / name))
    monkeypatch.setenv("ACADEMY_NEWS", str(tmp_path / "news_sources.csv"))
    monkeypatch.setenv("ACADEMY_PACKS", str(packs))
    return content, packs


def test_content_round_trips_as_excel_and_as_one_csv(tmp_path, monkeypatch):
    content, _ = _content_sandbox(tmp_path, monkeypatch)
    from academy.catalog import load_materials

    as_xlsx, as_csv = content.read(content.export_bytes()), content.read(content.csv_bytes(content.export_csv()))
    assert as_xlsx["problems"] == [] and as_csv["problems"] == []
    assert as_xlsx["packs"] == as_csv["packs"] and set(as_csv["packs"]) == {"cloud-security"}
    from academy.catalog import vendor_of
    from academy.route import build_routes

    cat, mats = load_catalog(), load_materials()  # the skills list and the learning paths travel too
    assert [(f.id, f.name, f.champion) for f in as_csv["catalog"].families] == [(f.id, f.name, f.champion) for f in cat.families]
    assert [(x.id, x.name, x.family, x.vendor) for x in as_csv["catalog"].skills] == [(x.id, x.name, x.family, vendor_of(x, mats)) for x in cat.skills]
    assert {k: sorted(i["url"] for i in v) for k, v in as_csv["materials"].items()} == {k: sorted(i["url"] for i in v) for k, v in mats.items()}
    steps = lambda c, m: [[(st.vendor, st.skill_id, st.number, st.url) for st in r.steps] for r in build_routes(c, m)]  # noqa: E731
    assert steps(as_csv["catalog"], as_csv["materials"]) == steps(cat, mats)  # same classes, in the same order
    for pid, d in as_csv["packs"].items():
        assert validate(load_pack(pid), load_catalog()) == []
        disk = json.loads(content.target_file(pid).read_text(encoding="utf-8"))
        assert [(x["id"], x["title"], x["resources"], [q["answer"] for q in x["quiz"]]) for x in d["lessons"]] == \
               [(x["id"], x["title"], x["resources"], [q["answer"] for q in x["quiz"]]) for x in disk["lessons"]]
        assert {k: v["url"] for k, v in d["resources"].items()} == {k: v["url"] for k, v in disk["resources"].items()}
    semicolons = "\r\n".join(";".join(f'"{c}"' for c in row) for row in __import__("csv").reader(content.export_csv().splitlines()))
    assert content.read(semicolons.encode("utf-8"))["packs"].keys() == as_csv["packs"].keys()  # what Excel saves in some regions


def test_content_file_edit_is_applied_and_a_broken_one_is_not(tmp_path, monkeypatch):
    from openpyxl import load_workbook

    content, packs = _content_sandbox(tmp_path, monkeypatch)
    from academy import content_sync

    assert content_sync.sync()["status"] == "none"
    assert content_sync.refresh()["status"] == "written" and content_sync.sync()["status"] == "same"
    path = content_sync.content_path()
    wb = load_workbook(path)
    assert wb.sheetnames[0] == "README" and wb.sheetnames[1:] == list(content.SHEETS)  # one tab per table, grouped by section
    assert wb["Families"].sheet_properties.tabColor.rgb.endswith("FF5800")

    def col(ws, name):
        return [c.value for c in ws[1]].index(name) + 1

    rec = wb["Resources"]
    video_row = next(r for r in range(2, rec.max_row + 1) if rec.cell(r, col(rec, "Kind")).value == "video")
    key = rec.cell(video_row, col(rec, "ResourceKey")).value
    for r in range(2, rec.max_row + 1):
        if rec.cell(r, col(rec, "ResourceKey")).value == key:
            rec.cell(r, col(rec, "Url")).value = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    les = wb["Lessons"]
    for r in range(2, les.max_row + 1):
        if les.cell(r, col(les, "LessonId")).value == "f1":
            les.cell(r, col(les, "Title")).value = "Shared responsibility, edited in Excel"
    wb.save(path)
    assert content_sync.sync()["status"] == "applied"
    en = load_pack(packs / "cloud-security")
    assert en.lessons[0].title == "Shared responsibility, edited in Excel" and en.resources[key].url.endswith("dQw4w9WgXcQ")
    assert any((tmp_path / "data" / "content_backups").rglob("pack.json"))  # the previous version is kept
    wb["Questions"].cell(2, col(wb["Questions"], "AnswerLetter")).value = "Z"
    wb.save(path)
    out = content_sync.sync()
    assert out["status"] == "problems" and any("AnswerLetter" in e for e in out["problems"])
    assert load_pack(packs / "cloud-security").lessons[0].title == "Shared responsibility, edited in Excel"  # nothing changed
    assert content_sync.sync()["status"] == "problems"  # still reported until the file is fixed


def test_former_single_csv_becomes_the_workbook(tmp_path, monkeypatch):
    content, packs = _content_sandbox(tmp_path, monkeypatch)
    from academy import content_sync

    old = content_sync.content_path().with_suffix(".csv")
    old.parent.mkdir(parents=True, exist_ok=True)
    old.write_bytes(content.csv_bytes(content.export_csv().replace("The shared responsibility model", "Edited in the old CSV", 1)))
    assert content_sync.sync()["status"] == "same"
    assert content_sync.content_path().exists() and not old.exists() and old.with_name(old.stem + " (old).csv").exists()
    assert load_pack(packs / "cloud-security").lessons[0].title == "Edited in the old CSV"  # the last edits of the CSV were kept


def test_content_file_carries_the_skills_catalog(tmp_path, monkeypatch):
    import csv
    import io

    content, _ = _content_sandbox(tmp_path, monkeypatch)
    rows = list(csv.reader(io.StringIO(content.export_csv(), newline="")))
    head = rows[0]
    t = head.index("Table")
    fam = next(r for r in rows if r[t] == "Families")
    fam[head.index("Champion")] = "Ana Champion"
    rows.append(["Skills"] + [{"SkillId": "defender-for-apis", "Name": "Defender for APIs", "FamilyId": fam[head.index("FamilyId")],
                              "Confirmed": "yes", "Severity": "High"}.get(c, "") for c in head[1:]])
    buf = io.StringIO(newline="")
    csv.writer(buf).writerows(rows)
    result = content.read(buf.getvalue().encode("utf-8"))
    assert result["problems"] == [] and result["new_catalog"]
    content.apply(result, backup_dir=tmp_path / "bk")
    cat = load_catalog()
    assert cat.families[0].champion == "Ana Champion" and "defender-for-apis" in cat.skill_ids()


def test_route_is_family_vendor_skill_classes():
    """Structure: role family -> technology / vendor -> skill -> class 1, class 2… from any source."""
    from academy.catalog import Catalog, Family, Skill, vendor_of
    from academy.route import build_routes

    cat = Catalog([Family("net", "Cloud & Network Security")],
                  [Skill("fw", "Firewalls", "net", vendor="Cisco"), Skill("azure-network-controls", "Azure Network Controls", "net"),
                   Skill("zero-trust", "Zero Trust", "net")])
    mats = {"fw": [{"title": "CCNA security", "url": "https://x.example/b", "kind": "course", "provider": "Workday Learning", "order": 2},
                   {"title": "Intro", "url": "https://x.example/a", "kind": "course", "provider": "Cisco Networking Academy", "order": 1},
                   {"title": "Data sheet", "url": "https://x.example/doc", "kind": "doc", "provider": "Cisco"}],
            "azure-network-controls": [{"title": "Path", "url": "https://learn.microsoft.com/p", "kind": "path", "provider": "Microsoft Learn"},
                                       {"title": "Module", "url": "https://learn.microsoft.com/m", "kind": "module", "provider": "Microsoft Learn"}]}
    assert [vendor_of(s, mats) for s in cat.skills] == ["Cisco", "Microsoft", "Vendor-neutral"]
    route = build_routes(cat, mats)[0]
    assert route.vendors() == ["Microsoft", "Cisco"]  # Microsoft first
    assert [(s.vendor, s.skill_id, s.number, s.title) for s in route.steps] == [
        ("Microsoft", "azure-network-controls", 1, "Module"), ("Microsoft", "azure-network-controls", 2, "Path"),
        ("Cisco", "fw", 1, "Intro"), ("Cisco", "fw", 2, "CCNA security")]  # written class order wins; any mix of sources
    assert route.uncovered == ["Zero Trust"] and list(route.extras) == ["Firewalls"]


# ---------------------------------------------------------------------------------------------- forum
def test_forum_questions_answers_and_moderation(tmp_path):
    from academy.forum import CHAMPION, SME, Forum

    f = Forum(connect(tmp_path / "forum.db"))
    f.set_smes("cloud-network-security", ["Marta@Empresa.com", " luis ", "luis"])
    assert f.smes()["cloud-network-security"] == ["Marta@Empresa.com", "luis"]
    assert f.sme_families("x", "marta@empresa.com") == {"cloud-network-security"} and f.sme_families("ana") == set()
    q1 = f.ask("ana", "cloud-network-security", "  ¿NSG o   Azure Firewall? ", "Tengo una VNet con 3 subredes.", "azure-network-controls")
    q2 = f.ask("ana", "identity-access-management", "¿PIM para grupos?")
    assert f.get(q1).title == "¿NSG o Azure Firewall?" and len(f.waiting()) == 2
    f.answer(q1, "carla", "Yo usé NSG.")  # a fellow learner: helpful, but the question still waits for an expert
    assert not f.get(q1).answered
    role = f.role_in("cloud-network-security", "luis")
    assert role == SME and f.role_in("identity-access-management", "luis") == "" and f.role_in("x", "pepe", champion_of={"x"}) == CHAMPION
    a = f.answer(q1, "luis", "NSG filtra por subred o NIC; Azure Firewall inspecciona y centraliza.", role)
    assert f.get(q1).answered and [q.id for q in f.waiting()] == [q2] and f.counts()["identity-access-management"]["waiting"] == 1
    f.accept(a)
    assert f.get(q1).answers[0].id == a and f.get(q1).answers[0].accepted  # the accepted answer goes first
    f.hide_answer(a)
    assert not f.get(q1).answered  # hidden posts do not count, but they are kept
    f.hide_answer(a, False)
    f.pin(q2)
    assert [q.id for q in f.questions()][0] == q2
    f.close(q2)
    with pytest.raises(ValueError):
        f.answer(q2, "luis", "tarde")
    assert f.waiting() == []
    f.hide_question(q2)
    assert [q.id for q in f.questions()] == [q1] and len(f.questions(include_hidden=True)) == 2
    assert {r["Type"] for r in f.rows()} == {"question", "answer"} and len(f.rows({"cloud-network-security"})) == 3
    with pytest.raises(ValueError):
        f.ask("ana", "cloud-network-security", "   ")


def test_forum_tab_and_report_column(tmp_path, monkeypatch):
    from academy import report
    from academy.forum import Forum

    conn = connect(tmp_path / "app.db")
    cat = load_catalog()
    Forum(conn).ask("ana", cat.families[0].id, "Where do I start with Defender?")
    conn.close()
    at = _run(tmp_path, monkeypatch)
    assert not at.exception
    assert any("Forum" in t.label for t in at.tabs) and any("Where do I start with Defender?" in e.label for e in at.expander)
    assert any("waiting for an expert" in w.value for w in at.warning)  # the owner is told at the top
    rep = report.build(connect(tmp_path / "app.db"), [load_pack("cloud-security")], [], cat, "en")
    assert next(r for r in rep["status"] if r["Role family"] == cat.families[0].name)["Forum: waiting"] == 1


# ---------------------------------------------------------------------------------------------- career path and certifications


# ---------------------------------------------------------------------------------------------- career path and certifications
def test_report_tells_who_keeps_up_with_the_career_path(tmp_path):
    from academy import notify, report

    conn, pack, cat, now, fam = _seed_family_activity(tmp_path)
    notify.set_email(conn, "pedro", "pedro@empresa.com")  # known to the academy, has not started anything
    rep = report.build(conn, [pack], [], cat, "en", only={fam}, now=now)
    state = {r["Person"]: r["_path"] for r in rep["paths"]}
    assert state == {"carla": report.BEHIND, "pedro": report.NOT_STARTED, "ana": report.GOING}
    assert [r["Person"] for r in rep["paths"]] == ["carla", "pedro", "ana"]  # who is not doing their part comes first
    people = {r["Person"]: r for r in rep["people"]}
    assert people["carla"]["Career path"] == "Not keeping up" and people["pedro"]["Career path"] == "Not started"
    assert rep["summary"]["behind"] == 1 and rep["summary"]["not_started"] == 1


def test_certification_register_csv_and_report(tmp_path):
    from datetime import date

    from academy.certs import CURRENT, DESIRED, Certs

    c = Certs(connect(tmp_path / "certs.db"))
    cat = load_catalog()
    fam = cat.families[0].id
    c.set_requirements(fam, [{"Code": "sc-200", "Name": "Security Operations Analyst", "Vendor": "Microsoft", "Level": "requerida"},
                             {"Code": "SC-900", "Name": "SCI Fundamentals", "Level": ""}])
    assert [(r["Code"], r["Level"]) for r in c.requirements()] == [("SC-200", "required"), ("SC-900", "desirable")]
    c.set_records("ana", [{"Code": "az-500", "Name": "Azure Security Engineer", "Status": "actual", "Obtained": "01/03/2026", "Expires": "2026-11-15"},
                          {"Code": "SC-200", "Status": "deseable", "Obtained": "2026-01-01"}], by="ana")
    recs = {r["Code"]: r for r in c.records("ANA")}
    assert recs["AZ-500"]["Status"] == CURRENT and recs["AZ-500"]["Obtained"] == "2026-03-01"
    assert recs["SC-200"]["Status"] == DESIRED and recs["SC-200"]["Obtained"] == ""  # a desired certification has no dates yet
    with pytest.raises(ValueError):
        c.set_records("luis", [{"Code": "X", "Obtained": "pronto"}])
    data, problems = Certs.parse_records(c.records_csv())  # CSV round trip
    assert problems == [] and list(data) == ["ana"] and len(data["ana"]) == 2
    csv_text = "Learner;Code;Name;Vendor;Status;Obtained;Expires;CredentialUrl\r\nluis;SC-200;;Microsoft;current;2026-02-01;;https://learn.microsoft.com/x\r\n"
    data, problems = Certs.parse_records(csv_text.encode("utf-8"))
    assert problems == []
    for who, rows in data.items():  # an owner's import replaces only the people in the file
        c.set_records(who, rows, by="owner")
    assert len(c.records("ana")) == 2 and c.records("luis")[0]["CredentialUrl"].startswith("https://")
    _, problems = Certs.parse_records(csv_text.encode("utf-8"), only_learner="ana")  # a learner cannot import someone else's rows
    assert any("luis" in e for e in problems)
    _, problems = Certs.parse_records(b"Learner,Code\nana,AZ-500\n")
    assert any("Missing columns" in e for e in problems)
    reqs, problems = Certs.parse_requirements(c.requirements_csv(), {f.id for f in cat.families}, allowed={"otra"})
    assert reqs == {} and len(problems) == 2  # a champion cannot change another family's requirements
    reqs, problems = Certs.parse_requirements(c.requirements_csv(), {f.id for f in cat.families})
    assert problems == [] and len(reqs[fam]) == 2
    rep = c.report(cat, "en", roster=["ana", "luis", "pedro"], today=date(2026, 10, 1))
    row = next(r for r in rep["families"] if r["Certification"].startswith("SC-200"))
    assert row["Level"] == "Required" and row["Hold it"] == 1 and row["Aiming for it"] == 1 and row["Who holds it"] == "luis"
    people = {r["Person"]: r for r in rep["people"]}
    assert people["ana"]["Required and missing"] == "SC-200" and people["luis"]["Required and missing"] == "—" and people["pedro"]["Current"] == 0
    assert [(r["Person"], r["Days left"]) for r in rep["expiring"]] == [("ana", 45)]
    assert rep["summary"] == {"people_with": 2, "people": 3, "current": 2, "desired": 1, "expiring": 1}
    assert c.load_suggested({f.id for f in cat.families}) > 0 and len(c.requirements({fam})) == 2  # never overwrites what a family already set


def test_reports_tab_and_my_certifications_render(tmp_path, monkeypatch):
    at = _run(tmp_path, monkeypatch, ak_view="manage")
    assert not at.exception
    assert any("Reports" in x for x in _tab_labels(at)) and not any("Demand" in x for x in _tab_labels(at))  # Demand is its own view
    assert any("Career path by family and person" in m.value for m in at.markdown)
    user = _run(tmp_path, monkeypatch, ak_cert_view="mine")  # Learning view: my certifications live in Progress
    assert not user.exception and not any("Reports" in x or "Demand" in x for x in _tab_labels(user))
    assert any("Register the certifications" in m.value for m in user.markdown)


# ---------------------------------------------------------------------------------------------- practice and demand
def test_practice_matches_what_the_demand_writes():
    from academy.practice import CORE, EMERGING, THIRD, load_practice

    p = load_practice(ROOT / "catalog" / "practice.json")
    cat = load_catalog(ROOT / "catalog" / "skills.json")
    assert all(not t.skill_id or t.skill_id in cat.skill_ids() for t in p.skills) and all(t.family in {f.id for f in cat.families} for t in p.skills)
    for text, term, scope in (("Azure AD", "Microsoft Entra ID", CORE), ("Microsoft Defender for Cloud Apps", "Microsoft Defender for Cloud Apps", CORE),
                              ("defender for cloud", "Microsoft Defender for Cloud", CORE), ("PIM", "Privileged Identity Management (PIM)", CORE),
                              ("Okta SSO", "Okta", THIRD), ("Azure OpenAI", "Azure AI Security", EMERGING)):
        m = p.match_skill(text)
        assert m is not None and (m.term, m.scope) == (term, scope), text
    assert p.match_skill("ServiceNow ITSM") is None and p.match_skill("Java") is None and p.match_skill("pimiento") is None
    assert p.match_role("Sr. Cloud Security Engineer").title == "Cloud Security Engineer" and p.match_role("ServiceNow Developer") is None


def test_demand_analysis_and_report(tmp_path):
    from academy import demand
    from academy.catalog import load_materials
    from academy.practice import load_practice

    rows = demand.sample_rows()
    assert list(rows[0]) == demand.COLUMNS and len(demand.COLUMNS) == 36
    again, problems = demand.parse(demand.to_csv(rows))
    assert again == rows and problems == []
    semi = "Role ID;Role Title;Role Primary Skill;Role Other Skills\nR1;Cloud Security Engineer;Azure AD;Sentinel, KQL | Java\nR2;SAP Consultant;SAP GRC;\n"
    few, problems = demand.parse(semi.encode("utf-8"))
    assert len(few) == 2 and len(problems) == 1 and "Warning" in problems[0]  # other columns may be absent
    assert demand.parse(b"Client,Project\nA,B\n")[1][0].startswith("Missing columns")
    assert demand.role_skills(few[0]) == ["Azure AD", "Sentinel", "KQL", "Java"]
    cat = load_catalog(ROOT / "catalog" / "skills.json")
    practice = load_practice(ROOT / "catalog" / "practice.json")
    a = demand.analyze(few, practice, cat, [load_pack("cloud-security")], load_materials(ROOT / "catalog" / "materials.json"), "en")
    assert a["summary"]["roles"] == 2 and a["summary"]["in_practice"] == 1 and a["summary"]["outside"] == 1
    skills = {r["Skill"]: r for r in a["skills"]}
    assert skills["Microsoft Entra ID"]["Roles"] == 1 and skills["Sentinel"]["Roles"] == 1  # Sentinel and KQL are the same practice skill
    assert skills["Java"]["_scope"] == "outside" and a["outside_roles"][0]["Role ID"] == "R2"
    full = demand.analyze(rows, practice, cat, [load_pack("cloud-security")], load_materials(ROOT / "catalog" / "materials.json"), "en")
    assert sum(full["scope_roles"].values()) == len(rows) and full["titles"][0]["Roles"] >= full["titles"][1]["Roles"]
    assert all(r["_cover"] != "lessons" and r["_scope"] != "outside" for r in full["backlog"]) and full["backlog"]
    charts = demand.charts(full)
    assert sum(v.count("<svg") for v in charts.values()) >= 5 and not hasattr(demand, "to_html")  # charts in the app; reports are PDF only
    sug = demand.catalog_suggestions(full).decode("utf-8-sig").splitlines()
    from academy.content_xlsx import SHEETS

    assert sug[0].split(",") == SHEETS["Skills"] and len(sug) > 1  # same columns as the Skills tab: paste and done
    merged = demand.merge(rows, [dict(rows[0], **{"Role Title": "Changed"})])
    assert len(merged) == len(rows) and merged[0]["Role Title"] == "Changed"
    assert demand.load(demand.save(rows, tmp_path / "d.csv")) == rows


def test_demand_tab_renders_with_the_sample(tmp_path, monkeypatch):
    from academy import demand

    demand.save(demand.sample_rows(), tmp_path / "demand_roles.csv")
    at = _run(tmp_path, monkeypatch, ak_view="demand")
    assert not at.exception
    assert any(m.label == "Practice skills without a course" for m in at.metric)


def test_demand_executive_report_for_owners(tmp_path, monkeypatch):
    from datetime import date

    from academy import demand, demand_exec
    from academy.catalog import load_materials
    from academy.practice import load_practice

    practice = load_practice(ROOT / "catalog" / "practice.json")
    cat = load_catalog(ROOT / "catalog" / "skills.json")
    history = demand.sample_history()
    a = demand.analyze(history[-1][1], practice, cat, [load_pack("cloud-security")], load_materials(ROOT / "catalog" / "materials.json"), "en")
    tr = demand.trend(history, practice, "en")
    top = [r for r in a["skills"] if r["_scope"] != "outside"][:10]
    bench = {r["_entry"].skill_id: 1 for r in top if r["_entry"] is not None and r["_entry"].skill_id}
    b = demand_exec.brief(a, tr, bench, cat, today=date(2026, 10, 8))
    assert len(b["skills"]) == 10 and b["skills"][0]["Roles"] >= b["skills"][-1]["Roles"] and b["skills"][0]["People at level 3+"] in (1, "—")
    assert any("belong to the practice" in m for m in b["messages"]) and any(m.startswith("Since 2026-09-30") for m in b["messages"])
    assert any("bench gap" in m for m in b["messages"]) and b["actions"] and all(r["Owner"] for r in b["actions"]) and all(r["Champion"] for r in b["skills"])
    assert dict(b["kpis"])["Roles in demand"] == str(len(history[-1][1])) and b["upcoming"] > 0  # roles start in Oct and Nov
    no_bench = demand_exec.brief(a, None, None, cat)
    assert any("team inventory has no skill levels" in m for m in no_bench["messages"]) and dict(no_bench["kpis"])["Change vs previous upload"] == "—"
    if demand_exec.available():
        pdf = demand_exec.to_pdf(a, practice, b, "saved upload of 2026-10-07", "2026-10-08 08:00", tr)
        assert pdf.startswith(b"%PDF") and pdf.count(b"/Type /Page") - pdf.count(b"/Type /Pages") >= 2
    # in the app: owners get the executive report; a champion sees the Demand tab without it
    demand.save(demand.sample_rows(), tmp_path / "demand_roles.csv")
    at = _run(tmp_path, monkeypatch, ak_view="demand")
    assert not at.exception and any("Executive summary" in e.label for e in at.expander)
    if demand_exec.available():
        assert any(getattr(b, "label", "") == "Executive report (PDF)" for b in at.get("download_button"))


def test_practice_travels_in_the_content_file(tmp_path, monkeypatch):
    content, _ = _content_sandbox(tmp_path, monkeypatch)
    from academy.practice import load_practice

    text = content.export_csv().replace("Microsoft Cloud Security", "ServiceNow Practice", 1)
    result = content.read(text.encode("utf-8"))
    assert result["problems"] == [] and result["practice"].name == "ServiceNow Practice" and len(result["practice"].skills) > 40
    content.apply(result, backup_dir=tmp_path / "bk")
    assert load_practice().name == "ServiceNow Practice"


def test_demand_snapshots_and_trend(tmp_path, monkeypatch):
    from academy import demand
    from academy.practice import load_practice

    monkeypatch.setenv("ACADEMY_DEMAND", str(tmp_path / "content" / "demand_roles.csv"))
    (week1, rows1), (week2, rows2) = demand.sample_history()
    assert demand.snapshot_date(rows1) == week1 == "2026-09-30" and demand.snapshot_date([{"Timestamp": "10/7/2026 09:00"}]) == "2026-10-07" \
        and demand.snapshot_date([{"Timestamp": "22/09/2026"}]) == "2026-09-22"
    assert demand.save_snapshot(rows2) == week2 and demand.save_snapshot(rows1) == week1  # loaded out of order
    assert [d for d, _ in demand.snapshots()] == [week1, week2] and demand.load() == rows2  # the current file is always the newest upload
    demand.sync_history()
    assert len(demand.snapshots()) == 2
    replaced = [dict(r, Timestamp="2026-10-14 08:00") for r in rows2[:20]]
    demand.save(replaced)  # the file replaced by hand, without the app
    demand.sync_history()
    assert [d for d, _ in demand.snapshots()] == [week1, week2, "2026-10-14"]
    with pytest.raises(ValueError):
        demand.save_snapshot(rows1, "14/10/2026")
    practice = load_practice(ROOT / "catalog" / "practice.json")
    t = demand.trend([(week1, rows1), (week2, rows2)], practice, "en")
    assert [p["roles"] for p in t["points"]] == [len(rows1), len(rows2)] and all(sum(p[s] for s in ("core", "third-party", "emerging", "outside")) == p["roles"] for p in t["points"])
    ids1, ids2 = {r["Role ID"] for r in rows1}, {r["Role ID"] for r in rows2}
    assert {r["Role ID"] for r in t["new_roles"]} == ids2 - ids1 and {r["Role ID"] for r in t["gone_roles"]} == ids1 - ids2
    row = t["skills"][0]
    assert row[week2] - row[week1] == row["_delta"] and row["Change vs previous"] in (f"{row['_delta']:+d}", "0")
    charts = demand.trend_charts(t)
    assert charts["lines"].count("<path") == 4 and "<svg" in charts["up"]
    one = demand.trend([(week2, rows2)], practice, "en")
    assert one["skills"][0]["Change vs previous"] == "—" and demand.trend_charts(one)["lines"] == ""  # one upload: no trend yet


def test_demand_report_as_pdf():
    from academy import demand, demand_pdf
    from academy.practice import load_practice

    if not demand_pdf.available():
        pytest.skip("reportlab is not installed")
    practice = load_practice(ROOT / "catalog" / "practice.json")
    history = demand.sample_history()
    a = demand.analyze(history[-1][1], practice, load_catalog(ROOT / "catalog" / "skills.json"), [load_pack("cloud-security")], {}, "en")
    pdf = demand_pdf.to_pdf(a, practice, "2026-10-07", demand.trend(history, practice, "en"))
    assert pdf.startswith(b"%PDF") and len(pdf) > 20_000
    assert demand_pdf.to_pdf(demand.analyze([], practice, lang="en"), practice).startswith(b"%PDF")  # an empty file does not break it


# ---------------------------------------------------------------------------------------------- copyright
def test_copyright_notice_is_fixed_and_sealed(tmp_path, monkeypatch):
    from academy import legal

    assert legal.verify()
    assert legal.notice("es") == "© 2026 Alejandro Zavala. Todos los derechos reservados."  # the sealed module keeps both
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


# ---------------------------------------------------------------------------------------------- edit mode
def test_edit_mode_lists_merge_and_save(tmp_path, monkeypatch):
    content, packs = _content_sandbox(tmp_path, monkeypatch)
    from academy import editor

    data = content.tables()
    extra = {("Resources", "Channel"): ["My new channel"]}
    assert editor.options("Lessons", "Level", data, {}) == load_pack("cloud-security").levels  # the course's own levels
    assert "f1" in editor.options("Questions", "LessonId", data, {}) and editor.options("Lessons", "LessonId", data, {}) is None  # keys are free
    assert editor.options("Questions", "AnswerLetter", data, {}) == list("ABCD")
    assert "My new channel" in editor.options("Resources", "Channel", data, extra)  # «➕ New option»
    assert "Microsoft" in editor.options("Skills", "Vendor", data, {}) and editor.options("Resources", "Url", data, {}) is None
    flt = {"PackId": "cloud-security", "LessonId": "f1"}
    shown = [r for r in data["Questions"] if editor._match("Questions", r, flt)]
    assert len(shown) == 3
    df = editor._frame("Questions", shown)
    df.loc[0, "Question"] = "Edited in the app?"
    rows = editor._rows("Questions", df)
    merged = editor._merge("Questions", data["Questions"], rows, flt)
    assert len(merged) == len(data["Questions"]) and merged[0]["Question"] == "Edited in the app?"  # same place, nothing lost
    data["Questions"] = merged
    new = {"PackId": "", "Term": "Zero-day", "Category": "Threats", "Definition": "A flaw attackers use before a fix exists."}
    data["Glossary"] = editor._merge("Glossary", data["Glossary"], data["Glossary"] + [new], {"PackId": "cloud-security"})  # added at the bottom
    assert data["Glossary"][-1]["PackId"] == "cloud-security"  # the new row takes the course of the filter
    editor._fill_ids(data)
    result = content.build(data)
    assert result["problems"] == []
    content.apply(result, backup_dir=tmp_path / "bk")
    pack = load_pack(packs / "cloud-security")
    assert pack.lessons[0].quiz[0].q == "Edited in the app?" and any(g["term"] == "Zero-day" for g in pack.glossary)
    data["Questions"][0]["AnswerLetter"] = "Z"  # a broken edit is refused with the reason, like an import
    assert any("AnswerLetter" in e for e in content.build(data)["problems"])


def test_edit_mode_shows_in_every_section_for_owners(tmp_path, monkeypatch):
    # Management view: each section's ✏️ Edit mode opens the editor of its own tables
    for section in ("tab_route", "tab_reports", "tab_demand", "tab_skills"):
        at = _run(tmp_path, monkeypatch, ak_view="demand" if section in ("tab_demand", "tab_skills") else "manage", **{f"ed_on_{section}": True})
        assert not at.exception, (section, at.exception[0].stack_trace if at.exception else "")
        assert any(str(b.key) == f"ed_{section}_save" for b in at.button), section
    at = _run(tmp_path, monkeypatch, ak_view="manage", mg_admin_part="✏️ Every table")  # Administration → every table of the workbook
    assert not at.exception and any(str(b.key) == "ed_team_0_save" for b in at.button)
    assert any(str(b.key) == "ed_tab_news_save" for b in at.button)  # Knowledge exchange → sources and material
    learner_view = _run(tmp_path, monkeypatch)  # the same owner in the Learning view: nothing to edit
    assert not learner_view.exception and not any(str(t.key).startswith("ed_on_") for t in learner_view.toggle)
    (tmp_path / "u").mkdir()  # a separate installation where "me" is a learner
    user = _run(tmp_path / "u", monkeypatch, owners=("jefa",), ak_view="manage")
    assert not user.exception and not any(str(t.key).startswith("ed_on_") for t in user.toggle)  # learners never see it


# ---------------------------------------------------------------------------------------------- news
RSS = b"""<?xml version="1.0"?><rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/"><channel><title>Blog</title>
<item><title>Older post</title><link>https://example.com/old</link><pubDate>Mon, 05 Oct 2026 10:00:00 +0000</pubDate>
<description>Old &lt;b&gt;news&lt;/b&gt;</description></item>
<item><title>New [threat] report</title><link>https://example.com/new</link><pubDate>Wed, 07 Oct 2026 10:00:00 +0000</pubDate>
<description><![CDATA[<p>Attackers <script>alert(1)</script>moved to the cloud.</p><img src="https://example.com/a.png">]]></description></item>
</channel></rss>"""
ATOM = b"""<?xml version="1.0" encoding="utf-8"?><feed xmlns="http://www.w3.org/2005/Atom"><title>F</title>
<entry><title>Atom entry</title><link rel="alternate" href="https://example.org/e1"/><updated>2026-10-06T09:00:00Z</updated>
<summary>Short summary</summary></entry></feed>"""
PAGE = b"""<html><head><title>ISO</title><meta property="og:title" content="ISO/IEC 27001"><meta property="og:description"
content="Information security management systems"><meta property="og:image" content="https://www.iso.org/i.png"></head></html>"""


def test_news_feeds_pages_and_sources(tmp_path, monkeypatch):
    from academy import news

    items = news.parse_feed(RSS, "Blog")
    assert [i.title for i in items] == ["New [threat] report", "Older post"] and items[0].published == "2026-10-07"
    assert items[0].image == "https://example.com/a.png" and "alert" not in items[0].summary and "<" not in items[1].summary
    (atom,) = news.parse_feed(ATOM)
    assert (atom.link, atom.published, atom.summary) == ("https://example.org/e1", "2026-10-06", "Short summary")
    page = news.parse_page(PAGE, "https://www.iso.org/standard/27001")
    assert page.title == "ISO/IEC 27001" and page.image.startswith("https://") and page.kind == "page"
    sources = news.load_sources(ROOT / "catalog" / "news_sources.csv")
    assert news.splash_source(sources).name == "Microsoft Security Insider"
    assert {"Microsoft", "Cloud providers", "Frameworks and standards"} <= {s.category for s in sources}
    assert all(s.url.startswith("https://") for s in sources)
    back, problems = news.parse_sources(news.to_csv(sources))
    assert back == sources and problems == []
    assert news.parse_sources(b"Name,Url\nX,http://insecure\n")[1]


def test_news_reading_falls_back_and_keeps_the_last_good_one(tmp_path, monkeypatch):
    from academy import news

    monkeypatch.setenv("ACADEMY_NEWS_CACHE", str(tmp_path / "cache.json"))
    monkeypatch.delenv("ACADEMY_NEWS_OFFLINE", raising=False)
    feed = news.Source("Blog", "Microsoft", "https://example.com", "https://example.com/feed")
    iso = news.Source("ISO", "Frameworks and standards", "https://www.iso.org/standard/27001")
    web = {"https://example.com/feed": RSS, "https://www.iso.org/standard/27001": PAGE}

    def fetch(url, timeout=0):
        if url not in web:
            raise OSError("down")
        return web[url]

    got = news.latest([feed, iso], fetch=fetch)
    assert got["Blog"].ok and got["Blog"].items[0].title == "New [threat] report" and got["ISO"].items[0].kind == "page"
    web.clear()  # offline now: the last good reading is still shown, marked as not fresh
    again = news.latest([feed, iso], fetch=fetch)
    assert not again["Blog"].ok and again["Blog"].items[0].title == "New [threat] report"
    assert news.cover_image(news.Item("t", "https://example.com/x", image="https://example.com/i.png")) == "https://example.com/i.png"


def test_knowledge_exchange_tab_renders(tmp_path, monkeypatch):
    import json as _json

    (tmp_path / "news_cache.json").write_text(_json.dumps({"AWS Security Blog": {"source": "AWS Security Blog", "fetched": "2026-10-07T10:00:00+00:00",
                                                          "ok": True, "error": "", "items": [{"title": "IAM tips", "link": "https://aws.amazon.com/x",
                                                          "summary": "Least privilege", "published": "2026-10-07", "image": "", "source": "AWS Security Blog",
                                                          "kind": "item"}]}}), encoding="utf-8")
    at = _run(tmp_path, monkeypatch)
    assert not at.exception and any("Knowledge exchange" in x for x in _tab_labels(at))
    assert any("reading bank" in c.value for c in at.caption)


# ---------------------------------------------------------------------------------------------- team inventory
def test_inventory_template_import_matrix_and_search(tmp_path):
    from academy import inventory as inv
    from academy.certs import Certs
    from academy.practice import load_practice

    conn = connect(tmp_path / "inv.db")
    cat, practice = load_catalog(), load_practice(ROOT / "catalog" / "practice.json")
    blank = inv.parse(inv.template_csv(), practice, cat)  # the example leaves the skill levels for each person to rate
    assert blank["problems"] and all("Level must be 1 to 5" in e for e in blank["problems"])
    import csv as _csv
    import io as _io

    table = list(_csv.DictReader(_io.StringIO(inv.template_csv().decode("utf-8-sig"))))
    for r in table:  # the person rates their skills
        if r["Type"] == "skill":
            r["Level"] = "4" if r["Name"] == "KQL" else "3"
    buf = _io.StringIO()
    w = _csv.DictWriter(buf, fieldnames=inv.COLUMNS)
    w.writeheader()
    w.writerows(table)
    parsed = inv.parse(buf.getvalue().encode("utf-8"), practice, cat)
    assert parsed["problems"] == [] and parsed["people"] == ["Alejandro Zavala"]
    assert {c["Code"] for c in parsed["certs"]["Alejandro Zavala"]} == {"AZ-900", "SC-200", "AZ-500", "AI-901"}
    kql = next(s for s in parsed["skills"]["Alejandro Zavala"] if s["Skill"] == "KQL")
    assert kql["SkillId"] == "microsoft-sentinel" and kql["Level"] == 4  # the practice's aliases map free names to the catalog
    assert inv.parse(inv.template_xlsx(skills=["KQL"]), practice, cat)["problems"] == blank["problems"]  # the Excel template reads the same
    store = inv.Inventory(conn)
    store.apply(parsed, by="owner")
    extra = "Person;Email;Type;Name;Code;Vendor;Level;Years;Status\nLuis;luis@x.com;skill;KQL;;Microsoft;3;2;current\n" \
            "Luis;;skill;Terraform;;HashiCorp;2;;current\nLuis;;certification;SC-200;SC-200;Microsoft;;;desired\n"
    store.apply(inv.parse(extra.encode(), practice, cat), by="owner")
    assert len(Certs(conn).records("Alejandro Zavala")) == 4 and Certs(conn).records("luis")[0]["Status"] == "desired"
    cols, rows = store.matrix(cat)
    assert "Microsoft Sentinel" in cols and {r["Person"] for r in rows} == {"Alejandro Zavala", "Luis"}
    found = store.who_has(["Microsoft Sentinel"], 3, cat)
    assert [r["Person"] for r in found] == ["Alejandro Zavala", "Luis"] and "AZ-500" in found[0]["Certifications"]
    store.validate("Luis", "KQL", "champion")
    assert store.matrix(cat)[1][1]["Microsoft Sentinel"] == "3 ✓"
    store.set_skills("Luis", [{"Skill": "KQL", "SkillId": "microsoft-sentinel", "Level": 4}], by="Luis")  # a new level drops the validation
    assert not store.skills("Luis")[0]["ValidatedBy"] and store.coverage(["microsoft-sentinel"]) == {"microsoft-sentinel": 2}
    back = inv.parse(store.export_csv(), practice, cat)  # round trip in the same columns
    assert back["problems"] == [] and set(back["people"]) == {"Alejandro Zavala", "Luis"}
    bad = inv.parse(b"Person,Type,Name,Level,Status\nAna,skill,KQL,,current\nAna,badge,x,,current\n", practice, cat)
    assert len(bad["problems"]) == 2


# ---------------------------------------------------------------------------------------------- rhythm
def test_rhythm_dates_invites_agendas_and_actions(tmp_path, pack, exam):
    from datetime import date

    from academy import rhythm as rh

    conn = connect(tmp_path / "rh.db")
    cat = load_catalog()
    r = rh.Rhythm(conn)
    made = r.standard(cat.families, "owner", today=date(2026, 10, 1))
    assert len(made) == 1 + len(cat.families) and r.standard(cat.families, "owner") == []  # created once
    monthly = next(s for s in r.all() if s.kind == rh.MONTHLY)
    assert rh.occurrences(monthly, date(2026, 10, 1), date(2026, 12, 31)) == [date(2026, 10, 6), date(2026, 11, 3), date(2026, 12, 1)]  # 1st Tuesday
    r.update(monthly.id, week=-1, weekday=4)
    assert rh.occurrences(r.get(monthly.id), date(2026, 10, 1), date(2026, 10, 31)) == [date(2026, 10, 30)]  # last Friday
    sid = r.create(rh.STUDY, "AI-901 study group", cert="ai-901", lead="ana", weekday=2, time="17:00", start="2026-10-01", end="2026-11-12")
    g = r.get(sid)
    days = rh.occurrences(g, date(2026, 10, 1), date(2026, 12, 31))
    assert days[0] == date(2026, 10, 7) and days[-1] == date(2026, 11, 11) and len(days) == 6  # weekly, until the day before the exam
    assert rh.session_number(g, date(2026, 10, 14)) == (2, 6)
    plan = rh.study_plan(exam, 6)
    assert len(plan) == 6 and "Mock exam" in plan[-2]
    r.join(sid, "luis")
    assert r.attendees(g, ["owner"], {}, None) == ["ana", "luis"]
    assert "owner" in r.attendees(r.get(monthly.id), ["owner"], {f.id: f.champion for f in cat.families})
    invite = rh.ics(g, {"ana": "ana@x.com", "luis": ""}, "ana@x.com", first=date(2026, 10, 7)).decode()
    assert "RRULE:FREQ=WEEKLY;INTERVAL=1;BYDAY=WE;UNTIL=20261111T235959" in invite and "DTSTART:20261007T170000" in invite
    assert "mailto:ana@x.com" in invite and "luis" not in invite and all(len(x.encode()) <= 75 for x in invite.split("\r\n"))
    assert "BYDAY=-1FR" in rh.ics(r.get(monthly.id), {}).decode()
    with pytest.raises(ValueError):
        r.create(rh.STUDY, "no date", cert="SC-200")
    with pytest.raises(ValueError):
        r.create(rh.WEEKLY, "bad time", time="25:99")
    aid = r.add_action(sid, "2026-10-07", "Share the Microsoft Learn path", "ana", "2026-10-10", by="ana")
    agenda = dict(rh.agenda(conn, g, date(2026, 10, 14), [pack], [exam], cat))
    assert any("Share the Microsoft Learn path" in x for x in next(v for k, v in agenda.items() if k.startswith("Open actions")))
    assert "Readiness" in agenda and any("luis" in x for x in agenda["Readiness"])
    r.set_done(aid)
    assert r.actions(sid, open_only=True) == []
    weekly = next(s for s in r.all() if s.kind == rh.WEEKLY)
    assert "People to follow up" in dict(rh.agenda(conn, weekly, date(2026, 10, 8), [pack], [exam], cat))
    assert "Demand against the bench" in dict(rh.agenda(conn, r.get(monthly.id), date(2026, 10, 30), [pack], [exam], cat))


def test_rhythm_and_skills_render_in_the_app(tmp_path, monkeypatch):
    from academy import rhythm as rh

    at = _run(tmp_path, monkeypatch, ak_view="manage")
    assert not at.exception and any("Rhythm" in x for x in _tab_labels(at))
    at.button(key="rh_std").click().run()
    assert not at.exception and len(rh.Rhythm(connect(tmp_path / "app.db")).all()) >= 2
    assert any("Meeting room" in m.value for m in at.markdown) and any("Open actions" in m.value for m in at.markdown)
    assert any("Team skills matrix" in m.value for m in at.markdown)  # Reports → Skills matrix
    skills = _run(tmp_path, monkeypatch, ak_cert_view="skills")  # Learning → Progress → My skills
    assert not skills.exception and any("Register the skills" in m.value for m in skills.markdown)
    assert any("Study groups" in x for x in _tab_labels(skills)) and not any("Meeting room" in m.value for m in skills.markdown)


# ---------------------------------------------------------------------------------------------- study material and people
SAVED_PAGE = b"""<html><body><h2>Azure Master Class</h2><a href="https://www.youtube.com/watch?v=aaa111">Module 1 - Introduction</a>
<a href="https://www.azadvertizer.net/other.html">not a video</a><h3>Security</h3><a href='//youtu.be/bbb222'>Key Vault &amp; HSM</a>
<a href="https://www.youtube.com/playlist?list=PL123">AZ-500 playlist</a><a href="https://www.youtube.com/watch?v=aaa111">dup</a></body></html>"""


def test_study_material_bank_import_and_learning_path(tmp_path):
    from academy import study

    seed = study.savill_seed()
    assert sum(i.kind == "video" for i in seed) == 6 and all(i.url.startswith("https://") for i in seed)
    assert {i.category for i in seed} == {"Microsoft"} and all(i.source == study.SAVILL for i in seed)
    known = load_catalog().skill_ids()
    assert all(not i.skill_id or i.skill_id in known for i in seed)  # every item points to a real skill of the catalog
    back, problems = study.parse(study.to_csv(seed))
    assert back == seed and problems == []
    page = study.from_page(SAVED_PAGE)
    assert [(i.title, i.theme, i.kind) for i in page] == [("Module 1 - Introduction", "Azure Master Class", "video"),
                                                         ("Key Vault & HSM", "Security", "video"), ("AZ-500 playlist", "Security", "playlist")]
    assert page[1].url == "https://youtu.be/bbb222"
    merged = study.merge(seed, page + seed[:2])
    assert len(merged) == len(seed) + 3  # links already in the bank are not repeated
    assert study.as_class(page[2])["kind"] == "course" and study.as_class(page[0])["kind"] == "video"
    assert study.parse(b"Title,Url,Kind\nX,http://x,video\nY,https://y,podcast\n")[1] and len(study.parse(b"Title,Url\n")[0]) == 0


def test_people_directory_roles_and_catalog_champions(tmp_path):
    from academy import people

    cat = load_catalog()
    net = "cloud-network-security"
    raw = (f"Person,Email,Role,Families,Active\nAlejandro Zavala,ale@x.com,owner,,yes\nCarla,carla@x.com,champion,{net},yes\n"
           f"Sam,,sme,{net}; ai-security-governance,yes\nOld,,learner,,no\n").encode()
    dirx, problems = people.parse(raw, {f.id for f in cat.families})
    assert problems == [] and len(dirx) == 4
    assert people.is_owner(dirx, "alejandro zavala") and people.is_owner(dirx, "x", "ALE@x.com") and not people.is_owner(dirx, "Carla")
    assert people.families_of(dirx, "Carla") == {net} and people.families_of(dirx, "Sam", role=people.SME) == {net, "ai-security-governance"}
    synced, changed = people.sync_catalog(dirx, cat)
    fam = next(f for f in synced.families if f.id == net)
    assert changed and (fam.champion, fam.champion_email) == ("Carla", "carla@x.com")
    bad = people.parse(b"Person,Role,Families\nA,boss,\nB,champion,\nC,sme,nope\n", {f.id for f in cat.families})[1]
    assert len(bad) == 3
    assert people.parse(people.to_csv(dirx))[0] == dirx


def test_directory_name_gives_the_owner_view_and_study_sections_render(tmp_path, monkeypatch):
    from academy import people

    people.save([people.Person("Alejandro Zavala", "ale@x.com", "owner"), people.Person("Luis", "", "learner")], tmp_path / "people.csv")
    at = _run(tmp_path, monkeypatch, owners=None)
    assert not at.exception and at.session_state["ak_person"] == "Alejandro Zavala"
    assert "ak_view" in [x.key for x in at.segmented_control]  # owner by name, no e-mail typed
    assert not any(str(b.key) == "ak_claim" for b in at.button)  # an owner exists in the directory: nothing to claim
    at.selectbox(key="ak_person").set_value("Luis").run()
    assert not at.exception and "ak_view" not in [x.key for x in at.segmented_control]
    at = _run(tmp_path, monkeypatch, owners=None, kx_part="📚 Study material")
    assert not at.exception and any("Study material" in m.value for m in at.markdown)
    assert any("Azure Master Class" in e.label for e in at.expander) or any("Certification study cram" in e.label for e in at.expander)


def test_demand_reads_the_organization_report_format(tmp_path, monkeypatch):
    """The real roles report numbers the skills, adds their proficiency, prefixes titles with codes, writes US dates and carries a
    «Matrix cross-skills Practice» column. (Made-up values in the same shape: the real file is confidential.)"""
    from academy import demand
    from academy.practice import load_practice

    head = demand.COLUMNS
    role = dict.fromkeys(head, "")
    role.update({"Timestamp": "9/15/2026", "Client": "Demo Client", "Role ID": "900001", "Role Title": "111111-22222_Security Architect",
                 "Combined Skills": "1 - Microsoft Sentinel (P3 - Advanced) | Security Operations | 2 - KQL (P2 - Intermediate) | 3 - Java (P1 - Basic)",
                 "Role Primary Skill": "1 - Microsoft Sentinel                                   (P3 - Advanced)", "Skill Category": "Security Operations",
                 "Role Other Skills": "2 - KQL                     (P2 - Intermediate) | 3 - Java       (P1 - Basic)",
                 "Role Start Date": "5-Nov-26", "Role End Date": "31-Aug-27", "Industry Level 1": "-",
                 "Matrix cross-skills Practice": "• Practice Matches (Aligned Capabilities)\n- Cyber Defense & Security Operations: Microsoft Sentinel\n\n"
                                                 "• Unaligned Skills & Gaps\n- Data Protection, Risk & Compliance: Microsoft Purview, DLP / Information Protection"})
    buf = __import__("io").StringIO()
    w = __import__("csv").DictWriter(buf, fieldnames=head)
    w.writeheader()
    w.writerow(role)
    rows, problems = demand.parse(buf.getvalue().encode("utf-8"))
    assert problems == [] and demand.snapshot_date(rows) == "2026-09-15"
    assert demand.role_skills(rows[0]) == ["Microsoft Sentinel", "KQL", "Java"]  # numbers, proficiency and the category left out
    a = demand.analyze(rows, load_practice(ROOT / "catalog" / "practice.json"), load_catalog(), [load_pack("cloud-security")], {}, "en")
    assert a["titles"][0]["Role title"] == "Security Architect" and a["months"] == [("2026-11", 1)]
    assert a["summary"]["in_practice"] == 1 and not any(name == "-" for name, _ in a["by"]["Industry Level 1"])
    gaps = {(r["Role family"], r["Skill"]): r for r in a["matrix"]}
    assert gaps[("Data Protection, Risk & Compliance", "Microsoft Purview")]["Roles where it is a gap"] == 1
    assert gaps[("Cyber Defense & Security Operations", "Microsoft Sentinel")]["Roles where it is aligned"] == 1
    # in the app: an uploaded file is read for the session only; nothing is written
    monkeypatch.setenv("ACADEMY_DEMAND", str(tmp_path / "demand_roles.csv"))
    at = _run(tmp_path, monkeypatch, dm_session={"name": "roles.csv", "rows": rows, "date": "2026-09-15"}, ak_view="demand")
    assert not at.exception and any("not saved" in w.value for w in at.warning)
    assert not (tmp_path / "demand_roles.csv").exists() and not (tmp_path / "demand_history").exists()


# ---------------------------------------------------------------------------------------------- Azure App Service
def test_entra_sign_in_is_trusted_only_on_azure(tmp_path, monkeypatch):
    import base64

    from academy import identity, people

    claims = {"claims": [{"typ": "name", "val": "Ana Lopez"}, {"typ": "preferred_username", "val": "ana.lopez@contoso.com"}]}
    headers = {"X-Ms-Client-Principal-Name": "ana.lopez@contoso.com",
               "X-Ms-Client-Principal": base64.b64encode(json.dumps(claims).encode()).decode().rstrip("=")}
    assert identity.signed_in(headers, {}) is None  # on a laptop the headers mean nothing
    me = identity.signed_in(headers, {"ACADEMY_AUTH": "entra"})
    assert me == identity.SignedIn("ana.lopez@contoso.com", "Ana Lopez")
    assert identity.signed_in({"x-ms-client-principal-name": "bo@contoso.com"}, {"ACADEMY_AUTH": "Entra"}).name == "Bo"
    assert identity.signed_in({}, {"ACADEMY_AUTH": "entra"}) is None
    # in the app: the signed-in account replaces «Who are you?» and the owner role goes by its e-mail
    people.save([people.Person("Ana Lopez", "ana.lopez@contoso.com", "owner")], tmp_path / "people.csv")
    monkeypatch.setenv("ACADEMY_AUTH", "entra")
    monkeypatch.setattr(identity, "signed_in", lambda h, env=None: identity.SignedIn("ana.lopez@contoso.com", "Ana L."))
    at = _run(tmp_path, monkeypatch, owners=None)
    assert not at.exception and any("Signed in as **Ana Lopez**" in c.value for c in at.caption)
    assert not any(s.label == "Who are you?" for s in at.selectbox) and "ak_view" in [x.key for x in at.segmented_control]


def test_azure_package_leaves_data_out(tmp_path):
    import importlib.util
    import zipfile

    spec = importlib.util.spec_from_file_location("package", ROOT / "deploy" / "azure" / "package.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    names = mod.build(tmp_path / "a.zip")
    assert "app.py" in names and "deploy/azure/startup.py" in names and "requirements.txt" in names
    assert not [n for n in names if n.startswith(("data/", "config/", "tests/", ".venv/", "export/"))]
    assert "content/demand_roles.csv" not in names and not any("demand_history" in n for n in names)
    assert set(zipfile.ZipFile(tmp_path / "a.zip").namelist()) == set(names)


def test_up_to_six_owners_kept_in_people(tmp_path, monkeypatch):
    from academy import people

    d = [people.Person("Alejandro Zavala", "alejandro@contoso.com", "owner"),
         people.Person("Ana Lopez", "ana@contoso.com", "champion", ("identity-access-management",))]
    new, problems = people.set_owners(d, [("Alejandro Zavala", "alejandro@contoso.com"), ("Ana Lopez", "ana@contoso.com"),
                                          ("Bo Chen", "bo@contoso.com")])
    assert problems == [] and [p.name for p in people.owners(new)] == ["Alejandro Zavala", "Ana Lopez", "Bo Chen"]
    assert next(p for p in new if p.name == "Ana Lopez").families == ("identity-access-management",)  # keeps her families
    six = [(c, f"{c.lower()}@x.com") for c in "ABCDEF"]
    seven = six + [("G", "g@x.com")]
    assert people.set_owners(d, six)[1] == [] and people.set_owners(d, seven)[1] == ["At most 6 owners."] and people.set_owners(d, [])[1]
    assert people.set_owners(d, [("Bo", "not-an-email")])[1]
    back, _ = people.set_owners(new, [("Alejandro Zavala", "alejandro@contoso.com")])  # the others step down, nobody is deleted
    assert len(back) == 3 and next(p for p in back if p.name == "Ana Lopez").role == "champion" and next(p for p in back if p.name == "Bo Chen").role == "learner"
    raw = people.to_csv([people.Person(n, e, "owner") for n, e in seven])
    assert any("at most 6 active owners" in m for m in people.parse(raw)[1])
    assert not people.parse(people.to_csv([people.Person(n, e, "owner") for n, e in six]))[1]
    monkeypatch.setenv("ACADEMY_MAX_OWNERS", "7")
    assert not people.parse(raw)[1]
    monkeypatch.delenv("ACADEMY_MAX_OWNERS")
    # in the app: each of the three owners gets the owner view; the Team tab shows «Global owners (3 of 6)»
    people.save(new, tmp_path / "people.csv")
    for who in ("Ana Lopez", "Bo Chen"):
        at = _run(tmp_path, monkeypatch, owners=None, ak_person=who, ak_view="manage", mg_admin_part="👑 People and access")
        assert not at.exception and any(e.label == "👑 Global owners (3 of 6)" for e in at.expander), who


def test_azure_startup_keeps_team_data_between_deploys(tmp_path):
    import importlib.util

    spec = importlib.util.spec_from_file_location("startup", ROOT / "deploy" / "azure" / "startup.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    app, home = tmp_path / "app", tmp_path / "home"
    (app / "catalog").mkdir(parents=True)
    (app / "catalog" / "people.csv").write_text("shipped", encoding="utf-8")
    added = mod.link_folders(app, home)
    assert "catalog/people.csv" in [a.replace("\\", "/") for a in added] and (app / "catalog").is_symlink()
    (home / "catalog" / "people.csv").write_text("edited in the app", encoding="utf-8")
    new = tmp_path / "app2"  # the next deploy: a fresh copy of the code, with one new file
    (new / "catalog").mkdir(parents=True)
    (new / "catalog" / "people.csv").write_text("shipped again", encoding="utf-8")
    (new / "catalog" / "new.csv").write_text("new", encoding="utf-8")
    mod.link_folders(new, home)
    assert (new / "catalog" / "people.csv").read_text(encoding="utf-8") == "edited in the app" and (home / "catalog" / "new.csv").exists()
    assert mod.link_folders(new, home) == []  # a restart changes nothing


def test_azure_owners_from_the_app_setting(tmp_path):
    import importlib.util

    from academy import people

    spec = importlib.util.spec_from_file_location("startup", ROOT / "deploy" / "azure" / "startup.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    (tmp_path / "catalog").mkdir()
    people.save([people.Person("Alejandro Zavala", "old@gmail.com", "owner")], tmp_path / "catalog" / "people.csv")
    msg = mod.apply_owners(ROOT, tmp_path, "a.zavala@contoso.com; Perla Marmolejo <perla.m@contoso.com>,\nsam.calles@contoso.com")
    d = people.load(tmp_path / "catalog" / "people.csv")
    assert msg.startswith("Owners from ACADEMY_OWNERS") and [p.email for p in people.owners(d)] == ["a.zavala@contoso.com", "perla.m@contoso.com", "sam.calles@contoso.com"]
    assert next(p for p in d if p.email == "sam.calles@contoso.com").name == "Sam Calles" and next(p for p in d if p.email == "old@gmail.com").role == "learner"
    assert "ignored" in mod.apply_owners(ROOT, tmp_path, "a@x.com; b@x.com; c@x.com; d@x.com; e@x.com; f@x.com; g@x.com")  # more than 6: nothing changes
    assert len(people.owners(people.load(tmp_path / "catalog" / "people.csv"))) == 3


def test_course_titles_say_practice_not_academy(tmp_path):
    import shutil

    from academy import english

    shutil.copytree(ROOT / "packs" / "cloud-security", tmp_path / "packs" / "cloud-security")
    import importlib

    fresh = importlib.reload(english)  # the module's own function (the fixture replaced it for the app runs)
    assert fresh.practice_titles(tmp_path) is True and fresh.practice_titles(tmp_path) is False
    title = json.loads((tmp_path / "packs" / "cloud-security" / "pack.json").read_text(encoding="utf-8"))["meta"]["title"]
    assert title == "Cloud Security Practice"




def test_practices_are_separate_spaces(tmp_path, monkeypatch):
    from academy import pack as packmod
    from academy import people, workspace

    monkeypatch.setenv("ACADEMY_PRACTICES", str(tmp_path / "practices.csv"))
    monkeypatch.setenv("ACADEMY_PRACTICES_DIR", str(tmp_path / "practices"))
    first = workspace.default_id()
    assert [p.id for p in workspace.load()] == [first] and workspace.root(first) == ROOT
    ppm = workspace.create("PPM", "Program and product management")
    assert ppm.id == "ppm" and [p.id for p in workspace.load()] == [first, "ppm"]
    with pytest.raises(ValueError):
        workspace.create("ppm")
    workspace.use("ppm")
    try:
        assert workspace.root() == tmp_path / "practices" / "ppm" and packmod.available_packs() == ["ppm"]
        starter = packmod.load_pack("ppm")
        assert starter.title == "PPM Practice" and starter.lessons == [] and packmod.validate(starter) == []
        from academy.catalog import catalog_path

        assert catalog_path() == tmp_path / "practices" / "ppm" / "catalog" / "skills.json"
    finally:
        workspace.use(first)
    assert packmod.available_packs() == ["cloud-security"]
    with pytest.raises(ValueError):
        workspace.update([workspace.Practice(first, "X", active=False), workspace.Practice("ppm", "PPM", active=False)])
    # people: one practice each; global owners everywhere, a practice's owners only there
    d = [people.Person("Ana", "ana@x.com", "owner"), people.Person("Perla", "perla@x.com", "owner", practice="ppm"),
         people.Person("Sam", "sam@x.com", "learner", practice="ppm"), people.Person("Bo", "bo@x.com", "learner")]
    assert people.is_owner(d, "", "ana@x.com", "ppm") and people.is_owner(d, "", "perla@x.com", "ppm")
    assert not people.is_owner(d, "", "perla@x.com", first) and not people.is_owner(d, "", "perla@x.com")
    assert [p.name for p in people.members(d, "ppm", first)] == ["Perla", "Sam"] and [p.name for p in people.members(d, first, first)] == ["Bo"]
    merged = people.replace_members(d, "ppm", first, [people.Person("Sam", "sam@x.com", "champion", ("delivery",))])
    assert {p.name for p in merged} == {"Ana", "Sam", "Bo"} and next(p for p in merged if p.name == "Sam").practice == "ppm"
    raw = people.to_csv(d)
    assert people.parse(raw)[0] == d and people.parse(raw)[1] == []
    # in the app: a global owner opens PPM from the sidebar; a PPM learner lands in PPM without a choice
    people.save(d, tmp_path / "people.csv")
    at = _run(tmp_path, monkeypatch, owners=None, ak_person="Ana", ak_practice="ppm")
    assert not at.exception
    assert next(s for s in at.selectbox if s.label == "Practice").value == "ppm"
    assert any("PPM Practice" in m.value for m in at.markdown) and any("Getting started" in m.value for m in at.markdown)
    at = _run(tmp_path, monkeypatch, owners=None, ak_person="Sam")
    assert not at.exception and not any(s.label == "Practice" for s in at.selectbox)
    assert any("Practice: **PPM**" in c.value for c in at.caption)


def test_roster_sets_course_roles(tmp_path, monkeypatch):
    from academy import people

    d = [people.Person("Ana", "ana@x.com", "owner"), people.Person("Bo", "bo@x.com", "learner"),
         people.Person("Sam", "sam@x.com", "learner", practice="ppm")]
    raw = "Person,Email,Course role\nBo,BO@x.com,Cloud Engineer\nNew Person,new@x.com,\n".encode()
    rows = people.parse_roster(raw)
    assert rows[0] == {"Person": "Bo", "Email": "BO@x.com", "CourseRole": "Cloud Engineer"}
    new, problems, added = people.apply_roster(d, rows, "main", "main", {"Cloud Engineer", "DevOps / SRE"})
    assert problems == [] and added == 1 and next(p for p in new if p.name == "Bo").course_role == "Cloud Engineer"
    assert next(p for p in new if p.name == "New Person").role == "learner" and len(new) == 4
    assert people.apply_roster(d, [{"Person": "Bo", "Email": "", "CourseRole": "Pilot"}], "main", "main", {"Cloud Engineer"})[1]
    assert people.apply_roster(d, [{"Person": "Sam", "Email": "sam@x.com", "CourseRole": ""}], "main", "main", set())[1]  # other practice
    assert people.parse(people.to_csv(new))[0] == new
    # the Team tab of an owner shows the roster
    people.save(new, tmp_path / "people.csv")
    at = _run(tmp_path, monkeypatch, owners=None, ak_person="Ana", ak_view="manage")  # Management → Team (the owner holds Learning)
    assert not at.exception and any(e.label.startswith("🧑‍🤝‍🧑 Roster and course roles") for e in at.expander)


def test_content_accepts_family_names_and_one_course_role(tmp_path, monkeypatch):
    content, _ = _content_sandbox(tmp_path, monkeypatch)
    data = content.tables()
    data["People"] = [{"Person": "Ana Lopez", "Email": "ana@contoso.com", "Role": "learner", "Families": "AI Security & Governance",
                       "Active": "yes", "CourseRole": "cloud security engineer"},
                      {"Person": "Bo Chen", "Email": "bo@contoso.com", "Role": "champion", "Families": "microsoft 365 security; identity-access-management",
                       "Active": "yes", "CourseRole": ""}]
    data["Roles"] = [{"PackId": "cloud-security", "Role": "Cloud Security Engineer", "Skills": "fundamentals; identity; iam"}]
    data["JobRoles"] = [{"FamilyId": "AI Security & Governance", "RoleId": "cse", "Name": "Cloud Security Engineer", "Description": "", "Active": "yes"}]
    result = content.build(data)
    assert result["problems"] == [], result["problems"][:5]
    by = {p.name: p for p in result["people"]}
    assert by["Ana Lopez"].families == ("ai-security-governance",) and by["Ana Lopez"].course_role == "Cloud Security Engineer"
    assert by["Bo Chen"].families == ("microsoft-365-security", "identity-access-management")
    assert result["notes"] and "in no course role" in result["notes"][0]  # a note, not a problem
    data["People"][1]["CourseRole"] = "Cloud Security Architect"  # not in JobRoles yet: a note, they see every path
    data["People"].append({"Person": "Lopez, Ana", "Email": "ANA@contoso.com", "Role": "learner", "Families": "", "Active": "yes", "CourseRole": ""})
    result = content.build(data)
    assert result["problems"] == [] and any("'Cloud Security Architect' (1 people) is not in JobRoles" in n for n in result["notes"])
    assert any("ana@contoso.com is on several rows" in n for n in result["notes"])
    data["People"][0]["Families"] = "Quantum Security"
    bad = content.build(data)["problems"]
    assert any("unknown role family: Quantum Security" in m and "ai-security-governance" in m for m in bad)


def test_job_role_narrows_the_learning_path(tmp_path, monkeypatch):
    """Practice -> role family -> vendor -> learning path -> skill -> module -> course; the job role (People) picks the paths."""
    from academy import paths as pathmod
    from academy import people
    from academy.catalog import load_materials
    from academy.route import RouteTracker, family_route

    cat = load_catalog(tmp_path / "skills.json") if (tmp_path / "skills.json").exists() else load_catalog()
    mats = load_materials()
    fid = "cyber-defense-security-operations"
    s = pathmod.default(cat, mats)
    assert s.vendors[0].id == "MSFT" and all(p.family in {f.id for f in cat.families} for p in s.paths) and pathmod.validate(s, cat) == []
    base = s.paths_of(fid)
    soc = pathmod.JobRole("soc", fid, "SOC analyst")
    sc200 = pathmod.LearningPath("sc-200", fid, "MSFT", "SC-200 Security Operations Analyst", cert="SC-200", roles=("soc",), order=1)
    sid = cat.in_family(fid)[0].id
    s = pathmod.Structure(s.vendors, [soc, pathmod.JobRole("eng", fid, "Engineer")], s.paths + [sc200], {**s.skills, sid: pathmod.Placement("sc-200", 1)})
    assert "sc-200" in [p.id for p in s.paths_of(fid, "soc")] and "sc-200" not in [p.id for p in s.paths_of(fid, "eng")]
    assert s.role_of(fid, "soc analyst") == soc and s.role_of(fid, "SOC") == soc and s.role_of(fid, "x") is None
    mats[sid] = [{"title": "KQL basics", "url": "https://learn.microsoft.com/kql", "kind": "module", "module": "Query", "order": 1},
                 {"title": "Our runbook", "url": "https://contoso.sharepoint.com/runbook", "kind": "doc", "status": "required", "module": "Operate",
                  "order": 2}]
    route = family_route(cat, mats, s, fid, "soc")
    first = [x for x in route.steps if x.path == "sc-200"]
    assert [(x.module, x.title, x.location) for x in first] == [("Query", "KQL basics", "Vendor site"), ("Operate", "Our runbook", "SharePoint")]
    assert any(p.cert == "SC-200" for p in route.paths) and len(route.paths) == len(base) + 1
    assert pathmod.from_dict(pathmod.to_dict(s)) == s
    # in the app: Ana (SOC analyst of the family) sees her path; no role choice in the sidebar
    pathmod.save(s, tmp_path / "paths.json")
    from academy.catalog import save_materials

    save_materials(mats, tmp_path / "materials.json")
    people.save([people.Person("Ana", "ana@x.com", "learner", (fid,), course_role="SOC analyst")], tmp_path / "people.csv")
    at = _run(tmp_path, monkeypatch, owners=None, ak_person="Ana")
    assert not at.exception and not any(x.label == "Your role" for x in at.selectbox)
    assert any("Your role: **SOC analyst**" in c.value for c in at.caption)
    page = " ".join(m.value for m in at.markdown)
    assert "Your next course" in page and "KQL basics" in page
    assert at.selectbox(key="rt_family").value == fid and at.selectbox(key=f"rt_role_{fid}").value == "soc"
    assert any("SC-200 Security Operations Analyst" in e.label for e in at.expander)
    at.button(key=f"rt_done_{sid}|https://learn.microsoft.com/kql").click().run()
    assert not at.exception and RouteTracker(connect(tmp_path / "app.db"), "Ana").done()


def test_learners_see_their_family_in_study_groups_and_knowledge_exchange(tmp_path):
    from academy import news, rhythm as rh, rhythm_page, study

    cat = load_catalog()
    iam = "identity-access-management"
    sk = next(s for s in cat.skills if s.family == iam)
    assert news.Source("A", "Microsoft", "https://a", families=iam).for_family(iam)
    assert not news.Source("A", "Microsoft", "https://a", families="microsoft-365-security").for_family(iam)
    assert news.Source("A", "Microsoft", "https://a").for_family(iam) and news.Source("A", "x", "https://a", families=iam).for_family(None)
    assert study.Item("V", "https://v", skill_id=sk.id).for_family(iam, cat)  # the family of its skill
    assert not study.Item("V", "https://v", skill_id=sk.id).for_family("microsoft-365-security", cat)
    assert study.Item("V", "https://v").for_family(iam, cat)  # practice-wide
    raw = study.to_csv([study.Item("V", "https://v", families=iam)])
    assert study.parse(raw)[0][0].families == iam and news.parse_sources(news.to_csv([news.Source("A", "x", "https://a", families=iam)]))[0][0].families == iam
    r = rh.Rhythm(connect(tmp_path / "r.db"))
    mine = r.get(r.create(rh.STUDY, "SC-300 group", cert="SC-300", end="2099-01-01", family=iam))
    other = r.get(r.create(rh.STUDY, "MS-102 group", cert="MS-102", end="2099-01-01", family="microsoft-365-security"))
    everyone = r.get(r.create(rh.STUDY, "AZ-500 group", cert="AZ-500", end="2099-01-01"))
    assert [s.title for s in (mine, other, everyone) if rhythm_page._family_ok(s, iam)] == ["SC-300 group", "AZ-500 group"]
    assert rhythm_page._can_manage(mine, "cam", False, {iam}) and not rhythm_page._can_manage(other, "cam", False, {iam})



def test_demand_results_for_each_career_path_lead(tmp_path, monkeypatch):
    from academy import demand, demand_family as dfam
    from academy import paths as pathmod
    from academy.catalog import load_materials
    from academy.practice import load_practice

    cat = load_catalog(ROOT / "catalog" / "skills.json")
    mats = load_materials(ROOT / "catalog" / "materials.json")
    a = demand.analyze(demand.sample_rows(), load_practice(ROOT / "catalog" / "practice.json"), cat, [load_pack("cloud-security")], mats, "en")
    st_ = pathmod.default(cat, mats)
    fam = max(cat.families, key=lambda f: sum(1 for r in a["skills"] if r["_entry"] is not None and r["_entry"].family == f.id))
    res = dfam.results(a, cat, st_, mats, fam.id)
    s = res["summary"]
    assert s["Demanded skills of the family"] == len(res["demand"]) > 0 and s["Gap volume"] == (fam.gap_volume or 0)
    assert s["Covered by your tree"] + s["In your tree without courses"] + s["Not in your tree"] == s["Demanded skills of the family"]
    assert len(res["tree"]) == len(cat.in_family(fam.id)) == s["Skills in your tree"]  # the default tree holds every skill of the family
    assert sum(r["Roles asking for it now"] for r in res["tree"]) > 0
    off = pathmod.Structure(st_.vendors, st_.roles, [pathmod.replace(p, active=False) if p.family == fam.id else p for p in st_.paths], st_.skills)
    assert dfam.results(a, cat, off, mats, fam.id)["summary"]["Covered by your tree"] == 0  # paths switched off: nothing covered
    assert dfam.to_xlsx(res, "test")[:2] == b"PK" and fam.name in dfam.message(res)
    # in the app: the Demand team picks any family and sends it; a champion sees only theirs
    demand.save(demand.sample_rows(), tmp_path / "demand_roles.csv")
    at = _run(tmp_path, monkeypatch, ak_view="demand", dr_family=fam.id)
    assert not at.exception and any(m.label == "Demanded skills of the family" for m in at.metric)
    assert any(getattr(b, "label", "") == "🗂 Every family's results (.zip)" for b in at.get("download_button"))
    data = json.loads(catmod.CATALOG_PATH.read_text(encoding="utf-8"))
    for f in data["families"]:
        if f["id"] == fam.id:
            f["champion"] = "me"
    (tmp_path / "c").mkdir()
    (tmp_path / "c" / "skills.json").write_text(json.dumps(data), encoding="utf-8")
    demand.save(demand.sample_rows(), tmp_path / "c" / "demand_roles.csv")
    lead = _run(tmp_path / "c", monkeypatch, owners=("jefa",), ak_view="demand")
    assert not lead.exception and [x.split(" · ", 1)[1] for x in _tab_labels(lead)] == ["Demand results"]
    assert lead.selectbox(key="dr_family").options == [next(o for o in lead.selectbox(key="dr_family").options)] and len(lead.selectbox(key="dr_family").options) == 1
    assert not any(getattr(b, "label", "") == "🗂 Every family's results (.zip)" for b in lead.get("download_button"))
