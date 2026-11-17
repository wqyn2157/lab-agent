import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from evals import evaluate_retrieval as evaluation


class RetrievalEvaluationTests(unittest.TestCase):
    def test_evidence_requires_matching_source_and_text(self):
        evidence = {"source": "rules.md", "quote": "students only"}
        self.assertFalse(evaluation.has_evidence([], evidence))
        self.assertFalse(evaluation.has_evidence(
            [{"source": "other.md", "content": "students only"}], evidence
        ))
        self.assertFalse(evaluation.has_evidence(
            [{"source": "rules.md", "content": "other paragraph"}], evidence
        ))
        self.assertTrue(evaluation.has_evidence([
            {"source": "rules.md", "content": "other paragraph"},
            {"source": "rules.md", "content": "policy: students only"},
        ], evidence))

    def test_report_excludes_non_static_cases_and_retains_failures(self):
        evidence = {"source": "rules.md", "quote": "students only"}
        cases = [
            {"id": "complete", "question": "first", "expected_behavior": "answer", "evidence": [evidence]},
            {"id": "wrong-source", "question": "second", "expected_behavior": "answer", "evidence": [evidence]},
            {"id": "partial", "question": "third", "expected_behavior": "answer", "evidence": [
                evidence, {"source": "safety.md", "quote": "wear goggles"},
            ]},
            {"id": "unknown", "question": "unknown", "expected_behavior": "abstain", "evidence": []},
            {"id": "live", "question": "live", "expected_behavior": "query_database", "evidence": []},
        ]
        good = [{"source": "rules.md", "content": "students only", "chunk_index": 0, "score": 0.9}]
        wrong = [{"source": "other.md", "content": "students only", "chunk_index": 0, "score": 0.9}]
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / "rag_cases.json").write_text(json.dumps({"cases": cases}), encoding="utf-8")
            with patch.object(evaluation, "__file__", str(directory / "evaluate_retrieval.py")), patch.object(
                evaluation.kb_service, "search_chunks", side_effect=[good, wrong, good]
            ) as search, patch("builtins.print"):
                report = evaluation.run_evaluation()
            self.assertEqual(report["total"], 3)
            self.assertEqual(report["passed"], 1)
            self.assertAlmostEqual(report["coverage"], 1 / 3)
            self.assertEqual([call.args[0] for call in search.call_args_list], ["first", "second", "third"])
            self.assertEqual(report["results"][1]["missing_evidence"], [evidence])
            self.assertEqual(report["results"][2]["missing_evidence"], [{"source": "safety.md", "quote": "wear goggles"}])
            self.assertEqual(report["results"][1]["chunks"], wrong)
            saved = json.loads((directory / "retrieval_report.json").read_text(encoding="utf-8"))
            self.assertEqual(saved, report)

    def test_empty_answerable_set_does_not_create_report(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / "rag_cases.json").write_text(json.dumps({"cases": []}), encoding="utf-8")
            with patch.object(evaluation, "__file__", str(directory / "evaluate_retrieval.py")), patch.object(
                evaluation.kb_service, "search_chunks"
            ) as search:
                with self.assertRaises(ValueError):
                    evaluation.run_evaluation()
            search.assert_not_called()
            self.assertFalse((directory / "retrieval_report.json").exists())


if __name__ == "__main__":
    unittest.main()
