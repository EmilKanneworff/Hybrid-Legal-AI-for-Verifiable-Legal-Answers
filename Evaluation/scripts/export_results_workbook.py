"""Export all V5 evaluation results to one Excel workbook.

Reads the human reference (outputs/v5_review/simple_reviews.csv), the LLM-judge
labels (outputs/v5_judge_c04_aligned/ai_review_c04_aligned.csv), the answer runs (outputs/final_v5) and
the provenance logs, and writes one sheet per table.

Run from the Evaluation folder:
    .venv/bin/python -m scripts.export_results_workbook [output.xlsx]
"""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from scripts.compare_judges_v5 import compare
from scripts.create_judge_template_v5 import CRITERIA
from scripts.dashboard_v5 import list_saved_runs, load_saved_run
from scripts.simple_review import MODE_DA, NAMES, criterion_code, question_number, short_model

ROOT = Path(__file__).resolve().parents[1]
REVIEW = ROOT / "outputs" / "v5_review"
RUNS = ROOT / "outputs" / "final_v5"
TESTCASES = ROOT / "benchmark" / "testcases_su_guidance_qa_v5.jsonl"
DEFAULT_OUT = ROOT.parent / "Testing" / "01_Results" / f"SU_evaluation_results_{date.today().isoformat()}.xlsx"

WORD = {"met": "Met", "not_met": "Not met", "not_assessable": "Not assessable"}
MODES = ["closed_book", "gold_context"]


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def changed_source_labels() -> list[dict[str, str]]:
    """Labels that differ between the first entry and the final human labels."""
    before = {
        (r["run_id"], r["case_id"]): r
        for r in read_csv(REVIEW / "simple_reviews_before_source_rule_2026-11-05.csv")
    }
    rows = []
    for r in read_csv(REVIEW / "simple_reviews.csv"):
        old = before.get((r["run_id"], r["case_id"]))
        if r.get("reviewer") != "human" or old is None:
            continue
        for key in r:
            if key.endswith("_label") and old.get(key) != r[key]:
                rows.append({
                    "run_id": r["run_id"], "case_id": r["case_id"],
                    "question_no": r.get("question_no", ""), "criterion": key[: -len("_label")],
                    "old_label": old.get(key, ""), "new_label": r[key],
                    "reason": r.get(key[: -len("_label")] + "_reason", ""),
                })
    return rows


def model_of(row: dict) -> str:
    return short_model(row.get("model") or row.get("requested_model") or row.get("system_id", ""))


def crit(criterion: str) -> str:
    return f"{criterion_code(criterion)} · {NAMES[criterion]}"


def blocks(rows: list[dict]) -> list[tuple[str, str]]:
    found = {(model_of(r), r["input_mode"]) for r in rows}
    return sorted(found, key=lambda b: (MODES.index(b[1]) if b[1] in MODES else 9, b[0]))


def in_block(rows: list[dict], block: tuple[str, str]) -> list[dict]:
    return [r for r in rows if (model_of(r), r["input_mode"]) == block]


