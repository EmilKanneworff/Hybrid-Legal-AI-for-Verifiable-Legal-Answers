from __future__ import annotations

import copy
import csv
import unittest
from pathlib import Path

from Evaluation.scripts.compare_judges_v5 import compare
from Evaluation.scripts.create_judge_template_v5 import (
    CRITERIA,
    create_judge_rows,
    load_jsonl,
    load_selection,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
TESTCASES = REPO_ROOT / "Evaluation" / "benchmark" / "testcases_su_guidance_qa_v5.jsonl"
SELECTION = REPO_ROOT / "Evaluation" / "benchmark" / "judge_subset_su_guidance_v5.csv"


class V5JudgePipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cases = load_jsonl(TESTCASES)
        cls.cases_by_id = {case["case_id"]: case for case in cls.cases}
        cls.selection = load_selection(SELECTION)

    def outputs(self) -> list[dict]:
        return [
            {
                "run_id": "run_v4_parent",
                "case_id": case["case_id"],
                "system_id": "test_system",
                "requested_model": "test-model",
                "provider_model": "test-model-2026",
                "input_mode": "gold_context",
                "content": '{"legal_claims": []}',
                "error": None,
            }
            for case in self.cases
        ]

    def test_selection_has_ten_included_and_four_excluded(self) -> None:
        with SELECTION.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 14)
        self.assertEqual(sum(row["included_in_v5"] == "yes" for row in rows), 10)
        self.assertEqual(sum(row["included_in_v5"] == "no" for row in rows), 4)
        self.assertEqual([int(row["v5_order"]) for row in self.selection], list(range(1, 11)))

    def test_template_selects_ten_answers_in_predeclared_order(self) -> None:
        rows = create_judge_rows(self.outputs(), self.cases_by_id, self.selection)
        self.assertEqual(len(rows), 10)
        self.assertEqual([int(row["v5_order"]) for row in rows], list(range(1, 11)))
        self.assertEqual(rows[0]["case_id"], "xsu_sg_001_general_conditions")
        self.assertEqual(rows[-1]["case_id"], "xsu_sg_014_occupational_injury_opinion")
        for row in rows:
            self.assertNotEqual(row["supporting_elements_json"], "")
            self.assertNotEqual(row["acceptable_answer_variants_json"], "")
            for criterion in CRITERIA:
                self.assertEqual(row[f"{criterion}_label"], "")
                self.assertEqual(row[f"{criterion}_reason"], "")

    def test_template_rejects_duplicate_selected_answer(self) -> None:
        outputs = self.outputs()
        outputs.append(copy.deepcopy(outputs[0]))
        with self.assertRaisesRegex(ValueError, "duplicate V5 answer keys"):
            create_judge_rows(outputs, self.cases_by_id, self.selection)

    def test_comparison_reports_agreement_disagreement_and_missing(self) -> None:
        base = create_judge_rows(self.outputs(), self.cases_by_id, self.selection)[:2]
        human = copy.deepcopy(base)
        llm = copy.deepcopy(base)
        for rows in (human, llm):
            for row in rows:
                for criterion in CRITERIA:
                    row[f"{criterion}_label"] = "met"
        llm[1][f"{CRITERIA[0]}_label"] = "not_met"
        llm[1][f"{CRITERIA[1]}_label"] = ""

        results = compare(human, llm)
        first = results[0]
        second = results[1]
        pooled = results[-1]
        self.assertEqual(first["paired_item_count"], 2)
        self.assertEqual(first["agreement_count"], 1)
        self.assertEqual(first["disagreement_count"], 1)
        self.assertEqual(first["raw_agreement_pct"], 50.0)
        self.assertEqual(second["paired_item_count"], 1)
        self.assertEqual(second["missing_or_invalid_pair_count"], 1)
        self.assertEqual(pooled["eligible_item_count"], 20)
        self.assertEqual(pooled["paired_item_count"], 19)

    def test_comparison_rejects_duplicate_answer_keys(self) -> None:
        rows = create_judge_rows(self.outputs(), self.cases_by_id, self.selection)
        with self.assertRaisesRegex(ValueError, "duplicate answer keys"):
            compare(rows + [copy.deepcopy(rows[0])], rows)


if __name__ == "__main__":
    unittest.main()
