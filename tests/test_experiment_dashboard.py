import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from src.dashboard.main import build_dashboard_data
from src.eval.l2.annotations import build_l2_issue_id, save_l2_annotation
from src.eval.l2.dashboard import build_l2_dashboard_data


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_jsonl(path: Path, records: list[object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )


class ExperimentDashboardTest(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        cases = [
            {
                "id": "case_a",
                "bucket": "direct",
                "question": "查订单10001",
                "should_call_tool": True,
                "expected_calls": [
                    {"tool_name": "query_order", "tool_params": {"order_id": "10001"}}
                ],
                "golden_answer_points": ["转述订单状态"],
            }
        ]
        _write_json(self.root / "data" / "eval_cases.json", cases)
        dataset_sha = hashlib.sha256(
            (self.root / "data" / "eval_cases.json").read_bytes()
        ).hexdigest()
        exp_id = "20260702_000000_test_exp"
        self.exp_id = exp_id
        self.variant = "A_baseline"
        exp_dir = self.root / "logs" / "experiments" / exp_id
        _write_json(
            exp_dir / "manifest.json",
            {
                "exp_id": exp_id,
                "name": "test_exp",
                "track": "agent",
                "variants": [{"name": self.variant, "config": {}}],
                "provenance": {
                    "git_commit": "abc",
                    "timestamp": "2026-07-02T00:00:00+08:00",
                    "n": 2,
                    "track": "agent",
                    "dataset_sha": {"eval_cases": dataset_sha},
                },
            },
        )
        variant_dir = exp_dir / "variants" / self.variant
        _write_json(
            variant_dir / "eval" / "l1_case_result.json",
            {
                "case_a": {
                    "case_id": "case_a",
                    "bucket": "direct",
                    "spec_tool": ["query_order"],
                    "n": 2,
                    "pass_rate": 0.5,
                    "hit_rate": 0.5,
                    "misfire_rate": 0.5,
                    "runs": [
                        {
                            "called_tools": ["query_order"],
                            "missing_tools": [],
                            "unexpected_tools": [],
                            "is_hit": True,
                            "is_misfire": False,
                        },
                        {
                            "called_tools": ["analyze_ops"],
                            "missing_tools": ["query_order"],
                            "unexpected_tools": ["analyze_ops"],
                            "is_hit": False,
                            "is_misfire": True,
                        },
                    ],
                }
            },
        )
        _write_json(variant_dir / "eval" / "l1_metrics.json", {})
        _write_json(
            variant_dir / "eval" / "l2_case_result.json",
            {
                "case_a": {
                    "case_id": "case_a",
                    "bucket": "direct",
                    "question": "查订单10001",
                    "n": 2,
                    "pass_rate": 0.5,
                    "runs": [
                        {
                            "answer": "订单已发货",
                            "verdict": {
                                "hit_axis": [
                                    {
                                        "point": "转述订单状态",
                                        "verdict": "hit",
                                        "evidence": "订单已发货",
                                    }
                                ],
                                "faithfulness_axis": [
                                    {
                                        "assertion": "订单已发货",
                                        "verdict": "supported",
                                        "evidence": "订单 10001：已发货",
                                    }
                                ],
                            },
                            "score": {
                                "hit_ok": 1,
                                "hit_total": 1,
                                "hit_rate": 1.0,
                                "faith_ok": 1,
                                "faith_total": 1,
                                "faithfulness_rate": 1.0,
                            },
                            "passed": True,
                        },
                        {
                            "answer": "订单已取消",
                            "verdict": {
                                "hit_axis": [
                                    {
                                        "point": "转述订单状态",
                                        "verdict": "miss",
                                        "evidence": "",
                                    }
                                ],
                                "faithfulness_axis": [
                                    {
                                        "assertion": "订单已取消",
                                        "verdict": "unsupported",
                                        "evidence": "",
                                    }
                                ],
                            },
                            "score": {
                                "hit_ok": 0,
                                "hit_total": 1,
                                "hit_rate": 0.0,
                                "faith_ok": 0,
                                "faith_total": 1,
                                "faithfulness_rate": 0.0,
                            },
                            "passed": False,
                        },
                    ],
                }
            },
        )
        _write_json(variant_dir / "eval" / "l2_metrics.json", {})
        for index, session_id, tool_name, tool_output in (
            (1, "session_1", "query_order", "订单 10001：已发货"),
            (2, "session_2", "analyze_ops", "全店运营概况"),
        ):
            run_dir = variant_dir / "trace" / f"run_{index}"
            _write_json(run_dir / "run_map.json", [{"case_id": "case_a", "session_id": session_id}])
            _write_jsonl(
                run_dir / "audit.jsonl",
                [
                    {
                        "session_id": session_id,
                        "tool_name": tool_name,
                        "tool_params": {},
                        "tool_duration_ms": 1,
                        "tool_output": tool_output,
                        "tool_error": None,
                    }
                ],
            )
            _write_jsonl(
                run_dir / "session_messages.jsonl",
                [
                    {
                        "session_id": session_id,
                        "messages": [
                            {"role": "user", "content": "查订单10001"},
                            {"role": "tool", "content": tool_output},
                            {"role": "assistant", "content": f"answer {index}"},
                        ],
                    }
                ],
            )

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_builds_l1_experiment_dashboard_with_per_run_trace(self):
        payload = build_dashboard_data(
            self.root,
            exp_id=self.exp_id,
            variant=self.variant,
        )

        self.assertEqual(payload["context"]["mode"], "experiment")
        self.assertTrue(payload["context"]["dataset_sha_match"])
        self.assertEqual(payload["metrics"]["case_count"], 1)
        self.assertEqual(payload["metrics"]["routing_accuracy"], 0.5)
        self.assertEqual(payload["metrics"]["misfire_rate"], 0.5)
        self.assertEqual(payload["metrics"]["failure_case_count"], 1)

        row = payload["cases"][0]
        self.assertEqual(row["pass_rate"], 0.5)
        self.assertEqual(len(row["experiment_runs"]), 2)
        self.assertEqual(row["experiment_runs"][1]["called_tools"], ["analyze_ops"])
        self.assertEqual(row["audit_count"], 2)
        self.assertEqual(len(row["messages_by_session"]), 2)

    def test_builds_l2_experiment_dashboard_with_contextual_annotations(self):
        annotation = save_l2_annotation(
            {
                "case_id": "case_a",
                "assertion": "订单已取消",
                "verdict": "unsupported",
                "root_cause": "agent_hallucination",
                "exp_id": self.exp_id,
                "variant": self.variant,
                "run_index": 2,
            },
            self.root,
        )

        payload = build_l2_dashboard_data(
            self.root,
            exp_id=self.exp_id,
            variant=self.variant,
        )

        self.assertEqual(payload["metrics"]["case_pass_rate"], 0.5)
        self.assertEqual(payload["metrics"]["hit_rate"], 0.5)
        self.assertEqual(payload["metrics"]["faithfulness_rate"], 0.5)
        row = payload["cases"][0]
        self.assertEqual(row["annotation_count"], 1)
        unsupported = row["experiment_runs"][1]["faithfulness_axis"][0]
        self.assertEqual(unsupported["annotation"]["issue_id"], annotation["issue_id"])
        self.assertEqual(
            unsupported["issue_id"],
            build_l2_issue_id(
                "case_a",
                "unsupported",
                "订单已取消",
                exp_id=self.exp_id,
                variant=self.variant,
                run_index=2,
            ),
        )


if __name__ == "__main__":
    unittest.main()
