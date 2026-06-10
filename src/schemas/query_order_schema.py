QUERY_ORDER_SCHEMA = {
    "type": "function",
    "function": {
        "name": "query_order",
        "description": "查询订单状态",
        "parameters": {
            "type": "object",
            "properties": {
                "order_id": {
                    "type": "string"
                }
            },
            "required": ["order_id"]
        }
    }
}