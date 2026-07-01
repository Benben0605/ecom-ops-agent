"""统一实验 harness（2.0 度量线骨架）。

一次 experiment 跑一条轨道的多个变体；每个变体：隔离 trace → 三层判分 → headline + per-sample，
全部落 logs/experiments/<exp_id>/，带 provenance（commit/ts/dataset_sha），
供 experiment_compare 出 A/B headline delta + 下钻索引。

轨道（track）——一次 run 只走一条，不白跑无关层：
- agent：变体改 system_prompt / 工具子集，跑 eval_cases 产 trace，L1(eval_judge)+L2(eval_l2_judge) 同判。
- retrieval：变体改 chunker，跑 eval_retrieval 出 Recall@k/P@k/MRR。

产物布局：
  logs/experiments/<exp_id>/
    manifest.json
    variants/<name>/trace/   (agent 轨：audit.jsonl/run_map.json/session_messages.jsonl)
    variants/<name>/eval/    (l1_metrics.json l1_case_result.json l2_* / retrieval_eval_result.json)
"""
from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import json
import subprocess
from pathlib import Path

from src import config
from src.agent import (
    ChatSession,
    _system_prompt,
    tools as DEFAULT_TOOL_SCHEMAS,
    TOOLS as DEFAULT_TOOL_IMPLS,
)
from src.eval.answer_runner import eval_answer_run
from src.eval.judge import eval_judge
from src.eval.l2.judge import run_l2
from src.eval.retrieval import run as run_retrieval, chunk_baseline

ROOT = Path(__file__).parents[2]
EXPERIMENTS_ROOT = ROOT / "logs" / "experiments"


@dataclass
class Variant:
    name: str
    config: dict = field(default_factory=dict)


@dataclass
class Experiment:
    name: str
    track: str  # "agent" | "retrieval"
    variants: list[Variant]
    n: int = 1  # 每变体重复跑数；当前实现 n=1，>1 留后续（manifest 记录，供后续 CI 扩展）
    case_filter: list[str] | None = None  # agent 轨只跑这组 case_id（冒烟验证省预算）；None=全集


# ========== provenance ==========
def _git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
    except Exception:
        return "unknown"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _provenance(exp: Experiment) -> dict:
    sha = {"eval_cases": _sha256(ROOT / "data" / "eval_cases.json")}
    if exp.track == "retrieval":
        sha["retrieval_eval"] = _sha256(ROOT / "data" / "retrieval_eval.json")
        sha["corpus"] = _sha256(ROOT / "data" / "faq" / "corpus.json")
    return {
        "git_commit": _git_commit(),
        "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
        "n": exp.n,
        "track": exp.track,
        "dataset_sha": sha,
    }


# ========== agent 轨 ==========
def _make_agent_factory(cfg: dict):
    """把变体 config 映射成 eval_answer_run 需要的 make_agent(recorder)->agent。
    变体旋钮：model（默认 config.MODEL）、system_prompt（默认现网 prompt）、工具子集（tool_schemas/tool_impls）。"""
    model = cfg.get("model", config.MODEL)
    system_prompt = cfg.get("system_prompt", _system_prompt)
    tool_schemas = cfg.get("tool_schemas", DEFAULT_TOOL_SCHEMAS)
    tool_impls = cfg.get("tool_impls", DEFAULT_TOOL_IMPLS)

    def make_agent(recorder):
        return ChatSession(
            system_prompt=system_prompt,
            audit_recorder=recorder,
            tool_schemas=tool_schemas,
            tool_impls=tool_impls,
            model=model,
        )

    return make_agent


def _l2_passed(r: dict) -> bool:
    """单次 L2：无 miss 且无 unsupported 才算过（口径与 l2_dashboard 一致）。"""
    v = r.get("verdict", {})
    miss = any(h["verdict"] == "miss" for h in v.get("hit_axis", []))
    unsup = any(a["verdict"] == "unsupported" for a in v.get("faithfulness_axis", []))
    return not (miss or unsup)


