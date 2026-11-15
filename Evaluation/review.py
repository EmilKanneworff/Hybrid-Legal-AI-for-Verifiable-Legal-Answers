#!/usr/bin/env python3
"""Legal AI answer evaluation: generate answers, assess them on ten criteria, report results.

Start from the Evaluation folder:
    .venv/bin/streamlit run review.py --server.port 8502
"""

from __future__ import annotations

import io
import json
import shutil
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

from scripts.create_judge_template_v5 import CRITERIA
from scripts.credential_store import CredentialStoreError, get_api_key, save_api_key
from scripts.dashboard_v5 import (
    build_ai_review_row,
    expected_source_bundle,
    list_saved_runs,
    load_csv_rows,
    load_expert_rubrics,
    load_gold_determinations,
    load_saved_run,
    parse_answer_claims,
    save_ai_review,
    save_raw_ai_response,
)
from scripts.manual_entry import load_draft, missing_fields, save_draft, save_manual_run
from scripts.run_evaluation import list_available_models, save_run
from scripts.run_evaluation import run as run_evaluation
from scripts.run_llm_judge_v5 import DEFAULT_MODEL, judge_answer
from scripts.simple_review import (
    CHOICE_BY_LABEL,
    CHOICES,
    NAMES,
    PROVIDERS,
    QUESTIONS,
    REVIEWER,
    ai_exists,
    answer_key,
    build_queue,
    build_system,
    count_done,
    criterion_code,
    find_review,
    is_locked,
    load_reviews,
    make_review_row,
    next_unreviewed,
    ANSWER_KEY_HELP,
    HELP,
    parts_of,
    part_name,
    table_status,
    part_position,
    question_number,
    save_review,
    table_agreement,
    table_answers,
    table_questions,
    table_xhaile_points,
    table_criteria,
    table_stability,
    write_csv,
)

ROOT = Path(__file__).resolve().parent
TESTCASES = ROOT / "benchmark" / "testcases_su_guidance_qa_v5.jsonl"
RUBRICS = ROOT / "benchmark" / "expert_answer_criteria_su_guidance_qa_v5.csv"
GOLD = ROOT / "benchmark" / "gold_determinations_su_v1.jsonl"
NEW_RUNS = ROOT / "outputs" / "final_v5"
# Only runs with the plain prompt. The structured-prompt runs in outputs/final_v4
# are kept unchanged as an archive and are not shown.
RUN_ROOTS = [NEW_RUNS]
REVIEW_ROOT = ROOT / "outputs" / "v5_review"
REVIEWS_PATH = REVIEW_ROOT / "simple_reviews.csv"
# The LLM-judge runs, with C04 worded as in the legal reviewer's tool.
JUDGE_ROOT = ROOT / "outputs" / "v5_judge_c04_aligned"
AI_PATH = JUDGE_ROOT / "ai_review_c04_aligned.csv"
AI_RAW = JUDGE_ROOT / "raw"
RESULTS = JUDGE_ROOT / "results"
CLEARED_ROOT = ROOT / "outputs" / "v5_cleared"
MANUAL_DRAFT = REVIEW_ROOT / "manual_self_retrieval_draft.json"
ALL_QUESTIONS = "Full question set (14)"

st.set_page_config(page_title="Legal AI Answer Evaluation", layout="wide")


@st.cache_data
def load_material():
    cases = {}
    for line in TESTCASES.read_text(encoding="utf-8").splitlines():
        if line.strip():
            case = json.loads(line)
            cases[case["case_id"]] = case
    outputs = []
    for run_dir in list_saved_runs(RUN_ROOTS):
        run_outputs, _ = load_saved_run(run_dir)
        outputs.extend(run_outputs)
    return cases, build_queue(outputs), load_expert_rubrics(RUBRICS), load_gold_determinations(GOLD)


cases, queue, rubrics, gold = load_material()
reviews = load_reviews(REVIEWS_PATH)
ai_rows = load_csv_rows(AI_PATH)
sorted_cases = sorted(cases.values(), key=lambda c: question_number(c["case_id"]))


human = [r for r in reviews if r.get("reviewer") == REVIEWER]
JUDGE_RUNS = (1, 2, 3)


