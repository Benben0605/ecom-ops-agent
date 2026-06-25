import hashlib
import json
import time
from pathlib import Path

from openai import OpenAI

from src import config

client = OpenAI(api_key=config.API_KEY, base_url=config.BASE_URL)

ROOT = Path(__file__).parents[1]

# 只有事实桶才有 golden、才进 L2；clarify/negative/weakness 缺席即信号
# complex_task（2.0 Phase1）也是事实桶：有 golden（=分解后的子目标）+ tool 输出可对照
FACTUAL_BUCKETS = {"direct", "rephrased", "multi_intent", "confusing", "complex_task"}

# orders.json 是冻结的 eval fixture：部分 golden 按订单状态 key（如已签收/已取消单删 eta，
# 见 case_021/044）。数据一旦改动，这些状态相关的 golden 可能烂掉，必须复核后更新此哈希。
# 守卫的是「改了数据却没复核 golden」的静默漂移（A 方案，详见招牌点 L2-21）。
_ORDERS_FROZEN_SHA256 = "5342675ce9bdd39c6b943d889b88be8e96000a23ce2c8d7697f4f347a0dd3acf"


def assert_eval_data_frozen() -> None:
    cur = hashlib.sha256((ROOT / "data" / "orders.json").read_bytes()).hexdigest()
    assert cur == _ORDERS_FROZEN_SHA256, (
        "orders.json 已变更——它是冻结的 eval fixture。请复核按订单状态 key 的 golden"
        "（已签收/已取消单的 eta，case_021/044 等），确认无误后把 _ORDERS_FROZEN_SHA256 更新为新哈希。"
    )


def load_l2_inputs() -> dict[str, dict]:
    """组装每个已标 golden 的事实桶 case 的 judge 三件套。
    返回 {case_id: {question, answer, tool_outputs(池), golden_points, bucket}}"""
    assert_eval_data_frozen()
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
  · 【抽取层】从 answer 挑出要进忠实轴的句子。
    闸门一=可证伪性：只抽「能用 tool output 判对/错的客观事实陈述」。无法用对错核的——
    主观评价、营销修辞、定性归纳（如「一整套搭配」）、服务承诺/行动引导（如「联系我跟进」）、
    寒暄粘合剂——都不是事实断言，不抽。
    注意：「这三款都适合敏感肌」这类可证伪的归纳要抽（之后判它有没有据），别因为是归纳就放过。
    闸门二=宁多勿漏：把每个可证伪事实点都单独抽出来，哪怕它被包在服务话术/行动引导里——
    如「您可以申请退款（未发货可直接取消）」要把『未发货可直接取消』单独抽出来判，别因为外面
    裹了层服务口吻就整句放过。抽多无妨（判定层会把有据的判 supported），抽漏才致命（真越界会
    静默逃逸成假阴）。
  · 【判定层】对已抽进来的每条断言，到 tool_outputs 找支撑，判 supported/unsupported。
    看语义不看字面：【同一事实的不同措辞】算支撑（如「更服帖」支撑「效果更好」、「原路退款」=
    「原路退回」），别因用词不同就判红。但【不同政策条目不是近义】：退货≠换货、7天≠15天、
    质量问题≠非质量问题——它们是不同事实，断言把它们张冠李戴（如把池里的『质量问题换货』说成
    『质量问题退货』）哪怕只差一字也判 unsupported。evidence 引那段原文。
    【商品描述：同向近义 + 一步品类外推算支撑】对商品 highlight/名称的断言，凡是同向近义、或由
    池里特征一步推出的品类/用途，都算支撑（如「防滑」支撑「稳固」、「深层补水」支撑「对付干燥」）。
    但【引入池里没有、甚至反向的新属性不算】——是凭空加戏，判 unsupported（如 highlight 只说
    「控油/清爽」却称商品「保湿」：控油≠保湿、方向相反）。注意此条只放宽「商品描述」域，上面
    「不同政策条目」的严格边界不受影响。
    【逐段核，再判红】tool_outputs 已按「## 标题」分段。判一条 unsupported 之前，必须逐个 ##
    段过一遍，确认每一段都找不到任何语义依据，才能判 unsupported；只要任一段对得上就判 supported，
    evidence 连同所在 ## 标题一起引出来。依据常埋在长文、跨多行，别一眼扫过就判红。
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


def judge_one(item: dict, _max_retries: int = 3) -> dict:
    last_err = None
    for attempt in range(_max_retries):
        try:
            resp = client.chat.completions.create(
                model=config.MODEL,
                messages=[
                    {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
                    {"role": "user", "content": build_user_payload(item)},
                ],
                response_format={"type": "json_object"},
                temperature=0,
                timeout=180,  # 单次挂死防护：慢端点下别让一次请求无限阻塞
            )
            return json.loads(resp.choices[0].message.content)
        except Exception as e:  # 超时/网络/JSON 解析失败都重试
            last_err = e
            time.sleep(2 * (attempt + 1))
    raise last_err


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
        try:
            verdict = judge_one(item)
        except Exception as e:  # 单 case 失败不拖垮整轮（无人值守过夜）
            results[case_id] = {"bucket": item["bucket"], "question": item["question"],
                                "answer": item["answer"], "error": str(e)}
            continue
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
