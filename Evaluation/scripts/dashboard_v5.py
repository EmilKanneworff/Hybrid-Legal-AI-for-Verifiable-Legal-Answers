#!/usr/bin/env python3
"""Pure data helpers for the simple V5 review dashboard."""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font
from openpyxl.worksheet.datavalidation import DataValidation

try:
    from .create_judge_template_v5 import (
        CONTEXT_FIELDS,
        CRITERIA,
        JUDGEMENT_FIELDS,
    )
except ImportError:  # pragma: no cover - direct script execution
    from create_judge_template_v5 import CONTEXT_FIELDS, CRITERIA, JUDGEMENT_FIELDS


ALLOWED_REVIEW_LABELS = {"met", "not_met", "not_assessable"}
ALLOWED_COVERAGE_LABELS = {"yes", "partial", "no"}
HUMAN_REVIEW_FIELDS = CONTEXT_FIELDS + JUDGEMENT_FIELDS + [
    "judge_type",
    "judge_id",
    "coding_round",
    "overall_notes",
    "review_date",
    "xhaile_coverage_json",
    "send_to_legal_reviewer",
    "legal_reviewer_note",
]
AI_REVIEW_FIELDS = HUMAN_REVIEW_FIELDS + [
    "repeat",
    "model_id",
    "prompt_hash",
    "judged_at",
    "attempts",
    "xhaile_coverage_reasons_json",
    "raw_response_file",
]
LABELS_DA = {
    "met": "Opfyldt",
    "not_met": "Ikke opfyldt",
    "not_assessable": "Kan ikke vurderes",
}
COVERAGE_DA = {"yes": "Ja", "partial": "Delvist", "no": "Nej"}
CRITERION_IDS = {
    criterion: f"C{index:02d}" for index, criterion in enumerate(CRITERIA, start=1)
}


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def list_saved_runs(roots: Iterable[Path]) -> list[Path]:
    """Return run folders with outputs, newest folder name first."""
    runs: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        runs.extend(
            path
            for path in root.iterdir()
            if path.is_dir() and (path / "outputs.jsonl").is_file()
        )
    return sorted(runs, key=lambda path: path.name, reverse=True)


def saved_run_label(run_dir: Path) -> str:
    generation = run_dir.parent.name.replace("final_", "").upper()
    return f"{generation} · {run_dir.name}"


