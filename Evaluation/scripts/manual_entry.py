"""Manual entry of answers from the researcher's own RAG system (self-retrieval condition).

The answers are copied by hand from the RAG system's user interface and saved as a
normal run, so the review tool, the legal reviewer and the LLM judge treat them like
every other run.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BENCHMARK_ID = "XSU-GUIDANCE-QA-V5"
INPUT_MODE = "self_retrieval"
ADAPTER = "manual_entry"
SOURCES_HEADING = "Kilder vist i systemet:"


def load_draft(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"meta": {}, "answers": {}}
    data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault("meta", {})
    data.setdefault("answers", {})
    return data


def save_draft(path: Path, draft: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8")


def answer_content(answer: str, sources: str) -> str:
    """The text the reviewer and the judge see: the answer, then any sources the system showed."""
    content = answer.strip()
    if sources.strip():
        content += f"\n\n{SOURCES_HEADING}\n{sources.strip()}"
    return content


def missing_fields(cases: list[dict[str, Any]], answers: dict[str, dict[str, str]], meta: dict[str, str]) -> list[str]:
    problems = []
    if not meta.get("system_name", "").strip():
        problems.append("system name")
    if not meta.get("system_version", "").strip():
        problems.append("version or commit")
    empty = [c["case_id"] for c in cases if not answers.get(c["case_id"], {}).get("answer", "").strip()]
    if empty:
        problems.append(f"{len(empty)} answers")
    return problems


def _safe(text: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in text).strip("_")


def build_manual_run(
    cases: list[dict[str, Any]],
    answers: dict[str, dict[str, str]],
    meta: dict[str, str],
    now: datetime | None = None,
) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    problems = missing_fields(cases, answers, meta)
    if problems:
        raise ValueError("Missing: " + ", ".join(problems))
    now = now or datetime.now(timezone.utc)
    system_name = meta["system_name"].strip()
    system_id = _safe(f"Manual_{system_name}_{INPUT_MODE}")
    run_id = f"{now.strftime('%Y%m%dT%H%M%S%fZ')}_{system_id}"
    outputs = []
    for case in cases:
        entry = answers[case["case_id"]]
        question = str(case["model_input"]["question"])
        outputs.append(
            {
                "case_id": case["case_id"],
                "system_id": system_id,
                "adapter": ADAPTER,
                "requested_model": system_name,
                "input_mode": INPUT_MODE,
                "timestamp_utc": entry.get("entered_utc") or now.isoformat(),
                "prompt": question,
                "prompt_sha256": hashlib.sha256(question.encode("utf-8")).hexdigest(),
                "content": answer_content(entry.get("answer", ""), entry.get("sources", "")),
                "answer_as_copied": entry.get("answer", "").strip(),
                "sources_as_copied": entry.get("sources", "").strip(),
                "retrieved_chunks": [],
                "error": None,
                "run_id": run_id,
            }
        )
    metadata = {
        "run_id": run_id,
        "benchmark_id": BENCHMARK_ID,
        "system": {
            "system_id": system_id,
            "adapter": ADAPTER,
            "input_mode": INPUT_MODE,
            "model": system_name,
            "system_version": meta["system_version"].strip(),
            "generator_model": meta.get("generator_model", "").strip(),
        },
        "input_mode": INPUT_MODE,
        "entry_method": (
            "Each question was typed or pasted into the RAG system's own interface and "
            "the answer, with any sources the system showed, was copied by hand into the "
            "review tool. One question per new conversation."
        ),
        "entered_by": meta.get("entered_by", "").strip(),
        "case_ids": [c["case_id"] for c in cases],
        "case_count": len(cases),
        "output_count": len(outputs),
        "run_error_count": 0,
        "finished_utc": now.isoformat(),
    }
    return run_id, outputs, metadata


def save_manual_run(
    out_dir: Path,
    cases: list[dict[str, Any]],
    answers: dict[str, dict[str, str]],
    meta: dict[str, str],
) -> Path:
    run_id, outputs, metadata = build_manual_run(cases, answers, meta)
    run_dir = out_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    outputs_path = run_dir / "outputs.jsonl"
    with outputs_path.open("w", encoding="utf-8") as handle:
        for row in outputs:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    metadata["outputs_sha256"] = hashlib.sha256(outputs_path.read_bytes()).hexdigest()
    (run_dir / "run_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return run_dir
