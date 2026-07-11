import hashlib
import json
from collections import defaultdict
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from src.dashboard.experiment_adapter import build_l2_fixtures_experiment_dashboard_data
from src.eval.l2 import fixtures as fx
from src.experiment.runner import Experiment, Variant, _resolve_case_ids, run_experiment


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _assertion(text: str, verdict: str) -> dict:
    return {"assertion": text, "verdict": verdict, "evidence": "e"}


def _anchor(match: str, expect: str, axis: str = "faithfulness") -> dict:
    return {"axis": axis, "match": match, "expect": expect, "note": f"{match} 锚"}


# 三次 run 的 judge 输出，覆盖四种锚点结局
_SCRIPT = [
    {"hit_axis": [], "faithfulness_axis": [
        _assertion("越界A", "unsupported"),
        _assertion("越界B", "unsupported"),
        _assertion("绿C", "unsupported"),
    ]},
    {"hit_axis": [], "faithfulness_axis": [
        _assertion("越界A", "unsupported"),
        _assertion("绿C", "supported"),
    ]},
    {"hit_axis": [], "faithfulness_axis": [
        _assertion("越界A", "unsupported"),
        _assertion("绿C", "supported"),
    ]},
]

_FIXTURE = {
    "case_id": "case_x",
    "question": "q-x",
    "answer": "a",
    "tool_outputs": ["pool"],
    "golden_points": ["g"],
    "anchors": [
        _anchor("越界A", "unsupported"),   # 每次都抓到 → pass
        _anchor("越界B", "unsupported"),   # 只有 run1 抓到 → false_negative
        _anchor("绿C", "supported"),       # run1 被误判 → false_positive
        _anchor("绿D", "supported"),       # 从未被抽到 → pass，但 not_extracted_runs == n
    ],
}


