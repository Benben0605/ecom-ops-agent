"""统一实验 harness（2.0 度量线骨架）。

一次 experiment 跑一条轨道的多个变体；每个变体：隔离 trace → 三层判分 → headline + per-sample，
全部落 logs/experiments/<exp_id>/，带 provenance（commit/ts/dataset_sha），
供 experiment_compare 出 A/B headline delta + 下钻索引。

轨道（track）——一次 run 只走一条，不白跑无关层：
- agent：变体改 system_prompt / 工具子集，跑 eval_cases 产 trace，L1(eval_judge)+L2(eval_l2_judge) 同判。
- retrieval：变体改 chunker，跑 eval_retrieval 出 Recall@k/P@k/MRR。

variants：同一 Experiment 下的多套配置（name + config dict），harness 逐一跑完后可用
  experiment_compare 出 A/B headline delta。单臂跑只放一个 Variant 即可。

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
import sys
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


VALID_STAGES = ("run", "l1", "l2")


@dataclass
class Experiment:
    name: str
    track: str  # "agent" | "retrieval"
    variants: list[Variant]
    n: int = 1  # 每变体重复跑数；当前实现 n=1，>1 留后续（manifest 记录，供后续 CI 扩展）
    case_filter: list[str] | None = None  # agent 轨只跑这组 case_id（冒烟验证省预算）；None=全集
    bucket_filter: list[str] | None = None  # 按桶选 case；与 case_filter 取并集
    stages: tuple = VALID_STAGES  # 选择性执行：("run",) / ("l1","l2") / 任意组合，默认全跑
    exp_id: str | None = None  # 复用已有实验目录（judge-only 时从它的 trace 取答案，不重跑 agent）


def _resolve_case_ids(exp: Experiment) -> list[str] | None:
    """case_filter ∪ bucket_filter 展开成 case_id 列表；两者都空 = None（全集）。
    未知 case_id / bucket 响亮报错，不静默跳过。"""
    if not exp.case_filter and not exp.bucket_filter:
        return None
    cases = json.loads((ROOT / "data" / "eval_cases.json").read_text(encoding="utf-8"))
    all_ids = {c["id"] for c in cases}
    all_buckets = {c["bucket"] for c in cases}
    ids = set(exp.case_filter or [])
    if unknown := ids - all_ids:
        raise ValueError(f"case_filter 里有不存在的 case_id: {sorted(unknown)}")
    if exp.bucket_filter:
        if unknown := set(exp.bucket_filter) - all_buckets:
            raise ValueError(f"bucket_filter 里有不存在的桶: {sorted(unknown)}（现有: {sorted(all_buckets)}）")
        wanted = set(exp.bucket_filter)
        ids |= {c["id"] for c in cases if c["bucket"] in wanted}
    return sorted(ids)


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


def _entrypoint() -> str:
    argv0 = sys.argv[0] if sys.argv else ""
    if not argv0:
        return "unknown"
    try:
        return str(Path(argv0).resolve().relative_to(ROOT))
    except ValueError:
        return argv0


def _provenance(exp: Experiment) -> dict:
    sha = {"eval_cases": _sha256(ROOT / "data" / "eval_cases.json")}
    if exp.track == "retrieval":
        sha["retrieval_eval"] = _sha256(ROOT / "data" / "retrieval_eval.json")
        sha["corpus"] = _sha256(ROOT / "data" / "faq" / "corpus.json")
    return {
        "git_commit": _git_commit(),
        "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
        "entrypoint": _entrypoint(),
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

    def make_agent(recorder, user_context=None):
        return ChatSession(
            system_prompt=system_prompt,
            audit_recorder=recorder,
            tool_schemas=tool_schemas,
            tool_impls=tool_impls,
            model=model,
            user_context=user_context,
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


def _existing_run_dirs(trace_dir: Path) -> list[Path]:
    """按 run_<i> 数字序返回已有 trace 子目录（judge-only 时判分范围跟着 trace 走，n 由 trace 决定）。"""
    dirs = [d for d in trace_dir.glob("run_*") if (d / "run_map.json").exists()]
    return sorted(dirs, key=lambda d: int(d.name.removeprefix("run_") or 0))


def _filter_case_results(per_run: list[dict], case_ids: list[str] | None) -> list[dict]:
    if case_ids is None:
        return per_run
    keep = set(case_ids)
    return [{cid: r for cid, r in run.items() if cid in keep} for run in per_run]


def run_variant(exp: Experiment, variant: Variant, exp_dir: Path,
                case_ids: list[str] | None = None) -> Path:
    vdir = exp_dir / "variants" / variant.name
    trace_dir = vdir / "trace"
    eval_dir = vdir / "eval"
    trace_dir.mkdir(parents=True, exist_ok=True)
    eval_dir.mkdir(parents=True, exist_ok=True)
    stages = tuple(exp.stages)
    if unknown := set(stages) - set(VALID_STAGES):
        raise ValueError(f"未知 stage: {sorted(unknown)}（可选: {VALID_STAGES}）")

    if exp.track == "agent":
        # 每个 case 跑 N 次：第 i 次写独立子目录 trace/run_<i>/，judge 原样跑（一 case 一 session），
        # 再在 harness 层把 N 份判分聚成 per-run 通过率。judge 零改动。
        if "run" in stages:
            make_agent = _make_agent_factory(variant.config)
            for i in range(1, exp.n + 1):
                eval_answer_run(make_agent=make_agent, run_dir=trace_dir / f"run_{i}",
                                case_filter=case_ids)

        run_dirs = _existing_run_dirs(trace_dir)
        if ("l1" in stages or "l2" in stages) and not run_dirs:
            raise FileNotFoundError(
                f"变体 [{variant.name}] 没有可判的 trace（{trace_dir}）——"
                f"先带 run 阶段跑一次，或用 exp_id 指向已有实验目录"
            )

        if "l1" in stages:
            per_run_l1 = _filter_case_results(
                [eval_judge(run_dir=rd) for rd in run_dirs], case_ids)
            l1_case, l1_metrics = _aggregate_l1(per_run_l1)
            _write(eval_dir / "l1_case_result.json", l1_case)
            _write(eval_dir / "l1_metrics.json", l1_metrics)

        if "l2" in stages:
            per_run_l2 = [run_l2(run_dir=rd, case_filter=case_ids) for rd in run_dirs]
            l2_case, l2_metrics = _aggregate_l2(per_run_l2)
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
    if exp.exp_id:  # 复用模式：judge-only / 补阶段，写回同一实验目录
        exp_id = exp.exp_id
        exp_dir = EXPERIMENTS_ROOT / exp_id
        if not exp_dir.exists():
            raise FileNotFoundError(f"exp_id 不存在：{exp_dir}——复用模式必须指向已有实验")
    else:
        exp_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{exp.name}"
        exp_dir = EXPERIMENTS_ROOT / exp_id
        exp_dir.mkdir(parents=True, exist_ok=True)

    case_ids = _resolve_case_ids(exp)
    scope_desc = f"{len(case_ids)} cases" if case_ids is not None else "全集"
    print(f">>> stages={list(exp.stages)} | 范围={scope_desc}")

    for v in exp.variants:
        print(f">>> 跑变体 [{v.name}] ...")
        run_variant(exp, v, exp_dir, case_ids=case_ids)

    old = json.loads((exp_dir / "manifest.json").read_text(encoding="utf-8")) \
        if (exp_dir / "manifest.json").exists() else {}
    manifest = {
        "exp_id": exp_id,
        "name": exp.name,
        "track": exp.track,
        "variants": [{"name": v.name, "config": _config_summary(v.config)} for v in exp.variants],
        "provenance": _provenance(exp),
        # 每次调用（含复用模式补阶段）追加一条，全历史可追溯
        "stage_runs": old.get("stage_runs", []) + [{
            "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
            "stages": list(exp.stages),
            "case_filter": exp.case_filter,
            "bucket_filter": exp.bucket_filter,
            "resolved_case_count": len(case_ids) if case_ids is not None else "all",
            "n": exp.n,
        }],
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


def _cli() -> Experiment:
    """命令行入口（单变体 A_baseline；多变体 A/B 仍走下方编码式）。示例：
    uv run python -m src.experiment.runner --name phase3_l2 --buckets role_flip,personalization --n 3
    uv run python -m src.experiment.runner --name rejudge --exp-id <已有exp_id> --stages l2 --cases case_073,case_075
    """
    import argparse
    p = argparse.ArgumentParser(description="实验 harness：选择性执行 run/l1/l2，case_id/bucket 过滤")
    p.add_argument("--name", required=True, help="实验名（进 exp_id）")
    p.add_argument("--stages", default="run,l1,l2", help="逗号分隔：run,l1,l2 的任意组合")
    p.add_argument("--cases", default=None, help="逗号分隔 case_id，如 case_073,case_075")
    p.add_argument("--buckets", default=None, help="逗号分隔桶名，如 role_flip,personalization；与 --cases 取并集")
    p.add_argument("--exp-id", default=None, help="复用已有实验目录（judge-only 从其 trace 取答案）")
    p.add_argument("--n", type=int, default=1, help="每 case 跑几次（仅 run 阶段用；judge-only 时 n 跟 trace 走）")
    a = p.parse_args()
    return Experiment(
        name=a.name,
        track="agent",
        variants=[Variant("A_baseline", {})],
        n=a.n,
        case_filter=a.cases.split(",") if a.cases else None,
        bucket_filter=a.buckets.split(",") if a.buckets else None,
        stages=tuple(a.stages.split(",")),
        exp_id=a.exp_id,
    )


if __name__ == "__main__":
    if len(sys.argv) > 1:  # 带参 = CLI 模式；不带参 = 下方编码式实验
        run_experiment(_cli())
        raise SystemExit(0)

    # 变体定义（A/B 两套配置），全量/指定 case 两种跑法共用
    variants = [
        Variant("A_baseline", {}),
    ]

    # ① 全量跑（72 case × 变体数 + L2 judge，几分钟 + 有 API 费用）
    # run_experiment(Experiment(name="prompt_ab", track="agent", variants=variants))

    # ② prompt("涉及多政策主题的问题,分别检索每个主题（退换货问题分别查退货政策和换货政策）") 引导 agent 对退换货发两次 kb_search(退货政策 + 换货政策)
    # run_experiment(Experiment(
    #     name="case049_exchange_recall_prompt_ab",
    #     track="agent",
    #     variants=variants,
    #     n = 4,
    #     case_filter=["case_049"],
    # ))

    # ③ 引入 persona前，看“case_017修复时给 system_prompt 加「善于根据用户角色」+ 给 analyze_ops 贴「商家工具」标签“的效果
    # case_017 query“订单数据怎样了？10001。“
    # 从实验结果看：成功将工具调用从 analyze_ops（商家侧） 引向 recommand_product（客户侧）
    # run_experiment(Experiment(
    #     name="case017_fix_prompt_ab",
    #     track="agent",
    #     variants=variants,
    #     n = 4,
    #     case_filter=["case_017"],
    # ))

    # ④ 引入 persona 前，看桶 role_flip 的表现
    # 从实验结果看：在没有persona的情况下，都指向 analyze
    # run_experiment(Experiment(
    #     name="role_flip_before_persona",
    #     track="agent",
    #     variants=variants,
    #     n = 4,
    #     case_filter=["case_073", "case_074", "case_075", "case_076", "case_077"],
    # ))

    # ⑤ 引入 persona 前，看桶 personalization 的表现
    # 预期： “随便推荐点东西吧“都指向 recommand，且param category 是必填，agent指导用户clarify
    # 从实验结果看：@todo
    # run_experiment(Experiment(
    #     name="answer_before_persona",
    #     track="agent",
    #     variants=variants,
    #     n = 4,
    #     case_filter=["case_078", "case_079", "case_080", "case_081", "case_082"],
    # ))

    # ⑥ 修 074/076 商家/顾客问“最近有什么好卖的？“都指向analyze 的问题，system_prompt 加 _AUDIENCE_GATE
    # 预期： 修好074/076
    # 从实验结果看：修好了075，未修好076。_AUDIENCE_GATE 解决了路由问题，076 堵住调用analyze，但是堵住没疏，模型知道要调用recommend，但是一直让用户clarify
    # run_experiment(Experiment(
    #     name="with_tool_audience_gate_after_persona",
    #     track="agent",
    #     variants=variants,
    #     n = 4,
    #     case_filter=["case_074", "case_076"],
    # ))

    # ⑦ 现状076 顾客问“你们坚果卖得好吗？“， agent 知道要调recommend，但是一直让用户clarify，做疏通
    # 预期： 076 直接调用recommend
    # 从实验结果看：076 转绿（recommend description 划入「热不热门」意图面）
    # run_experiment(Experiment(
    #     name="audience_gate_recommend_product_schema_nudge",
    #     track="agent",
    #     variants=variants,
    #     n = 3,
    #     case_filter=["case_073", "case_074", "case_075", "case_076", "case_077",
    #                  "case_078", "case_079", "case_080", "case_081", "case_082"],
    # )) 

    # ⑧ 增加 role-flip, personalization， 完整FACTUAL BUCKET 跑 l1/l2 judge
    # 新能力示例：bucket 过滤 + 全阶段（等价 CLI：--name phase3_two_buckets --buckets role_flip,personalization --n 3）
    run_experiment(Experiment(
        name="phase3_factual_buckets_l1_l2",
        track="agent",
        variants=variants,
        n=3,
        bucket_filter=["direct", "rephrased", "multi_intent", "confusing", "complex_task",
                   "role_flip", "personalization"],
    ))
