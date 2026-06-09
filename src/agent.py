from uuid import uuid4

from openai import OpenAI
from src.schemas.query_order_schema import QUERY_ORDER_SHCEMA
from src.schemas.kb_search_schema import KB_SEARCH_SCHEMA
from src.schemas.recommend_product_schema import RECOMMEND_PRODUCT_SCHEMA
from src.schemas.analyze_ops_schema import ANALYZE_OPS_SCHEMA
from src import config
from src.tools import kb_search, query_order, recommend_product, analyze_ops
import json

client = OpenAI(api_key=config.API_KEY, base_url=config.BASE_URL)

TOOLS = {
    "query_order": query_order.run,
    "kb_search": kb_search.run,
    "recommend_product": recommend_product.run,
    "analyze_ops": analyze_ops.run,
}

tools = [QUERY_ORDER_SHCEMA, KB_SEARCH_SCHEMA, RECOMMEND_PRODUCT_SCHEMA, ANALYZE_OPS_SCHEMA]
_system_prompt = "你是私域电商运营客服助手，负责订单查询、售后/政策咨询、商品推荐和运营数据分析，善于利用工具解决问题"

class ChatSession():
    """单会话多轮对话，内置工具路由与历史压缩。

    self.messages 全程只存放 JSON 原生类型（dict/list/str/...），
    SDK 返回的 Pydantic 对象在入栈前必须 model_dump() 转 dict，
    否则下一轮请求会因为 tool_calls 被 str() 降级而报 400。
    """

    def __init__(self, system_prompt: str = _system_prompt):
        self.id = uuid4().hex
        self.messages = [{"role": "system", "content": system_prompt} ]

    def chat(self, user_input: str) -> str:
        """跑一轮用户输入：循环调用模型 + 执行工具，直到模型不再请求工具。

        返回模型最终的文本回复。每轮结束后根据 usage.prompt_tokens
        触发 _maybe_compress 做历史压缩。
        """
        self.messages.append({"role": "user", "content": user_input})
        while True:
            r = client.chat.completions.create(
            model=config.MODEL,
            messages=self.messages,
            tools=tools
            )
            assistant_message = r.choices[0].message
            tool_calls = assistant_message.tool_calls
            
            if not tool_calls:
                self.messages.append({"role": assistant_message.role, "content": assistant_message.content})
                prompt_tokens = r.usage.prompt_tokens
                self._maybe_compress(prompt_tokens)
                return assistant_message.content
            
            tool_calls_dicts = [tc.model_dump() for tc in tool_calls]
            self.messages.append({"role": assistant_message.role, "content": assistant_message.content, "tool_calls": tool_calls_dicts})
            for tool_call in tool_calls:
                result = TOOLS[tool_call.function.name](**json.loads(tool_call.function.arguments))
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result
                })
            

    def _maybe_compress(self, prompt_tokens: int):
        """超过阈值时把早期历史摘要成一条 system 消息，保留最近 lately_round 轮 user 之后的全部消息。

        切点取 user_idx[-lately_round]，确保 assistant + tool 配对不被截断
        （否则带 tool_calls 的 assistant 消息找不到对应 tool 结果会报错）。
        """
        if prompt_tokens <= config.compress_token_threshold:
            return

        user_idx = [i for i, m in enumerate(self.messages) if m["role"] == "user"]
        if len(user_idx) <= config.lately_round:
            return

        cut = user_idx[-config.lately_round]
        old = self.messages[1:cut]
        recent = self.messages[cut:]

        summary_prompt = "请用一段简洁中文总结以下对话的关键信息（用户意图、已查询到的订单/政策事实、未完成的事项），保留对后续回答有用的事实：\n\n" + "\n".join(json.dumps(old_dict, ensure_ascii=False) for old_dict in old)
        s = client.chat.completions.create(
            model=config.MODEL,
            messages=[{"role": "user", "content": summary_prompt}],
        )
        summary = s.choices[0].message.content

        self.messages = [
            self.messages[0],
            {"role": "system", "content": f"以下是被压缩的历史对话摘要：\n{summary}"},
            *recent,
        ]
        print("***触发压缩***")
