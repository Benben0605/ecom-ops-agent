import json
from pathlib import Path

from src.profile import get_preferences

_PRODUCTS = json.loads((Path(__file__).parents[2] / "data" / "products.json").read_text())


def run(category: str | None = None, budget: float | None = None, user_id: str | None = None) -> str:
    # 缺类目时用画像 fav 补（确定性映射归代码，不靠 LLM 转抄）；user_id 由执行层注入
    attribution = ""
    if not category and user_id:
        preferences = get_preferences(user_id)
        if preferences:
            category = preferences["fav_categories"][0]
            attribution = f"（根据你常买的「{category}」类目为你挑选）"
    if not category:
        return "想看哪个类目的商品呢？可选：美妆护肤、家居日用、数码、运动户外、食品"

    hits = [p for p in _PRODUCTS if category in p["category"] or p["category"] in category]
    if budget is not None:
        hits = [p for p in hits if p["price"] <= budget]
    if not hits:
        tip = f"，预算 {budget} 元内" if budget is not None else ""
        return f"没找到「{category}」类目{tip}的商品，换个类目或放宽预算试试"

    hits.sort(key=lambda p: p["price"])
    lines = [f"- {p['name']}（¥{p['price']}）：{p['highlight']}" for p in hits[:3]]
    return f"为你推荐「{category}」类目的商品{attribution}：\n" + "\n".join(lines)
