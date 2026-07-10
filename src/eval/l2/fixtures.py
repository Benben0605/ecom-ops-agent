"""L2 judge 回归夹具：拿冻结的「答案+池+期望裁定」N 次跑 judge，钉死假阳/假阴。

单 run 判 judge 会被抽取抖动骗（同句时抽时不抽→间歇性假阴）。这里答案不动、跑 N 次，
报每条锚点的 recall（该红的越界有没有被漏抽）和假阳率（该绿的有没有被误判 unsupported）。
judge prompt 每改一版都跑这个，别再靠单 run + 肉眼。

入口只有 src.experiment.runner（track=l2_fixtures_judge）；本模块只算不落盘。
"""
import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

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


def _run_verdict(matched: list[dict]) -> str:
    """一次 run 里该锚点的裁定。三态：judge 没抽出匹配的断言 ≠ 判它 supported。"""
    if not matched:
        return "not_extracted"
    if any(a["verdict"] == "unsupported" for a in matched):
        return "unsupported"
    return "supported"


def _anchor_record(case_id: str, index: int, anchor: dict, verdicts: list[dict], n: int) -> dict:
    if anchor["axis"] != "faithfulness":
        raise ValueError(
            f"[{case_id}] 锚点 axis={anchor['axis']!r} 不支持——本模块只匹配 faithfulness_axis。"
            f"加 hit 轴锚点前先实现对应匹配逻辑，别让它静默失配。"
        )
    pat = re.compile(anchor["match"])
    red = anchor["expect"] == "unsupported"

    runs = []
    for i, v in enumerate(verdicts, start=1):
        matched = [a for a in v.get("faithfulness_axis", []) if pat.search(a["assertion"])]
        rv = _run_verdict(matched)
        ok = (rv == "unsupported") if red else (rv != "unsupported")
        runs.append({"run_index": i, "run_verdict": rv, "ok": ok, "matched": matched})

    counts = {"unsupported_runs": 0, "supported_runs": 0, "not_extracted_runs": 0}
    for r in runs:
        counts[f"{r['run_verdict']}_runs"] += 1

    if red:
        flag = "pass" if counts["unsupported_runs"] == n else "false_negative"
    else:
        flag = "pass" if counts["unsupported_runs"] == 0 else "false_positive"

    return {
        "anchor_id": f"{case_id}::{index}",
        "case_id": case_id,
        "axis": anchor["axis"],
        "match": anchor["match"],
        "expect": anchor["expect"],
        "note": anchor["note"],
        "flag": flag,
        "n": n,
        **counts,
        "pass_rate": sum(1 for r in runs if r["ok"]) / n,
        "runs": runs,
    }


def _print_anchor(a: dict) -> None:
    n, u, ne = a["n"], a["unsupported_runs"], a["not_extracted_runs"]
    if a["expect"] == "unsupported":
        mark = "✅" if a["flag"] == "pass" else "❌假阴"
        detail = f"该红] recall {u}/{n}（漏抽 {ne}）"
    else:
        mark = "✅" if a["flag"] == "pass" else "❌假阳"
        detail = f"该绿] 假阳 {u}/{n}（被抽到 {n - ne}/{n}）"
    print(f"  {mark} [{a['match']} → {detail}  {a['note']}")


def _case_record(fx: dict, bucket: str, verdicts: list[dict], n: int) -> dict:
    anchors = [_anchor_record(fx["case_id"], i, a, verdicts, n)
               for i, a in enumerate(fx["anchors"])]
    for a in anchors:
        _print_anchor(a)

    # run 级通过：该 run 里每条锚点都符合预期（与 l1/l2 轨的 pass_rate 同义，可横向比）
    passing_runs = sum(1 for i in range(n) if all(a["runs"][i]["ok"] for a in anchors))
    passed = [a for a in anchors if a["flag"] == "pass"]

    return {
        "case_id": fx["case_id"],
        "bucket": bucket,
        "question": fx["question"],
        "answer": fx["answer"],
        "tool_outputs": fx["tool_outputs"],
        "golden_points": fx["golden_points"],
        "n": n,
        "pass_rate": passing_runs / n,
        "anchor_count": len(anchors),
        "passed_anchor_count": len(passed),
        "anchor_pass_rate": len(passed) / len(anchors) if anchors else None,
        "has_issue": len(passed) < len(anchors),
        "issue_types": sorted({a["flag"] for a in anchors if a["flag"] != "pass"}),
        "anchors": anchors,
        "runs": [{"run_index": i, **v} for i, v in enumerate(verdicts, start=1)],
    }


def _metrics(case_result: dict, n: int) -> dict:
    anchors = [a for case in case_result.values() for a in case["anchors"]]
    red = [a for a in anchors if a["expect"] == "unsupported"]
    green = [a for a in anchors if a["expect"] == "supported"]
    failed = [a for a in anchors if a["flag"] != "pass"]
    anchor_runs = len(anchors) * n

    return {
        "n": n,
        "case_count": len(case_result),
        "anchor_count": len(anchors),
        "anchor_pass_rate": (len(anchors) - len(failed)) / len(anchors) if anchors else None,
        "red_anchor_count": len(red),
        "green_anchor_count": len(green),
        "red_anchor_recall": sum(a["unsupported_runs"] for a in red) / (len(red) * n) if red else None,
        "green_anchor_fp_rate": sum(a["unsupported_runs"] for a in green) / (len(green) * n) if green else None,
        # 抽取覆盖度：绿锚从未被抽到也记 pass，靠这个把低置信度的假绿暴露出来
        "extract_rate": (1 - sum(a["not_extracted_runs"] for a in anchors) / anchor_runs)
                        if anchor_runs else None,
        "failed_anchor_count": len(failed),
        "failed_anchors": [{k: a[k] for k in ("case_id", "anchor_id", "match", "expect", "flag")}
                           for a in failed],
    }


def run_fixtures(
    n: int = N,
    case_filter: list[str] | None = None,
    max_workers: int = MAX_WORKERS,
) -> tuple[dict, dict]:
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

    case_result = {}
    for i, fx in enumerate(fixtures):
        print(f"\n[{fx['case_id']}]")
        case_result[fx["case_id"]] = _case_record(
            fx, buckets.get(fx["case_id"], "unknown"), flat[i * n:(i + 1) * n], n)

    return case_result, _metrics(case_result, n)


if __name__ == "__main__":
    # 惰性 import 避免 runner ↔ fixtures 循环导入；本模块不再自行落盘，统一走 logs/experiments/
    from src.experiment.runner import Experiment, Variant, run_experiment

    run_experiment(Experiment(
        name="l2_fixtures_judge",
        track="l2_fixtures_judge",
        variants=[Variant("A_baseline", {})],
        n=N,
    ))
