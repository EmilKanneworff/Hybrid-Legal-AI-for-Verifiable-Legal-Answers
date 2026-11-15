import tempfile
import unittest
from pathlib import Path

from Evaluation.scripts.create_judge_template_v5 import CRITERIA
from Evaluation.scripts import simple_review as sr


def output(case_no: int, mode: str = "closed_book", run: str = "run1") -> dict:
    return {
        "run_id": run,
        "case_id": f"xsu_sg_{case_no:03d}_topic",
        "input_mode": mode,
        "requested_model": "gpt-test",
    }


def all_yes() -> dict:
    return {criterion: ("met", "") for criterion in CRITERIA}


def row(reviewer: str, case_no: int, labels: dict | None = None, mode: str = "closed_book") -> dict:
    choices = all_yes()
    for criterion, label in (labels or {}).items():
        choices[criterion] = (label, "grund")
    return sr.make_review_row(output(case_no, mode), reviewer, choices, "2026-11-05")


class SimpleReviewTests(unittest.TestCase):
    def test_queue_is_in_parts_by_condition(self):
        queue = sr.build_queue(
            [output(2, "gold_context"), output(1, "gold_context"), output(2), output(1)]
        )
        self.assertEqual(
            [(o["input_mode"], sr.question_number(o["case_id"])) for o in queue],
            [("closed_book", 1), ("closed_book", 2), ("gold_context", 1), ("gold_context", 2)],
        )
        place = sr.part_position(queue, 2)
        self.assertEqual((place["part"], place["parts"], place["position"], place["size"]), (2, 2, 1, 2))
        self.assertEqual(place["name"], "gpt-test · Correct source supplied")

    def test_reason_needed_only_for_no_and_cannot_assess(self):
        choices = all_yes()
        self.assertEqual(sr.missing_choices(choices), [])
        choices["c01_overall_legal_correctness"] = ("not_met", "")
        choices["c02_required_elements_complete"] = (None, "")
        problems = sr.missing_choices(choices)
        self.assertEqual(len(problems), 2)
        self.assertTrue(problems[0].startswith("C1:"))
        self.assertTrue(problems[1].startswith("C2:"))

    def test_two_reviewers_do_not_overwrite_each_other(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "reviews.csv"
            sr.save_review(path, row("human", 1))
            sr.save_review(path, row("other", 1, {"c01_overall_legal_correctness": "not_met"}))
            sr.save_review(path, row("human", 1, {"c03_direct_relevance": "not_met"}))
            rows = sr.load_reviews(path)
            self.assertEqual(len(rows), 2)
            key = sr.answer_key(output(1))
            first = sr.find_review(rows, key, "human")
            second = sr.find_review(rows, key, "other")
            self.assertEqual(first["c03_direct_relevance_label"], "not_met")
            self.assertEqual(second["c01_overall_legal_correctness_label"], "not_met")

    def test_lock_only_after_own_review_and_ai_review(self):
        self.assertFalse(sr.is_locked(None, True))
        self.assertFalse(sr.is_locked({"x": 1}, False))
        self.assertTrue(sr.is_locked({"x": 1}, True))

    def test_next_unreviewed_skips_done_answers(self):
        queue = sr.build_queue([output(1), output(2), output(3)])
        reviews = [row("human", 2)]
        self.assertEqual(sr.next_unreviewed(queue, reviews, "human", 0), 2)
        self.assertEqual(sr.next_unreviewed(queue, reviews, "other", 0), 1)

    def test_table_criteria_counts_met_and_legally_sound(self):
        rows = [
            row("other", 1),
            row("other", 2, {"c01_overall_legal_correctness": "not_met"}),
            row("other", 3, {"c01_overall_legal_correctness": "not_assessable"}),
        ]
        table = sr.table_criteria(rows)
        column = "gpt-test · Question only"
        self.assertEqual(table[0][column], "1 met · 1 not met · 1 not assessable")
        self.assertEqual(table[1][column], "3 met")
        self.assertEqual(table[-1][column], "1 of 3")

    def test_table_answers_has_one_row_per_question_and_a_total(self):
        rows = [
            row("human", 2, {"c01_overall_legal_correctness": "not_met"}),
            row("human", 1),
            row("human", 1, mode="gold_context"),
        ]
        table = sr.table_answers(rows, "gpt-test · Question only", {"xsu_sg_001_topic": "Emne"})
        self.assertEqual([r["Question"] for r in table], ["01. Emne", "02. ", "Total ✓ (of 2)"])
        self.assertEqual((table[0]["C1"], table[1]["C1"], table[2]["C1"]), ("✓", "✗", "1"))
        self.assertEqual((table[0]["Legally adequate"], table[1]["Legally adequate"]), ("Yes", "No"))
        self.assertEqual(sr.parts_of(rows), ["gpt-test · Question only", "gpt-test · Correct source supplied"])

    def test_table_agreement_uses_only_common_answers(self):
        first = [row("human", 1), row("human", 2)]
        second = [row("other", 1, {"c01_overall_legal_correctness": "not_met"})]
        table = sr.table_agreement({"Par": (first, second), "Tom": ([], second)})
        self.assertTrue(table[0]["Par"].startswith("0 of 1"))
        self.assertTrue(table[1]["Par"].startswith("1 of 1"))
        self.assertEqual(table[0]["Tom"], "—")
        self.assertIn("Par · kappa", table[0])

    def test_table_stability_needs_three_repeats(self):
        base = row("human", 1)
        ai = [dict(base, repeat=str(r)) for r in (1, 2, 3)]
        ai[2]["c01_overall_legal_correctness_label"] = "not_met"
        table = sr.table_stability(ai)
        self.assertEqual(table[0]["Identical label in all three runs"], "0 of 1")
        self.assertEqual(table[1]["Identical label in all three runs"], "1 of 1")
        self.assertEqual(sr.table_stability(ai[:2])[0]["Identical label in all three runs"], "—")


class ChecklistTests(unittest.TestCase):
    def test_checklist_is_saved_and_loaded(self):
        ticks = {"c02_required_elements_complete": [True, False]}
        saved = sr.make_review_row(output(1), "human", all_yes(), "2026-11-05", ticks)
        self.assertEqual(sr.load_checklist(saved), ticks)
        self.assertEqual(sr.load_checklist({"checklist_json": ""}), {})


class QuestionsAndDataTests(unittest.TestCase):
    def setUp(self):
        import json
        root = Path(__file__).resolve().parents[1] / "benchmark"
        self.cases = [
            json.loads(line)
            for line in (root / "testcases_su_guidance_qa_v5.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        self.gold = {
            row["determination_id"]: row
            for row in (
                json.loads(line)
                for line in (root / "gold_determinations_su_v1.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            )
        }

    def test_fourteen_questions_with_full_text(self):
        rows = sr.table_questions(self.cases)
        self.assertEqual(len(rows), 14)
        self.assertEqual(rows[0]["No."], "01")
        self.assertEqual(rows[0]["XHAILe points"], "A1, A2, A3, A4, A6")
        self.assertTrue(rows[0]["Question (sent to the model)"].endswith("?"))

    def test_all_34_points_with_use_or_reason(self):
        rows = sr.table_xhaile_points(self.gold, self.cases)
        self.assertEqual(len(rows), 34)
        by_id = {r["XHAILe point"]: r for r in rows}
        self.assertEqual(by_id["A1"]["Used in question"], "01")
        self.assertTrue(by_id["A11"]["Used in question"].startswith("Not used."))
        self.assertTrue(by_id["A43"]["Used in question"].startswith("Not used."))
        used = [r for r in rows if not r["Used in question"].startswith("Not used")]
        self.assertEqual(len(used), 32)


class ShortModelTests(unittest.TestCase):
    def test_gguf_path_is_shortened(self):
        self.assertEqual(
            sr.short_model("Llama-3.3-70B-Instruct-Q8_0/Llama-3.3-70B-Instruct-Q8_0-00001-of-00002.gguf"),
            "Llama-3.3-70B-Instruct-Q8_0",
        )
        self.assertEqual(sr.short_model("gpt-5.6-luna"), "gpt-5.6-luna")


class BuildSystemTests(unittest.TestCase):
    def test_configs_pass_runner_validation(self):
        from Evaluation.scripts.run_evaluation import validate_system_config

        cases = [
            ("OpenAI", "gpt-test", "sk-test", "", "closed_book"),
            ("Anthropic", "claude-test", "sk-ant-test", "", "gold_context"),
            ("UCloud / local model", "llama-test", "", "http://localhost:8000/v1", "closed_book"),
            ("Own RAG system", "", "", "http://localhost:3000/evaluate", "closed_book"),
        ]
        for provider, model, key, endpoint, mode in cases:
            system = sr.build_system(provider, model, key, endpoint, mode, version="abc123")
            validate_system_config(system)
        rag = sr.build_system("Own RAG system", "", "", "http://x/evaluate", "closed_book", "abc")
        self.assertEqual(rag["input_mode"], "self_retrieval")


class PlainPromptTests(unittest.TestCase):
    def setUp(self):
        import json
        from Evaluation.scripts import run_evaluation

        self.run_evaluation = run_evaluation
        path = Path(run_evaluation.REPO_ROOT) / "Evaluation" / "benchmark" / "testcases_su_guidance_qa_v5.jsonl"
        self.cases = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def test_closed_book_prompt_is_only_the_question(self):
        for case in self.cases:
            prompt = self.run_evaluation.build_prompt(case, "closed_book")
            self.assertEqual(prompt, case["model_input"]["question"])

    def test_source_prompt_has_sources_and_question_and_no_hidden_material(self):
        for case in self.cases:
            prompt = self.run_evaluation.build_prompt(case, "gold_context")
            self.assertTrue(prompt.startswith("Kilde:"))
            self.assertTrue(prompt.endswith("Spørgsmål: " + case["model_input"]["question"]))
            for passage in case["model_input"]["source_passages"]:
                self.assertIn(passage["text"], prompt)
            for hidden in ("determination_ids", "expert_criteria", "reference_answer"):
                self.assertNotIn(hidden, prompt)
            for word in ("JSON", "legal_claims", "Regler", "Opfind"):
                self.assertNotIn(word, prompt)


if __name__ == "__main__":
    unittest.main()
