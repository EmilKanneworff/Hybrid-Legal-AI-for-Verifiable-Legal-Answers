"""Recompute the numbers reported in the thesis from the saved label files.

Run from the repository root:

    python3 Evaluation/scripts/check_thesis_numbers.py

Only the Python standard library is used, so no virtual environment is needed.
Each line prints OK or MISMATCH, followed by the place in the thesis where the
number is reported. The script exits with code 1 if anything does not match.

Terms: the thesis says "without source", "with correct source" and "my own RAG
system". The files say closed_book, gold_context and self_retrieval. The thesis
says "correct and complete" for answers where C01 and C02 are both Met. The
review tool and its CSV exports call the same thing "Legally adequate".
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REVIEW = ROOT / "Evaluation" / "outputs" / "v5_review"
RUNS = ROOT / "Evaluation" / "outputs" / "final_v5"

CRITERIA = [
    "c01_overall_legal_correctness",
    "c02_required_elements_complete",
    "c03_direct_relevance",
    "c04_source_traceability",
    "c05_source_validity",
    "c06_claim_source_support",
    "c07_no_unsupported_legal_additions",
    "c08_qualifications_and_exceptions",
    "c09_reasoning_coherence",
    "c10_legal_modality_precision",
]
JUDGEMENT = [c for c in CRITERIA if c[:3] in {"c01", "c02", "c03", "c07", "c08", "c09", "c10"}]
SOURCE = [c for c in CRITERIA if c[:3] in {"c04", "c05", "c06"}]

# The five blocks in the order of Table 6.2 in the thesis.
BLOCKS = [
    ("Llama, without source", "Llama", "closed_book"),
    ("GPT-6-luna, without source", "gpt-6-luna", "closed_book"),
    ("Llama, with correct source", "Llama", "gold_context"),
    ("GPT-6-luna, with correct source", "gpt-6-luna", "gold_context"),
    ("My own RAG system", "Own RAG system", "self_retrieval"),
]

failures = 0


def check(label: str, found, expected, where: str) -> None:
    global failures
    ok = found == expected
    if not ok:
        failures += 1
    status = "OK      " if ok else "MISMATCH"
    extra = "" if ok else f" (expected {expected})"
    print(f"{status} {label}: {found}{extra}  [{where}]")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def block_of(row: dict[str, str]) -> str | None:
    for name, model, mode in BLOCKS:
        if row["input_mode"] == mode and row["model"].startswith(model):
            return name
    return None


def met(row: dict[str, str], criterion: str) -> bool:
    return row[f"{criterion}_label"] == "met"


def kappa(first: list[str], second: list[str]) -> float:
    """Cohen's kappa, computed as in Evaluation/scripts/compare_judges_v5.py."""
    observed = sum(a == b for a, b in zip(first, second)) / len(first)
    c1, c2 = Counter(first), Counter(second)
    expected = sum((c1[x] / len(first)) * (c2[x] / len(second)) for x in set(c1) | set(c2))
    return round((observed - expected) / (1 - expected), 2)


# --- The legal reviewer's labels -------------------------------------------
human = [r for r in read_csv(REVIEW / "simple_reviews.csv") if r["reviewer"] == "human"]
by_block: dict[str, list[dict[str, str]]] = {name: [] for name, _, _ in BLOCKS}
for row in human:
    by_block[block_of(row)].append(row)

print("The legal reviewer (Evaluation/outputs/v5_review/simple_reviews.csv)")
check("answers assessed", len(human), 70, "Chapter 6")
check(
    "decisions",
    sum(1 for r in human for c in CRITERIA if r[f"{c}_label"]),
    700,
    "Chapter 6, Section 6.3",
)
check("answers per block", [len(by_block[n]) for n, _, _ in BLOCKS], [14] * 5, "Table 6.2")

table_6_2 = {
    "c01_overall_legal_correctness": [1, 3, 12, 14, 10],
    "c02_required_elements_complete": [0, 2, 7, 12, 4],
    "c08_qualifications_and_exceptions": [5, 9, 6, 13, 8],
    "c10_legal_modality_precision": [6, 6, 11, 13, 9],
    "c04_source_traceability": [0, 0, 0, 1, 14],
    "c05_source_validity": [0, 0, 0, 1, 13],
    "c06_claim_source_support": [0, 0, 0, 1, 6],
    "c07_no_unsupported_legal_additions": [1, 4, 13, 14, 8],
    "c03_direct_relevance": [13, 14, 14, 14, 13],
    "c09_reasoning_coherence": [13, 14, 14, 14, 13],
}
for criterion, expected in table_6_2.items():
    found = [sum(met(r, criterion) for r in by_block[n]) for n, _, _ in BLOCKS]
    check(f"Met for {criterion.upper()[:3]}", found, expected, "Table 6.2")

correct_complete = [
    sum(met(r, CRITERIA[0]) and met(r, CRITERIA[1]) for r in by_block[n]) for n, _, _ in BLOCKS
]
check("correct and complete per block", correct_complete, [0, 1, 6, 12, 4], "Table 6.2, Figure 6.4")
check("correct and complete without source", f"{correct_complete[0] + correct_complete[1]} of 28", "1 of 28", "Chapters 6 and 9")
check("correct and complete with correct source", f"{correct_complete[2] + correct_complete[3]} of 28", "18 of 28", "Chapters 6 and 9")
check("correct and complete, my own RAG system", f"{correct_complete[4]} of 14", "4 of 14", "Chapters 6, 7 and 9")


