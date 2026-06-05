from openai import OpenAI

from src import config
from src.tools import kb_search, query_order

client = OpenAI(api_key=config.API_KEY, base_url=config.BASE_URL)

TOOLS = {
    "query_order": query_order.run,
    "kb_search": kb_search.run,
}


def run(user_input: str) -> str:
    # TODO(你来写 · Week1-Step2)：在这里手写 ReAct 风格的 Agent loop
    #   1. 把 user_input + 工具说明拼成 prompt，告诉模型可用 TOOLS 和调用格式
    #   2. client.chat.completions.create(...) 拿到模型输出（思考 + 要调的工具 + 参数）
    #   3. 解析出工具名/参数，从 TOOLS 取函数执行，得到 Observation
    #   4. 把 Observation 回灌进对话历史，继续循环
    #   5. 模型给出最终答案时跳出循环并 return
    raise NotImplementedError("Week1-Step2：在这里手写 Agent loop")
