ESCALATE_TO_HUMAN_SCHEMA = {
    "type": "function",
    "function": {
        "name": "escalate_to_human",
        "description": "仅当用户提出与电商业务相关、但本系统无对应工具自助办理的请求时调用，礼貌告知并转交人工客服。适用：修改订单/收货地址、开发票、查会员积分、转人工/投诉、促销活动咨询等。不要为这类请求硬调订单查询或知识库工具兜底。注意：用户闲聊、寒暄、常识或开放性问答（如天气、时间、笑话、观点）不属于业务请求，不要调用本工具，直接用自然语言回复。",
        "parameters": {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "用户诉求的简要概括"
                }
            },
            "required": ["summary"]
        }
    }
}