class RunFixturesTest(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.fixtures_path = self.root / "l2_judge_fixtures.json"
        self.cases_path = self.root / "eval_cases.json"
        _write_json(self.cases_path, [{"id": "case_x", "bucket": "direct"},
                                      {"id": "case_y", "bucket": "confusing"}])

    def tearDown(self):
        self.temporary_directory.cleanup()

    def _run(self, fixtures: list[dict], n: int = 3, case_filter=None):
        _write_json(self.fixtures_path, fixtures)
        counters: dict[str, int] = defaultdict(int)

        def fake_judge_one(item):
            index = counters[item["question"]]
            counters[item["question"]] += 1
            return _SCRIPT[index]

        with patch.object(fx, "FIXTURES", self.fixtures_path), \
             patch.object(fx, "EVAL_CASES", self.cases_path), \
             patch.object(fx, "judge_one", fake_judge_one):
            # max_workers=1：让 pool.map 按提交序执行，脚本第 i 条才对应 run_i
            return fx.run_fixtures(n=n, case_filter=case_filter, max_workers=1)

    def test_anchor_three_state_counts(self):
        case_result, _ = self._run([_FIXTURE])
        anchors = {a.match: a for a in case_result.cases["case_x"].anchors}

        for anchor in anchors.values():
            total = anchor.unsupported_runs + anchor.supported_runs + anchor.not_extracted_runs
            self.assertEqual(total, anchor.n, f"{anchor.match} 三态之和应等于 n")

        self.assertEqual(anchors["越界A"].flag, "pass")
        self.assertEqual(anchors["越界A"].unsupported_runs, 3)

        self.assertEqual(anchors["越界B"].flag, "false_negative")
        self.assertEqual(anchors["越界B"].unsupported_runs, 1)
        self.assertEqual(anchors["越界B"].not_extracted_runs, 2)

        self.assertEqual(anchors["绿C"].flag, "false_positive")
        self.assertEqual(anchors["绿C"].unsupported_runs, 1)
        self.assertEqual(anchors["绿C"].supported_runs, 2)

        # 从未被抽到的绿锚仍记 pass，但 extract 信号把它和"真的判 supported"区分开
        self.assertEqual(anchors["绿D"].flag, "pass")
        self.assertEqual(anchors["绿D"].not_extracted_runs, 3)
        self.assertEqual(anchors["绿D"].supported_runs, 0)

    def test_case_and_metrics_rollup(self):
        case_result, metrics = self._run([_FIXTURE])
        case = case_result.cases["case_x"]

        self.assertEqual(case.bucket, "direct")          # 从 eval_cases join
        self.assertEqual(case.anchor_count, 4)
        self.assertEqual(case.passed_anchor_count, 2)
        self.assertEqual(case.anchor_pass_rate, 0.5)
        self.assertEqual(case.run_pass_rate, 0.0)        # 没有一次 run 让四条锚点全部就位
        self.assertTrue(case.has_issue)
        self.assertEqual(case.issue_types, ["false_negative", "false_positive"])
        self.assertEqual([v.run_index for v in case.judge_verdicts], [1, 2, 3])
        self.assertEqual(case.anchors[0].anchor_id, "case_x::0")
        self.assertEqual(case.input.question, "q-x")     # 输入收进 input，与产出分开

        self.assertEqual(metrics.anchor_count, 4)
        self.assertEqual(metrics.red_anchor_count, 2)
        self.assertEqual(metrics.green_anchor_count, 2)
        self.assertEqual(metrics.anchor_pass_rate, 0.5)
        self.assertAlmostEqual(metrics.red_anchor_recall, 4 / 6)
        self.assertAlmostEqual(metrics.green_anchor_fp_rate, 1 / 6)
        self.assertAlmostEqual(metrics.extract_rate, 1 - 5 / 12)
        self.assertEqual(metrics.failed_anchor_count, 2)
        self.assertEqual({a.match for a in metrics.failed_anchors}, {"越界B", "绿C"})

    def test_metrics_carry_the_denominators_of_every_rate(self):
        """率必须能被产物里的计数复核，不必回代码读分母。"""
        _, metrics = self._run([_FIXTURE])
        self.assertEqual(metrics.red_anchor_recall,
                         metrics.red_unsupported_runs / metrics.red_runs)
        self.assertEqual(metrics.green_anchor_fp_rate,
                         metrics.green_unsupported_runs / metrics.green_runs)
        self.assertEqual(metrics.extract_rate,
                         1 - metrics.not_extracted_runs / metrics.anchor_runs)
        self.assertEqual(metrics.anchor_pass_rate,
                         metrics.passed_anchor_count / metrics.anchor_count)

    def test_artifact_round_trips_through_json(self):
        """落盘再读回等价——computed 字段被忽略后由 runs 重新算出同一个值。"""
        case_result, metrics = self._run([_FIXTURE])
        for model in (case_result, metrics):
            reloaded = type(model).model_validate(json.loads(model.model_dump_json()))
            self.assertEqual(reloaded.model_dump(), model.model_dump())

    def test_case_filter_narrows_fixtures(self):
        other = {**_FIXTURE, "case_id": "case_y", "question": "q-y"}
        case_result, metrics = self._run([_FIXTURE, other], case_filter=["case_y"])
        self.assertEqual(list(case_result.cases), ["case_y"])
        self.assertEqual(metrics.case_count, 1)

    def test_non_faithfulness_axis_raises(self):
        bad = {**_FIXTURE, "anchors": [_anchor("越界A", "unsupported", axis="hit")]}
        with self.assertRaisesRegex(ValueError, "axis"):
            self._run([bad])


class FixturesTrackFilterTest(unittest.TestCase):
    """过滤条件解析（跑在仓库真实 data/ 上）。"""

    def _exp(self, **kwargs):
        return Experiment(name="t", track="l2_fixtures_judge",
                          variants=[Variant("A_baseline", {})], **kwargs)

    def test_resolves_against_fixtures_not_eval_cases(self):
        self.assertEqual(_resolve_case_ids(self._exp(case_filter=["case_072"])), ["case_072"])
        self.assertEqual(_resolve_case_ids(self._exp(bucket_filter=["personalization"])),
                         ["case_078", "case_079"])
        self.assertIsNone(_resolve_case_ids(self._exp()))

    def test_case_in_eval_cases_but_not_in_fixtures_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "case_001"):
            _resolve_case_ids(self._exp(case_filter=["case_001"]))

    def test_exp_id_reuse_with_filter_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "过滤跑请开新实验目录"):
            run_experiment(self._exp(exp_id="whatever", case_filter=["case_072"]))


