import json
from collections import Counter
from pathlib import Path

_PROFILES = json.loads((Path(__file__).parents[1] / "data" / "profiles.json").read_text())


def _budget_band(avg: float) -> str:
    if avg < 80:
        return "low"
    if avg <= 200:
        return "mid"
    return "high"


def derive_preferences(order_history: list[dict]) -> dict | None:
    """偏好是 order_history 的运行时视图，不落盘（防双事实源漂移）。
    fav_categories 按购买频次排名、同频次用累计金额破平（口径见 Phase3 数据契约）。"""
    if not order_history:
        return None
    freq = Counter(o["category"] for o in order_history)
    amount = Counter()
    for o in order_history:
        amount[o["category"]] += o["amount"]
    fav = sorted(freq, key=lambda c: (-freq[c], -amount[c]))
    avg = sum(o["amount"] for o in order_history) / len(order_history)
    return {
        "fav_categories": fav,
        "avg_order_value": round(avg, 1),
        "budget_band": _budget_band(avg),
    }


def get_preferences(user_id: str) -> dict | None:
    """未知 user_id 返回 None = 无画像，调用方走澄清兜底，不报错。
    role 是会话属性（来自登录态/会话层），不在画像库——这里只管购买史派生的偏好。"""
    profile = _PROFILES.get(user_id)
    if profile is None:
        return None
    return derive_preferences(profile["order_history"])

if __name__ == "__main__":
    print(json.dumps(get_preferences("u_beauty"), ensure_ascii=False, indent=2))