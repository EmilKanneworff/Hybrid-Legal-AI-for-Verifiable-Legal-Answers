#!/usr/bin/env python3
"""Pure helpers for the simple review page (review.py).

One row in the review file is one reviewer's assessment of one answer.
The reviewer never sees the AI labels on the review page. The tables compare
the label sets afterwards.
"""

from __future__ import annotations

import csv
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

try:
    from .compare_judges_v5 import compare
    from .create_judge_template_v5 import CRITERIA
except ImportError:  # pragma: no cover - direct script execution
    from compare_judges_v5 import compare
    from create_judge_template_v5 import CRITERIA


# The page is used by one person. The value is stored so that later review
# sets (for example a second reviewer) can be kept apart in the same file.
REVIEWER = "human"

CHOICES = {"Met": "met", "Not met": "not_met", "Not assessable": "not_assessable"}
CHOICE_BY_LABEL = {value: key for key, value in CHOICES.items()}

NAMES = {
    "c01_overall_legal_correctness": "Overall legal correctness",
    "c02_required_elements_complete": "Required elements complete",
    "c03_direct_relevance": "Direct relevance",
    "c04_source_traceability": "Source traceability",
    "c05_source_validity": "Source validity",
    "c06_claim_source_support": "Claim–source support",
    "c07_no_unsupported_legal_additions": "No unsupported legal additions",
    "c08_qualifications_and_exceptions": "Qualifications and exceptions preserved",
    "c09_reasoning_coherence": "Reasoning coherence",
    "c10_legal_modality_precision": "Legal modality precision",
}

# Same wording as the criteria table in Chapter 6 of the thesis.
QUESTIONS = {
    "c01_overall_legal_correctness": "Are the conclusion and material legal statements correct within the defined task?",
    "c02_required_elements_complete": "Does the answer contain every critical element in the expert rubric?",
    "c03_direct_relevance": "Does the answer address all material parts of the question?",
    "c04_source_traceability": "Can the material legal statements be connected to identifiable sources?",
    "c05_source_validity": "Are the stated sources current, authoritative and applicable to the task?",
    "c06_claim_source_support": "Do the cited passages support the full meaning of the material claims?",
    "c07_no_unsupported_legal_additions": "Does the answer avoid invented or unsubstantiated rules, conditions, exceptions or effects?",
    "c08_qualifications_and_exceptions": "Are limits and non-absolute wording that change the legal meaning retained?",
    "c09_reasoning_coherence": "Do the stated legal steps support the answer's conclusion without contradiction?",
    "c10_legal_modality_precision": "Does the answer distinguish what is required, allowed, excluded or discretionary?",
}

# Decision rule for each criterion. "Met" always means that the answer is adequate on this point.
HELP = {
    "c01_overall_legal_correctness": (
        "Compare with the approved expected answer and the reference source.  \n"
        "**Met**: the conclusion and material statements are consistent with the reference · "
        "**Not met**: the conclusion or a material statement deviates from or contradicts it"
    ),
    "c02_required_elements_complete": (
        "**Met**: all critical elements listed below are present (accepted variants count) · "
        "**Not met**: one or more critical elements are missing"
    ),
    "c03_direct_relevance": (
        "**Met**: the answer addresses all material parts of the question · "
        "**Not met**: it addresses a different issue or omits part of the question"
    ),
    "c04_source_traceability": (
        "**Met**: material statements are attributed to an identifiable source (statute, provision "
        "or guidance) · **Not met**: no identifiable source is cited  \n"
        "If not met, record C5 and C6 as **Not assessable**."
    ),
    "c05_source_validity": (
        "**Met**: the cited source is current, authoritative and applicable (e.g. the SU Act or "
        "VEJ nr. 10157/2026) · **Not met**: the source is incorrect, outdated or non-existent · "
        "**Not assessable**: no source is cited"
    ),
    "c06_claim_source_support": (
        "Compare with the reference passage.  \n"
        "**Met**: the cited source supports the full meaning of the material claims · "
        "**Not met**: the source does not support, or contradicts, a claim · "
        "**Not assessable**: no source is cited"
    ),
    "c07_no_unsupported_legal_additions": (
        "**Met**: no rules, amounts, deadlines, conditions or effects beyond the source · "
        "**Not met**: the answer adds legal content without support in the source"
    ),
    "c08_qualifications_and_exceptions": (
        "**Met**: the required qualification below is retained · "
        "**Not met**: it is omitted, or the rule is stated as absolute"
    ),
    "c09_reasoning_coherence": (
        "**Met**: the legal steps are consistent and support the conclusion · "
        "**Not met**: the reasoning is contradictory or does not support the conclusion"
    ),
    "c10_legal_modality_precision": (
        "**Met**: modal terms correspond to the source (\"skal\", \"kan\", \"som udgangspunkt\") · "
        "**Not met**: modality is altered, e.g. \"kan\" or \"som udgangspunkt\" rendered as \"skal\", or vice versa"
    ),
}