# ================================================================= shared helpers
def saved_key(adapter: str) -> str:
    try:
        return get_api_key(adapter)
    except CredentialStoreError:
        return ""


def key_field(adapter: str, label: str) -> str:
    """One place for API keys: shows a stored key as stored, otherwise asks for one."""
    stored = saved_key(adapter)
    if stored:
        st.caption(f"✓ {label} stored on this computer.")
        with st.expander("Use a different key"):
            new = st.text_input(label, type="password", key=f"new_{adapter}").strip()
            if st.button("Store this key", key=f"store_new_{adapter}", disabled=not new):
                save_api_key(adapter, new)
                st.success("Key stored.")
            return new or stored
    typed = st.text_input(label, type="password", key=f"key_{adapter}").strip()
    if st.button("Store key on this computer", key=f"store_{adapter}", disabled=not typed):
        save_api_key(adapter, typed)
        st.success("Key stored.")
    return typed


def judged_keys(repeat: int) -> set:
    return {
        answer_key(r)
        for r in ai_rows
        if str(r.get("repeat") or r.get("coding_round", "")) == str(repeat)
    }


def excel_bytes(sheets: dict[str, list[dict]]) -> bytes:
    """Excel workbook with one sheet per table; symbols written out as labels.

    Excel on macOS misreads UTF-8 CSV files (garbled æøå and symbols, all columns
    in one cell under a Danish locale), so downloads are .xlsx files.
    """
    words = {"✓": "Met", "✗": "Not met", "?": "Not assessable", "·": ""}
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        for name, rows in sheets.items():
            if not rows:
                continue
            frame = pd.DataFrame(rows).map(lambda v: words.get(v, v) if isinstance(v, str) else v)
            frame.to_excel(writer, index=False, sheet_name=name[:31])
            sheet = writer.sheets[name[:31]]
            for column in sheet.columns:
                width = max(len(str(cell.value or "")) for cell in column)
                sheet.column_dimensions[column[0].column_letter].width = min(max(width + 2, 10), 70)
    return buffer.getvalue()


def excel_download(label: str, sheets: dict[str, list[dict]], name: str) -> None:
    if not any(sheets.values()):
        return
    st.download_button(
        label,
        excel_bytes(sheets),
        file_name=name,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="dl_" + name,
    )


def show_table(rows: list[dict], hide_kappa: bool = False) -> None:
    frame = pd.DataFrame(rows)
    if hide_kappa:
        frame = frame[[c for c in frame.columns if not c.endswith("· kappa")]]
    st.dataframe(frame, hide_index=True, width="stretch")


# ================================================================= status strip
def next_step() -> tuple[int, str]:
    """Index of the page to open and a one-line instruction."""
    if not queue:
        return 0, "Next step: generate answers in the left panel."
    remaining = len(queue) - count_done(queue, reviews, REVIEWER)
    if remaining:
        return 0, f"Next step: assess the remaining {remaining} answers."
    for repeat in JUDGE_RUNS:
        missing = sum(1 for o in queue if answer_key(o) not in judged_keys(repeat) and not o.get("error"))
        if missing:
            return 1, f"Next step: start LLM-judge run {repeat}."
    return 2, "All steps are complete. The results are final for the current answers."


def show_status() -> int:
    done = count_done(queue, reviews, REVIEWER)
    parts = list(dict.fromkeys(part_name(row) for row in queue))
    runs_done = sum(
        1 for r in JUDGE_RUNS if queue and all(answer_key(o) in judged_keys(r) for o in queue if not o.get("error"))
    )
    one, two, three, four = st.columns(4)
    one.metric("Answers", len(queue), help=f"{len(parts)} model and input-condition combinations")
    two.metric("Assessed", f"{done} of {len(queue)}")
    three.metric("LLM-judge runs", f"{runs_done} of 3")
    four.metric("Results", "Final" if queue and runs_done == 3 else "Provisional")
    index, text = next_step()
    st.info(text)
    return index


