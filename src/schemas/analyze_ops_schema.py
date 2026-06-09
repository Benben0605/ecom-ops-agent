ANALYZE_OPS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "analyze_ops",
        "description": "统计运营数据：总销售额、订单数、客单价、热销商品 Top3、订单状态分布。当用户问经营情况、卖得怎么样、有多少订单、哪些好卖、有多少待发货时调用。可选按类目过滤。",
        "parameters": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "只统计某个类目，如：美妆护肤、数码。不传则统计全部"
                }
            },
            "required": []
        }
    }
}