def _aggregate_l1(per_run: list[dict]) -> tuple[dict, dict]:
    """N 次 eval_judge 结果 → per-case per-run 通过率 + headline。
    每个 case 跑 N 次，pass_rate=N 次里 pass 的比例（正样本 pass=命中且不误触发；负样本 pass=不误触发）。"""
    case_ids = {cid for pr in per_run for cid in pr}
    case_result: dict[str, dict] = {}
    for cid in case_ids:
        runs = [pr[cid] for pr in per_run if cid in pr]
        spec = runs[0]["spec_tool"]
        positive = bool(spec)
        n = len(runs)
        hit_runs = sum(1 for r in runs if r["is_hit"])
        misfire_runs = sum(1 for r in runs if r["is_misfire"])
        if positive:
            pass_runs = sum(1 for r in runs if r["is_hit"] and not r["is_misfire"])
        else:
            pass_runs = sum(1 for r in runs if not r["is_misfire"])
        case_result[cid] = {
            "case_id": cid,
            "bucket": runs[0]["bucket"],
            "spec_tool": spec,
            "n": n,
            "pass_rate": pass_runs / n,
            "hit_rate": (hit_runs / n) if positive else None,
            "misfire_rate": misfire_runs / n,
            "runs": [{k: r[k] for k in
                      ("called_tools", "missing_tools", "unexpected_tools", "is_hit", "is_misfire")}
                     for r in runs],
        }
    pos = [c for c in case_result.values() if c["spec_tool"]]
    metrics = {
        "evaluated_case_count": len(case_result),
        "positive_case_count": len(pos),
        "n": max((c["n"] for c in case_result.values()), default=0),
        "routing_accuracy": (sum(c["hit_rate"] for c in pos) / len(pos)) if pos else 0,
        "misfire_rate": (sum(c["misfire_rate"] for c in case_result.values()) / len(case_result))
                        if case_result else 0,
    }
    return case_result, metrics


def _aggregate_l2(per_run: list[dict]) -> tuple[dict, dict]:
    """N 次 run_l2 结果 → per-case per-run 通过率 + headline。
    pass_rate=N 次里 pass 比例；hit_rate/faith_rate 为 N 次池化（命中点/断言累加）。"""
    case_ids = {cid for pr in per_run for cid in pr}
    case_result: dict[str, dict] = {}
    tot_hit_ok = tot_hit_total = tot_faith_ok = tot_faith_total = 0
    for cid in case_ids:
        runs = [pr[cid] for pr in per_run if cid in pr and "score" in pr[cid]]
        if not runs:
            continue
        n = len(runs)
        pass_runs = sum(1 for r in runs if _l2_passed(r))
        hit_ok = sum(r["score"]["hit_ok"] for r in runs)
        hit_total = sum(r["score"]["hit_total"] for r in runs)
        faith_ok = sum(r["score"]["faith_ok"] for r in runs)
        faith_total = sum(r["score"]["faith_total"] for r in runs)
        tot_hit_ok += hit_ok; tot_hit_total += hit_total
        tot_faith_ok += faith_ok; tot_faith_total += faith_total
        case_result[cid] = {
            "case_id": cid,
            "bucket": runs[0]["bucket"],
            "question": runs[0]["question"],
            "n": n,
            "pass_rate": pass_runs / n,
            "hit_rate": hit_ok / hit_total if hit_total else None,
            "faithfulness_rate": faith_ok / faith_total if faith_total else None,
            "runs": [{"answer": r["answer"], "verdict": r["verdict"],
                      "score": r["score"], "passed": _l2_passed(r)} for r in runs],
        }
    metrics = {
        "case_count": len(case_result),
        "n": max((c["n"] for c in case_result.values()), default=0),
        "case_pass_rate": (sum(c["pass_rate"] for c in case_result.values()) / len(case_result))
                          if case_result else None,
        "hit_rate": tot_hit_ok / tot_hit_total if tot_hit_total else None,
        "faithfulness_rate": tot_faith_ok / tot_faith_total if tot_faith_total else None,
    }
    return case_result, metrics


