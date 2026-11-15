import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from Evaluation.scripts.manual_entry import (
    SOURCES_HEADING,
    build_manual_run,
    load_draft,
    missing_fields,
    save_draft,
    save_manual_run,
)

CASES = [
    {"case_id": "xsu_sg_001_general_conditions", "model_input": {"question": "Spørgsmål 1?"}},
    {"case_id": "xsu_sg_002_permanence_requirement", "model_input": {"question": "Spørgsmål 2?"}},
]
META = {"system_name": "Own RAG", "system_version": "abc123", "generator_model": "gpt-x"}


def full_answers():
    return {
        "xsu_sg_001_general_conditions": {"answer": "Svar 1", "sources": "SU-loven § 1"},
        "xsu_sg_002_permanence_requirement": {"answer": "Svar 2", "sources": ""},
    }


class ManualEntryTest(unittest.TestCase):
    def test_missing_fields(self):
        self.assertEqual(missing_fields(CASES, {}, {}), ["system name", "version or commit", "2 answers"])
        self.assertEqual(missing_fields(CASES, full_answers(), META), [])

    def test_build_run_shape(self):
        now = datetime(2026, 11, 7, 12, 0, tzinfo=timezone.utc)
        run_id, outputs, meta = build_manual_run(CASES, full_answers(), META, now=now)
        self.assertTrue(run_id.startswith("20261107T120000"))
        self.assertTrue(run_id.endswith("Manual_Own_RAG_self_retrieval"))
        self.assertEqual(len(outputs), 2)
        first = outputs[0]
        self.assertEqual(first["input_mode"], "self_retrieval")
        self.assertEqual(first["requested_model"], "Own RAG")
        self.assertEqual(first["content"], f"Svar 1\n\n{SOURCES_HEADING}\nSU-loven § 1")
        self.assertEqual(outputs[1]["content"], "Svar 2")
        self.assertEqual(meta["system"]["system_version"], "abc123")
        self.assertEqual(meta["case_count"], 2)

    def test_build_rejects_incomplete(self):
        answers = full_answers()
        answers["xsu_sg_002_permanence_requirement"]["answer"] = " "
        with self.assertRaises(ValueError):
            build_manual_run(CASES, answers, META)

    def test_save_run_and_draft(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = save_manual_run(root, CASES, full_answers(), META)
            rows = [json.loads(l) for l in (run_dir / "outputs.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(rows), 2)
            meta = json.loads((run_dir / "run_metadata.json").read_text(encoding="utf-8"))
            self.assertEqual(len(meta["outputs_sha256"]), 64)
            draft_path = root / "draft.json"
            self.assertEqual(load_draft(draft_path), {"meta": {}, "answers": {}})
            save_draft(draft_path, {"meta": META, "answers": full_answers()})
            self.assertEqual(load_draft(draft_path)["meta"], META)


if __name__ == "__main__":
    unittest.main()
