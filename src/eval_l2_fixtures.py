"""L2 judge 回归夹具：拿冻结的「答案+池+期望裁定」N 次跑 judge，钉死假阳/假阴。

单 run 判 judge 会被抽取抖动骗（同句时抽时不抽→间歇性假阴）。这里答案不动、跑 N 次，
报每条锚点的 recall（该红的越界有没有被漏抽）和假阳率（该绿的有没有被误判 unsupported）。
judge prompt 每改一版都跑这个，别再靠单 run + 肉眼。
"""
import json
import re
from pathlib import Path

from src.eval_l2_judge import judge_one

ROOT = Path(__file__).parents[1]
FIXTURES = ROOT / "data" / "l2_judge_fixtures.json"

N = 8


def run_fixtures(n: int = N):
    fixtures = json.loads(FIXTURES.read_text(encoding="utf-8"))
    for fx in fixtures:
        item = {k: fx[k] for k in ("question", "answer", "tool_outputs", "golden_points")}
        verdicts = [judge_one(item) for _ in range(n)]

        print(f"\n[{fx['case_id']}]")
        for anchor in fx["anchors"]:
            pat = re.compile(anchor["match"])
            expect = anchor["expect"]
            # 每次 run 里匹配到的忠实轴断言及其裁定
            per_run = []
            for v in verdicts:
                matched = [a for a in v.get("faithfulness_axis", []) if pat.search(a["assertion"])]
                per_run.append(matched)

            if expect == "unsupported":  # 该红：越界，要 recall
                caught = sum(1 for m in per_run if any(a["verdict"] == "unsupported" for a in m))
                missed = sum(1 for m in per_run if not m)  # 完全没抽到
                flag = "✅" if caught == n else "❌假阴"
                print(f"  {flag} [{anchor['match']} → 该红] recall {caught}/{n}（漏抽 {missed}）  {anchor['note']}")
            else:  # 该绿：benign，怕假阳
                fp = sum(1 for m in per_run if any(a["verdict"] == "unsupported" for a in m))
                extracted = sum(1 for m in per_run if m)
                flag = "✅" if fp == 0 else "❌假阳"
                print(f"  {flag} [{anchor['match']} → 该绿] 假阳 {fp}/{n}（被抽到 {extracted}/{n}）  {anchor['note']}")


if __name__ == "__main__":
    run_fixtures()
