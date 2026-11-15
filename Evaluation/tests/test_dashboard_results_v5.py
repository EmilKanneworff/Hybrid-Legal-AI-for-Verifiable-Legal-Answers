from __future__ import annotations

import io
import unittest

from openpyxl import load_workbook

from Evaluation.scripts.create_judge_template_v5 import CRITERIA
from Evaluation.scripts.dashboard_v5 import (
    build_coverage_comparison,
    build_criteria_matrix,
    build_human_review_row,
    create_lawyer_excel,
    import_lawyer_excel,
)


class DashboardResultsV5Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.case = {
            "case_id": "q1",
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
            "case_id": "q1",
            "input_mode": "closed_book",
            "system_id": "system",
            "content": "AI-svar",
        }
        self.rubric = {
            "reference_answer_danish": "Facit",
            "critical_elements_json": [],
            "supporting_elements_json": [],
            "material_errors_json": [],
            "acceptable_answer_variants_json": [],
            "required_qualifications_json": [],
        }
        decisions = {
            criterion: {"label": "met", "reason": f"Grund {criterion}"}
            for criterion in CRITERIA
        }
        self.human = build_human_review_row(
            self.case,
            self.output,
            self.rubric,
            decisions,
            {"A1": "yes"},
            "EK",
            "2026-11-04",
            False,
            "",
        )
        self.ai = dict(self.human)
        self.ai["judge_type"] = "llm"
        self.ai["c01_overall_legal_correctness_label"] = "not_met"
        self.ai["xhaile_coverage_json"] = '{"A1": "partial"}'

    def test_criteria_and_coverage_tables_mark_disagreement(self) -> None:
        matrix = build_criteria_matrix(
            [self.output], {"q1": self.case}, [self.human], [self.ai]
        )
        self.assertIn("Uenig", matrix[0]["C01"])
        self.assertIn("Enig", matrix[0]["C02"])
        coverage = build_coverage_comparison(
            [self.output], {"q1": self.case}, [self.human], [self.ai]
        )
        self.assertEqual(coverage[0]["Menneske"], "Ja")
        self.assertEqual(coverage[0]["AI"], "Delvist")
        self.assertEqual(coverage[0]["Sammenligning"], "Uenig")

    def test_ai_labels_remain_hidden_without_a_human_review(self) -> None:
        matrix = build_criteria_matrix(
            [self.output], {"q1": self.case}, [], [self.ai]
        )
        self.assertEqual(matrix[0]["C01"], "Menneske: — | AI: —")

    def test_excel_roundtrip_applies_lawyer_correction_separately(self) -> None:
        excel = create_lawyer_excel(
            [self.output],
            {"q1": self.case},
            {"q1": self.rubric},
            {"A1": {"label": "Punkt et"}},
            [self.human],
        )
        workbook = load_workbook(io.BytesIO(excel))
        sheet = workbook.active
        headers = {cell.value: cell.column for cell in sheet[1]}
        sheet.cell(2, headers["Kontrolleret af jurist"], "Ja")
        sheet.cell(2, headers["C01 Juristens rettelse"], "Ikke opfyldt")
        sheet.cell(2, headers["C01 Juristens begrundelse"], "Juridisk rettelse")
        buffer = io.BytesIO()
        workbook.save(buffer)

        checked = import_lawyer_excel(buffer.getvalue(), [self.human])
        self.assertEqual(
            checked[0]["c01_overall_legal_correctness_label"], "not_met"
        )
        self.assertEqual(
            checked[0]["c01_overall_legal_correctness_reason"],
            "Juridisk rettelse",
        )
        self.assertEqual(
            self.human["c01_overall_legal_correctness_label"], "met"
        )

    def test_lawyer_excel_skips_no(self) -> None:
        excel = create_lawyer_excel(
            [self.output], {"q1": self.case}, {"q1": self.rubric}, {}, [self.human]
        )
        self.assertEqual(import_lawyer_excel(excel, [self.human]), [])

    def test_lawyer_excel_skips_empty_check(self) -> None:
        excel = create_lawyer_excel(
            [self.output], {"q1": self.case}, {"q1": self.rubric}, {}, [self.human]
        )
        workbook = load_workbook(io.BytesIO(excel))
        sheet = workbook.active
        headers = {cell.value: cell.column for cell in sheet[1]}
        sheet.cell(2, headers["Kontrolleret af jurist"], "")
        buffer = io.BytesIO()
        workbook.save(buffer)
        self.assertEqual(import_lawyer_excel(buffer.getvalue(), [self.human]), [])

    def test_lawyer_excel_empty_correction_means_agreement(self) -> None:
        excel = create_lawyer_excel(
            [self.output], {"q1": self.case}, {"q1": self.rubric}, {}, [self.human]
        )
        workbook = load_workbook(io.BytesIO(excel))
        sheet = workbook.active
        headers = {cell.value: cell.column for cell in sheet[1]}
        sheet.cell(2, headers["Kontrolleret af jurist"], "Ja")
        buffer = io.BytesIO()
        workbook.save(buffer)

        checked = import_lawyer_excel(buffer.getvalue(), [self.human])
        self.assertEqual(checked[0]["c01_overall_legal_correctness_label"], "met")
        self.assertEqual(checked[0]["coding_round"], "legal_check")


if __name__ == "__main__":
    unittest.main()