# ================================================================= page 1: generate
def run_label(run_dir: Path) -> str:
    try:
        meta = json.loads((run_dir / "run_metadata.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return run_dir.name
    model = str(meta.get("system", {}).get("model", "")).split("/")[0] or run_dir.name
    source = {"gold_context": "correct source supplied", "self_retrieval": "self-retrieval (RAG)"}.get(
        meta.get("input_mode"), "question only"
    )
    count = meta.get("output_count", "?")
    stamp = run_dir.name[:13]  # 20261104T1802
    when = f"{stamp[6:8]}/{stamp[4:6]} {stamp[9:11]}:{stamp[11:13]}"
    return f"{model} · {source} · {count} answers · {when}"


def clear_runs(run_dirs: list[Path]) -> Path:
    """Move runs and their assessments to an archive folder. Nothing is deleted."""
    archive = CLEARED_ROOT / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive.mkdir(parents=True, exist_ok=False)
    run_ids = {run_dir.name for run_dir in run_dirs}
    for path, name in ((REVIEWS_PATH, "simple_reviews_cleared.csv"), (AI_PATH, "ai_review_cleared.csv")):
        rows = load_csv_rows(path)
        if not rows:
            continue
        moved = [row for row in rows if row.get("run_id") in run_ids]
        if moved:
            write_csv(archive / name, moved, list(rows[0]))
            write_csv(path, [row for row in rows if row.get("run_id") not in run_ids], list(rows[0]))
    for run_dir in run_dirs:
        shutil.move(str(run_dir), str(archive / run_dir.name))
    return archive


def show_generate_panel() -> None:
    st.title("Generate answers")
    st.caption("One run sends the questions to one model under one input condition.")
    st.markdown("**Model**")
    provider = st.selectbox("Provider", list(PROVIDERS))
    adapter = PROVIDERS[provider]
    if adapter == "openai_chat_completions":
        api_key = key_field(adapter, "API key (if the UCloud job requires one)")
    else:
        api_key = key_field(adapter, "API key")
    endpoint, version, model = "", "", ""
    if adapter in ("openai_chat_completions", "generic_http_json"):
        endpoint = st.text_input(
            "Endpoint",
            key=f"endpoint_{adapter}",
            placeholder="https://app-….cloud.sdu.dk/api/v1"
            if adapter == "openai_chat_completions"
            else "https://.../evaluate",
        ).strip()
        if adapter == "openai_chat_completions" and endpoint and not endpoint.rstrip("/").endswith("v1"):
            st.caption("A UCloud endpoint ends in /api/v1.")
    if adapter == "generic_http_json":
        version = st.text_input("System version", placeholder="Build, release or commit ID")
    else:
        models = st.session_state.get(f"models_{adapter}", [])
        if st.button("Load available models"):
            try:
                models = list_available_models(adapter, api_key, endpoint)
                st.session_state[f"models_{adapter}"] = models
            except Exception as exc:  # provider errors are shown, not raised
                st.error(f"The model list could not be loaded: {exc}")
        if models:
            model = st.selectbox("Model ID", models)
        else:
            model = st.text_input("Model ID", placeholder="Load the list or enter the model ID")

    st.markdown("**Input condition**")
    if adapter == "generic_http_json":
        mode = "self_retrieval"
        st.caption("The RAG system retrieves the source itself.")
        st.info("No endpoint? Open the page **Paste RAG answers** and paste the answers by hand.")
    else:
        condition = st.radio(
            "Input condition",
            ["Question only", "Question + correct source"],
            captions=[
                "Shows what the model knows by itself.",
                "Shows whether the model reads the source correctly.",
            ],
            label_visibility="collapsed",
        )
        mode = "closed_book" if condition == "Question only" else "gold_context"
    selected = sorted_cases
    with st.expander("Only one question (for testing)"):
        labels = [ALL_QUESTIONS] + [
            f"{question_number(c['case_id']):02d}. {c.get('topic', '')}" for c in sorted_cases
        ]
        choice = st.selectbox("Questions", labels, label_visibility="collapsed")
        if choice != ALL_QUESTIONS:
            selected = [sorted_cases[labels.index(choice) - 1]]

    if st.button(f"Generate {len(selected)} answers", type="primary", width="stretch"):
        if adapter != "generic_http_json" and not model:
            st.error("Select a model.")
            return
        if adapter in ("openai_responses", "anthropic_messages") and not api_key:
            st.error("Enter an API key.")
            return
        system = build_system(provider, model, api_key, endpoint, mode, version)
        with st.spinner(f"Generating {len(selected)} answers ..."):
            try:
                outputs = run_evaluation(system, selected)
                save_run(system, selected, outputs, NEW_RUNS, testcases_path=TESTCASES)
            except Exception as exc:  # show runner errors to the user
                st.error(f"The run failed: {exc}")
                return
        errors = sum(1 for o in outputs if o.get("error"))
        st.session_state["notice"] = f"Run saved: {len(outputs) - errors} answers, {errors} errors."
        st.session_state.pop("pos", None)
        load_material.clear()
        st.rerun()

    st.divider()
    st.markdown("**Runs in the current dataset**")
    runs = list_saved_runs(RUN_ROOTS)
    if not runs:
        st.caption("No runs yet.")
        return
    st.markdown("\n".join(f"- {run_label(run_dir)}" for run_dir in runs))
    st.caption("Archiving removes runs from the dataset, for example runs made with an earlier question wording.")
    with st.expander("Archive runs"):
        st.caption("Answers and their assessments are moved to outputs/v5_cleared; nothing is deleted.")
        assessed = {r.get("run_id") for r in reviews} | {r.get("run_id") for r in ai_rows}
        protected = [run_dir for run_dir in runs if run_dir.name in assessed]
        if protected:
            st.caption(
                f"{len(protected)} runs already have assessments and cannot be archived here: "
                + "; ".join(run_label(run_dir) for run_dir in protected)
            )
        labels = {run_label(run_dir): run_dir for run_dir in runs if run_dir not in protected}
        if not labels:
            st.caption("No runs without assessments.")
            return
        chosen = st.multiselect("Runs to archive", list(labels))
        sure = st.checkbox("I want to archive the selected runs", key="clear_sure")
        if st.button("Archive", disabled=not (chosen and sure)):
            archive = clear_runs([labels[label] for label in chosen])
            st.session_state["notice"] = f"{len(chosen)} runs archived in {archive.relative_to(ROOT)}."
            st.session_state.pop("pos", None)
            st.session_state.pop("clear_sure", None)
            load_material.clear()
            st.rerun()


# ================================================================= page 2: assess
def go_to(index: int) -> None:
    st.session_state["pos"] = index % len(queue)


def show_answer(output: dict, case: dict) -> dict:
    bundle = expected_source_bundle(case, gold, rubrics)
    left, right = st.columns(2, gap="large")
    with left, st.container(border=True):
        st.markdown("#### Model answer")
        content = str(output.get("content", ""))
        if output.get("error"):
            st.error(f"Generation error: {output['error']}")
        try:
            claims = parse_answer_claims(content)
        except ValueError:
            st.markdown(content)  # normal running text
        else:
            for number, claim in enumerate(claims, 1):
                st.markdown(f"**{number}.** {claim['claim']}")
                st.caption(f"Source: {claim['source_locator'] or 'none cited'}")
    with right, st.container(border=True):
        st.markdown("#### Correct source")
        for passage in bundle["passages"]:
            st.caption(passage.get("citation_label", ""))
            st.markdown(passage.get("text", ""))
        st.markdown("#### Expected answer")
        st.markdown(bundle["reference_answer_danish"])
        with st.expander("XHAILe determinations behind the question"):
            for determination in bundle["determinations"]:
                st.markdown(f"- {determination['determination_id']}: {determination['label']}")
    return bundle


def show_navigation(index: int) -> None:
    """Jump to a block, a question or the next unassessed answer."""
    done = {answer_key(r) for r in reviews if r.get("reviewer") == REVIEWER}
    parts = list(dict.fromkeys(part_name(row) for row in queue))
    members = {name: [i for i, row in enumerate(queue) if part_name(row) == name] for name in parts}

    def label(name: str) -> str:
        assessed = sum(1 for i in members[name] if answer_key(queue[i]) in done)
        return f"{name} ({assessed} of {len(members[name])} assessed)"

    current = part_name(queue[index])
    block, question, jump = st.columns([3, 2, 2], vertical_alignment="bottom")
    chosen = block.selectbox(
        "Block", parts, index=parts.index(current), format_func=label, key=f"nav_part_{index}"
    )
    if chosen != current:
        open_answers = [i for i in members[chosen] if answer_key(queue[i]) not in done]
        go_to((open_answers or members[chosen])[0])
        st.rerun()
    numbers = [question_number(queue[i]["case_id"]) for i in members[current]]
    mark = {n: ("✓ " if answer_key(queue[i]) in done else "") for n, i in zip(numbers, members[current])}
    picked = question.selectbox(
        "Question",
        numbers,
        index=members[current].index(index),
        format_func=lambda n: f"{mark[n]}Question {n}",
        key=f"nav_q_{index}",
    )
    if picked != numbers[members[current].index(index)]:
        go_to(members[current][numbers.index(picked)])
        st.rerun()
    remaining = len(queue) - len(done & {answer_key(row) for row in queue})
    if jump.button(
        f"Next unassessed ({remaining}) ▶", disabled=not remaining, width="stretch", type="primary"
    ):
        go_to(next_unreviewed(queue, reviews, REVIEWER, index))
        st.rerun()


def show_assess_page() -> None:
    if not queue:
        st.info("No answers yet. Generate answers in the left panel.")
        return
    if "pos" not in st.session_state:
        st.session_state["pos"] = max(next_unreviewed(queue, reviews, REVIEWER, -1), 0)
    show_navigation(st.session_state["pos"])
    index = st.session_state["pos"]
    output = queue[index]
    case = cases[output["case_id"]]
    key = answer_key(output)
    own = find_review(reviews, key, REVIEWER)
    locked = is_locked(own, ai_exists(ai_rows, key))

    place = part_position(queue, index)
    st.subheader(f"{place['name']} · answer {place['position']} of {place['size']}")
    current_question = str(case["model_input"]["question"])
    sent_prompt = str(output.get("prompt", ""))
    if sent_prompt and current_question not in sent_prompt:
        sent_question = sent_prompt.strip().split("\n\n")[-1]
        st.markdown(f"**Question {question_number(case['case_id'])}:** {sent_question}")
        st.warning(
            "This answer was generated with an earlier wording of the question. "
            "Archive the run in the left panel and generate new answers before assessing."
        )
    else:
        st.markdown(f"**Question {question_number(case['case_id'])}:** {current_question}")
    if own:
        st.success("Already assessed. The saved labels are shown.")

    bundle = show_answer(output, case)

    st.markdown("### Ten criteria")
    st.caption(
        "Choose one label per criterion. A short reason is required for Not met and Not assessable. "
        "If the answer cites no source: C4 Not met, C5 and C6 Not assessable."
    )
    choices: dict[str, tuple[str | None, str]] = {}
    widget = "|".join(key)
    for criterion in CRITERIA:
        with st.container(border=True):
            st.markdown(f"**{criterion_code(criterion)} · {NAMES[criterion]}** — {QUESTIONS[criterion]}")
            # Always visible (not folded), so the reviewer sees the rule before choosing a label.
            st.markdown(f"**Decision rule.** {HELP[criterion]}")
            if criterion in ANSWER_KEY_HELP:
                field, heading = ANSWER_KEY_HELP[criterion]
                st.markdown(heading)
                st.markdown("\n".join(f"- {item}" for item in bundle[field]))
                if criterion == "c02_required_elements_complete" and bundle["acceptable_answer_variants"]:
                    st.caption("Accepted variants: " + " · ".join(bundle["acceptable_answer_variants"]))
            saved_label = own.get(f"{criterion}_label") if own else None
            options = list(CHOICES)
            selected = st.radio(
                f"Label for {criterion_code(criterion)}",
                options,
                index=options.index(CHOICE_BY_LABEL[saved_label]) if saved_label else None,
                horizontal=True,
                key=f"{widget}|{criterion}",
                disabled=locked,
                label_visibility="collapsed",
            )
            label = CHOICES.get(selected) if selected else None
            reason = ""
            if label in ("not_met", "not_assessable"):
                reason = st.text_input(
                    "Reason (required)",
                    value=own.get(f"{criterion}_reason", "") if own else "",
                    key=f"{widget}|{criterion}|reason",
                    disabled=locked,
                )
            choices[criterion] = (label, reason)

    if locked:
        st.info("Locked: the LLM judge has already assessed this answer.")

    back, save, skip = st.columns(3)
    if back.button("◀ Previous", width="stretch"):
        go_to(index - 1)
        st.rerun()
    if save.button("Save and next ▶", type="primary", width="stretch", disabled=locked):
        try:
            row = make_review_row(output, REVIEWER, choices, date.today().isoformat())
        except ValueError as exc:
            st.error("Incomplete: " + str(exc))
        else:
            updated = save_review(REVIEWS_PATH, row)
            go_to(next_unreviewed(queue, updated, REVIEWER, index))
            st.rerun()
    if skip.button("Skip", width="stretch"):
        go_to(index + 1)
        st.rerun()


# ================================================================= page 3: LLM judge
def run_ai_judge(repeat: int, api_key: str) -> None:
    already = judged_keys(repeat)
    todo = [o for o in queue if answer_key(o) not in already and not o.get("error")]
    bar = st.progress(0.0, text="LLM judge starting ...")
    for number, output in enumerate(todo, 1):
        case = cases[output["case_id"]]
        rubric = rubrics[output["case_id"]]
        try:
            result = judge_answer(case, output, rubric, {"model": DEFAULT_MODEL, "_api_key": api_key}, repeat)
        except (RuntimeError, ValueError) as exc:
            st.warning(f"Question {question_number(output['case_id'])}: {exc}")
            continue
        raw_path = save_raw_ai_response(AI_RAW, output, result)
        save_ai_review(AI_PATH, build_ai_review_row(case, output, rubric, result, str(raw_path)))
        bar.progress(number / len(todo), text=f"Judging answer {number} of {len(todo)}")
    st.session_state["notice"] = f"LLM-judge run {repeat} completed."


def show_judge_page() -> None:
    st.subheader("LLM judge")
    st.caption(
        f"{DEFAULT_MODEL} assesses every answer on the same ten criteria without seeing your "
        "labels. It runs three times, so its stability can be measured."
    )
    if not queue:
        st.info("No answers yet. Generate answers in the left panel.")
        return

    with st.container(border=True):
        api_key = key_field("anthropic_messages", "Anthropic API key")
        if st.button("Check key", disabled=not api_key):
            try:
                available = list_available_models("anthropic_messages", api_key, "")
            except Exception as exc:  # provider errors are shown, not raised
                st.error(f"The key was rejected: {exc}")
            else:
                if DEFAULT_MODEL in available:
                    st.success(f"The key works, and {DEFAULT_MODEL} is available.")
                else:
                    st.warning(f"The key works, but {DEFAULT_MODEL} is not available to it.")

    remaining = len(queue) - count_done(queue, reviews, REVIEWER)
    if remaining:
        st.warning(
            f"The judge starts when all answers are assessed ({remaining} remaining). "
            "Assessed answers are locked once the judge has seen them."
        )
    answerable = [o for o in queue if not o.get("error")]
    columns = st.columns(3)
    for column, repeat in zip(columns, JUDGE_RUNS):
        done = sum(1 for o in answerable if answer_key(o) in judged_keys(repeat))
        with column, st.container(border=True):
            st.metric(f"Run {repeat}", f"{done} of {len(answerable)}")
            finished = done == len(answerable)
            if st.button(
                "Completed" if finished else f"Start run {repeat}",
                key=f"judge_{repeat}",
                disabled=bool(remaining) or finished or not api_key,
                width="stretch",
            ):
                run_ai_judge(repeat, api_key)
                st.rerun()


# ================================================================= page 4: results
def show_results_page() -> None:
    if not queue:
        st.info("No answers yet. Generate answers in the left panel.")
        return
    if not human:
        st.info("Results appear as soon as the first answer has been assessed.")
        return
    topics = {case_id: case.get("topic", "") for case_id, case in cases.items()}
    parts = list(dict.fromkeys(part_name(row) for row in queue))
    sizes = {name: sum(1 for row in queue if part_name(row) == name) for name in parts}

    st.subheader("Criteria per model and input condition")
    st.caption(
        "For each criterion: how many assessed answers were labelled met, not met and not "
        "assessable. Compare the columns to see what the correct source changes."
    )
    summary = table_criteria(human, parts, sizes)
    show_table(summary)

    st.subheader("Answer by answer")
    st.caption("✓ met · ✗ not met · ? not assessable · empty: not yet assessed. Legally adequate = C1 and C2 met.")
    part = st.selectbox("Model · input condition", parts)
    answers_by_part = {
        name: table_answers(human, name, topics, [row for row in queue if part_name(row) == name])
        for name in parts
    }
    show_table(answers_by_part[part])

    st.subheader("Human reference and LLM judge")
    ai_first = [r for r in ai_rows if str(r.get("repeat")) == "1"]
    agreement = table_agreement({"Human reference vs LLM judge (run 1)": (human, ai_first)}) if ai_first else []
    stability = table_stability(ai_rows) if ai_rows else []
    if not ai_first:
        st.caption("Appears after the first LLM-judge run.")
    else:
        st.caption("\"25 of 28\" = same label on 25 of 28 answers.")
        show_table(agreement, hide_kappa=True)
        st.markdown("**Stability across the three judge runs**")
        show_table(stability)

    # The CSV files in results/ feed the thesis tables; the download is for reading.
    RESULTS.mkdir(parents=True, exist_ok=True)
    combined = [
        {"Model · input condition": name, **row} for name, rows in answers_by_part.items() for row in rows
    ]
    for name, rows in (
        ("table1_answers.csv", combined),
        ("table2_summary.csv", summary),
        ("table3_agreement.csv", agreement),
        ("table4_stability.csv", stability),
        ("all_reviews.csv", human),
    ):
        if rows:
            write_csv(RESULTS / name, rows, list(rows[0]))
    st.divider()
    excel_download(
        "Download all results (Excel)",
        {
            "Criteria summary": summary,
            "Answers": combined,
            "Agreement (with kappa)": agreement,
            "Judge stability": stability,
            "Human labels": human,
        },
        "evaluation_results.xlsx",
    )


# ================================================================= page 5: about the questions
def show_about_page() -> None:
    st.subheader("Where the questions come from")
    st.markdown(
        "1. XHAILe provided **34 determinations** from the guidance on SU-handicaptillæg "
        "(VEJ nr. 9577 af 25/06/2025).\n"
        "2. **14 questions** cover 32 of them. A11 and A43 are left out because their labels "
        "do not match the guidance text.\n"
        "3. Each question is checked against the current guidance, VEJ nr. 10157 af 05/10/2026.\n"
        "4. The expected answers were written with the legal reviewer, Patrick Michel, and approved "
        "on 5 November 2026."
    )
    st.subheader("The 14 questions")
    for case in sorted_cases:
        number = question_number(case["case_id"])
        bundle = expected_source_bundle(case, gold, rubrics)
        with st.expander(f"{number:02d}. {case.get('topic', '')}"):
            st.markdown(f"> {case['model_input']['question']}")
            st.markdown("**XHAILe determinations**")
            st.markdown("\n".join(f"- {d['determination_id']}: {d['label']}" for d in bundle["determinations"]))
            st.markdown("**Correct source**")
            for passage in bundle["passages"]:
                st.caption(passage.get("citation_label", ""))
                st.markdown(passage.get("text", ""))
            st.markdown("**Expected answer**")
            st.markdown(bundle["reference_answer_danish"])
    st.subheader("The 34 XHAILe determinations")
    points_table = table_xhaile_points(gold, sorted_cases)
    show_table(points_table)
    excel_download(
        "Download questions and determinations (Excel)",
        {"Questions": table_questions(sorted_cases), "Determinations": points_table},
        "questions_and_determinations.xlsx",
    )


def show_manual_page() -> None:
    st.subheader("Paste answers from your own RAG system")
    st.markdown(
        "1. Fill in the system details below.\n"
        "2. For each question: start a **new conversation** in your RAG system, paste the question "
        "exactly as shown, and copy the full answer back here. If the system shows sources or links "
        "separately, paste them in the second field.\n"
        "3. Press **Save draft** as you go. When all 14 answers are filled in, press **Save as run**. "
        "The answers then appear under Assess like the other runs."
    )
    existing = [r for r in list_saved_runs(RUN_ROOTS) if r.name.endswith("self_retrieval")]
    if existing:
        st.warning("A self-retrieval run already exists: " + ", ".join(run_label(r) for r in existing))
    draft = load_draft(MANUAL_DRAFT)
    meta, answers = draft["meta"], draft["answers"]
    with st.container(border=True):
        st.markdown("**System details**")
        a, b, c = st.columns(3)
        meta["system_name"] = a.text_input("System name", meta.get("system_name", "Own RAG system"))
        meta["system_version"] = b.text_input(
            "Version or commit", meta.get("system_version", ""), placeholder="e.g. git commit or release"
        )
        meta["generator_model"] = c.text_input(
            "Answer model in the RAG system (if known)", meta.get("generator_model", "")
        )
        meta["entered_by"] = REVIEWER
    filled = 0
    for case in sorted_cases:
        cid = case["case_id"]
        entry = answers.setdefault(cid, {"answer": "", "sources": ""})
        done = bool(entry.get("answer", "").strip())
        filled += done
        number = question_number(cid)
        with st.expander(f"{'✓' if done else '·'} {number:02d}. {case.get('topic', '')}", expanded=not done and filled == number - 1):
            st.caption("Question to paste into the RAG system")
            st.code(case["model_input"]["question"], language=None, wrap_lines=True)
            new_answer = st.text_area("Answer from the RAG system", entry.get("answer", ""), key=f"man_a_{cid}", height=220)
            new_sources = st.text_area(
                "Sources or links shown separately (optional)", entry.get("sources", ""), key=f"man_s_{cid}", height=80
            )
            if new_answer != entry.get("answer") or new_sources != entry.get("sources"):
                entry.update(
                    {"answer": new_answer, "sources": new_sources, "entered_utc": datetime.now(timezone.utc).isoformat()}
                )
    # Count after the text areas have updated the entries, so the bar reflects what was just pasted.
    filled = sum(bool(answers.get(c["case_id"], {}).get("answer", "").strip()) for c in sorted_cases)
    st.progress(filled / len(sorted_cases), text=f"{filled} of {len(sorted_cases)} answers filled in")
    left, right = st.columns(2)
    if left.button("Save draft", width="stretch"):
        save_draft(MANUAL_DRAFT, draft)
        st.success("Draft saved.")
    problems = missing_fields(sorted_cases, answers, meta)
    if right.button("Save as run", type="primary", width="stretch", disabled=bool(problems)):
        save_draft(MANUAL_DRAFT, draft)
        run_dir = save_manual_run(NEW_RUNS, sorted_cases, answers, meta)
        MANUAL_DRAFT.rename(MANUAL_DRAFT.with_name(f"{run_dir.name}_draft.json"))
        st.session_state["notice"] = f"Run saved with {len(sorted_cases)} answers: {run_label(run_dir)}"
        st.session_state.pop("pos", None)
        load_material.clear()
        st.rerun()
    if problems:
        st.caption("Missing before you can save the run: " + ", ".join(problems))


# ================================================================= main
PAGES = {
    "Assess": show_assess_page,
    "LLM judge": show_judge_page,
    "Results": show_results_page,
    "About the questions": show_about_page,
    "Paste RAG answers": show_manual_page,
}

with st.sidebar:
    show_generate_panel()
st.title("Legal AI Answer Evaluation")
st.caption("SU-handicaptillæg · 14 questions derived from XHAILe's determinations")
if st.session_state.get("notice"):
    st.success(st.session_state.pop("notice"))
suggested = show_status()
page = st.radio(
    "Page", list(PAGES), index=suggested, horizontal=True, label_visibility="collapsed", key="page"
)
st.divider()
PAGES[page]()
