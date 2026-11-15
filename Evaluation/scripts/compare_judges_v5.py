#!/usr/bin/env python3
"""Compare human and LLM V5 answer-level coding sheets."""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path
from typing import Any

try:
    from .create_judge_template_v5 import CRITERIA
except ImportError:  # pragma: no cover - direct script execution
    from create_judge_template_v5 import CRITERIA


ALLOWED_LABELS = {"met", "not_met", "not_assessable"}
OUTPUT_FIELDS = [
    "criterion",
    "eligible_item_count",
    "paired_item_count",
    "missing_or_invalid_pair_count",
    "agreement_count",
    "disagreement_count",
    "raw_agreement_pct",
    "cohen_kappa",
    "kappa_status",
]


def _normalise(value: Any) -> str:
    return str(value or "").strip().lower()


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def item_key(row: dict[str, str]) -> tuple[str, str, str]:
    return (
        str(row.get("run_id", "")).strip(),
        str(row.get("case_id", "")).strip(),
        _normalise(row.get("input_mode")),
    )


def _indexed(rows: list[dict[str, str]]) -> dict[tuple[str, str, str], dict[str, str]]:
    keys = [item_key(row) for row in rows]
    duplicates = [key for key, count in Counter(keys).items() if count > 1]
    if duplicates:
        raise ValueError(f"Coding sheet contains duplicate answer keys: {duplicates}")
    return {item_key(row): row for row in rows}


def _cohen_kappa(first: list[str], second: list[str]) -> tuple[float | str, str]:
    if not first:
        return "", "not_estimable_no_pairs"
    observed = sum(a == b for a, b in zip(first, second, strict=True)) / len(first)
    first_counts = Counter(first)
    second_counts = Counter(second)
    labels = set(first_counts) | set(second_counts)
    expected = sum(
        (first_counts[label] / len(first)) * (second_counts[label] / len(second))
        for label in labels
    )
    if expected >= 1.0:
        return "", "not_estimable_no_category_variation"
    return round((observed - expected) / (1 - expected), 3), "estimated"


def compare(
    human_rows: list[dict[str, str]], llm_rows: list[dict[str, str]]
) -> list[dict[str, Any]]:
    human = _indexed(human_rows)
    llm = _indexed(llm_rows)
    answer_keys = sorted(set(human) | set(llm))
    results: list[dict[str, Any]] = []
    all_human: list[str] = []
    all_llm: list[str] = []
    all_missing = 0

    for criterion in CRITERIA:
        field = f"{criterion}_label"
        human_values: list[str] = []
        llm_values: list[str] = []
        missing = 0
        for key in answer_keys:
            human_value = _normalise(human.get(key, {}).get(field))
            llm_value = _normalise(llm.get(key, {}).get(field))
            if human_value not in ALLOWED_LABELS or llm_value not in ALLOWED_LABELS:
                missing += 1
                continue
            human_values.append(human_value)
            llm_values.append(llm_value)
        agreement = sum(
            first == second for first, second in zip(human_values, llm_values, strict=True)
        )
        paired = len(human_values)
        kappa, status = _cohen_kappa(human_values, llm_values)
        results.append(
            {
                "criterion": criterion,
                "eligible_item_count": len(answer_keys),
                "paired_item_count": paired,
                "missing_or_invalid_pair_count": missing,
                "agreement_count": agreement,
                "disagreement_count": paired - agreement,
                "raw_agreement_pct": round(100 * agreement / paired, 1) if paired else "",
                "cohen_kappa": kappa,
                "kappa_status": status,
            }
        )
        all_human.extend(human_values)
        all_llm.extend(llm_values)
        all_missing += missing

    all_agreement = sum(
        first == second for first, second in zip(all_human, all_llm, strict=True)
    )
    all_paired = len(all_human)
    all_kappa, all_status = _cohen_kappa(all_human, all_llm)
    results.append(
        {
            "criterion": "all_criteria",
            "eligible_item_count": len(answer_keys) * len(CRITERIA),
            "paired_item_count": all_paired,
            "missing_or_invalid_pair_count": all_missing,
            "agreement_count": all_agreement,
            "disagreement_count": all_paired - all_agreement,
            "raw_agreement_pct": (
                round(100 * all_agreement / all_paired, 1) if all_paired else ""
            ),
            "cohen_kappa": all_kappa,
            "kappa_status": all_status,
        }
    )
    return results


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare human and LLM V5 coding.")
    parser.add_argument("--human", required=True, type=Path)
    parser.add_argument("--llm", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    results = compare(load_rows(args.human), load_rows(args.llm))
    write_csv(args.out, results)
    missing = results[-1]["missing_or_invalid_pair_count"]
    print(f"Wrote {args.out} ({missing} missing or invalid criterion pairs)")


if __name__ == "__main__":
    main()
