from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from Evaluation.scripts.create_judge_template_v5 import CRITERIA
from Evaluation.scripts.dashboard_v5 import (
    build_ai_review_row,
    find_ai_review,
    load_csv_rows,
    save_ai_review,
    save_raw_ai_response,
)
from Evaluation.scripts.run_llm_judge_v5 import judge_answer


class LlmJudgeV5Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.case = {
            "case_id": "test_case",
            "benchmark_id": "benchmark",
            "topic": "Emne",
            "model_input": {
                "question": "Hvad gælder?",
                "source_passages": [
                    {"citation_label": "VEJ 1", "text": "Kildetekst"}
                ],
            },
            "reference": {"determination_ids": ["A1"]},
        }
        self.output = {
            "run_id": "run_1",
            "case_id": "test_case",
            "input_mode": "closed_book",
            "system_id": "system",
            "content": "Et AI-svar",
        }
        self.rubric = {
            "reference_answer_danish": "Facit",
            "critical_elements_json": ["Element"],
            "supporting_elements_json": [],
            "material_errors_json": ["Fejl"],
            "acceptable_answer_variants_json": ["Acceptabel variant"],
            "required_qualifications_json": ["Forbehold"],
        }

    def valid_payload(self) -> dict[str, object]:
        return {
            "case_id": "test_case",
            "criteria": {
                criterion: {"label": "met", "reason": f"Grund {criterion}"}
                for criterion in CRITERIA
            },
            "xhaile_coverage": {
                "A1": {"label": "partial", "reason": "Delvist dækket"}
            },
            "overall_notes": "Samlet note",
        }

    def test_judge_is_blind_validates_all_fields_and_returns_metadata(self) -> None:
        prompts: list[str] = []

        def mock_provider(system, case, prompt):
            prompts.append(prompt)
            return {
                "content": json.dumps(self.valid_payload()),
                "raw_response": {
                    "ok": True,
                    "json": {"model": "mock-claude"},
                },
            }

        result = judge_answer(
            self.case,
            self.output,
            self.rubric,
            {
                "model": "mock-model",
                "human_labels": "HUMAN_SENTINEL",
                "_adapter": mock_provider,
            },
            2,
        )
        self.assertEqual(set(result["criteria"]), set(CRITERIA))
        self.assertEqual(result["xhaile_coverage"]["A1"]["label"], "partial")
        self.assertEqual(result["model_id"], "mock-claude")
        self.assertEqual(result["repeat"], 2)
        self.assertEqual(len(result["prompt_hash"]), 64)
        self.assertIn("Acceptabel variant", prompts[0])
        self.assertNotIn("HUMAN_SENTINEL", prompts[0])

    def test_judge_retries_invalid_json_at_most_twice(self) -> None:
        calls = 0

        def mock_provider(system, case, prompt):
            nonlocal calls
            calls += 1
            content = "ikke json" if calls < 3 else json.dumps(self.valid_payload())
            return {"content": content, "raw_response": {"ok": True}}

        result = judge_answer(
            self.case,
            self.output,
            self.rubric,
            {"_adapter": mock_provider},
            1,
        )
        self.assertEqual(calls, 3)
        self.assertEqual(result["attempts"], 3)

    def test_ai_review_and_raw_response_are_saved_by_repeat(self) -> None:
        result = {
            **self.valid_payload(),
            "raw_response": {"content": "råt"},
            "model_id": "mock-claude",
            "prompt_hash": "a" * 64,
            "judged_at": "2026-11-04T12:00:00+00:00",
            "repeat": 1,
            "attempts": 1,
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw_path = save_raw_ai_response(root / "raw", self.output, result)
            row = build_ai_review_row(
                self.case, self.output, self.rubric, result, str(raw_path)
            )
            csv_path = root / "ai_review.csv"
            save_ai_review(csv_path, row)
            restored = find_ai_review(
                load_csv_rows(csv_path), "run_1", "test_case", "closed_book", 1
            )
            self.assertIsNotNone(restored)
            self.assertEqual(restored["judge_type"], "llm")
            self.assertEqual(restored["repeat"], "1")
            self.assertEqual(restored["c10_legal_modality_precision_label"], "met")
            self.assertTrue(raw_path.is_file())


if __name__ == "__main__":
    unittest.main()
