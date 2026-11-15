from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from Evaluation.scripts.dashboard_v5 import (
    automatic_source_label,
    build_human_review_row,
    expected_source_bundle,
    find_human_review,
    list_saved_runs,
    load_csv_rows,
    load_coverage,
    load_saved_run,
    parse_answer_claims,
    save_ai_review,
    save_human_review,
    saved_run_label,
    selected_case_ids,
)
from Evaluation.scripts.create_judge_template_v5 import CRITERIA


class DashboardV5SelectionTests(unittest.TestCase):
    def test_lists_only_run_folders_with_outputs_newest_first(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "final_v5"
            (root / "20260101_old").mkdir(parents=True)
            (root / "20260101_old" / "outputs.jsonl").write_text("{}\n")
            (root / "20260102_new").mkdir()
            (root / "20260102_new" / "outputs.jsonl").write_text("{}\n")
            (root / "not_a_run").mkdir()
            self.assertEqual(
                [path.name for path in list_saved_runs([root])],
                ["20260102_new", "20260101_old"],
            )

    def test_loads_saved_output_and_adds_run_id_from_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "run"
            run_dir.mkdir()
            (run_dir / "outputs.jsonl").write_text(
                json.dumps({"case_id": "case_1"}) + "\n", encoding="utf-8"
            )
            (run_dir / "run_metadata.json").write_text(
                json.dumps({"run_id": "recorded_run"}), encoding="utf-8"
            )
            outputs, metadata = load_saved_run(run_dir)
            self.assertEqual(outputs[0]["run_id"], "recorded_run")
            self.assertEqual(metadata["run_id"], "recorded_run")

    def test_selection_is_one_question_or_all_questions(self) -> None:
        ids = ["q1", "q2", "q3"]
        self.assertEqual(selected_case_ids("q2", False, ids), ["q2"])
        self.assertEqual(selected_case_ids("q2", True, ids), ids)

    def test_saved_run_label_names_generation(self) -> None:
        path = Path("Evaluation/outputs/final_v4/run_id")
        self.assertEqual(saved_run_label(path), "V4 · run_id")

    def test_parses_claims_and_source_locators(self) -> None:
        claims = parse_answer_claims(
            json.dumps(
                {"legal_claims": [{"claim": "Regel A", "source_locator": "Kilde 1"}]}
            )
        )
        self.assertEqual(
            claims, [{"claim": "Regel A", "source_locator": "Kilde 1"}]
        )

    def test_rejects_invalid_answer_contract(self) -> None:
        with self.assertRaisesRegex(ValueError, "legal_claims"):
            parse_answer_claims(json.dumps({"answer": "tekst"}))

    def test_maps_automatic_source_status_to_three_danish_labels(self) -> None:
        self.assertEqual(automatic_source_label("benchmark_source"), "Kilde fundet")
        self.assertEqual(automatic_source_label("official_framework"), "Kilde fundet")
        self.assertEqual(automatic_source_label("missing"), "Ingen kilde angivet")
        self.assertEqual(
            automatic_source_label("unknown"), "Kilde ikke fundet automatisk"
        )

    def test_expected_source_uses_gold_labels_passages_and_rubric(self) -> None:
        case = {
            "case_id": "q1",
            "model_input": {"source_passages": [{"citation_label": "VEJ 1"}]},
            "reference": {"determination_ids": ["A1"]},
        }
        gold = {"A1": {"determination_id": "A1", "label": "Punkt et"}}
        rubric = {
            "q1": {
                "reference_answer_danish": "Facit",
                "critical_elements_json": ["Kritisk"],
                "material_errors_json": ["Fejl"],
                "acceptable_answer_variants_json": ["Variant"],
                "required_qualifications_json": ["Forbehold"],
            }
        }
        bundle = expected_source_bundle(case, gold, rubric)
        self.assertEqual(bundle["determinations"][0]["label"], "Punkt et")
        self.assertEqual(bundle["passages"][0]["citation_label"], "VEJ 1")
        self.assertEqual(bundle["reference_answer_danish"], "Facit")
        self.assertEqual(bundle["acceptable_answer_variants"], ["Variant"])

    def test_human_review_validates_saves_and_restores_one_answer(self) -> None:
        case = {
            "case_id": "q1",
            "benchmark_id": "benchmark",
            "topic": "Emne",
            "model_input": {"question": "Spørgsmål?", "source_passages": []},
            "reference": {"determination_ids": ["A1", "A2"]},
        }
        output = {
            "run_id": "run_1",
            "case_id": "q1",
            "input_mode": "closed_book",
            "system_id": "system",
            "content": "Svar",
        }
        rubric = {
            "reference_answer_danish": "Facit",
            "critical_elements_json": [],
            "material_errors_json": [],
            "acceptable_answer_variants_json": [],
            "required_qualifications_json": [],
        }
        decisions = {
            criterion: {"label": "met", "reason": f"Grund {criterion}"}
            for criterion in CRITERIA
        }
        row = build_human_review_row(
            case,
            output,
            rubric,
            decisions,
            {"A1": "yes", "A2": "partial"},
            "EK",
            "2026-11-04",
            True,
            "Tjek A2",
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "human_review.csv"
            save_human_review(path, row)
            restored = find_human_review(
                load_csv_rows(path), "run_1", "q1", "closed_book"
            )
            self.assertIsNotNone(restored)
            self.assertEqual(restored["c01_overall_legal_correctness_label"], "met")
            self.assertEqual(load_coverage(restored), {"A1": "yes", "A2": "partial"})
            self.assertEqual(restored["send_to_legal_reviewer"], "yes")

    def test_human_review_requires_a_reason_for_every_criterion(self) -> None:
        decisions = {
            criterion: {"label": "met", "reason": "Begrundelse"}
            for criterion in CRITERIA
        }
        decisions[CRITERIA[0]]["reason"] = ""
        with self.assertRaisesRegex(ValueError, "begrundelse"):
            build_human_review_row(
                {
                    "case_id": "q1",
                    "model_input": {"question": "Q"},
                    "reference": {"determination_ids": ["A1"]},
                },
                {
                    "run_id": "run",
                    "input_mode": "closed_book",
                    "system_id": "system",
                },
                {},
                decisions,
                {"A1": "yes"},
                "EK",
                "2026-11-04",
                False,
                "",
            )


if __name__ == "__main__":
    unittest.main()
