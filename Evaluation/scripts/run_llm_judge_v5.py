#!/usr/bin/env python3
"""Run the blind Anthropic V5 answer-level judge."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

try:
    from .create_judge_template_v5 import CRITERIA
    from . import run_evaluation
except ImportError:  # pragma: no cover - direct script execution
    from create_judge_template_v5 import CRITERIA
    import run_evaluation


EVALUATION_ROOT = Path(__file__).resolve().parents[1]
PROMPT_PATH = EVALUATION_ROOT / "prompts" / "llm_judge_prompt_v3_c04_reviewer_wording.txt"
RUBRIC_PATH = EVALUATION_ROOT / "scoring" / "TEN_CRITERIA_JUDGE_RUBRIC_V5_C04_ALIGNED.md"
AUTHORITIES_PATH = EVALUATION_ROOT / "benchmark" / "legal_authorities_su_v1.json"
GOLD_PATH = EVALUATION_ROOT / "benchmark" / "gold_determinations_su_v1.jsonl"
ALLOWED_LABELS = {"met", "not_met", "not_assessable"}
ALLOWED_COVERAGE_LABELS = {"yes", "partial", "no"}
DEFAULT_MODEL = "claude-sonnet-5-5"


def _json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if not str(value or "").strip():
        return []
    parsed = json.loads(str(value))
    if not isinstance(parsed, list):
        raise ValueError("Ekspertrubrikkens listefelt er ugyldigt")
    return parsed


def _load_gold() -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    with GOLD_PATH.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                row = json.loads(line)
                rows[str(row["determination_id"])] = row
    return rows


def build_judge_input(
    case: dict[str, Any], output: dict[str, Any], rubric: dict[str, Any]
) -> dict[str, Any]:
    determination_ids = [
        str(value) for value in case.get("reference", {}).get("determination_ids", [])
    ]
    gold = _load_gold()
    missing = [value for value in determination_ids if value not in gold]
    if missing:
        raise ValueError(f"XHAILe-punkter mangler: {', '.join(missing)}")
    authorities = json.loads(AUTHORITIES_PATH.read_text(encoding="utf-8"))
    expert_rubric = {
        "reference_answer_danish": str(rubric.get("reference_answer_danish", "")),
        "critical_elements": _json_list(rubric.get("critical_elements_json", [])),
        "supporting_elements": _json_list(rubric.get("supporting_elements_json", [])),
        "material_errors": _json_list(rubric.get("material_errors_json", [])),
        "acceptable_answer_variants": _json_list(
            rubric.get("acceptable_answer_variants_json", [])
        ),
        "required_qualifications": _json_list(
            rubric.get("required_qualifications_json", [])
        ),
    }
    return {
        "case_id": str(case["case_id"]),
        "question": str(case["model_input"]["question"]),
        "answer": str(output.get("content", "")),
        "official_passages": list(case["model_input"].get("source_passages", [])),
        "formal_provisions": authorities.get("authorities", []),
        "expert_rubric": expert_rubric,
        "xhaile_determinations": [gold[value] for value in determination_ids],
        "criterion_definitions": RUBRIC_PATH.read_text(encoding="utf-8"),
    }


def build_judge_prompt(
    case: dict[str, Any], output: dict[str, Any], rubric: dict[str, Any]
) -> str:
    template = PROMPT_PATH.read_text(encoding="utf-8")
    judge_input = build_judge_input(case, output, rubric)
    return template.replace(
        "{{JUDGE_INPUT_JSON}}",
        json.dumps(judge_input, ensure_ascii=False, indent=2),
    )


def _extract_json(text: str) -> dict[str, Any]:
    value = text.strip()
    if value.startswith("```"):
        value = re.sub(r"^```(?:json)?\s*", "", value, flags=re.IGNORECASE)
        value = re.sub(r"\s*```$", "", value)
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError("AI-dommeren returnerede ikke et JSON-objekt")
    return parsed


def _validate_result(
    parsed: dict[str, Any], case_id: str, determination_ids: list[str]
) -> dict[str, Any]:
    if str(parsed.get("case_id", "")) != case_id:
        raise ValueError("AI-dommeren returnerede et forkert case_id")
    criteria = parsed.get("criteria")
    if not isinstance(criteria, dict) or set(criteria) != set(CRITERIA):
        raise ValueError("AI-dommeren returnerede ikke alle ti kriterier")
    clean_criteria: dict[str, dict[str, str]] = {}
    for criterion in CRITERIA:
        decision = criteria.get(criterion)
        if not isinstance(decision, dict):
            raise ValueError(f"Ugyldigt kriterium: {criterion}")
        label = str(decision.get("label", "")).strip()
        reason = str(decision.get("reason", "")).strip()
        if label not in ALLOWED_LABELS or not reason:
            raise ValueError(f"Ugyldig label eller begrundelse for {criterion}")
        clean_criteria[criterion] = {"label": label, "reason": reason}

    coverage = parsed.get("xhaile_coverage")
    if not isinstance(coverage, dict) or set(coverage) != set(determination_ids):
        raise ValueError("AI-dommeren returnerede ikke alle XHAILe-punkter")
    clean_coverage: dict[str, dict[str, str]] = {}
    for determination_id in determination_ids:
        decision = coverage.get(determination_id)
        if not isinstance(decision, dict):
            raise ValueError(f"Ugyldigt XHAILe-punkt: {determination_id}")
        label = str(decision.get("label", "")).strip()
        reason = str(decision.get("reason", "")).strip()
        if label not in ALLOWED_COVERAGE_LABELS or not reason:
            raise ValueError(f"Ugyldig dækning for {determination_id}")
        clean_coverage[determination_id] = {"label": label, "reason": reason}
    return {
        "case_id": case_id,
        "criteria": clean_criteria,
        "xhaile_coverage": clean_coverage,
        "overall_notes": str(parsed.get("overall_notes", "")).strip(),
    }


def _provider_error(provider_result: dict[str, Any]) -> str:
    raw = provider_result.get("raw_response", {})
    if not isinstance(raw, dict):
        return "AI-udbyderen returnerede et ugyldigt råsvar"
    if raw.get("ok") is False:
        return str(raw.get("error") or "AI-udbyderen returnerede en fejl")
    if raw.get("parse_error"):
        return str(raw["parse_error"])
    if not str(provider_result.get("content", "")).strip():
        return "AI-udbyderen returnerede et tomt svar"
    return ""


def judge_answer(
    case: dict[str, Any],
    output: dict[str, Any],
    rubric: dict[str, Any],
    model_config: dict[str, Any],
    repeat: int,
) -> dict[str, Any]:
    """Judge one answer blindly, with at most two retries on call or JSON errors."""
    if repeat not in {1, 2, 3}:
        raise ValueError("Gentagelse skal være 1, 2 eller 3")
    prompt = build_judge_prompt(case, output, rubric)
    prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    system = dict(model_config)
    model = str(system.get("model") or DEFAULT_MODEL)
    system["model"] = model
    # 2026-11-08: raised from 4096/180. Claude Sonnet 5.5 thinks adaptively by default and the
    # thinking counts toward max_tokens; the long self-retrieval answers hit the old cap
    # (stop_reason max_tokens). max_tokens is a ceiling the model does not see, so completed
    # judgements are unaffected; all 168 earlier judgements ended with end_turn below 4096.
    system.setdefault("max_tokens", 16000)
    system.setdefault("timeout_seconds", 300)
    adapter: Callable[[dict[str, Any], dict[str, Any], str], dict[str, Any]] = (
        system.pop("_adapter", None) or run_evaluation.call_anthropic
    )
    if adapter is run_evaluation.call_anthropic:
        run_evaluation.require_api_key(system)

    determination_ids = [
        str(value) for value in case.get("reference", {}).get("determination_ids", [])
    ]
    last_error = ""
    last_provider_result: dict[str, Any] = {}
    for attempt in range(1, 4):
        try:
            provider_result = adapter(system, case, prompt)
            last_provider_result = provider_result
            provider_error = _provider_error(provider_result)
            if provider_error:
                raise RuntimeError(provider_error)
            parsed = _extract_json(str(provider_result["content"]))
            validated = _validate_result(parsed, str(case["case_id"]), determination_ids)
            raw_response = provider_result.get("raw_response", {})
            returned_model = model
            if isinstance(raw_response, dict) and isinstance(raw_response.get("json"), dict):
                returned_model = str(raw_response["json"].get("model") or model)
            return {
                **validated,
                "raw_response": provider_result,
                "model_id": returned_model,
                "prompt_hash": prompt_hash,
                "judged_at": datetime.now(timezone.utc).isoformat(),
                "repeat": repeat,
                "attempts": attempt,
            }
        except (json.JSONDecodeError, RuntimeError, ValueError) as exc:
            last_error = str(exc)
            if attempt == 3:
                break
    raise RuntimeError(
        f"AI-dommeren fejlede efter tre forsøg: {last_error}"
    ) from None
