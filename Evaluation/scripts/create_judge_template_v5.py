#!/usr/bin/env python3
"""Create answer-level V5 coding sheets from frozen V4 outputs."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


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

CONTEXT_FIELDS = [
    "run_id",
    "parent_benchmark_id",
    "v5_protocol_id",
    "v4_question_number",
    "v5_order",
    "case_id",
    "topic",
    "input_mode",
    "system_id",
    "requested_model",
    "provider_model",
    "question",
    "raw_answer",
    "source_passages_json",
    "reference_answer_danish",
    "critical_elements_json",
    "supporting_elements_json",
    "material_errors_json",
    "acceptable_answer_variants_json",
    "required_qualifications_json",
]

JUDGEMENT_FIELDS = [
    field
    for criterion in CRITERIA
    for field in (f"{criterion}_label", f"{criterion}_reason")
]

OUTPUT_FIELDS = CONTEXT_FIELDS + JUDGEMENT_FIELDS + [
    "judge_type",
    "judge_id",
    "coding_round",
    "overall_notes",
]


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def load_selection(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    selected = [
        row for row in rows if str(row.get("included_in_v5", "")).strip().lower() == "yes"
    ]
    if len(selected) != 10:
        raise ValueError(f"V5 selection must contain exactly 10 included cases, found {len(selected)}")
    if any(not str(row.get("v5_order", "")).strip() for row in selected):
        raise ValueError("Every included V5 case must have a v5_order")
    selected.sort(key=lambda row: int(row["v5_order"]))
    case_ids = [row["case_id"] for row in selected]
    orders = [int(row["v5_order"]) for row in selected]
    if len(set(case_ids)) != len(case_ids) or orders != list(range(1, 11)):
        raise ValueError("V5 case IDs must be unique and v5_order must be 1 through 10")
    return selected


def _expert_fields(case: dict[str, Any]) -> dict[str, Any]:
    reference = case.get("reference", {})
    criteria = reference.get("expert_criteria", {}) if isinstance(reference, dict) else {}
    if not isinstance(criteria, dict):
        criteria = {}
    model_input = case.get("model_input", {})
    passages = model_input.get("source_passages", []) if isinstance(model_input, dict) else []
    return {
        "source_passages_json": json.dumps(passages, ensure_ascii=False),
        "reference_answer_danish": str(criteria.get("reference_answer_danish", "")),
        "critical_elements_json": json.dumps(
            criteria.get("critical_elements", []), ensure_ascii=False
        ),
        "supporting_elements_json": json.dumps(
            criteria.get("supporting_elements", []), ensure_ascii=False
        ),
        "material_errors_json": json.dumps(
            criteria.get("material_errors", []), ensure_ascii=False
        ),
        "acceptable_answer_variants_json": json.dumps(
            criteria.get("acceptable_answer_variants", []), ensure_ascii=False
        ),
        "required_qualifications_json": json.dumps(
            criteria.get("required_qualifications", []), ensure_ascii=False
        ),
    }


def create_judge_rows(
    outputs: Iterable[dict[str, Any]],
    cases_by_id: dict[str, dict[str, Any]],
    selection: list[dict[str, str]],
) -> list[dict[str, Any]]:
    """Return one blank ten-criterion coding row per selected answer."""
    outputs = list(outputs)
    selected_by_id = {row["case_id"]: row for row in selection}
    selected_outputs = [row for row in outputs if row.get("case_id") in selected_by_id]
    keys = [
        (str(row.get("run_id", "")), str(row.get("case_id", "")))
        for row in selected_outputs
    ]
    duplicates = [key for key, count in Counter(keys).items() if count > 1]
    if duplicates:
        raise ValueError(f"Outputs contain duplicate V5 answer keys: {duplicates}")
    run_ids = sorted({str(row.get("run_id", "")) for row in outputs})
    if not run_ids or any(not run_id for run_id in run_ids):
        raise ValueError("Every output must have a non-empty run_id")
    expected_ids = set(selected_by_id)
    for run_id in run_ids:
        actual_ids = {
            str(row.get("case_id", ""))
            for row in selected_outputs
            if str(row.get("run_id", "")) == run_id
        }
        if actual_ids != expected_ids:
            missing = sorted(expected_ids - actual_ids)
            extra = sorted(actual_ids - expected_ids)
            raise ValueError(
                f"Run {run_id} does not contain exactly the V5 subset; "
                f"missing={missing}, extra={extra}"
            )

    rows: list[dict[str, Any]] = []
    for output in selected_outputs:
        if output.get("error"):
            raise ValueError(
                f"Cannot create a judge row for failed output {output.get('case_id')}: "
                f"{output.get('error')}"
            )
        case_id = str(output["case_id"])
        if case_id not in cases_by_id:
            raise ValueError(f"Selected output has no matching testcase: {case_id}")
        case = cases_by_id[case_id]
        selected = selected_by_id[case_id]
        model_input = case.get("model_input", {})
        row: dict[str, Any] = {
            "run_id": output.get("run_id", ""),
            "parent_benchmark_id": case.get("benchmark_id", ""),
            "v5_protocol_id": "XSU-JUDGE-PILOT-V5",
            "v4_question_number": selected.get("v4_question_number", ""),
            "v5_order": selected.get("v5_order", ""),
            "case_id": case_id,
            "topic": case.get("topic", ""),
            "input_mode": output.get("input_mode", ""),
            "system_id": output.get("system_id", ""),
            "requested_model": output.get("requested_model", ""),
            "provider_model": output.get("provider_model", ""),
            "question": (
                model_input.get("question", case.get("question", ""))
                if isinstance(model_input, dict)
                else case.get("question", "")
            ),
            "raw_answer": output.get("content", ""),
            **_expert_fields(case),
            **{field: "" for field in JUDGEMENT_FIELDS},
            "judge_type": "",
            "judge_id": "",
            "coding_round": "",
            "overall_notes": "",
        }
        rows.append(row)
    return sorted(rows, key=lambda row: (str(row["run_id"]), int(row["v5_order"])))


def write_csv(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Create blank V5 ten-criterion judge rows.")
    parser.add_argument("--outputs", required=True, type=Path)
    parser.add_argument("--testcases", required=True, type=Path)
    parser.add_argument("--selection", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    cases = {row["case_id"]: row for row in load_jsonl(args.testcases)}
    rows = create_judge_rows(
        load_jsonl(args.outputs), cases, load_selection(args.selection)
    )
    write_csv(args.out, rows)
    print(f"Wrote {args.out} ({len(rows)} selected answer rows)")


if __name__ == "__main__":
    main()