MODE_DA = {
    "closed_book": "Question only",
    "gold_context": "Correct source supplied",
    "self_retrieval": "Self-retrieval (RAG)",
}

REVIEW_FIELDS = [
    "run_id",
    "case_id",
    "input_mode",
    "model",
    "question_no",
    "reviewer",
    "review_date",
] + [f"{c}_{part}" for c in CRITERIA for part in ("label", "reason")] + ["checklist_json"]

# The answer key is shown as plain help text under the criterion that uses it.
ANSWER_KEY_HELP = {
    "c02_required_elements_complete": (
        "critical_elements",
        "Critical elements (expert rubric):",
    ),
    "c08_qualifications_and_exceptions": (
        "required_qualifications",
        "Required qualification (expert rubric):",
    ),
}


PROVIDERS = {
    "OpenAI": "openai_responses",
    "Anthropic": "anthropic_messages",
    "UCloud / local model": "openai_chat_completions",
    "Own RAG system": "generic_http_json",
}
SU_CORPUS_SHA256 = "62fd240e73b477a5a526147c28c72f9403ae6f9ee279acd93f3cb6de95063a5f"


def build_system(
    provider: str, model: str, api_key: str, endpoint: str, input_mode: str, version: str = ""
) -> dict[str, Any]:
    """Build one runner configuration, as the old dashboard does."""
    adapter = PROVIDERS[provider]
    if adapter == "generic_http_json":
        input_mode = "self_retrieval"
    name = model or version or "rag"
    system_id = "".join(c if c.isalnum() or c in "_-" else "_" for c in f"{provider}_{name}_{input_mode}")
    system: dict[str, Any] = {
        "system_id": system_id.strip("_"),
        "adapter": adapter,
        "input_mode": input_mode,
        "max_tokens": 12288 if adapter == "openai_responses" else 4096,
        "timeout_seconds": 120,
    }
    if api_key:
        system["_api_key"] = api_key
    if adapter == "openai_responses":
        system.update({"model": model, "base_url": "https://api.openai.com/v1"})
    elif adapter == "anthropic_messages":
        system.update({"model": model, "base_url": "https://api.anthropic.com"})
    elif adapter == "openai_chat_completions":
        system.update({"model": model, "base_url": endpoint, "api_key_required": bool(api_key)})
    else:
        system.update(
            {
                "endpoint": endpoint,
                "system_version": version,
                "corpus_id": "su_handicaptillaeg_v1",
                "corpus_sha256": SU_CORPUS_SHA256,
            }
        )
    return system


def criterion_code(criterion: str) -> str:
    """Plain name shown to the user: 'c01_overall_legal_correctness' -> 'Kriterie 1'."""
    return f"C{int(criterion[1:3])}"


def question_number(case_id: str) -> int:
    """`xsu_sg_005_work_capacity_scope` -> 5."""
    return int(str(case_id).split("_")[2])


def answer_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("run_id", "")),
        str(row.get("case_id", "")),
        str(row.get("input_mode", "")),
    )