# ========== 跑变体 ==========
def _write(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def run_variant(exp: Experiment, variant: Variant, exp_dir: Path) -> Path:
    vdir = exp_dir / "variants" / variant.name
    trace_dir = vdir / "trace"
    eval_dir = vdir / "eval"
    trace_dir.mkdir(parents=True, exist_ok=True)
    eval_dir.mkdir(parents=True, exist_ok=True)

    if exp.track == "agent":
        make_agent = _make_agent_factory(variant.config)
        # 每个 case 跑 N 次：第 i 次写独立子目录 trace/run_<i>/，judge 原样跑（一 case 一 session），
        # 再在 harness 层把 N 份判分聚成 per-run 通过率。judge 零改动。
        per_run_l1, per_run_l2 = [], []
        for i in range(1, exp.n + 1):
            rdir = trace_dir / f"run_{i}"
            eval_answer_run(make_agent=make_agent, run_dir=rdir, case_filter=exp.case_filter)
            per_run_l1.append(eval_judge(run_dir=rdir))
            per_run_l2.append(run_l2(run_dir=rdir))

        l1_case, l1_metrics = _aggregate_l1(per_run_l1)
        l2_case, l2_metrics = _aggregate_l2(per_run_l2)
        _write(eval_dir / "l1_case_result.json", l1_case)
        _write(eval_dir / "l1_metrics.json", l1_metrics)
        _write(eval_dir / "l2_case_result.json", l2_case)
        _write(eval_dir / "l2_metrics.json", l2_metrics)

    elif exp.track == "retrieval":
        chunker = variant.config.get("chunker", chunk_baseline)
        run_retrieval(chunker=chunker, out_dir=eval_dir)

    else:
        raise ValueError(f"未知 track: {exp.track}")

    return vdir


def _config_summary(cfg: dict) -> dict:
    """把变体 config 转成 JSON 安全的摘要写进 manifest（callable/工具 impls 不可序列化）。"""
    out = {}
    for k, val in cfg.items():
        if callable(val):
            out[k] = getattr(val, "__name__", str(val))
        elif k == "tool_impls" and isinstance(val, dict):
            out[k] = sorted(val.keys())
        else:
            out[k] = val
    return out


def run_experiment(exp: Experiment) -> Path:
    exp_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{exp.name}"
    exp_dir = EXPERIMENTS_ROOT / exp_id
    exp_dir.mkdir(parents=True, exist_ok=True)

    for v in exp.variants:
        print(f">>> 跑变体 [{v.name}] ...")
        run_variant(exp, v, exp_dir)

    manifest = {
        "exp_id": exp_id,
        "name": exp.name,
        "track": exp.track,
        "variants": [{"name": v.name, "config": _config_summary(v.config)} for v in exp.variants],
        "provenance": _provenance(exp),
    }
    _write(exp_dir / "manifest.json", manifest)

    names = [v.name for v in exp.variants]
    print(f"\n实验落盘：{exp_dir}")
    if len(names) >= 2:
        print(f"对比：uv run python -m src.experiment.compare {exp_id} {names[0]} {names[1]}")
    return exp_dir


def list_experiments() -> list[dict]:
    """列出所有实验的 manifest（最新在前），供前端选择。"""
    if not EXPERIMENTS_ROOT.exists():
        return []
    out = []
    for d in sorted(EXPERIMENTS_ROOT.iterdir(), reverse=True):
        mf = d / "manifest.json"
        if mf.exists():
            out.append(json.loads(mf.read_text(encoding="utf-8")))
    return out


if __name__ == "__main__":
    # 变体定义（A/B 两套配置），全量/指定 case 两种跑法共用
    variants = [
        Variant("A_baseline", {}),
        Variant("B_concise", {"system_prompt": "你是私域电商运营客服助手，负责订单查询、售后/政策咨询、商品推荐和运营数据分析，善于利用工具解决问题。涉及多政策主题的问题,分别检索每个主题（退换货问题分别查退货政策和换货政策）。必填参数齐全时直接调用工具，不要因为选填参数缺失而反问；但若必填参数缺失且无法从对话中合理推断，应先向用户询问澄清，不要猜测或随意填充必填参数。如果是电商业务相关但无工具，调用 escalate_to_human 转人工，不要硬调最接近的工具兜底。只陈述工具/检索输出明确给出的事实；不合并、不外推、不把某政策条目的细节（操作步骤/时效/运费/适用范围）搬到另一条目上（如换货政策只写了时限和运费、没有操作步骤，就别拿退货流程的步骤当换货步骤；某条目没有的就说没有、按该政策申请即可）；工具没提的（取消/额外时效/适用范围/操作步骤）一律不编"}),
    ]

    # ① 全量跑（72 case × 变体数 + L2 judge，几分钟 + 有 API 费用）
    # run_experiment(Experiment(name="prompt_ab", track="agent", variants=variants))

    # ② prompt 引导 agent 对退换货发两次 kb_search(退货政策 + 换货政策)
    run_experiment(Experiment(
        name="case049_exchange_recall_prompt_ab",
        track="agent",
        variants=variants,
        n = 4,
        case_filter=["case_049"],
    ))
