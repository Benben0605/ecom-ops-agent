import json
from pathlib import Path

from openai import OpenAI

from src import config

client = OpenAI(api_key=config.API_KEY, base_url=config.BASE_URL)

ROOT = Path(__file__).parents[1]

# 只有事实桶才有 golden、才进 L2；clarify/negative/weakness 缺席即信号
FACTUAL_BUCKETS = {"direct", "rephrased", "multi_intent", "confusing"}


def load_l2_inputs() -> dict[str, dict]:
    """组装每个已标 golden 的事实桶 case 的 judge 三件套。
    返回 {case_id: {question, answer, tool_outputs(池), golden_points, bucket}}"""
    cases = json.loads((ROOT / "data" / "eval_cases.json").read_text(encoding="utf-8"))
    run_map = json.loads((ROOT / "logs" / "run_map.json").read_text(encoding="utf-8"))

    sess_by_id: dict[str, list] = {}
    with open(ROOT / "logs" / "session_messages.jsonl", encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            sess_by_id[d["session_id"]] = d["messages"]

    case_to_session = {r["case_id"]: r["session_id"] for r in run_map}

    inputs: dict[str, dict] = {}
    for c in cases:
        gp = c.get("golden_answer_points")
        if c["bucket"] not in FACTUAL_BUCKETS or not gp:
            continue
        sid = case_to_session.get(c["id"])
        if sid is None:
            continue
        msgs = sess_by_id.get(sid, [])
        answer = next(
            (m["content"] for m in reversed(msgs)
             if m["role"] == "assistant" and m.get("content")),
            "",
        )
        tool_outputs = [m["content"] for m in msgs if m["role"] == "tool"]
        inputs[c["id"]] = {
            "question": c["question"],
            "answer": answer,
            "tool_outputs": tool_outputs,
            "golden_points": gp,
            "bucket": c["bucket"],
        }
    return inputs


# ========== 招牌核心：由你来写 ==========
# 要求 judge 输出严格遵守上面定死的 schema：
#   {"hit_axis":[{point,verdict:hit|miss}],
#    "faithfulness_axis":[{assertion,verdict:supported|unsupported,evidence}]}
JUDGE_SYSTEM_PROMPT = """
关键约束：
- 命中轴：遍历 golden_points，每个 point 判 answer 说了没（hit/miss）。
- 忠实轴分两道独立工序，别混：
  · 【抽取层】从 answer 挑出要进忠实轴的句子。唯一闸门=可证伪性：只抽「能用 tool output
    判对/错的客观事实陈述」。无法用对错核的——主观评价、营销修辞、定性归纳（如「一整套搭配」）、
    服务承诺/行动引导（如「联系我跟进」）、寒暄粘合剂——都不是事实断言，不抽。
    注意：「这三款都适合敏感肌」这类可证伪的归纳要抽（之后判它有没有据），别因为是归纳就放过。
  · 【判定层】对已抽进来的每条断言，到 tool_outputs 整池找支撑，判 supported/unsupported。
    看语义不看字面：能由池中某段原文【语义等价/概括/直接推出】即 supported（依据可能埋在
    长文、跨多行，须通读整池）；evidence 引那段原文。整池都找不到任何语义依据才判 unsupported。
- 逐项独立判断，别让前一项的结论带偏后一项。

请严格输出如下结构的 JSON：
{
    "hit_axis": [
        {
            "point": "<golden point 原文>", 
            "verdict": "hit | miss",
            "evidence": "<支撑它的那段 assistant answer 原文；miss 留空>"
        }
    ],
    "faithfulness_axis": [
        {
            "assertion": "<从答案抽出的事实性断言>",
            "verdict": "supported | unsupported",
            "evidence": "<支撑它的那段 tool output 原文；unsupported 留空>"
        }
    ]
}
"""


def build_user_payload(item: dict) -> str:
    return json.dumps(
        {
            "question": item["question"],
            "answer": item["answer"],
            "tool_outputs": item["tool_outputs"],
            "golden_points": item["golden_points"],
        },
        ensure_ascii=False,
        indent=2,
    )


def judge_one(item: dict) -> dict:
    resp = client.chat.completions.create(
        model=config.MODEL,
        messages=[
            {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
            {"role": "user", "content": build_user_payload(item)},
        ],
        response_format={"type": "json_object"},
        temperature=0,
    )
    return json.loads(resp.choices[0].message.content)


def score_one(verdict: dict) -> dict:
    hits = verdict.get("hit_axis", [])
    faith = verdict.get("faithfulness_axis", [])
    hit_ok = sum(1 for h in hits if h["verdict"] == "hit")
    faith_ok = sum(1 for a in faith if a["verdict"] == "supported")
    return {
        "hit_ok": hit_ok,
        "hit_total": len(hits),
        "hit_rate": hit_ok / len(hits) if hits else None,
        "faith_ok": faith_ok,
        "faith_total": len(faith),
        "faithfulness_rate": faith_ok / len(faith) if faith else None,
    }


def run_l2():
    inputs = load_l2_inputs()
    results = {}
    for case_id, item in inputs.items():
        verdict = judge_one(item)
        results[case_id] = {
            "bucket": item["bucket"],
            "question": item["question"],
            "answer": item["answer"],
            "verdict": verdict,
            "score": score_one(verdict),
        }
    return results


if __name__ == "__main__":
    results = run_l2()
    out_path = ROOT / "logs" / "l2_eval_result.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    for cid, r in results.items():
        s = r["score"]
        print(f"\n[{cid}] {r['bucket']}  命中 {s['hit_ok']}/{s['hit_total']}  "
              f"忠实 {s['faith_ok']}/{s['faith_total']}")
        for h in r["verdict"].get("hit_axis", []):
            mark = "✓" if h["verdict"] == "hit" else "✗"
            print(f"  命中 {mark} {h['point']}")
        for a in r["verdict"].get("faithfulness_axis", []):
            mark = "✓" if a["verdict"] == "supported" else "✗"
            print(f"  忠实 {mark} {a['assertion']}  ← {a.get('evidence','')}")
