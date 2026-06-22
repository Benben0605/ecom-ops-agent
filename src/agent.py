import time
from uuid import uuid4

from openai import OpenAI
from src.schemas.query_order_schema import QUERY_ORDER_SCHEMA
from src.schemas.kb_search_schema import KB_SEARCH_SCHEMA
from src.schemas.recommend_product_schema import RECOMMEND_PRODUCT_SCHEMA
from src.schemas.analyze_ops_schema import ANALYZE_OPS_SCHEMA
from src.schemas.escalate_to_human_schema import ESCALATE_TO_HUMAN_SCHEMA
from src import config
from src.tools import kb_search, query_order, recommend_product, analyze_ops, escalate_to_human
import json

from src.audit import ToolAudit, AuditRecorder, NoOpRecorder

client = OpenAI(api_key=config.API_KEY, base_url=config.BASE_URL)

TOOLS = {
    "query_order": query_order.run,
    "kb_search": kb_search.run,
    "recommend_product": recommend_product.run,
    "analyze_ops": analyze_ops.run,
    "escalate_to_human": escalate_to_human.run,
}

tools = [QUERY_ORDER_SCHEMA, KB_SEARCH_SCHEMA, RECOMMEND_PRODUCT_SCHEMA, ANALYZE_OPS_SCHEMA, ESCALATE_TO_HUMAN_SCHEMA]
_system_prompt = "你是私域电商运营客服助手，负责订单查询、售后/政策咨询、商品推荐和运营数据分析，善于利用工具解决问题。必填参数齐全时直接调用工具，不要因为选填参数缺失而反问；但若必填参数缺失且无法从对话中合理推断，应先向用户询问澄清，不要猜测或随意填充必填参数。如果是电商业务相关但无工具，调用 escalate_to_human 转人工，不要硬调最接近的工具兜底。只陈述工具/检索输出明确给出的事实；不合并、不外推、不补全不同政策条目；工具没提的（取消/额外时效/适用范围）一律不编"

class ChatSession():
    """单会话多轮对话，内置工具路由与历史压缩。

    self.messages 全程只存放 JSON 原生类型（dict/list/str/...），
    SDK 返回的 Pydantic 对象在入栈前必须 model_dump() 转 dict，
    否则下一轮请求会因为 tool_calls 被 str() 降级而报 400。
    """

    def __init__(self, system_prompt: str = _system_prompt, audit_recorder=None,
                 tool_schemas: list | None = None, tool_impls: dict | None = None,
                 session_id: str | None = None):
        self.id = session_id or uuid4().hex
        self.messages = [{"role": "system", "content": system_prompt} ]
        self.audit_recorder = audit_recorder or AuditRecorder()
        # 默认全工具（单 Agent 不变）；专家 Agent 传子集
        self.tool_schemas = tool_schemas if tool_schemas is not None else tools
        self.tool_impls = tool_impls if tool_impls is not None else TOOLS

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
                tools=self.tool_schemas
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
                func_name = tool_call.function.name
                start = time.perf_counter()
                try:
                    func_dict = json.loads(tool_call.function.arguments)
                    result = self.tool_impls[func_name](**func_dict)
                    elapsed = (time.perf_counter() - start) * 1000
                    tool_audit = ToolAudit(
                        session_id=self.id,
                        has_tool_call=True,
                        tool_name=func_name,
                        tool_params=func_dict,
                        tool_duration_ms=elapsed, 
                        tool_output=result
                    )   
                except Exception as e:
                    result = f"工具执行失败，错误信息：{e}"
                    elapsed = (time.perf_counter() - start) * 1000
                    tool_audit = ToolAudit(
                        session_id=self.id,
                        has_tool_call=False,
                        tool_name=func_name,
                        tool_params=tool_call.function.arguments,
                        tool_duration_ms=elapsed,
                        tool_output=result,
                        tool_error=str(e)
                    )
                self.audit_recorder.record(tool_audit)

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


# ============================================================================
# 多 Agent（Supervisor + 按 persona 拆分的专家，agent-as-tool）
# 拆分轴 = persona（点13/19）：客户侧 vs 商家侧。专家只见自己域的工具 →
# 结构性消除工具边界歧义（如 case_017 客户 Agent 压根看不到 analyze_ops）。
# ============================================================================

# ---- 专家 1：客户侧（订单/售后/推荐/转人工）----
CUSTOMER_TOOL_IMPLS = {
    "query_order": query_order.run,
    "kb_search": kb_search.run,
    "recommend_product": recommend_product.run,
    "escalate_to_human": escalate_to_human.run,
}
CUSTOMER_TOOL_SCHEMAS = [QUERY_ORDER_SCHEMA, KB_SEARCH_SCHEMA, RECOMMEND_PRODUCT_SCHEMA, ESCALATE_TO_HUMAN_SCHEMA]
CUSTOMER_PROMPT = "你是面向【客户】的电商客服助手，负责订单查询、售后/政策咨询、商品推荐。必填参数齐全时直接调用工具，不要因选填参数缺失而反问；必填参数缺失且无法从对话推断时，先向用户询问澄清，不要猜测或随意填充。若没有任何工具能满足请求，调用 escalate_to_human 转人工，不要硬调最接近的工具兜底。"

