import json
from collections import Counter
from pathlib import Path

_ORDERS = json.loads((Path(__file__).parents[2] / "data" / "orders.json").read_text())


def run(category: str | None = None) -> str:
    orders = list(_ORDERS.values())
    if category:
        orders = [o for o in orders if category in o["category"] or o["category"] in category]
    if not orders:
        return f"没有「{category}」类目的订单数据"

    scope = f"「{category}」类目" if category else "全店"
    valid = [o for o in orders if o["status"] != "已取消"]  # GMV 口径剔除已取消
    gmv = sum(o["amount"] for o in valid)
    aov = gmv / len(valid) if valid else 0

    hot = Counter(o["item"] for o in valid).most_common(3)
    hot_lines = "\n".join(f"  {i}. {item}（{n} 单）" for i, (item, n) in enumerate(hot, 1))

    status = Counter(o["status"] for o in orders)
    status_line = "，".join(f"{s} {n} 单" for s, n in status.items())

    return (
        f"{scope}运营概况（{len(valid)} 笔有效订单）：\n"
        f"- 总销售额：¥{gmv}\n"
        f"- 客单价：¥{aov:.0f}\n"
        f"- 热销 Top3：\n{hot_lines}\n"
        f"- 订单状态分布：{status_line}"
    )
