"""kb_search 消融实验 harness（工程化「正确姿势」：参数化变量、同代码跑配置矩阵、
结果落 logs/runs/<ts>/ 带 provenance、一次一变量、N 跑）。

为什么不用旧代码/git worktree：grader 和 top_k 都参数化成 kb_search 的模块级开关，
同一份代码 toggle 即可——参数化省掉了下旧代码。corpus 固定 60（4→60 的影响另由
检索 trace 归因）。

变量隔离：
- A(grader_off, k3) vs B(grader_on, k3)：同 corpus 同 top_k，只 grader → 隔离 grader 效应
- B(grader_on, k3) vs C(grader_on, k5)：同 corpus 同 grader，只 top_k → 隔离 top_k 效应（049 验证）

跑法：python -m src.experiment_kb [N]
"""
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from src.tools import kb_search
from src.agent import ChatSession
from src.audit import AuditRecorder, MessageRecorder
from src.eval_l2_judge import run_l2

ROOT = Path(__file__).parents[1]
LOGS = ROOT / "logs"
KB_CASES = ['case_004', 'case_005', 'case_013', 'case_016', 'case_026', 'case_027',
            'case_031', 'case_033', 'case_040', 'case_045', 'case_047', 'case_048',
            'case_049', 'case_051', 'case_052']

CONFIGS = [
    {"name": "A_grader_off_k3", "grader": False, "top_k": 3},
    {"name": "B_grader_on_k3",  "grader": True,  "top_k": 3},
    {"name": "C_grader_on_k5",  "grader": True,  "top_k": 5},
]


def _git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    except Exception:
        return "unknown"


def _run_cases_once() -> dict:
    """跑 15 个 kb case 一遍，落 run_map+session_messages，judge，返回每 case 的 score。"""
    (LOGS / "session_messages.jsonl").write_text("", encoding="utf-8")
    cases = {c['id']: c for c in json.loads((ROOT / "data" / "eval_cases.json").read_text(encoding="utf-8"))}
    run_map = []
    for cid in KB_CASES:
        s = ChatSession(audit_recorder=AuditRecorder(recorder_path=LOGS / "audit.jsonl"))
        s.chat(cases[cid]['question'])
        MessageRecorder(recorder_path=LOGS / "session_messages.jsonl").record(
            {"session_id": s.id, "messages": s.messages})
        run_map.append({"case_id": cid, "session_id": s.id})
    (LOGS / "run_map.json").write_text(json.dumps(run_map, ensure_ascii=False, indent=2), encoding="utf-8")
    return {cid: r.get("score") for cid, r in run_l2().items()}


def run_experiment(n: int = 2):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = LOGS / "runs" / f"{ts}_kb_ablation"
    run_dir.mkdir(parents=True, exist_ok=True)
    # 备份用户 logs
    bak = {p: (LOGS / p).read_text(encoding="utf-8") if (LOGS / p).exists() else None
           for p in ("run_map.json", "session_messages.jsonl")}

    results = {"provenance": {"git_commit": _git_commit(), "timestamp": ts, "n": n,
                              "corpus": "corpus.json(60)", "cases": KB_CASES},
               "configs": {}}
    try:
        for cfg in CONFIGS:
            kb_search.GRADER_ENABLED = cfg["grader"]
            kb_search.TOP_K = cfg["top_k"]
            kb_search._indexed = False  # 保证干净（corpus 不变，仅重置标志）
            # N 跑累加每 case 的 hit/total、faith/total
            acc = {cid: {"hit": 0, "hit_tot": 0, "faith": 0, "faith_tot": 0} for cid in KB_CASES}
            for _ in range(n):
                scores = _run_cases_once()
                for cid, s in scores.items():
                    if not s:
                        continue
                    acc[cid]["hit"] += s["hit_ok"]; acc[cid]["hit_tot"] += s["hit_total"]
                    acc[cid]["faith"] += s["faith_ok"]; acc[cid]["faith_tot"] += s["faith_total"]
            results["configs"][cfg["name"]] = {"config": cfg, "per_case": acc}
            print(f"[done] {cfg['name']}")
    finally:
        # 还原 kb_search 默认 + 用户 logs
        kb_search.GRADER_ENABLED, kb_search.TOP_K, kb_search._indexed = True, 3, False
        for p, txt in bak.items():
            if txt is not None:
                (LOGS / p).write_text(txt, encoding="utf-8")

    (run_dir / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    _print_table(results)
    print(f"\n结果落盘 → {run_dir.relative_to(ROOT)}/results.json（provenance: {results['provenance']['git_commit'][:8]}）")
    return results


def _agg(per_case, key, tot):
    s = sum(per_case[c][key] for c in per_case); t = sum(per_case[c][tot] for c in per_case)
    return s, t, (s / t if t else 0)


def _print_table(results):
    print(f"\n{'='*70}\nkb 消融（N={results['provenance']['n']}, corpus=60, 15 kb case）")
    print(f"  {'config':18} {'命中率':>10} {'忠实率':>10}")
    for name, r in results["configs"].items():
        hs, ht, hr = _agg(r["per_case"], "hit", "hit_tot")
        fs, ft, fr = _agg(r["per_case"], "faith", "faith_tot")
        print(f"  {name:18} {hs}/{ht}={hr:5.1%} {fs}/{ft}={fr:5.1%}")
    # 049 单看（top_k 验证）
    print("\n  case_049（top_k 验证·换货块该捞回）逐配置命中：")
    for name, r in results["configs"].items():
        a = r["per_case"]["case_049"]
        print(f"    {name:18} 命中 {a['hit']}/{a['hit_tot']}")
    print("\n  隔离读法：A→B 同corpus同top_k只grader（看忠实是否升、命中是否持平）；"
          "B→C 同corpus同grader只top_k（看049命中是否升）")


if __name__ == "__main__":
    run_experiment(int(sys.argv[1]) if len(sys.argv) > 1 else 2)
