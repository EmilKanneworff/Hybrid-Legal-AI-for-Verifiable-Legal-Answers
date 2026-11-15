#!/usr/bin/env python3
"""Run the blind LLM judge on the 70 assessed answers.

The judge (claude-sonnet-5-5) uses llm_judge_prompt_v3_c04_reviewer_wording.txt and
TEN_CRITERIA_JUDGE_RUBRIC_V5_C04_ALIGNED.md, in which C04 is worded exactly as in the
legal reviewer's review tool. Results go to outputs/v5_judge_c04_aligned/.

Usage: Evaluation/.venv/bin/python -m Evaluation.scripts.run_llm_judge_c04_aligned --repeat 1   # and 2, 3
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

try:
    from . import run_llm_judge_v5 as judge
    from .credential_store import get_api_key
    from .dashboard_v5 import (
        build_ai_review_row,
        list_saved_runs,
        load_expert_rubrics,
        load_saved_run,
        save_ai_review,
        save_raw_ai_response,
    )
    from .simple_review import answer_key, build_queue
except ImportError:  # pragma: no cover - direct script execution
    import run_llm_judge_v5 as judge
    from credential_store import get_api_key
    from dashboard_v5 import (
        build_ai_review_row,
        list_saved_runs,
        load_expert_rubrics,
        load_saved_run,
        save_ai_review,
        save_raw_ai_response,
    )
    from simple_review import answer_key, build_queue

ROOT = Path(__file__).resolve().parents[1]
PROMPT_V3 = ROOT / "prompts" / "llm_judge_prompt_v3_c04_reviewer_wording.txt"
RUBRIC_ALIGNED = ROOT / "scoring" / "TEN_CRITERIA_JUDGE_RUBRIC_V5_C04_ALIGNED.md"
TESTCASES = ROOT / "benchmark" / "testcases_su_guidance_qa_v5.jsonl"
RUBRICS = ROOT / "benchmark" / "expert_answer_criteria_su_guidance_qa_v5.csv"
REVIEWED = ROOT / "outputs" / "v5_review" / "simple_reviews.csv"
OUT = ROOT / "outputs" / "v5_judge_c04_aligned"
OUT_CSV = OUT / "ai_review_c04_aligned.csv"
RAW = OUT / "raw"
LOG = OUT / "run_log.txt"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--repeat", type=int, default=1, choices=[1, 2, 3])
    args = parser.parse_args()

    # The judge prompt and the rubric file the judge receives.
    judge.PROMPT_PATH = PROMPT_V3
    judge.RUBRIC_PATH = RUBRIC_ALIGNED

    cases = {}
    for line in TESTCASES.read_text(encoding="utf-8").splitlines():
        if line.strip():
            case = json.loads(line)
            cases[case["case_id"]] = case
    outputs = []
    for run_dir in list_saved_runs([ROOT / "outputs" / "final_v5"]):
        run_outputs, _ = load_saved_run(run_dir)
        outputs.extend(run_outputs)
    queue = build_queue(outputs)
    rubrics = load_expert_rubrics(RUBRICS)

    # Exactly the 70 answers the legal reviewer assessed.
    with REVIEWED.open(encoding="utf-8") as handle:
        judged = {answer_key(row) for row in csv.DictReader(handle)}
    todo = [o for o in queue if answer_key(o) in judged]
    if len(todo) != len(judged):
        raise SystemExit(f"Expected {len(judged)} answers, found {len(todo)}")

    api_key = get_api_key("anthropic_messages")
    if not api_key:
        raise SystemExit("No Anthropic API key in the keychain (account anthropic_messages)")

    OUT.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)
    manifest = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "model": judge.DEFAULT_MODEL,
        "repeat": args.repeat,
        "answers": len(todo),
        "prompt_file": PROMPT_V3.name,
        "prompt_sha256": sha(PROMPT_V3),
        "rubric_file": RUBRIC_ALIGNED.name,
        "rubric_sha256": sha(RUBRIC_ALIGNED),
    }
    (OUT / f"manifest_repeat_{args.repeat}.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    done = {p.name for p in RAW.glob(f"*_repeat_{args.repeat}.json")}
    lock = threading.Lock()

    def raw_name(output: dict) -> str:
        parts = [
            "".join(c if c.isalnum() else "_" for c in str(output.get(k, d)))
            for k, d in (("run_id", "run"), ("case_id", "case"), ("input_mode", "mode"))
        ]
        return "_".join(parts) + f"_repeat_{args.repeat}.json"

    pending = [o for o in todo if raw_name(o) not in done]

    def work(output: dict) -> str:
        case = cases[output["case_id"]]
        rubric = rubrics[output["case_id"]]
        result = judge.judge_answer(
            case, output, rubric, {"model": judge.DEFAULT_MODEL, "_api_key": api_key}, args.repeat
        )
        with lock:
            raw_path = save_raw_ai_response(RAW, output, result)
            save_ai_review(OUT_CSV, build_ai_review_row(case, output, rubric, result, str(raw_path)))
        return f"{output['case_id']} {output['input_mode']}"

    with LOG.open("a", encoding="utf-8") as log, ThreadPoolExecutor(max_workers=args.workers) as pool:
        log.write(f"{datetime.now(timezone.utc).isoformat()} repeat {args.repeat} start, {len(pending)} pending of {len(todo)}\n")
        futures = {pool.submit(work, o): o for o in pending}
        for number, future in enumerate(as_completed(futures), 1):
            try:
                message = "ok " + future.result()
            except Exception as exc:  # report and continue; rerunning resumes
                o = futures[future]
                message = f"FAILED {o['case_id']} {o['input_mode']}: {exc}"
            line = f"{number}/{len(pending)} {message}"
            print(line, flush=True)
            log.write(line + "\n")
            log.flush()
    print("finished", flush=True)


if __name__ == "__main__":
    main()