# ---- 专家 2：商家侧（运营数据分析）----
MERCHANT_TOOL_IMPLS = {
    "analyze_ops": analyze_ops.run,
}
MERCHANT_TOOL_SCHEMAS = [ANALYZE_OPS_SCHEMA]
MERCHANT_PROMPT = "你是面向【商家】的运营数据分析助手，负责统计销售额、订单数、客单价、热销 Top3、订单状态分布。直接调用 analyze_ops 工具回答，可选按类目过滤。"

# ---- agent-as-tool：把专家暴露成 supervisor 的「工具」----
ASK_CUSTOMER_AGENT_SCHEMA = {
    "type": "function",
    "function": {
        "name": "ask_customer_agent",
        "description": "把【客户视角】的请求转交客户服务专家处理：查询某个订单状态、退换货/售后政策咨询、商品推荐、以及本系统不支持的客户请求转人工。",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "转交给客户服务专家的完整子任务描述"}
            },
            "required": ["query"],
        },
    },
}
ASK_MERCHANT_AGENT_SCHEMA = {
    "type": "function",
    "function": {
        "name": "ask_merchant_agent",
        "description": "把【商家视角】的请求转交运营分析专家处理：经营/销售数据统计，如总销售额、订单数、客单价、哪些好卖、有多少待发货等。",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "转交给运营分析专家的完整子任务描述"}
            },
            "required": ["query"],
        },
    },
}
SUPERVISOR_PROMPT = "你是调度器。判断用户请求属于【客户服务】还是【商家运营分析】，调用对应的子 Agent 工具转交；一句话含多个意图时，分别调用多个子 Agent。纯闲聊/寒暄/常识问答直接回复，不要调用任何子 Agent。拿到子 Agent 的返回后，综合成给用户的最终回复。"


class SupervisorAgent:
    """多 Agent 编排器：与 ChatSession 同接口（.chat(str)->str / .id / .messages /
    可注入 audit_recorder），方便 runner/eval 零改动对比单 Agent vs 多 Agent。
    """

    def __init__(self, audit_recorder=None, message_recorder=None, session_id: str | None = None):
        self.id = session_id or uuid4().hex
        # 真 recorder：给专家记叶子业务工具（落到 self.id 这个 session）
        self._leaf_recorder = audit_recorder or AuditRecorder()
        self._message_recorder = message_recorder
        #  构造两个 dispatch 闭包 ask_customer_agent(query)/ask_merchant_agent(query)
        #   —— 每个闭包内：用专家子集 + self._leaf_recorder + session_id=self.id 建 ChatSession，
        #      跑 .chat(query)，return 专家的最终文本。
        # self._session = ChatSession(SUPERVISOR_PROMPT,
        #      audit_recorder=NoOpRecorder(), tool_schemas=[...两个agent-as-tool...],
        #      tool_impls={...两个dispatch...}, session_id=self.id)
        _supervisor_schemas = [ASK_CUSTOMER_AGENT_SCHEMA, ASK_MERCHANT_AGENT_SCHEMA]
        _supervisor_impls = {
            "ask_customer_agent": self.ask_customer_agent,
            "ask_merchant_agent": self.ask_merchant_agent
        }
        self._session = ChatSession(
            system_prompt=SUPERVISOR_PROMPT,
            audit_recorder=NoOpRecorder(),
            tool_schemas=_supervisor_schemas,
            tool_impls=_supervisor_impls,
            session_id=self.id
        )

    @property
    def messages(self):
        # 返回 supervisor 那条会话的 messages（self._session.messages）
        return self._session.messages

    def ask_customer_agent(self, query: str) -> str:
        print(f"running ask_customer_agent({query})")
        customer_session = ChatSession(
            system_prompt=CUSTOMER_PROMPT,
            audit_recorder=self._leaf_recorder,
            tool_schemas=CUSTOMER_TOOL_SCHEMAS,
            tool_impls=CUSTOMER_TOOL_IMPLS,
            session_id=self.id
        )
        response = customer_session.chat(query)
        self._message_recorder.record(
            {
                "session_id": self.id,
                "messages": customer_session.messages
            }
        )
        return response
    
    def ask_merchant_agent(self, query: str) -> str:
        print(f"running ask_merchant_agent({query})")
        merchant_session = ChatSession(
            system_prompt=MERCHANT_PROMPT,
            audit_recorder=self._leaf_recorder,
            tool_schemas=MERCHANT_TOOL_SCHEMAS,
            tool_impls=MERCHANT_TOOL_IMPLS,
            session_id=self.id
        )
        response = merchant_session.chat(query)
        self._message_recorder.record(
            {
                "session_id": self.id,
                "messages": merchant_session.messages
            })
        return response

    def chat(self, user_input: str) -> str:
        return self._session.chat(user_input)
        
    