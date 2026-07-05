import json
from collections import Counter,defaultdict
from pathlib import Path

_ORDERS = json.loads((Path(__file__).parents[2] / "data" / "orders.json").read_text())


def run(category: str | None = None, metric : str | None = None, role: str | None = None) -> str:
    # 鉴权在工具内=物理保证（role 由执行层注入，不让 LLM 填）；prompt 门控只是省调用的礼貌层
    if role != "merchant":
        return "经营数据仅商家可见。如需查看店铺运营数据，请使用商家账号登录。"
    orders = list(_ORDERS.values())
    if category:
        orders = [o for o in orders if category in o["category"] or o["category"] in category]
    if not orders:
        # 给模型出口：列出有数据的类目，别让错误信息成死胡同（坚果→模型可自己归到食品重试）
        existing = "、".join(sorted({o["category"] for o in _ORDERS.values()}))
        return f"没有「{category}」类目的订单数据；有订单数据的类目：{existing}"

    scope = f"「{category}」类目" if category else "全店"
    valid = [o for o in orders if o["status"] != "已取消"]  # GMV 口径剔除已取消
    gmv = sum(o["amount"] for o in valid)
    aov = gmv / len(valid) if valid else 0

    hot_count = Counter(o["item"] for o in valid).most_common(3)
    sales_by_item = defaultdict(float)
    for o in valid:
        sales_by_item[o["item"]] += o["amount"]
    hot_sales = Counter(sales_by_item).most_common(3)
    hot_count_lines = "按订单数口径：\n" + "\n".join(f"{i}. {item}（{n} 单）" for i, (item, n) in enumerate(hot_count, 1))
    # 销售额口径带成交单数：不留白，模型无需拿单价心算「卖了几单」（避免池外算术）
    hot_sales_lines = "按销售额口径：\n" + "\n".join(
        f"{i}. {item}（¥{n}，{sum(1 for o in valid if o['item'] == item)} 单）"
        for i, (item, n) in enumerate(hot_sales, 1))
    if metric == "count":
        hot_lines = hot_count_lines
    elif metric == "sales":
        hot_lines = hot_sales_lines
    else:
        hot_lines = f"{hot_count_lines}\n{hot_sales_lines}"

    status = Counter(o["status"] for o in orders)
    status_line = "，".join(f"{s} {n} 单" for s, n in status.items())

    return (
        f"根据历史订单数据，{scope}运营概况（{len(valid)} 笔有效订单；以下为订单统计，非在售商品清单）：\n"
        f"- 总销售额：¥{gmv}\n"
        f"- 客单价：¥{aov:.0f}\n"
        f"- 热销 Top3：\n{hot_lines}\n"
        f"- 订单状态分布：{status_line}"
    )