def magesh(rows: list[dict[str, str]]) -> list[int]:
    """Correct with source, correct without a shown source, wrong or unsupported."""
    accurate = incomplete = hallucinated = 0
    for r in rows:
        if met(r, CRITERIA[0]) and met(r, "c06_claim_source_support"):
            accurate += 1
        elif not met(r, CRITERIA[0]) or (met(r, "c04_source_traceability") and not met(r, "c06_claim_source_support")):
            hallucinated += 1
        else:
            incomplete += 1
    return [accurate, incomplete, hallucinated]


check("Magesh typology, without source", magesh(by_block[BLOCKS[0][0]] + by_block[BLOCKS[1][0]]), [0, 4, 24], "Figure 8.1")
check("Magesh typology, with correct source", magesh(by_block[BLOCKS[2][0]] + by_block[BLOCKS[3][0]]), [1, 25, 2], "Figure 8.1")
check("Magesh typology, my own RAG system", magesh(by_block[BLOCKS[4][0]]), [6, 0, 8], "Figure 8.1")

first_entry = {(r["run_id"], r["case_id"]): r for r in read_csv(REVIEW / "simple_reviews_before_source_rule_2026-11-05.csv")}
changed = [
    c
    for key, old in first_entry.items()
    for c in CRITERIA
    if key in {(r["run_id"], r["case_id"]) for r in human}
    and old[f"{c}_label"] != next(r for r in human if (r["run_id"], r["case_id"]) == key)[f"{c}_label"]
]
check("source labels changed once the source rule was clear", (len(changed), all(c in SOURCE for c in changed)), (3, True), "Chapter 6, Section 6.3")

# --- The LLM judge -----------------------------------------------------------
JUDGE = ROOT / "Evaluation" / "outputs" / "v5_judge_c04_aligned"
judge = read_csv(JUDGE / "ai_review_c04_aligned.csv")
print("\nThe LLM judge (Evaluation/outputs/v5_judge_c04_aligned/ai_review_c04_aligned.csv)")
check("judge assessments (70 answers, three runs)", len(judge), 210, "Chapter 6, Appendix D")
check("judge decisions", sum(1 for r in judge for c in CRITERIA if r[f"{c}_label"]), 2100, "70 answers x 10 criteria x 3 runs")
run1 = {(r["run_id"], r["case_id"]): r for r in judge if r["repeat"] == "1"}


def agreement(rows: list[dict[str, str]], criteria: list[str]):
    h, j = [], []
    for r in rows:
        other = run1[(r["run_id"], r["case_id"])]
        for c in criteria:
            h.append(r[f"{c}_label"])
            j.append(other[f"{c}_label"])
    same = sum(a == b for a, b in zip(h, j))
    stricter = sum(b == "not_met" and a != "not_met" for a, b in zip(h, j))
    return same, len(h), kappa(h, j), stricter


first_56 = [r for r in human if r["input_mode"] in {"closed_book", "gold_context"}]
own_14 = by_block[BLOCKS[4][0]]
for name, rows, crit, expected, where in [
    ("56 answers, seven judgement criteria", first_56, JUDGEMENT, ("310 of 392", 79.1, 0.59), "Chapters 6 and 9, Appendix E"),
    ("56 answers, three source criteria", first_56, SOURCE, ("164 of 168", 97.6, 0.95), "Chapter 6, Appendix E"),
    ("my own RAG system, seven judgement criteria", own_14, JUDGEMENT, ("68 of 98", 69.4, 0.43), "Chapters 6 and 8"),
    ("my own RAG system, three source criteria", own_14, SOURCE, ("31 of 42", 73.8, 0.46), "Chapter 6"),
]:
    same, total, k, _ = agreement(rows, crit)
    check(f"agreement, {name}", (f"{same} of {total}", round(100 * same / total, 1), k), expected, where)

same, total, _, stricter = agreement(first_56, CRITERIA)
check("judge stricter, 56 answers", f"{stricter} of {total - same} disagreements", "83 of 86 disagreements", "Chapter 6")
same, total, _, stricter = agreement(own_14, CRITERIA)
check("judge stricter, my own RAG system", f"{stricter} of {total - same} disagreements", "39 of 41 disagreements", "Chapter 6")

# --- Fingerprints of the five answer runs -----------------------------------
print("\nThe five answer runs (Evaluation/outputs/final_v5)")
runs = sorted(RUNS.glob("*/run_metadata.json"))
check("answer runs", len(runs), 5, "Chapter 6")
for meta_path in runs:
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    digest = hashlib.sha256((meta_path.parent / "outputs.jsonl").read_bytes()).hexdigest()
    check(f"SHA-256 of {meta_path.parent.name[:48]}", digest == meta["outputs_sha256"], True, "Chapter 6, Section 6.3")

print()
print("All numbers match the thesis." if failures == 0 else f"{failures} number(s) do not match.")
sys.exit(1 if failures else 0)