class FixturesDashboardTest(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.exp_id = "20260710_000000_fx"
        self.variant = "A_baseline"

        fixtures_path = self.root / "data" / "l2_judge_fixtures.json"
        _write_json(fixtures_path, [_FIXTURE])
        dataset_sha = hashlib.sha256(fixtures_path.read_bytes()).hexdigest()

        self.exp_dir = self.root / "logs" / "experiments" / self.exp_id
        self.manifest = {
            "exp_id": self.exp_id,
            "name": "fx",
            "track": "l2_fixtures_judge",
            "variants": [{"name": self.variant, "config": {}}],
            "provenance": {
                "git_commit": "abc",
                "timestamp": "2026-07-10T00:00:00+08:00",
                "n": 3,
                "track": "l2_fixtures_judge",
                "dataset_sha": {"l2_judge_fixtures": dataset_sha},
            },
            "stage_runs": [{"stages": ["l2_fixtures_judge"], "n": 3}],
        }
        _write_json(self.exp_dir / "manifest.json", self.manifest)

        counters: dict[str, int] = defaultdict(int)

        def fake_judge_one(item):
            index = counters[item["question"]]
            counters[item["question"]] += 1
            return _SCRIPT[index]

        cases_path = self.root / "data" / "eval_cases.json"
        _write_json(cases_path, [{"id": "case_x", "bucket": "direct"}])
        with patch.object(fx, "FIXTURES", fixtures_path), \
             patch.object(fx, "EVAL_CASES", cases_path), \
             patch.object(fx, "judge_one", fake_judge_one):
            case_result, metrics = fx.run_fixtures(n=3, max_workers=1)

        eval_dir = self.exp_dir / "variants" / self.variant / "eval"
        _write_json(eval_dir / "l2_fixtures_case_result.json", json.loads(case_result.model_dump_json()))
        _write_json(eval_dir / "l2_fixtures_metrics.json", json.loads(metrics.model_dump_json()))

    def tearDown(self):
        self.temporary_directory.cleanup()

    def _build(self):
        return build_l2_fixtures_experiment_dashboard_data(
            root=self.root, exp_id=self.exp_id, variant=self.variant)

    def test_context_and_provenance(self):
        context = self._build()["context"]
        self.assertEqual(context["mode"], "experiment")
        self.assertEqual(context["track"], "l2_fixtures_judge")
        self.assertTrue(context["dataset_sha_match"])
        self.assertEqual(context["warnings"], [])

    def test_fixture_drift_warns(self):
        _write_json(self.root / "data" / "l2_judge_fixtures.json", [{**_FIXTURE, "answer": "改了"}])
        context = self._build()["context"]
        self.assertFalse(context["dataset_sha_match"])
        self.assertIn("夹具答案或锚点可能已改", context["warnings"][0])

    def test_metrics_and_breakdowns(self):
        payload = self._build()
        metrics = payload["metrics"]
        self.assertEqual(metrics["n"], 3)
        self.assertEqual(metrics["case_count"], 1)
        self.assertEqual(metrics["anchor_count"], 4)
        self.assertEqual(metrics["anchor_pass_rate"], 0.5)
        self.assertAlmostEqual(metrics["red_anchor_recall"], 4 / 6)
        self.assertAlmostEqual(metrics["green_anchor_fp_rate"], 1 / 6)
        self.assertEqual(metrics["failed_anchor_count"], 2)
        self.assertEqual(metrics["issue_case_count"], 1)

        by_bucket = payload["breakdowns"]["by_bucket"]
        self.assertEqual([b["bucket"] for b in by_bucket], ["direct"])
        self.assertEqual(by_bucket[0]["anchor_count"], 4)

        by_expect = {row["expect"]: row for row in payload["breakdowns"]["by_expect"]}
        self.assertEqual(by_expect["unsupported"]["anchor_count"], 2)
        self.assertAlmostEqual(by_expect["unsupported"]["unsupported_run_rate"], 4 / 6)
        self.assertAlmostEqual(by_expect["supported"]["unsupported_run_rate"], 1 / 6)

    def test_cases_shape_for_frontend(self):
        payload = self._build()
        self.assertEqual(len(payload["cases"]), 1)
        case = payload["cases"][0]
        self.assertEqual(case["case_id"], "case_x")
        self.assertNotIn("judge_verdicts", case)           # 出口统一叫 experiment_runs
        self.assertEqual([r["run_index"] for r in case["experiment_runs"]], [1, 2, 3])
        self.assertEqual(case["anchors"][0]["runs"][0]["run_verdict"], "unsupported")
        self.assertEqual(case["input"]["question"], "q-x")

        self.assertEqual([c["case_id"] for c in payload["issue_cases"]], ["case_x"])
        self.assertEqual({a["match"] for a in payload["failed_anchors"]}, {"越界B", "绿C"})
        self.assertEqual(payload["failed_anchors"][0]["bucket"], "direct")

    def test_rejects_other_tracks(self):
        _write_json(self.exp_dir / "manifest.json", {**self.manifest, "track": "agent"})
        with self.assertRaisesRegex(ValueError, "l2_fixtures_judge"):
            self._build()

    def test_missing_experiment_raises_file_not_found(self):
        with self.assertRaises(FileNotFoundError):
            build_l2_fixtures_experiment_dashboard_data(
                root=self.root, exp_id="nope", variant=self.variant)


if __name__ == "__main__":
    unittest.main()
