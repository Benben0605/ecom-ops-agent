"""A/B 对比（泛化自 eval_compare）。

读 logs/experiments/<exp_id>/ 下两个变体的 eval 产物，出：
- headline_delta：逐层 A/B/delta（L1 路由准确率·误触发率 / L2 命中·忠实·case_pass / RAG R@k·MRR）。
- case_diff：逐 case × 逐层 A 判定 vs B 判定，标 improved/regressed/same——headline 下钻索引。

落 compare.json + 终端打对照表。前端按 (layer, metric, status) 筛 case_diff 即下钻。
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parents[2]
EXPERIMENTS_ROOT = ROOT / "logs" / "experiments"


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _delta(a_metrics: dict, b_metrics: dict, keys: list[str]) -> dict:
    out = {}
    for k in keys:
        a, b = a_metrics.get(k), b_metrics.get(k)
        d = (b - a) if isinstance(a, (int, float)) and isinstance(b, (int, float)) else None
        out[k] = {"a": a, "b": b, "delta": d}
    return out


def _status(a, b) -> str:
    """per-run 通过率比较：B 高=变好，低=变差，相等=持平。对 bool（retrieval）同样成立。"""
    if a is None or b is None:
        return "na"
    if a == b:
        return "same"
    return "improved" if b > a else "regressed"


def _compare_agent(a_dir: Path, b_dir: Path) -> tuple[dict, list[dict]]:
    a_l1m, b_l1m = _load(a_dir / "l1_metrics.json"), _load(b_dir / "l1_metrics.json")
    a_l2m, b_l2m = _load(a_dir / "l2_metrics.json"), _load(b_dir / "l2_metrics.json")
    a_l1c, b_l1c = _load(a_dir / "l1_case_result.json"), _load(b_dir / "l1_case_result.json")
    a_l2c, b_l2c = _load(a_dir / "l2_case_result.json"), _load(b_dir / "l2_case_result.json")

    headline = {
        "L1": _delta(a_l1m, b_l1m, ["routing_accuracy", "misfire_rate"]),
        "L2": _delta(a_l2m, b_l2m, ["hit_rate", "faithfulness_rate", "case_pass_rate"]),
    }

    # 翻转判定用 per-run 通过率（a/b 是 0~1 的 rate，N=1 时退化成 0/1）
    case_diff = []
    for cid in sorted(set(a_l1c) | set(b_l1c)):
        ra, rb = a_l1c.get(cid), b_l1c.get(cid)
        row = {"case_id": cid, "bucket": (ra or rb).get("bucket")}
        la = ra.get("pass_rate") if ra else None
        lb = rb.get("pass_rate") if rb else None
        row["L1"] = {"a": la, "b": lb, "status": _status(la, lb)}
        if cid in a_l2c or cid in b_l2c:
            l2a = a_l2c[cid].get("pass_rate") if cid in a_l2c else None
            l2b = b_l2c[cid].get("pass_rate") if cid in b_l2c else None
            row["L2"] = {"a": l2a, "b": l2b, "status": _status(l2a, l2b)}
        case_diff.append(row)
    return headline, case_diff


# ========== retrieval 轨 ==========
def _compare_retrieval(a_dir: Path, b_dir: Path) -> tuple[dict, list[dict]]:
    a = _load(a_dir / "retrieval_eval_result.json")
    b = _load(b_dir / "retrieval_eval_result.json")
    a_all = a["aggregate"].get("ALL", {})
    b_all = b["aggregate"].get("ALL", {})
    headline = {"RAG": _delta(a_all, b_all, ["R@1", "R@3", "R@5", "P@3", "MRR"])}

    a_q = {r["id"]: r for r in a["per_query"]}
    b_q = {r["id"]: r for r in b["per_query"]}
    case_diff = []
    for qid in sorted(set(a_q) | set(b_q)):
        ra, rb = a_q.get(qid), b_q.get(qid)
        # 以 R@3 命中与否作为 per-query 翻转判定
        pa = (ra["R@3"] > 0) if ra and ra.get("R@3") is not None else None
        pb = (rb["R@3"] > 0) if rb and rb.get("R@3") is not None else None
        case_diff.append({
            "case_id": qid,
            "bucket": (ra or rb).get("bucket"),
            "RAG": {"a": pa, "b": pb, "status": _status(pa, pb),
                    "a_mrr": ra.get("MRR") if ra else None,
                    "b_mrr": rb.get("MRR") if rb else None},
        })
    return headline, case_diff


def compare(exp_id: str, variant_a: str, variant_b: str) -> dict:
    exp_dir = EXPERIMENTS_ROOT / exp_id
    manifest = _load(exp_dir / "manifest.json")
    track = manifest["track"]
    a_dir = exp_dir / "variants" / variant_a / "eval"
    b_dir = exp_dir / "variants" / variant_b / "eval"

    if track == "agent":
        headline, case_diff = _compare_agent(a_dir, b_dir)
    elif track == "retrieval":
        headline, case_diff = _compare_retrieval(a_dir, b_dir)
    else:
        raise ValueError(f"未知 track: {track}")

    out = {
        "exp_id": exp_id,
        "track": track,
        "variant_a": variant_a,
        "variant_b": variant_b,
        "headline_delta": headline,
        "case_diff": case_diff,
    }
    (exp_dir / "compare.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def compare_with_detail(exp_id: str, variant_a: str, variant_b: str) -> dict:
    """compare() + 逐 case 的 A/B 明细（前端下钻抽屉用，不写盘）。
    detail[case_id] = {question, a:{l1,l2}, b:{l1,l2}}，retrieval 轨为 {a,b} per_query 行。"""
    out = compare(exp_id, variant_a, variant_b)
    exp_dir = EXPERIMENTS_ROOT / exp_id
    a_dir = exp_dir / "variants" / variant_a / "eval"
    b_dir = exp_dir / "variants" / variant_b / "eval"
    detail: dict[str, dict] = {}

    if out["track"] == "agent":
        a_l1c, b_l1c = _load(a_dir / "l1_case_result.json"), _load(b_dir / "l1_case_result.json")
        a_l2c, b_l2c = _load(a_dir / "l2_case_result.json"), _load(b_dir / "l2_case_result.json")

        def _l1_detail(r):
            if not r:
                return None
            return {k: r.get(k) for k in
                    ("spec_tool", "n", "pass_rate", "hit_rate", "misfire_rate", "runs")}

        def _l2_detail(r):
            if not r:
                return None
            return {k: r.get(k) for k in
                    ("n", "pass_rate", "hit_rate", "faithfulness_rate", "runs")}

        for row in out["case_diff"]:
            cid = row["case_id"]
            src = a_l2c.get(cid) or b_l2c.get(cid) or {}
            detail[cid] = {
                "question": src.get("question", ""),
                "a": {"l1": _l1_detail(a_l1c.get(cid)), "l2": _l2_detail(a_l2c.get(cid))},
                "b": {"l1": _l1_detail(b_l1c.get(cid)), "l2": _l2_detail(b_l2c.get(cid))},
            }
    elif out["track"] == "retrieval":
        a = {r["id"]: r for r in _load(a_dir / "retrieval_eval_result.json")["per_query"]}
        b = {r["id"]: r for r in _load(b_dir / "retrieval_eval_result.json")["per_query"]}
        for row in out["case_diff"]:
            cid = row["case_id"]
            detail[cid] = {"question": "", "a": a.get(cid), "b": b.get(cid)}

    out["detail"] = detail
    return out


def _print(out: dict) -> None:
    print(f"\n=========== A/B：{out['variant_a']} vs {out['variant_b']}  (track={out['track']}) ===========")
    print(f"{'层/指标':<24}{'A':>10}{'B':>10}{'Δ':>10}")
    for layer, metrics in out["headline_delta"].items():
        for k, d in metrics.items():
            fa = f"{d['a']*100:.2f}%" if isinstance(d["a"], (int, float)) else "-"
            fb = f"{d['b']*100:.2f}%" if isinstance(d["b"], (int, float)) else "-"
            fd = f"{d['delta']*100:+.2f}%" if isinstance(d["delta"], (int, float)) else "-"
            print(f"{layer+'·'+k:<24}{fa:>10}{fb:>10}{fd:>10}")

    flips = [c for c in out["case_diff"]
             for layer in ("L1", "L2", "RAG") if c.get(layer, {}).get("status") in ("improved", "regressed")]
    print(f"\n翻转样本（improved/regressed）：{len(flips)} 处，详见 compare.json 的 case_diff")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("用法：uv run python -m src.experiment.compare <exp_id> <variant_a> <variant_b>")
        sys.exit(1)
    _print(compare(sys.argv[1], sys.argv[2], sys.argv[3]))