MODE_ORDER = {"closed_book": 0, "gold_context": 1, "self_retrieval": 2}


def part_name(row: dict[str, Any]) -> str:
    """One part = one model in one condition, for example 'gpt-5.6-luna · Uden kilde'."""
    model = str(row.get("requested_model") or row.get("system_id", ""))
    return condition_label(model, str(row.get("input_mode", "")))


def build_queue(outputs: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """All answers in parts: first condition, then model and run, then question."""
    return sorted(
        outputs,
        key=lambda row: (
            MODE_ORDER.get(str(row.get("input_mode", "")), 9),
            str(row.get("requested_model") or row.get("system_id", "")),
            str(row.get("run_id", "")),
            question_number(row["case_id"]),
        ),
    )


def part_position(queue: list[dict[str, Any]], index: int) -> dict[str, Any]:
    """Where the answer at `index` is: part number, number of parts, place in the part."""
    names: list[str] = []
    for row in queue:
        if part_name(row) not in names:
            names.append(part_name(row))
    name = part_name(queue[index])
    members = [i for i, row in enumerate(queue) if part_name(row) == name]
    return {
        "name": name,
        "part": names.index(name) + 1,
        "parts": len(names),
        "position": members.index(index) + 1,
        "size": len(members),
    }


def missing_choices(choices: dict[str, tuple[str | None, str]]) -> list[str]:
    """Return the criteria that still need a choice or a reason."""
    missing: list[str] = []
    for criterion in CRITERIA:
        label, reason = choices.get(criterion, (None, ""))
        code = criterion_code(criterion)
        if label not in CHOICES.values():
            missing.append(f"{code}: label missing")
        elif label != "met" and not str(reason).strip():
            missing.append(f"{code}: justification missing")
    return missing


def make_review_row(
    output: dict[str, Any],
    reviewer: str,
    choices: dict[str, tuple[str | None, str]],
    review_date: str,
    checklist: dict[str, list[bool]] | None = None,
) -> dict[str, str]:
    problems = missing_choices(choices)
    if problems:
        raise ValueError("; ".join(problems))
    if not reviewer.strip():
        raise ValueError("Reviewer is missing")
    row = {
        "run_id": str(output.get("run_id", "")),
        "case_id": str(output.get("case_id", "")),
        "input_mode": str(output.get("input_mode", "")),
        "model": str(output.get("requested_model", "")),
        "question_no": str(question_number(output["case_id"])),
        "reviewer": reviewer,
        "review_date": review_date,
    }
    for criterion in CRITERIA:
        label, reason = choices[criterion]
        row[f"{criterion}_label"] = str(label)
        row[f"{criterion}_reason"] = "" if label == "met" else str(reason).strip()
    row["checklist_json"] = json.dumps(checklist or {}, sort_keys=True)
    return row


def load_checklist(review: dict[str, Any] | None) -> dict[str, list[bool]]:
    if not review or not str(review.get("checklist_json") or "").strip():
        return {}
    value = json.loads(review["checklist_json"])
    return value if isinstance(value, dict) else {}


def load_reviews(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def find_review(
    rows: Iterable[dict[str, Any]], key: tuple[str, str, str], reviewer: str
) -> dict[str, Any] | None:
    return next(
        (row for row in rows if answer_key(row) == key and row.get("reviewer") == reviewer),
        None,
    )


def save_review(path: Path, row: dict[str, str]) -> list[dict[str, str]]:
    """Insert or replace this reviewer's row for this answer only."""
    rows = [
        existing
        for existing in load_reviews(path)
        if not (
            answer_key(existing) == answer_key(row)
            and existing.get("reviewer") == row["reviewer"]
        )
    ]
    rows.append(row)
    rows.sort(key=lambda r: (r["reviewer"], int(r["question_no"]), r["input_mode"], r["run_id"]))
    write_csv(path, rows, REVIEW_FIELDS)
    return rows


def ai_exists(ai_rows: Iterable[dict[str, Any]], key: tuple[str, str, str]) -> bool:
    return any(answer_key(row) == key for row in ai_rows)


def is_locked(own_review: dict[str, Any] | None, ai_review_exists: bool) -> bool:
    """A first review is always allowed. A saved review is locked once the AI has assessed the answer."""
    return own_review is not None and ai_review_exists


def next_unreviewed(
    queue: list[dict[str, Any]], reviews: list[dict[str, Any]], reviewer: str, start: int
) -> int:
    """Index of the next answer after `start` that this reviewer has not assessed."""
    done = {answer_key(row) for row in reviews if row.get("reviewer") == reviewer}
    for offset in range(1, len(queue) + 1):
        index = (start + offset) % len(queue)
        if answer_key(queue[index]) not in done:
            return index
    return start


def count_done(queue: list[dict[str, Any]], reviews: list[dict[str, Any]], reviewer: str) -> int:
    keys = {answer_key(row) for row in queue}
    return sum(
        1 for row in reviews if row.get("reviewer") == reviewer and answer_key(row) in keys
    )


def short_model(model: str) -> str:
    """'Llama-3.3-70B-Instruct-Q8_0/Llama-...-00001-of-00002.gguf' -> 'Llama-3.3-70B-Instruct-Q8_0'."""
    name = str(model).strip().split("/")[-1]
    name = re.sub(r"\.gguf$", "", name)
    return re.sub(r"-\d{5}-of-\d{5}$", "", name)


def condition_label(model: str, input_mode: str) -> str:
    return f"{short_model(model)} · {MODE_DA.get(input_mode, input_mode)}"


SYMBOL = {"met": "✓", "not_met": "✗", "not_assessable": "?"}


def short_code(criterion: str) -> str:
    """'c01_overall_legal_correctness' -> 'K1'."""
    return f"C{int(criterion[1:3])}"


def is_legally_sound(row: dict[str, Any]) -> bool:
    return (
        row.get("c01_overall_legal_correctness_label") == "met"
        and row.get("c02_required_elements_complete_label") == "met"
    )


def parts_of(rows: Iterable[dict[str, Any]]) -> list[str]:
    """Part names (model · setting) in a stable order."""
    names = {condition_label(r.get("model", ""), r["input_mode"]) for r in rows}
    order = {label: i for i, label in enumerate(MODE_DA.values())}
    return sorted(names, key=lambda n: (order.get(n.split(" · ")[-1], 9), n))


def table_answers(
    rows: list[dict[str, Any]],
    part: str,
    topics: dict[str, str],
    expected: list[dict[str, Any]] | None = None,
) -> list[dict[str, str]]:
    """Answer by answer: one row per question, one column per criterion (✓ ✗ ?).

    With `expected` (the answers in this part), answers that are not assessed yet
    are shown as an empty row, so the table shows the current status.
    The last row gives the number of ✓ for each criterion.
    """
    chosen = sorted(
        (r for r in rows if condition_label(r.get("model", ""), r["input_mode"]) == part),
        key=lambda r: int(r["question_no"]),
    )
    by_key = {answer_key(r): r for r in chosen}
    if expected is None:
        order = [(int(r["question_no"]), r["case_id"], answer_key(r)) for r in chosen]
    else:
        order = sorted(
            (question_number(o["case_id"]), o["case_id"], answer_key(o)) for o in expected
        )
    table: list[dict[str, str]] = []
    for number, case_id, key in order:
        r = by_key.get(key)
        line = {"Question": f"{number:02d}. {topics.get(case_id, '')}"}
        for criterion in CRITERIA:
            line[short_code(criterion)] = SYMBOL.get(r[f"{criterion}_label"], "") if r else "·"
        line["Legally adequate"] = ("Yes" if is_legally_sound(r) else "No") if r else "Not yet assessed"
        table.append(line)
    if chosen:
        label = f"Total ✓ (of {len(chosen)})"
        if expected is not None and len(chosen) < len(order):
            label = f"Total ✓ (of {len(chosen)} assessed to date)"
        total = {"Question": label}
        for criterion in CRITERIA:
            total[short_code(criterion)] = str(
                sum(1 for r in chosen if r[f"{criterion}_label"] == "met")
            )
        total["Legally adequate"] = str(sum(1 for r in chosen if is_legally_sound(r)))
        table.append(total)
    return table


def _count_cell(labels: list[str]) -> str:
    """Counts written out, e.g. '3 met · 10 not met · 1 not assessable'."""
    parts = [f"{labels.count('met')} met"]
    if labels.count("not_met"):
        parts.append(f"{labels.count('not_met')} not met")
    if labels.count("not_assessable"):
        parts.append(f"{labels.count('not_assessable')} not assessable")
    return " · ".join(parts)


def table_criteria(
    reference_rows: list[dict[str, Any]],
    columns: list[str] | None = None,
    sizes: dict[str, int] | None = None,
) -> list[dict[str, str]]:
    """Summary: for each criterion, how many answers meet it, for each part.

    With `columns` and `sizes`, every part is shown, also before it is assessed,
    and the first row says how many of its answers are assessed so far.
    """
    columns = columns if columns is not None else parts_of(reference_rows)
    groups = {
        c: [r for r in reference_rows if condition_label(r.get("model", ""), r["input_mode"]) == c]
        for c in columns
    }
    table: list[dict[str, str]] = []
    if sizes is not None:
        table.append(
            {"Criterion": "Answers assessed to date",
             **{c: f"{len(groups[c])} of {sizes.get(c, len(groups[c]))}" for c in columns}}
        )
    for criterion in CRITERIA:
        line = {"Criterion": f"{criterion_code(criterion)} · {NAMES[criterion]}"}
        for column in columns:
            labels = [r[f"{criterion}_label"] for r in groups[column]]
            line[column] = _count_cell(labels) if labels else "—"
        table.append(line)
    line = {"Criterion": "Legally adequate (C1 and C2 met)"}
    for column in columns:
        group = groups[column]
        line[column] = f"{sum(1 for r in group if is_legally_sound(r))} of {len(group)}" if group else "—"
    table.append(line)
    return table


def table_status(
    queue: list[dict[str, Any]],
    reviews: list[dict[str, Any]],
    reviewer: str,
    ai_rows: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """Current status for each part: answers, your assessments and AI judge runs."""
    done = {answer_key(r) for r in reviews if r.get("reviewer") == reviewer}
    ai_done: dict[str, set] = {"1": set(), "2": set(), "3": set()}
    for row in ai_rows:
        repeat = str(row.get("repeat") or row.get("coding_round", ""))
        if repeat in ai_done:
            ai_done[repeat].add(answer_key(row))
    names: list[str] = []
    for row in queue:
        if part_name(row) not in names:
            names.append(part_name(row))
    table: list[dict[str, str]] = []
    for name in names:
        keys = {answer_key(r) for r in queue if part_name(r) == name}
        line = {"Model · input condition": name, "Answers": str(len(keys)), "Human assessment": f"{len(keys & done)} of {len(keys)}"}
        for repeat, judged in ai_done.items():
            line[f"LLM judge run {repeat}"] = f"{len(keys & judged)} of {len(keys)}"
        table.append(line)
    return table


def _common(first: list[dict[str, Any]], second: list[dict[str, Any]]):
    keys = {answer_key(r) for r in first} & {answer_key(r) for r in second}
    return (
        [r for r in first if answer_key(r) in keys],
        [r for r in second if answer_key(r) in keys],
    )


def table_agreement(pairs: dict[str, tuple[list[dict[str, Any]], list[dict[str, Any]]]]):
    """For each criterion: on how many answers the two assessments are the same.

    Kappa is kept in a separate column '<name> · kappa' for the CSV file and the thesis.
    """
    results = {}
    for name, (first, second) in pairs.items():
        first, second = _common(first, second)
        results[name] = {row["criterion"]: row for row in compare(first, second)} if first else {}
    table: list[dict[str, str]] = []
    for criterion in CRITERIA:
        line = {"Criterion": f"{criterion_code(criterion)} · {NAMES[criterion]}"}
        for name, rows in results.items():
            row = rows.get(criterion)
            if not row or not row["paired_item_count"]:
                line[name] = "—"
                line[f"{name} · kappa"] = ""
                continue
            line[name] = f"{row['agreement_count']} of {row['paired_item_count']}"
            line[f"{name} · kappa"] = str(row["cohen_kappa"])
        table.append(line)
    return table


def table_stability(ai_rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    """For each criterion: on how many answers the AI gave the same choice in all 3 runs."""
    by_answer: dict[tuple[str, str, str], dict[str, dict[str, Any]]] = {}
    for row in ai_rows:
        repeat = str(row.get("repeat") or row.get("coding_round", ""))
        by_answer.setdefault(answer_key(row), {})[repeat] = row
    complete = [runs for runs in by_answer.values() if {"1", "2", "3"} <= set(runs)]
    table: list[dict[str, str]] = []
    for criterion in CRITERIA:
        line = {"Criterion": f"{criterion_code(criterion)} · {NAMES[criterion]}"}
        if not complete:
            line["Identical label in all three runs"] = "—"
        else:
            same = sum(
                1
                for runs in complete
                if len(Counter(runs[r][f"{criterion}_label"] for r in ("1", "2", "3"))) == 1
            )
            line["Identical label in all three runs"] = f"{same} of {len(complete)}"
        table.append(line)
    return table


# ---------------------------------------------------------------- questions and data
# Reasons from benchmark/TESTCASE_MAPPING_SU_GUIDANCE_QA_V4.md, section "Excluded Determinations".
EXCLUDED_POINTS = {
    "A11": "Not used. The label says that the impairment will not improve, but the "
    "attached text (lines 191-211) gives examples, not the definition.",
    "A43": "Not used. The label is about daily function, but the attached text "
    "(line 341) is about the ability to work.",
}


def _point_number(point_id: str) -> int:
    return int(str(point_id).lstrip("A"))


def table_questions(cases: Iterable[dict[str, Any]]) -> list[dict[str, str]]:
    """The 14 questions: full text, the XHAILe points behind each, and the correct source."""
    rows = []
    for case in sorted(cases, key=lambda c: question_number(c["case_id"])):
        sources = [
            str(p.get("citation_label", "")).replace("VEJ nr. 10157 af 05/10/2026, ", "")
            for p in case["model_input"].get("source_passages", [])
        ]
        rows.append(
            {
                "No.": f"{question_number(case['case_id']):02d}",
                "Topic": str(case.get("topic", "")),
                "Question (sent to the model)": str(case["model_input"]["question"]),
                "XHAILe points": ", ".join(case["reference"]["determination_ids"]),
                "Correct source (guidance 2026)": " · ".join(sources),
            }
        )
    return rows


def table_xhaile_points(
    gold_by_id: dict[str, dict[str, Any]], cases: Iterable[dict[str, Any]]
) -> list[dict[str, str]]:
    """All XHAILe points: their text, and the question that uses each one."""
    used: dict[str, list[str]] = {}
    for case in cases:
        for point in case["reference"]["determination_ids"]:
            used.setdefault(str(point), []).append(f"{question_number(case['case_id']):02d}")
    rows = []
    for point_id in sorted(gold_by_id, key=_point_number):
        point = gold_by_id[point_id]
        rows.append(
            {
                "XHAILe point": point_id,
                "Text from XHAILe": str(point.get("label", "")).strip(),
                "Used in question": ", ".join(sorted(used.get(point_id, [])))
                or EXCLUDED_POINTS.get(point_id, "Not used."),
                "Place in the 2025 guidance": f"Section {point.get('section_no', '')}, "
                f"line {point.get('line_number', '')}",
            }
        )
    return rows
