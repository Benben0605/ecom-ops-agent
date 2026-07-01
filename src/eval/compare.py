"""单 Agent vs 多 Agent 对比 harness（架构选型四问·④数据裁决）。
跑两套 agent 各打全套评估集，judge 出 headline + 分桶 misfire，并排对照。"""
from collections import defaultdict
import json
from pathlib import Path

from src.eval.answer_runner import eval_answer_run, multi_agent_run
from src.eval.judge import eval_judge, summarize_results

LOGS = Path(__file__).parents[2] / "logs"
_TRANSIENT = ["audit.jsonl", "run_map.json", "session_messages.jsonl",
              "case_eval_result.json", "eval_metrics.json"]


def _clear():
    for f in _TRANSIENT:
        p = LOGS / f
        if p.exists():
            p.unlink()


def _bucket_misfire(case_eval: dict) -> dict:
    agg = defaultdict(lambda: [0, 0])  # bucket -> [总数, misfire数]
    for v in case_eval.values():
        agg[v["bucket"]][0] += 1
        if v["is_misfire"]:
            agg[v["bucket"]][1] += 1
    return agg


def run_arch(run_fn) -> tuple[dict, dict]:
    _clear()
    run_dir = run_fn()  # runner 返回隔离 trace 目录，judge 对齐读取（修断链）
    case_eval = eval_judge(run_dir)
    return summarize_results(case_eval), _bucket_misfire(case_eval)


if __name__ == "__main__":
    print(">>> 跑单 Agent ...")
    single_m, single_b = run_arch(eval_answer_run)
    print(">>> 跑多 Agent ...")
    multi_m, multi_b = run_arch(multi_agent_run)

    print("\n================ 单 Agent vs 多 Agent ================")
    print(f"{'指标':<16}{'单Agent':>12}{'多Agent':>12}")
    print(f"{'路由准确率':<16}{single_m['routing_accuracy']*100:>11.2f}%{multi_m['routing_accuracy']*100:>11.2f}%")
    print(f"{'误触发率':<16}{single_m['misfire_rate']*100:>11.2f}%{multi_m['misfire_rate']*100:>11.2f}%")

    print(f"\n{'bucket misfire':<16}{'单Agent':>12}{'多Agent':>12}")
    for b in sorted(set(single_b) | set(multi_b)):
        s = single_b.get(b, [0, 0]); m = multi_b.get(b, [0, 0])
        print(f"{b:<16}{f'{s[1]}/{s[0]}':>12}{f'{m[1]}/{m[0]}':>12}")
