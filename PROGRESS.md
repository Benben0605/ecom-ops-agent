# PROGRESS · 私域电商运营 AI Agent 工作台

> 每天收工花 5 分钟更新最下方「每日日志」。第二天开新对话只需说：
> "继续 Agent 求职项目，今天 Day X，进度看 PROGRESS.md"，我就能回到现场。

## 项目一句话
面向私域电商运营的 AI Agent 工作台：客服问答(RAG) + 订单查询 + 商品推荐 + 运营分析 + 工具审计。
命中 JD2(群接龙)/JD3(新励成)/JD4(MINISO)/JD6(医药数智)。招牌差异点 = 工具审计层 → 评估体系。

## 当前状态
- **所在周**：Week 1（MVP 跑通）
- **底座决策**：Agent loop 用 ____（A 纯手写 / B 框架）；模型 API ____（OpenAI / DeepSeek / 通义）
- **下一步**：Week1-Step1 环境与骨架

## Week 进度看板
- [ ] Week 1 · MVP：Orchestrator + query_order(mock) + kb_search(RAG)，命令行跑通意图路由
- [ ] Week 2 · 工程化：FastAPI + 前端 + 记忆 + Docker 部署 + 在线链接；加 recommend/analyze 工具
- [ ] Week 3 · 招牌：工具审计层 + 评估集(50-100条) + 2-3 轮优化迭代 + 多Agent亮点
- [ ] Week 4 · 包装：README/架构图/技术博客 + 简历STAR + 八股自测 + 模拟面试 + 投递

## Week 1 步骤清单
- [ ] 1. 环境与骨架：venv、装 SDK、跑通一次最小 LLM API 调用
- [ ] 2. 手写 Agent loop（ReAct：思考→选工具→调用→回灌→循环）← 我引导你写
- [ ] 3. 工具 query_order：mock 订单数据，按单号返状态
- [ ] 4. 工具 kb_search：电商 FAQ → 切分/embedding/检索（基础 RAG）
- [ ] 5. 验收：命令行问 2 类问题，能各自正确路由并闭环

---

## 每日日志

### Day 0 (2026-06-05)
- 做了：定方案、拆 6 份 JD、搭项目骨架 + PROGRESS 模板
- 卡点：—
- 明天：选 Agent loop 底座，做 Week1-Step1 环境与最小 API 调用
- 学到/没懂：—

<!-- 模板，复制使用：
### Day X (日期)
- 做了：写完 Agent loop 的工具解析
- 卡点：多轮时上下文越来越长，不知怎么裁
- 明天：加 kb_search 工具
- 学到/没懂：ReAct 的 Observation 怎么回灌还没吃透
-->
