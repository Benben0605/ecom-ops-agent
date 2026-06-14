KB_SEARCH_SCHEMA = {
    "type": "function",
    "function": {
        "name": "kb_search",
        "description": "仅检索退换货政策。不用于检索促销活动/优惠，不用于查询具体某个订单的状态，不用于查询或开具订单发票。",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "用户的咨询问题"}
            },
            "required": ["query"]
        }
    }
}