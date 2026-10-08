"""Check a content pack against the methodology rules.

    python tools/validate_pack.py packs/cloud-security
    python tools/validate_pack.py --all
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from academy.catalog import load_catalog, validate_catalog  # noqa: E402
from academy.exam import available_exams, load_exam, validate_exam  # noqa: E402
from academy.pack import available_packs, load_pack, validate  # noqa: E402


def check(path: str) -> bool:
    pack = load_pack(path)
    cat = load_catalog()
    errs = validate(pack, cat) + ([f"[catalog] {e}" for e in validate_catalog(cat)] if cat else [])
    n_vid = sum(r.kind != "link" for r in pack.resources.values())
    print(f"\n{pack.title} ({pack.id}) — {len(pack.lessons)} lessons, {len(pack.glossary)} terms, "
          f"{len(pack.resources)} resources ({n_vid} videos)")
    for e in errs:
        print("  ✗", e)
    print("  ✓ valid" if not errs else f"  {len(errs)} problem(s)")
    return not errs


def check_exam(name: str) -> bool:
    exam = load_exam(name)
    errs = validate_exam(exam, load_catalog())
    print(f"\n{exam.name} ({exam.id}) — {len(exam.modules)} modules, {len(exam.questions)} questions, {len(exam.exercises())} exercises")
    for e in errs:
        print("  ✗", e)
    print("  ✓ valid" if not errs else f"  {len(errs)} problem(s)")
    return not errs


if __name__ == "__main__":
    args = sys.argv[1:]
    targets = available_packs() if (not args or args == ["--all"]) else args
    ok = [check(t) for t in targets] + ([check_exam(e) for e in available_exams()] if (not args or args == ["--all"]) else [])
    sys.exit(0 if all(ok) else 1)