def load_saved_run(run_dir: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Load one immutable answer run and attach its recorded run ID."""
    output_path = run_dir / "outputs.jsonl"
    metadata_path = run_dir / "run_metadata.json"
    if not output_path.is_file():
        raise ValueError(f"Kørslen mangler outputs.jsonl: {run_dir}")
    metadata = (
        json.loads(metadata_path.read_text(encoding="utf-8"))
        if metadata_path.is_file()
        else {}
    )
    run_id = str(metadata.get("run_id") or run_dir.name)
    outputs = load_jsonl(output_path)
    for output in outputs:
        output.setdefault("run_id", run_id)
    if not outputs:
        raise ValueError(f"Kørslen indeholder ingen svar: {run_dir}")
    return outputs, metadata


def selected_case_ids(
    selected_case_id: str, run_all: bool, available_case_ids: Iterable[str]
) -> list[str]:
    ids = list(available_case_ids)
    if selected_case_id not in ids:
        raise ValueError(f"Ukendt spørgsmål: {selected_case_id}")
    return ids if run_all else [selected_case_id]


def load_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def parse_answer_claims(content: str) -> list[dict[str, str]]:
    """Parse the answer contract without depending on Streamlit."""
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError("AI-svaret er ikke gyldig JSON.") from exc
    claims = parsed.get("legal_claims") if isinstance(parsed, dict) else None
    if not isinstance(claims, list):
        raise ValueError("AI-svaret mangler listen legal_claims.")
    result: list[dict[str, str]] = []
    for item in claims:
        if not isinstance(item, dict) or not str(item.get("claim", "")).strip():
            raise ValueError("AI-svaret indeholder en ugyldig påstand.")
        result.append(
            {
                "claim": str(item["claim"]).strip(),
                "source_locator": str(item.get("source_locator", "")).strip(),
            }
        )
    return result


def automatic_source_label(status: str) -> str:
    if status in {"benchmark_source", "official_direct", "official_framework"}:
        return "Kilde fundet"
    if status == "missing":
        return "Ingen kilde angivet"
    return "Kilde ikke fundet automatisk"


def load_gold_determinations(path: Path) -> dict[str, dict[str, Any]]:
    rows = load_jsonl(path)
    return {str(row["determination_id"]): row for row in rows}


def load_expert_rubrics(path: Path) -> dict[str, dict[str, Any]]:
    rows = load_csv_rows(path)
    result: dict[str, dict[str, Any]] = {}
    json_fields = (
        "critical_elements_json",
        "supporting_elements_json",
        "material_errors_json",
        "acceptable_answer_variants_json",
        "required_qualifications_json",
    )
    for row in rows:
        parsed: dict[str, Any] = dict(row)
        for field in json_fields:
            parsed[field] = json.loads(str(row.get(field) or "[]"))
        result[str(row["case_id"])] = parsed
    return result


def expected_source_bundle(
    case: dict[str, Any],
    gold_by_id: dict[str, dict[str, Any]],
    rubrics_by_case: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    case_id = str(case["case_id"])
    ids = [str(value) for value in case["reference"]["determination_ids"]]
    missing = [value for value in ids if value not in gold_by_id]
    if missing:
        raise ValueError(f"XHAILe-punkter mangler i gold-filen: {', '.join(missing)}")
    if case_id not in rubrics_by_case:
        raise ValueError(f"Ekspertrubrik mangler for {case_id}")
    rubric = rubrics_by_case[case_id]
    return {
        "determinations": [gold_by_id[value] for value in ids],
        "passages": list(case["model_input"].get("source_passages", [])),
        "reference_answer_danish": str(rubric.get("reference_answer_danish", "")),
        "critical_elements": list(rubric["critical_elements_json"]),
        "material_errors": list(rubric["material_errors_json"]),
        "acceptable_answer_variants": list(rubric["acceptable_answer_variants_json"]),
        "required_qualifications": list(rubric["required_qualifications_json"]),
    }


def human_review_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("run_id", "")),
        str(row.get("case_id", "")),
        str(row.get("input_mode", "")),
    )


def find_human_review(
    rows: Iterable[dict[str, Any]], run_id: str, case_id: str, input_mode: str
) -> dict[str, Any] | None:
    wanted = (run_id, case_id, input_mode)
    return next((row for row in rows if human_review_key(row) == wanted), None)


def build_human_review_row(
    case: dict[str, Any],
    output: dict[str, Any],
    rubric: dict[str, Any],
    decisions: dict[str, dict[str, str]],
    coverage: dict[str, str],
    coder: str,
    review_date: str,
    send_to_legal_reviewer: bool,
    legal_reviewer_note: str,
) -> dict[str, Any]:
    """Validate and build one answer-level human V5 review row."""
    missing_criteria = [criterion for criterion in CRITERIA if criterion not in decisions]
    if missing_criteria:
        raise ValueError(f"Vurderingen mangler kriterier: {', '.join(missing_criteria)}")
    judgement: dict[str, str] = {}
    for criterion in CRITERIA:
        label = str(decisions[criterion].get("label", "")).strip()
        reason = str(decisions[criterion].get("reason", "")).strip()
        if label not in ALLOWED_REVIEW_LABELS:
            raise ValueError(f"Ugyldig vurdering for {criterion}: {label}")
        if not reason:
            raise ValueError(f"Skriv en kort begrundelse for {criterion.upper()[:3]}")
        judgement[f"{criterion}_label"] = label
        judgement[f"{criterion}_reason"] = reason

    determination_ids = [
        str(value) for value in case.get("reference", {}).get("determination_ids", [])
    ]
    if set(coverage) != set(determination_ids):
        raise ValueError("XHAILe-dækningen skal udfyldes for alle punkter")
    invalid_coverage = sorted(
        value for value in coverage.values() if value not in ALLOWED_COVERAGE_LABELS
    )
    if invalid_coverage:
        raise ValueError(f"Ugyldig XHAILe-dækning: {', '.join(invalid_coverage)}")
    if not coder.strip():
        raise ValueError("Skriv dit navn eller dine initialer")
    if not review_date.strip():
        raise ValueError("Vælg en dato")

    model_input = case.get("model_input", {})
    row: dict[str, Any] = {
        "run_id": str(output.get("run_id", "")),
        "parent_benchmark_id": str(case.get("benchmark_id", "")),
        "v5_protocol_id": "XSU-JUDGE-PILOT-V5",
        "v4_question_number": "",
        "v5_order": "",
        "case_id": str(case.get("case_id", "")),
        "topic": str(case.get("topic", "")),
        "input_mode": str(output.get("input_mode", "")),
        "system_id": str(output.get("system_id", "")),
        "requested_model": str(output.get("requested_model", "")),
        "provider_model": str(output.get("provider_model", "")),
        "question": str(model_input.get("question", case.get("question", ""))),
        "raw_answer": str(output.get("content", "")),
        "source_passages_json": json.dumps(
            model_input.get("source_passages", []), ensure_ascii=False
        ),
        "reference_answer_danish": str(rubric.get("reference_answer_danish", "")),
        "critical_elements_json": json.dumps(
            rubric.get("critical_elements_json", []), ensure_ascii=False
        ),
        "supporting_elements_json": json.dumps(
            rubric.get("supporting_elements_json", []), ensure_ascii=False
        ),
        "material_errors_json": json.dumps(
            rubric.get("material_errors_json", []), ensure_ascii=False
        ),
        "acceptable_answer_variants_json": json.dumps(
            rubric.get("acceptable_answer_variants_json", []), ensure_ascii=False
        ),
        "required_qualifications_json": json.dumps(
            rubric.get("required_qualifications_json", []), ensure_ascii=False
        ),
        **judgement,
        "judge_type": "human",
        "judge_id": coder.strip(),
        "coding_round": "independent",
        "overall_notes": legal_reviewer_note.strip(),
        "review_date": review_date.strip(),
        "xhaile_coverage_json": json.dumps(coverage, ensure_ascii=False, sort_keys=True),
        "send_to_legal_reviewer": "yes" if send_to_legal_reviewer else "no",
        "legal_reviewer_note": legal_reviewer_note.strip(),
    }
    if not all(human_review_key(row)):
        raise ValueError("Kørsels-id, spørgsmål og testmetode skal være udfyldt")
    return row


def save_human_review(path: Path, review: dict[str, Any]) -> list[dict[str, str]]:
    """Insert or replace one review without changing reviews of other answers."""
    rows = load_csv_rows(path)
    key = human_review_key(review)
    rows = [row for row in rows if human_review_key(row) != key]
    rows.append({field: str(review.get(field, "")) for field in HUMAN_REVIEW_FIELDS})
    rows.sort(key=human_review_key)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=HUMAN_REVIEW_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return rows


def load_coverage(review: dict[str, Any] | None) -> dict[str, str]:
    if not review or not str(review.get("xhaile_coverage_json", "")).strip():
        return {}
    parsed = json.loads(str(review["xhaile_coverage_json"]))
    if not isinstance(parsed, dict):
        raise ValueError("Den gemte XHAILe-dækning er ugyldig")
    return {str(key): str(value) for key, value in parsed.items()}


def ai_review_key(row: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        *human_review_key(row),
        str(row.get("repeat") or row.get("coding_round", "")),
    )


def find_ai_review(
    rows: Iterable[dict[str, Any]],
    run_id: str,
    case_id: str,
    input_mode: str,
    repeat: int,
) -> dict[str, Any] | None:
    wanted = (run_id, case_id, input_mode, str(repeat))
    return next((row for row in rows if ai_review_key(row) == wanted), None)


def build_ai_review_row(
    case: dict[str, Any],
    output: dict[str, Any],
    rubric: dict[str, Any],
    result: dict[str, Any],
    raw_response_file: str,
) -> dict[str, Any]:
    coverage_decisions = result.get("xhaile_coverage", {})
    coverage = {
        str(key): str(value.get("label", ""))
        for key, value in coverage_decisions.items()
    }
    base = build_human_review_row(
        case,
        output,
        rubric,
        result.get("criteria", {}),
        coverage,
        str(result.get("model_id", "")),
        str(result.get("judged_at", ""))[:10],
        False,
        "",
    )
    base.update(
        {
            "judge_type": "llm",
            "judge_id": str(result.get("model_id", "")),
            "coding_round": str(result.get("repeat", "")),
            "overall_notes": str(result.get("overall_notes", "")),
            "repeat": str(result.get("repeat", "")),
            "model_id": str(result.get("model_id", "")),
            "prompt_hash": str(result.get("prompt_hash", "")),
            "judged_at": str(result.get("judged_at", "")),
            "attempts": str(result.get("attempts", "")),
            "xhaile_coverage_reasons_json": json.dumps(
                {
                    str(key): str(value.get("reason", ""))
                    for key, value in coverage_decisions.items()
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            "raw_response_file": raw_response_file,
        }
    )
    return base


def save_ai_review(path: Path, review: dict[str, Any]) -> list[dict[str, str]]:
    rows = load_csv_rows(path)
    key = ai_review_key(review)
    rows = [row for row in rows if ai_review_key(row) != key]
    rows.append({field: str(review.get(field, "")) for field in AI_REVIEW_FIELDS})
    rows.sort(key=ai_review_key)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=AI_REVIEW_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return rows


def save_raw_ai_response(
    raw_dir: Path, output: dict[str, Any], result: dict[str, Any]
) -> Path:
    safe_parts = [
        "".join(character if character.isalnum() else "_" for character in value)
        for value in (
            str(output.get("run_id", "run")),
            str(output.get("case_id", "case")),
            str(output.get("input_mode", "mode")),
        )
    ]
    filename = "_".join(safe_parts) + f"_repeat_{result.get('repeat', '')}.json"
    path = raw_dir / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(result.get("raw_response", {}), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def _unique_review_index(
    rows: Iterable[dict[str, Any]],
) -> dict[tuple[str, str, str], dict[str, Any]]:
    result: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        key = human_review_key(row)
        if key in result:
            raise ValueError(f"Flere vurderinger har samme svarnøgle: {key}")
        result[key] = row
    return result


def _comparison_cell(human_label: str, ai_label: str) -> str:
    if not human_label:
        return "Menneske: — | AI: —"
    human_display = LABELS_DA.get(human_label, human_label)
    if not ai_label:
        return f"Menneske: {human_display} | AI: —"
    ai_display = LABELS_DA.get(ai_label, ai_label)
    status = "Enig" if human_label == ai_label else "Uenig"
    return f"Menneske: {human_display} | AI: {ai_display} | {status}"


def build_criteria_matrix(
    outputs: Iterable[dict[str, Any]],
    cases_by_id: dict[str, dict[str, Any]],
    human_rows: Iterable[dict[str, Any]],
    ai_rows: Iterable[dict[str, Any]],
) -> list[dict[str, str]]:
    human = _unique_review_index(human_rows)
    ai = _unique_review_index(ai_rows)
    matrix: list[dict[str, str]] = []
    for output in outputs:
        key = human_review_key(output)
        case = cases_by_id[str(output["case_id"])]
        row = {"Spørgsmål": str(case.get("topic") or case["model_input"]["question"])}
        for criterion in CRITERIA:
            human_label = str(human.get(key, {}).get(f"{criterion}_label", ""))
            ai_label = str(ai.get(key, {}).get(f"{criterion}_label", ""))
            row[CRITERION_IDS[criterion]] = _comparison_cell(human_label, ai_label)
        matrix.append(row)
    return matrix


def build_coverage_comparison(
    outputs: Iterable[dict[str, Any]],
    cases_by_id: dict[str, dict[str, Any]],
    human_rows: Iterable[dict[str, Any]],
    ai_rows: Iterable[dict[str, Any]],
) -> list[dict[str, str]]:
    human = _unique_review_index(human_rows)
    ai = _unique_review_index(ai_rows)
    rows: list[dict[str, str]] = []
    for output in outputs:
        key = human_review_key(output)
        case = cases_by_id[str(output["case_id"])]
        human_coverage = load_coverage(human.get(key))
        ai_coverage = load_coverage(ai.get(key)) if key in human else {}
        for determination_id in case.get("reference", {}).get(
            "determination_ids", []
        ):
            determination_id = str(determination_id)
            human_value = human_coverage.get(determination_id, "")
            ai_value = ai_coverage.get(determination_id, "")
            status = ""
            if human_value and ai_value:
                status = "Enig" if human_value == ai_value else "Uenig"
            rows.append(
                {
                    "Spørgsmål": str(
                        case.get("topic") or case["model_input"]["question"]
                    ),
                    "XHAILe-punkt": determination_id,
                    "Menneske": COVERAGE_DA.get(human_value, "—"),
                    "AI": COVERAGE_DA.get(ai_value, "—") if human_value else "—",
                    "Sammenligning": status or "—",
                }
            )
    return rows


def _expected_source_text(
    case: dict[str, Any],
    rubric: dict[str, Any],
    gold_by_id: dict[str, dict[str, Any]],
) -> str:
    determination_lines = [
        f"{determination_id}: {gold_by_id.get(str(determination_id), {}).get('label', '')}"
        for determination_id in case.get("reference", {}).get("determination_ids", [])
    ]
    passage_lines = [
        f"{passage.get('citation_label', '')}\n{passage.get('text', '')}"
        for passage in case.get("model_input", {}).get("source_passages", [])
    ]
    return (
        "XHAILe-punkter:\n"
        + "\n".join(determination_lines)
        + "\n\nOfficiel kilde:\n"
        + "\n\n".join(passage_lines)
        + "\n\nForventet svar:\n"
        + str(rubric.get("reference_answer_danish", ""))
    )


def create_lawyer_excel(
    outputs: Iterable[dict[str, Any]],
    cases_by_id: dict[str, dict[str, Any]],
    rubrics_by_case: dict[str, dict[str, Any]],
    gold_by_id: dict[str, dict[str, Any]],
    human_rows: Iterable[dict[str, Any]],
) -> bytes:
    human = _unique_review_index(human_rows)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Juridisk kontrol"
    headers = [
        "run_id",
        "case_id",
        "input_mode",
        "Spørgsmål",
        "AI-svar",
        "Forventet kilde",
        "Kontrolleret af jurist",
    ]
    for criterion in CRITERIA:
        criterion_id = CRITERION_IDS[criterion]
        headers.extend(
            [
                f"{criterion_id} Menneskets vurdering",
                f"{criterion_id} Menneskets begrundelse",
                f"{criterion_id} Juristens rettelse",
                f"{criterion_id} Juristens begrundelse",
            ]
        )
    sheet.append(headers)
    for cell in sheet[1]:
        cell.font = Font(bold=True)
        cell.alignment = Alignment(wrap_text=True, vertical="top")

    for output in outputs:
        case_id = str(output["case_id"])
        case = cases_by_id[case_id]
        review = human.get(human_review_key(output), {})
        row: list[str] = [
            str(output.get("run_id", "")),
            case_id,
            str(output.get("input_mode", "")),
            str(case["model_input"]["question"]),
            str(output.get("content", "")),
            _expected_source_text(case, rubrics_by_case[case_id], gold_by_id),
            "Nej",
        ]
        for criterion in CRITERIA:
            row.extend(
                [
                    LABELS_DA.get(
                        str(review.get(f"{criterion}_label", "")),
                        str(review.get(f"{criterion}_label", "")),
                    ),
                    str(review.get(f"{criterion}_reason", "")),
                    "",
                    "",
                ]
            )
        sheet.append(row)

    for row in sheet.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    sheet.freeze_panes = "A2"
    sheet.column_dimensions["D"].width = 45
    sheet.column_dimensions["E"].width = 60
    sheet.column_dimensions["F"].width = 70
    correction_columns = [10 + (index * 4) for index in range(len(CRITERIA))]
    checked_validation = DataValidation(type="list", formula1='"Ja,Nej"')
    sheet.add_data_validation(checked_validation)
    checked_validation.add(f"G2:G{max(sheet.max_row, 2)}")
    validation = DataValidation(
        type="list",
        formula1='"Opfyldt,Ikke opfyldt,Kan ikke vurderes"',
        allow_blank=True,
    )
    sheet.add_data_validation(validation)
    for column in correction_columns:
        validation.add(f"{sheet.cell(1, column).column_letter}2:{sheet.cell(1, column).column_letter}{max(sheet.max_row, 2)}")
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _normalise_lawyer_label(value: Any) -> str:
    normalized = str(value or "").strip().casefold()
    mapping = {
        "opfyldt": "met",
        "ikke opfyldt": "not_met",
        "kan ikke vurderes": "not_assessable",
        "met": "met",
        "not_met": "not_met",
        "not_assessable": "not_assessable",
    }
    return mapping.get(normalized, "")


def import_lawyer_excel(
    data: bytes, original_rows: Iterable[dict[str, Any]]
) -> list[dict[str, str]]:
    originals = _unique_review_index(original_rows)
    workbook = load_workbook(io.BytesIO(data), data_only=True)
    sheet = workbook.active
    headers = [str(cell.value or "").strip() for cell in sheet[1]]
    positions = {header: index for index, header in enumerate(headers)}
    required_columns = (
        "run_id", "case_id", "input_mode", "Kontrolleret af jurist"
    )
    for required in required_columns:
        if required not in positions:
            raise ValueError(f"Excel-filen mangler kolonnen {required}")

    checked: dict[tuple[str, str, str], dict[str, Any]] = {}
    for values in sheet.iter_rows(min_row=2, values_only=True):
        is_checked = str(
            values[positions["Kontrolleret af jurist"]] or ""
        ).strip().casefold()
        if is_checked != "ja":
            continue
        key = tuple(
            str(values[positions[field]] or "").strip()
            for field in ("run_id", "case_id", "input_mode")
        )
        corrections = False
        for criterion in CRITERIA:
            correction_header = f"{CRITERION_IDS[criterion]} Juristens rettelse"
            if correction_header in positions and str(
                values[positions[correction_header]] or ""
            ).strip():
                corrections = True
        if key not in originals:
            if corrections:
                raise ValueError(
                    f"Juristen har rettet et svar uden en menneskelig vurdering: {key[1]}"
                )
            continue
        row = dict(originals[key])
        for criterion in CRITERIA:
            criterion_id = CRITERION_IDS[criterion]
            correction_header = f"{criterion_id} Juristens rettelse"
            reason_header = f"{criterion_id} Juristens begrundelse"
            if correction_header not in positions:
                raise ValueError(f"Excel-filen mangler {correction_header}")
            if reason_header not in positions:
                raise ValueError(f"Excel-filen mangler {reason_header}")
            raw_correction = values[positions[correction_header]]
            if not str(raw_correction or "").strip():
                continue
            corrected_label = _normalise_lawyer_label(raw_correction)
            if not corrected_label:
                raise ValueError(f"Ugyldig rettelse for {criterion_id}: {raw_correction}")
            corrected_reason = str(values[positions[reason_header]] or "").strip()
            if not corrected_reason:
                raise ValueError(f"Juristens begrundelse mangler for {criterion_id}")
            row[f"{criterion}_label"] = corrected_label
            row[f"{criterion}_reason"] = corrected_reason
        row["coding_round"] = "legal_check"
        row["overall_notes"] = (
            str(row.get("overall_notes", "")).strip()
            + f" [Juristkontrolleret {datetime.now(timezone.utc).date().isoformat()}]"
        ).strip()
        checked[key] = row
    return [
        {field: str(row.get(field, "")) for field in HUMAN_REVIEW_FIELDS}
        for _, row in sorted(checked.items())
    ]


def write_human_reviews(
    path: Path, rows: Iterable[dict[str, Any]]
) -> list[dict[str, str]]:
    normalized = [
        {field: str(row.get(field, "")) for field in HUMAN_REVIEW_FIELDS}
        for row in rows
    ]
    normalized.sort(key=human_review_key)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=HUMAN_REVIEW_FIELDS)
        writer.writeheader()
        writer.writerows(normalized)
    return normalized
