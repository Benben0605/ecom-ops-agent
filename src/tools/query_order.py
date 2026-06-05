import json
from pathlib import Path

_ORDERS = json.loads((Path(__file__).parents[2] / "data" / "orders.json").read_text())


def run(order_id: str) -> str:
    o = _ORDERS.get(order_id)
    if o is None:
        return f"未找到订单 {order_id}"
    return f"订单 {order_id}：{o['status']}，预计 {o['eta']} 送达，商品：{o['item']}"
