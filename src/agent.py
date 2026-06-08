from openai import OpenAI
from src.schemas.query_order_schema import QUERY_ORDER_SHCEMA
from src.schemas.kb_search_schema import KB_SEARCH_SCHEMA
from src import config
from src.tools import kb_search, query_order
import json

client = OpenAI(api_key=config.API_KEY, base_url=config.BASE_URL)

TOOLS = {
    "query_order": query_order.run,
    "kb_search": kb_search.run,
}

tools = [QUERY_ORDER_SHCEMA, KB_SEARCH_SCHEMA]

def run(user_input: str) -> str:
    #   1. 把 user_input + 工具说明拼成 prompt，告诉模型可用 TOOLS 和调用格式
    #   2. client.chat.completions.create(...) 拿到模型输出（思考 + 要调的工具 + 参数）
    #   3. 解析出工具名/参数，从 TOOLS 取函数执行，得到 Observation
    #   4. 把 Observation 回灌进对话历史，继续循环
    #   5. 模型给出最终答案时跳出循环并 return
    prompt = "你是私域电商运营客服助手，负责订单查询和售后/政策咨询，善于利用工具解决问题"
    messages = [{
        "role": "system",
        "content": prompt
    },
    {
        "role": "user",
        "content": user_input
    }
    ]
    
    while True:
        r = client.chat.completions.create(
        model=config.MODEL,
        messages=messages,
        tools=tools
        )
        assistant_message = r.choices[0].message
        tool_calls = assistant_message.tool_calls
        
        if not tool_calls:
            return assistant_message.content
        
        messages.append(assistant_message)
        for tool_call in tool_calls:
            result = TOOLS[tool_call.function.name](**json.loads(tool_call.function.arguments))
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result
            })

if __name__ == "__main__":
    run("七天无理由怎么退货")