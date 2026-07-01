import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from src.eval.l2.annotations import (
    build_l2_issue_id,
    load_latest_l2_annotations,
    save_l2_annotation,
)
from src.eval.l2.dashboard import build_l2_dashboard_data


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
            save_l2_annotation(
                {
                    "case_id": "case_a",
                    "assertion": "assertion b",
                    "verdict": "unsupported",
                    "root_cause": "agent_hallucination",
                    "root_cause_note": "Agent 凭空补充取消规则",
                },
                root,
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
            self.assertEqual(row["annotation_count"], 1)

            unsupported_axis = row["faithfulness_axis"][1]
            self.assertEqual(
                unsupported_axis["issue_id"],
                build_l2_issue_id("case_a", "unsupported", "assertion b"),
            )
            self.assertEqual(
                unsupported_axis["annotation"]["root_cause"],
                "agent_hallucination",
            )
            self.assertIn(
                "case_a | L2 忠实轴 | UNSUPPORTED",
                unsupported_axis["annotation"]["summary"],
            )
            self.assertEqual(payload["annotations"]["count"], 1)

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

    def test_preserves_custom_root_cause_label_and_summary(self):
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "logs").mkdir()

            annotation = save_l2_annotation(
                {
                    "case_id": "case_custom",
                    "assertion": "assertion custom",
                    "verdict": "unsupported",
                    "root_cause": "prompt 约束缺失",
                    "root_cause_note": "需要增加只能基于工具证据回答的约束",
                },
                root,
            )
            latest = load_latest_l2_annotations(root)

            self.assertEqual(annotation["root_cause"], "prompt 约束缺失")
            self.assertEqual(annotation["root_cause_label"], "prompt 约束缺失")
            self.assertIn("根因：prompt 约束缺失", annotation["summary"])
            self.assertEqual(latest[annotation["issue_id"]]["root_cause"], "prompt 约束缺失")


if __name__ == "__main__":
    unittest.main()