def build(out_path: Path) -> Path:
    human = read_csv(REVIEW / "simple_reviews.csv")
    judge = read_csv(ROOT / "outputs" / "v5_judge_c04_aligned" / "ai_review_c04_aligned.csv")
    runs = {str(r.get("repeat") or r.get("coding_round")): [] for r in judge}
    for row in judge:
        runs[str(row.get("repeat") or row.get("coding_round"))].append(row)
    cases = {
        c["case_id"]: c
        for c in (json.loads(line) for line in TESTCASES.read_text(encoding="utf-8").splitlines() if line.strip())
    }
    outputs = []
    for run_dir in list_saved_runs([RUNS]):
        outputs.extend(load_saved_run(run_dir)[0])
    block_list = blocks(human)
    sheets: dict[str, list[dict]] = {}

    # 1 criteria summary ---------------------------------------------------
    rows = []
    for block in block_list:
        group = in_block(human, block)
        for criterion in CRITERIA:
            labels = Counter(r[f"{criterion}_label"] for r in group)
            rows.append({
                "Model": block[0], "Input condition": MODE_DA.get(block[1], block[1]), "Criterion": crit(criterion),
                "Met": labels["met"], "Not met": labels["not_met"], "Not assessable": labels["not_assessable"],
                "Answers": len(group), "Met (%)": round(100 * labels["met"] / len(group), 1) if group else "",
            })
    sheets["1 Criteria summary"] = rows

    # 2 legally adequate -----------------------------------------------------
    sheets["2 Legally adequate"] = [
        {
            "Model": block[0], "Input condition": MODE_DA.get(block[1], block[1]),
            "Legally adequate (C1 and C2 met)": sum(
                1 for r in in_block(human, block)
                if r["c01_overall_legal_correctness_label"] == "met" and r["c02_required_elements_complete_label"] == "met"
            ),
            "Answers": len(in_block(human, block)),
        }
        for block in block_list
    ]

    # 3 effect of the correct source ------------------------------------------
    rows = []
    for model in sorted({b[0] for b in block_list}):
        without = in_block(human, (model, "closed_book"))
        with_source = in_block(human, (model, "gold_context"))
        for criterion in CRITERIA:
            a = sum(1 for r in without if r[f"{criterion}_label"] == "met")
            b = sum(1 for r in with_source if r[f"{criterion}_label"] == "met")
            rows.append({"Model": model, "Criterion": crit(criterion), "Met · question only": a,
                         "Met · correct source supplied": b, "Change": b - a,
                         "Answers per condition": len(without)})
    sheets["3 Effect of the source"] = rows

    # 4 agreement human vs judge, per run, per block and overall -------------
    rows = []
    scopes = [("All answers", None)] + [(f"{b[0]} · {MODE_DA.get(b[1], b[1])}", b) for b in block_list]
    for scope_name, block in scopes:
        h = human if block is None else in_block(human, block)
        line_by_criterion: dict[str, dict] = {}
        for repeat in sorted(runs):
            j = runs[repeat] if block is None else in_block(runs[repeat], block)
            for result in compare(h, j):
                key = result["criterion"]
                line = line_by_criterion.setdefault(key, {
                    "Scope": scope_name,
                    "Criterion": "All ten criteria" if key == "all_criteria" else crit(key),
                    "Paired answers": result["paired_item_count"],
                })
                line[f"Run {repeat} · agreement"] = result["agreement_count"]
                line[f"Run {repeat} · agreement (%)"] = result["raw_agreement_pct"]
                line[f"Run {repeat} · Cohen's kappa"] = result["cohen_kappa"] if result["cohen_kappa"] != "" else "not estimable"
        rows.extend(line_by_criterion.values())
    sheets["4 Agreement"] = rows

    # 5 direction of disagreement (run 1) -------------------------------------
    first = {(r["run_id"], r["case_id"], r["input_mode"]): r for r in runs.get("1", [])}
    rows = []
    for scope_name, block in scopes:
        h = human if block is None else in_block(human, block)
        for criterion in CRITERIA:
            pairs = Counter()
            for r in h:
                other = first.get((r["run_id"], r["case_id"], r["input_mode"]))
                if other:
                    pairs[(r[f"{criterion}_label"], other[f"{criterion}_label"])] += 1
            line = {"Scope": scope_name, "Criterion": crit(criterion)}
            for hl in WORD:
                for jl in WORD:
                    line[f"Human {WORD[hl]} / judge {WORD[jl]}"] = pairs[(hl, jl)]
            rows.append(line)
    sheets["5 Disagreement direction"] = rows

    # 6 judge stability across three runs ------------------------------------
    by_answer: dict[tuple, dict[str, dict]] = {}
    for row in judge:
        key = (row["run_id"], row["case_id"], row["input_mode"])
        by_answer.setdefault(key, {})[str(row.get("repeat") or row.get("coding_round"))] = row
    complete = {k: v for k, v in by_answer.items() if {"1", "2", "3"} <= set(v)}
    rows = []
    for scope_name, block in scopes:
        keys = [k for k, v in complete.items() if block is None or (model_of(v["1"]), v["1"]["input_mode"]) == block]
        for criterion in CRITERIA:
            same = sum(1 for k in keys if len({complete[k][r][f"{criterion}_label"] for r in "123"}) == 1)
            rows.append({"Scope": scope_name, "Criterion": crit(criterion),
                         "Identical label in all three runs": same, "Answers": len(keys),
                         "Stable (%)": round(100 * same / len(keys), 1) if keys else ""})
    sheets["6 Judge stability"] = rows

    # 7 every disagreement (run 1), for qualitative reading ---------------------
    rows = []
    for r in human:
        other = first.get((r["run_id"], r["case_id"], r["input_mode"]))
        if not other:
            continue
        for criterion in CRITERIA:
            if r[f"{criterion}_label"] != other[f"{criterion}_label"]:
                rows.append({
                    "Model": model_of(r), "Input condition": MODE_DA.get(r["input_mode"], r["input_mode"]),
                    "Question": question_number(r["case_id"]), "Criterion": crit(criterion),
                    "Human label": WORD.get(r[f"{criterion}_label"], ""), "Human reason": r[f"{criterion}_reason"],
                    "Judge label (run 1)": WORD.get(other[f"{criterion}_label"], ""),
                    "Judge reason (run 1)": other[f"{criterion}_reason"],
                })
    sheets["7 Disagreements run 1"] = rows

    # 8 human labels, 9 judge labels -----------------------------------------
    def long(rows_in: list[dict], with_run: bool) -> list[dict]:
        out = []
        for r in rows_in:
            for criterion in CRITERIA:
                line = {"Model": model_of(r), "Input condition": MODE_DA.get(r["input_mode"], r["input_mode"]),
                        "Question": question_number(r["case_id"])}
                if with_run:
                    line["Run"] = int(r.get("repeat") or r.get("coding_round"))
                line.update({"Criterion": crit(criterion), "Label": WORD.get(r[f"{criterion}_label"], ""),
                             "Reason": r[f"{criterion}_reason"]})
                out.append(line)
        return sorted(out, key=lambda x: tuple(str(v) for v in x.values())[:5])
    sheets["8 Human labels"] = long(human, False)
    sheets["9 Judge labels"] = long(judge, True)

    # 10 answers --------------------------------------------------------------
    sheets["10 Answers"] = sorted(
        [
            {"Model": model_of(o), "Input condition": MODE_DA.get(o["input_mode"], o["input_mode"]),
             "Question": question_number(o["case_id"]), "Topic": cases.get(o["case_id"], {}).get("topic", ""),
             "Question text": cases.get(o["case_id"], {}).get("model_input", {}).get("question", ""),
             "Model answer": o.get("content", ""), "Run ID": o.get("run_id", "")}
            for o in outputs
        ],
        key=lambda x: (x["Input condition"], x["Model"], x["Question"]),
    )

    # 11 provenance ------------------------------------------------------------
    sheets["11 Provenance"] = read_csv(REVIEW / "human_label_provenance.csv")
    sheets["12 Changed source labels"] = changed_source_labels()

    readme = [
        {"Sheet": "1 Criteria summary", "Content": "Human reference: count of Met / Not met / Not assessable per criterion, model and input condition."},
        {"Sheet": "2 Legally adequate", "Content": "Answers where C1 and C2 are both Met."},
        {"Sheet": "3 Effect of the source", "Content": "Met without source vs. with the correct source, per model and criterion."},
        {"Sheet": "4 Agreement", "Content": "Human reference vs. LLM judge (Claude Sonnet 5.5), runs 1-3: agreement count, % and Cohen's kappa. Run 1 is the protocol comparison; runs 2-3 show robustness."},
        {"Sheet": "5 Disagreement direction", "Content": "Cross-tabulation of human and judge labels (run 1)."},
        {"Sheet": "6 Judge stability", "Content": "Answers where the judge gave the identical label in all three runs."},
        {"Sheet": "7 Disagreements run 1", "Content": "Every human-judge disagreement with both reasons, for qualitative reading."},
        {"Sheet": "8 Human labels", "Content": "All human labels and reasons."},
        {"Sheet": "9 Judge labels", "Content": "All LLM-judge labels and reasons, runs 1-3."},
        {"Sheet": "10 Answers", "Content": "The question and the full model answer for every answer."},
        {"Sheet": "11 Provenance", "Content": "Where each block of human labels comes from."},
        {"Sheet": "12 Changed source labels", "Content": "Three source labels that changed on 5 November 2026 once the source rule was clear to the legal reviewer, with the first and final value."},
        {"Sheet": "", "Content": ""},
        {"Sheet": "Generated", "Content": f"{date.today().isoformat()} by Evaluation/scripts/export_results_workbook.py"},
        {"Sheet": "Answers", "Content": f"{len(human)} human-assessed answers; {len(judge)} judge assessments ({len(runs)} runs)."},
        {"Sheet": "Rule", "Content": "If an answer cites no source: C4 Not met, C5 and C6 Not assessable."},
    ]
    write_workbook(out_path, {"Read me": readme, **sheets})
    return out_path


def write_workbook(path: Path, sheets: dict[str, list[dict]]) -> None:
    wb = Workbook()
    wb.remove(wb.active)
    header_fill = PatternFill("solid", fgColor="DDE3EA")
    for name, rows in sheets.items():
        ws = wb.create_sheet(name[:31])
        if not rows:
            ws.append(["No data"])
            continue
        columns = list(rows[0])
        ws.append(columns)
        for row in rows:
            ws.append([row.get(c, "") for c in columns])
        for cell in ws[1]:
            cell.font = Font(bold=True)
            cell.fill = header_fill
            cell.alignment = Alignment(wrap_text=True, vertical="top")
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
        for index, column in enumerate(columns, 1):
            longest = max(len(str(column)), *(len(str(r.get(column, ""))) for r in rows))
            width = min(max(longest + 2, 10), 80)
            ws.column_dimensions[get_column_letter(index)].width = width
            if longest > 80:
                for cell in ws[get_column_letter(index)][1:]:
                    cell.alignment = Alignment(wrap_text=True, vertical="top")
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
    print(f"Wrote {build(target)}")
