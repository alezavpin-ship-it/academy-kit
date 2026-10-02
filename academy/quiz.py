"""Quiz helpers: stable option shuffling and glossary questions (pure functions)."""

from __future__ import annotations

import hashlib
import random


def _seed(key: str) -> int:
    return int(hashlib.sha1(key.encode("utf-8")).hexdigest()[:8], 16)


def shuffled(key: str, options: list[str], correct: int) -> tuple[list[str], int]:
    """Options in a stable pseudo-random order (the same on every refresh). Returns (options, index of the right one)."""
    order = list(range(len(options)))
    random.Random(_seed(key)).shuffle(order)
    return [options[i] for i in order], order.index(correct)


def glossary_question(glossary: list[dict], rng: random.Random) -> dict:
    """Term → definition or definition → term, with 3 distractors (same category first)."""
    g = rng.choice(glossary)
    same = [x for x in glossary if x["category"] == g["category"] and x["term"] != g["term"]]
    others = [x for x in glossary if x["category"] != g["category"]]
    pool = rng.sample(same, min(3, len(same)))
    pool += rng.sample(others, 3 - len(pool))
    to_def = rng.random() < 0.5
    if to_def:
        prompt = f"¿Qué significa **{g['term']}**?"
        opts = [g["definition"]] + [x["definition"] for x in pool]
    else:
        prompt = f"¿Qué término corresponde a: _{g['definition']}_?"
        opts = [g["term"]] + [x["term"] for x in pool]
    order = list(range(4))
    rng.shuffle(order)
    return {"prompt": prompt, "options": [opts[i] for i in order], "correct": order.index(0), "term": g["term"],
            "category": g["category"], "explanation": f"**{g['term']}**: {g['definition']}"}
