# 私域电商运营 AI Agent 工作台

面向私域电商运营场景的 AI Agent 工作台。一个 Orchestrator Agent 接收自然语言请求，
通过工具编排完成任务闭环，并对每次工具调用做审计（延迟/Token/成本/选对没），
由此长出评估体系。

## 能力（北极星）
- **客服问答**：基于企业知识库的 RAG（`kb_search`）
- **订单查询**：调用订单系统（`query_order`）
- **商品推荐**：`recommend_product`
- **运营分析**：`analyze_ops`
- **工具审计**：调用日志 + 成本统计 + 自动评估集 ★ 招牌差异点

## 架构
```
用户自然语言 → Orchestrator Agent (ReAct/工具编排，意图路由)
   ├─ kb_search       (RAG 知识库)   → 客服问答
   ├─ query_order     (mock 订单 API) → 订单查询
   ├─ recommend_product              → 商品推荐
   └─ analyze_ops     (mock 销售数据) → 运营分析
   + Memory(多轮 + 用户画像)
   + 工具审计层 (输入/输出/延迟/token/成本/选对没 → 日志 + 评估)
```

## 当前进度
见 [PROGRESS.md](./PROGRESS.md)。现处于 Week 1（MVP）。

## 快速开始
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # 填入 API key
python main.py
```

## 目录
```
src/agent.py        Orchestrator / Agent loop
src/tools/          工具集（query_order / kb_search ...）
src/config.py       配置（模型、API base_url 等）
data/orders.json    mock 订单数据
data/faq/           电商 FAQ 知识源
main.py             CLI 入口
```
