RECOMMEND_PRODUCT_SCHEMA = {
    "type": "function",
    "function": {
        "name": "recommend_product",
        "description": "按商品类目（可选预算上限）推荐商品。当顾客问某商品/类目卖得好不好、热不热门、想买东西、求推荐、问某类目有什么好货时调用。从用户的话里抽取类目和预算。",
        "parameters": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "商品类目，如：美妆护肤、家居日用、数码、运动户外、食品。类目不确定时可不传，直接调用即可，系统会处理"
                },
                "budget": {
                    "type": "number",
                    "description": "预算上限（元）。用户没提就不传"
                }
            },
            "required": []
        }
    }
}
