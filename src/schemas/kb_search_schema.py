KB_SEARCH_SCHEMA = {
    "type": "function",
    "function": {
        "name": "kb_search",
        "description": "查询退换货政策、物流规则、活动规则等知识库/FAQ类问题。不用于查询具体某个订单的状态。",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "用户的咨询问题"}
            },
            "required": ["query"]
        }
    }
}