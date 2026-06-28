"""检索可观测链路（Phase2）：对走 kb_search 的评估 case 跑真 agent，摊开全链路供人工裁决。

链路：case 原句 → LLM 改写的 kb param → 检索 top_k(item, sim) → grader(can_answer, reason)
      → 留 chunk / abstain → 最终答案。

依赖 kb_search.TRACE（每次检索记一条 query→命中→判定→留弃）。输出 logs/kb_observe.{json,md}，
md 供人读着逐条裁决「这个 abstain 该不该」。kb case 从 eval_cases.json 动态取（expected_calls 含 kb_search）。
"""
import json
from pathlib import Path

from src.tools import kb_search
from src.agent import ChatSession
from src.audit import NoOpRecorder

ROOT = Path(__file__).parents[1]


def kb_cases() -> list[dict]:
    cases = json.loads((ROOT / "data" / "eval_cases.json").read_text(encoding="utf-8"))
    return [c for c in cases
            if any(d.get("tool_name") == "kb_search" for d in c.get("expected_calls", []))]


class _Cap(NoOpRecorder):
    def __init__(self): self.calls = []
    def record(self, a): self.calls.append(a.tool_name)


def observe() -> list[dict]:
    rows = []
    for c in kb_cases():
        kb_search.TRACE.clear()
        rec = _Cap()
        ans = ChatSession(audit_recorder=rec).chat(c["question"])
        rows.append({
            "case_id": c["id"], "bucket": c["bucket"], "question": c["question"],
            "kb_calls": [dict(t) for t in kb_search.TRACE],
            "tools": rec.calls, "answer": ans,
        })
    return rows


def write_reports(rows: list[dict]):
    (ROOT / "logs").mkdir(exist_ok=True)
    (ROOT / "logs" / "kb_observe.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = ["# KB 检索可观测链路\n",
             "> 链路：原句 → LLM改写kb param → 检索top_k(item,sim) → grader判定 → 留/abstain → 答案\n"]
    for r in rows:
        lines.append(f"\n## [{r['case_id']}] {r['bucket']}")
        lines.append(f"**原句**：{r['question']}")
        for t in r["kb_calls"]:
            mark = "✅ 留" if t["outcome"] == "answer" else "⛔ **ABSTAIN**"
            lines.append(f"- kb param「{t['query']}」→ 留 {t['kept']}/{len(t['chunks'])}　{mark}")
            for c in t["chunks"]:
                keep = "✅相关" if c["relevant"] else "✗弃"
                lines.append(f"  - {c['item']}({c['sim']}) {keep} —— {c['reason']}")
        lines.append(f"- 工具序列：{r['tools']}")
        lines.append(f"- 最终答案：{r['answer'][:300].strip()}")
    (ROOT / "logs" / "kb_observe.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    rows = observe()
    write_reports(rows)
    ab = [(r["case_id"], t["query"], "全部弃: " + "/".join(c["item"] for c in t["chunks"]))
          for r in rows for t in r["kb_calls"] if t["outcome"] == "abstain"]
    print(f"观测 {len(rows)} 个 kb case，报告 → logs/kb_observe.md（人读）/ .json（程序读）")
    print(f"触发 abstain：{len(ab)}")
    for cid, q, reason in ab:
        print(f"  [{cid}] 「{q}」← {reason}")
