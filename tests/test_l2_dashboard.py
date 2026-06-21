import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from src.l2_dashboard import build_l2_dashboard_data


class L2DashboardDataTest(unittest.TestCase):
    def test_aggregates_verdicts_and_backfills_legacy_five_part_context(self):
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "data").mkdir()
            (root / "logs").mkdir()
            (root / "data" / "eval_cases.json").write_text(
                json.dumps(
                    [
                        {
                            "id": "case_a",
                            "bucket": "direct",
                            "question": "source question",
                            "golden_answer_points": ["point a", "point b"],
                        }
                    ]
                ),
                encoding="utf-8",
            )
            (root / "logs" / "run_map.json").write_text(
                json.dumps([{"case_id": "case_a", "session_id": "session_a"}]),
                encoding="utf-8",
            )
            (root / "logs" / "session_messages.jsonl").write_text(
                json.dumps(
                    {
                        "session_id": "session_a",
                        "messages": [
                            {"role": "tool", "content": "source tool output"}
                        ],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (root / "logs" / "l2_eval_result.json").write_text(
                json.dumps(
                    {
                        "case_a": {
                            "bucket": "direct",
                            "question": "question",
                            "answer": "answer",
                            "verdict": {
                                "hit_axis": [
                                    {"point": "point a", "verdict": "hit"},
                                    {"point": "point b", "verdict": "miss"},
                                ],
                                "faithfulness_axis": [
                                    {
                                        "assertion": "assertion a",
                                        "verdict": "supported",
                                        "evidence": "source tool output",
                                    },
                                    {
                                        "assertion": "assertion b",
                                        "verdict": "unsupported",
                                        "evidence": "",
                                    },
                                ],
                            },
                        }
                    }
                ),
                encoding="utf-8",
            )

            payload = build_l2_dashboard_data(root)

            self.assertEqual(payload["metrics"]["case_count"], 1)
            self.assertEqual(payload["metrics"]["hit_rate"], 0.5)
            self.assertEqual(payload["metrics"]["faithfulness_rate"], 0.5)
            self.assertEqual(payload["metrics"]["issue_case_count"], 1)
            self.assertEqual(payload["metrics"]["hit_issue_case_count"], 1)
            self.assertEqual(payload["metrics"]["faith_issue_case_count"], 1)

            row = payload["cases"][0]
            self.assertEqual(row["golden_points"], ["point a", "point b"])
            self.assertEqual(row["tool_outputs"], ["source tool output"])
            self.assertEqual(row["issue_types"], ["miss", "unsupported"])

    def test_returns_empty_dashboard_before_first_l2_run(self):
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "data").mkdir()
            (root / "logs").mkdir()

            payload = build_l2_dashboard_data(root)

            self.assertFalse(payload["source"]["exists"])
            self.assertEqual(payload["metrics"]["case_count"], 0)
            self.assertIsNone(payload["metrics"]["hit_rate"])
            self.assertEqual(payload["cases"], [])


if __name__ == "__main__":
    unittest.main()
