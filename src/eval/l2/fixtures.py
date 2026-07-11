"""L2 judge 回归夹具：拿冻结的「答案+池+期望裁定」N 次跑 judge，钉死假阳/假阴。

单 run 判 judge 会被抽取抖动骗（同句时抽时不抽→间歇性假阴）。这里答案不动、跑 N 次，
报每条锚点的 recall（该红的越界有没有被漏抽）和假阳率（该绿的有没有被误判 unsupported）。
judge prompt 每改一版都跑这个，别再靠单 run + 肉眼。

入口只有 src.experiment.runner（track=l2_fixtures_judge）；本模块只算不落盘。
产物 schema 见 src/contracts/l2_fixtures.py，计数/通过率一律由 model computed，本模块不自己算。
"""
import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from src.contracts.l2_fixtures import (
    AnchorRecord,
    AnchorRun,
    CaseRecord,
    FixtureInput,
    FixturesCaseResult,
    FixturesMetrics,
    JudgeVerdict,
)
from src.eval.l2.judge import judge_one

ROOT = Path(__file__).parents[3]
FIXTURES = ROOT / "data" / "l2_judge_fixtures.json"
EVAL_CASES = ROOT / "data" / "eval_cases.json"

N = 8
MAX_WORKERS = 16  # judge_one 是纯 IO（LLM API 调用），线程池并发省的是真实等待时间

JUDGE_INPUT_KEYS = ("question", "answer", "tool_outputs", "golden_points")


def _load_fixtures() -> list[dict]:
    return json.loads(FIXTURES.read_text(encoding="utf-8"))


def fixture_case_index() -> list[tuple[str, str]]:
    """(case_id, bucket)：夹具文件没有 bucket，按 id 从 eval_cases 借。供 runner 解析过滤条件。"""
    buckets = {c["id"]: c["bucket"] for c in json.loads(EVAL_CASES.read_text(encoding="utf-8"))}
    return [(fx["case_id"], buckets.get(fx["case_id"], "unknown")) for fx in _load_fixtures()]


def _anchor_record(case_id: str, index: int, anchor: dict,
                   verdicts: list[JudgeVerdict]) -> AnchorRecord:
    if anchor["axis"] != "faithfulness":
        raise ValueError(
            f"[{case_id}] 锚点 axis={anchor['axis']!r} 不支持——本模块只匹配 faithfulness_axis。"
            f"加 hit 轴锚点前先实现对应匹配逻辑，别让它静默失配。"
        )
    pat = re.compile(anchor["match"])
    expect = anchor["expect"]
    return AnchorRecord(
        anchor_id=f"{case_id}::{index}",
        case_id=case_id,
        axis=anchor["axis"],
        match=anchor["match"],
        expect=expect,
        note=anchor["note"],
        runs=[
            AnchorRun.build(
                run_index=v.run_index,
                matched=[a for a in v.faithfulness_axis if pat.search(a.assertion)],
                expect=expect,
            )
            for v in verdicts
        ],
    )


def _print_anchor(a: AnchorRecord) -> None:
    n, u, ne = a.n, a.unsupported_runs, a.not_extracted_runs
    if a.is_red:
        mark = "✅" if a.flag == "pass" else "❌假阴"
        detail = f"该红] recall {u}/{n}（漏抽 {ne}）"
    else:
        mark = "✅" if a.flag == "pass" else "❌假阳"
        detail = f"该绿] 假阳 {u}/{n}（被抽到 {n - ne}/{n}）"
    print(f"  {mark} [{a.match} → {detail}  {a.note}")


def _case_record(fx: dict, bucket: str, verdicts: list[JudgeVerdict]) -> CaseRecord:
    anchors = [_anchor_record(fx["case_id"], i, a, verdicts) for i, a in enumerate(fx["anchors"])]
    for a in anchors:
        _print_anchor(a)
    return CaseRecord(
        case_id=fx["case_id"],
        bucket=bucket,
        input=FixtureInput(**{k: fx[k] for k in JUDGE_INPUT_KEYS}),
        anchors=anchors,
        judge_verdicts=verdicts,
    )


def run_fixtures(
    n: int = N,
    case_filter: list[str] | None = None,
    max_workers: int = MAX_WORKERS,
) -> tuple[FixturesCaseResult, FixturesMetrics]:
    """返回 (case_result, metrics)：下钻详情 + headline。落盘由调用方（experiment runner）负责。"""
    fixtures = _load_fixtures()
    if case_filter is not None:
        keep = set(case_filter)
        fixtures = [fx for fx in fixtures if fx["case_id"] in keep]
    buckets = dict(fixture_case_index())

    # 所有 (case × n 次重复) 任务一次性铺开并发，而不是逐 case 串行等 n 次跑完
    items = [{k: fx[k] for k in JUDGE_INPUT_KEYS} for fx in fixtures]
    jobs = [item for item in items for _ in range(n)]
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        flat = list(pool.map(judge_one, jobs))

    cases = {}
    for i, fx in enumerate(fixtures):
        print(f"\n[{fx['case_id']}]")
        verdicts = [JudgeVerdict(run_index=j, **raw)
                    for j, raw in enumerate(flat[i * n:(i + 1) * n], start=1)]
        cases[fx["case_id"]] = _case_record(fx, buckets.get(fx["case_id"], "unknown"), verdicts)

    return FixturesCaseResult(cases=cases), FixturesMetrics.from_cases(cases.values())


if __name__ == "__main__":
    # 惰性 import 避免 runner ↔ fixtures 循环导入；本模块不再自行落盘，统一走 logs/experiments/
    from src.experiment.runner import Experiment, Variant, run_experiment

    run_experiment(Experiment(
        name="l2_fixtures_judge",
        track="l2_fixtures_judge",
        variants=[Variant("A_baseline", {})],
        n=N,
    ))
