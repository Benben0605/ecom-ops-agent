import json
from pathlib import Path

_PRODUCTS = json.loads((Path(__file__).parents[2] / "data" / "products.json").read_text())


def run(category: str, budget: float | None = None) -> str:
    hits = [p for p in _PRODUCTS if category in p["category"] or p["category"] in category]
    if budget is not None:
        hits = [p for p in hits if p["price"] <= budget]
    if not hits:
        tip = f"，预算 {budget} 元内" if budget is not None else ""
        return f"没找到「{category}」类目{tip}的商品，换个类目或放宽预算试试"

    hits.sort(key=lambda p: p["price"])
    lines = [f"- {p['name']}（¥{p['price']}）：{p['highlight']}" for p in hits[:3]]
    return f"为你推荐「{category}」类目的商品：\n" + "\n".join(lines)
