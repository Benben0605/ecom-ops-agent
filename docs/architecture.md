# 系统架构与能力地图

本文记录 ecom-ops-agent 当前可验证的系统边界、能力入口和成熟度。它是导航图，不是实现证明；设计变更的
写作与生命周期规则见 [`Specifications Bootstrap`](./specs/README.md)。

## 如何阅读 Capability Status

| Capability Status | Meaning |
|-------------------|---------|
| `planned` | 只有设计意图，尚不能从代码推断为可用 |
| `experimental` | 有实现，但非默认、迁移未完成、证据有限或结果依赖非确定性裁判 |
| `operational` | 默认或受支持路径已存在，并有测试、评估或运行证据 |
| `deprecated` | 能力仍可能存在，但已不再推荐继续采用，正等待迁移或移除 |

规格描述意图，代码描述现状，测试与实验提供证据。三者冲突时应先定位差异；case 数、准确率、误触发率和
L2 分数必须从当前数据集和带 provenance 的实验产物计算，不在架构文档中作为长期承诺。这里的
`Capability Status` 只描述能力成熟度；Spec 的 `draft`、`accepted`、`implementing`、`verified`、
`superseded` 描述设计生命周期，两条轴的定义与同步规则见
[`Specifications Bootstrap`](./specs/README.md#两条独立的状态轴)。

## 架构边界

- 默认运行主线是 `ChatSession` 的单 Agent ReAct/tool-calling loop；`SupervisorAgent` 只用于对照实验。
- 模型只能提交工具 schema 声明的业务参数。可信身份和权限由执行层注入并由敏感工具校验；prompt 和工具
  description 只用于路由，不是安全边界。
- 最终回复中的业务事实必须来自工具、检索结果或版本化业务数据；无法可靠完成时应澄清、拒答或转人工。
- `data/` 中的 mock 业务数据和 eval fixture 是版本化输入；`logs/`、`.chroma/`、`frontend/dist/` 是可再生
  产物，不得作为唯一决策记录。
- 跨边界数据契约遵循 [`Coding Standards`](./development/coding-standards.md#contracts-and-data-changes)；
  实验设计、运行和裁决遵循 [`CONTRIBUTING.md`](../CONTRIBUTING.md#一次实验的生命周期)。

## Core Runtime

| Capability | Code | Verification / Evidence | Capability Status | Design Contract |
|------------|------|-------------------------|-------------------|-----------------|
| 单 Agent 编排 | [`src/agent.py`](../src/agent.py) | L1/L2 实验与 chat 路径 | `operational` | `ChatSession` 维护会话并循环执行模型 tool calls，直到生成最终回复 |
| 多 Agent 对照 | [`src/agent.py`](../src/agent.py) | `src/eval/compare.py`、实验 harness | `experimental` | `SupervisorAgent` 仅用于对照；叶子业务工具审计与单 Agent 保持同口径 |
| 工具系统 | [`src/tools/`](../src/tools/), [`src/schemas/`](../src/schemas/) | `data/eval_cases.json`、L1 judge | `operational` | schema 是模型可见接口；实现是执行边界；注册、schema、实现、case 必须同步 |
| 会话上下文与压缩 | [`src/agent.py`](../src/agent.py) | 运行时 token threshold | `experimental` | 只在轮边界压缩，保留最近完整 user/tool 交互，不拆散 tool-call 配对 |
| 身份与权限 | [`src/agent.py`](../src/agent.py), [`src/tools/analyze_ops.py`](../src/tools/analyze_ops.py), [`src/profile.py`](../src/profile.py) | `role_flip`、`personalization` case | `operational` | 可信 `role`/`user_id` 由执行层注入；敏感运营数据在工具层鉴权 |
| HTTP API 与 session | [`src/api.py`](../src/api.py) | chat/dashboard API 运行路径 | `operational` | session 当前为进程内存态；API 同时提供评估视图和前端静态托管 |

## Knowledge, Commerce Data, and Safety

| Capability | Code / Data | Verification / Evidence | Capability Status | Design Contract |
|------------|-------------|-------------------------|-------------------|-----------------|
| 退换货 RAG | [`src/tools/kb_search.py`](../src/tools/kb_search.py), [`data/faq/`](../data/faq/) | `src/eval/retrieval.py`、相关 eval cases | `operational` | 向量召回后由 relevance grader 逐块门控；无相关片段时 abstain |
| 订单查询 | [`src/tools/query_order.py`](../src/tools/query_order.py), [`data/orders.json`](../data/orders.json) | 订单类 eval cases | `operational` | 只返回 mock 订单源中存在的状态、ETA 与商品信息 |
| 商品推荐与画像 | [`src/tools/recommend_product.py`](../src/tools/recommend_product.py), [`src/profile.py`](../src/profile.py) | 推荐、个性化 eval cases | `operational` | 类目可由显式输入或执行层注入的用户画像确定；预算仅作上限过滤 |
| 运营分析 | [`src/tools/analyze_ops.py`](../src/tools/analyze_ops.py) | 商家身份与统计 eval cases | `operational` | 仅商家可见；GMV/客单价剔除取消订单，热销支持订单数和销售额两种口径 |
| 不支持请求转人工 | [`src/tools/escalate_to_human.py`](../src/tools/escalate_to_human.py) | `weakness`、`negative` cases | `operational` | 只处理电商相关但无自助工具的请求；闲聊和常识问答不得误触发 |
| 事实忠实约束 | [`src/agent.py`](../src/agent.py), [`src/eval/l2/judge.py`](../src/eval/l2/judge.py) | L2 faithfulness axis | `operational` | 回复只能复述工具输出池支持的事实，不跨政策拼接或补写缺失细节 |

## Evaluation and Observability

| Capability | Code / Data | Verification / Evidence | Capability Status | Design Contract |
|------------|-------------|-------------------------|-------------------|-----------------|
| 调用级审计 | [`src/audit.py`](../src/audit.py) | audit JSONL、dashboard tests | `operational` | 记录 session、工具、参数、耗时、输出、错误；粒度是叶子业务工具调用 |
| L1 路由评估 | [`src/eval/judge.py`](../src/eval/judge.py), [`data/eval_cases.json`](../data/eval_cases.json) | deterministic Counter 判分 | `operational` | 用 multiset 比对期望与实际调用；路由准确率和误触发率保持正交分母 |
| L2 最终回复评估 | [`src/eval/l2/judge.py`](../src/eval/l2/judge.py) | golden points、tool output pool | `experimental` | 分开判断要点命中与事实忠实；LLM judge 的单次结果不能用于裁决 |
| L2 judge 夹具 | [`src/eval/l2/fixtures.py`](../src/eval/l2/fixtures.py), [`data/l2_judge_fixtures.json`](../data/l2_judge_fixtures.json) | fixture evaluation output、dashboard adapter | `operational` | 用成对红/绿锚点评 judge 自身的漏抽与假阳，不与 Agent 质量混为一谈 |
| 实验 harness | [`src/experiment/runner.py`](../src/experiment/runner.py), [`src/experiment/compare.py`](../src/experiment/compare.py) | manifest、dataset hashes、trace | `operational` | 保存配置、版本、数据哈希、逐 run trace 和聚合结果 |
| 缺陷账本对账 | [`src/eval/reconcile.py`](../src/eval/reconcile.py), [`data/defect_ledger.json`](../data/defect_ledger.json) | experiment result reconciliation | `operational` | 区分仍复现、候选关账、未覆盖和新红；单次绿不能自动关闭已知缺陷 |
| Dashboard | [`src/dashboard/`](../src/dashboard/), [`frontend/`](../frontend/) | dashboard API 运行路径、frontend build | `operational` | 支持 legacy 与 experiment 数据源，并保留 case → run → audit/message 下钻 |

## Contracts and Persistence

| Capability | Code | Verification / Evidence | Capability Status | Design Contract |
|------------|------|-------------------------|-------------------|-----------------|
| 跨边界 Pydantic 契约 | [`src/contracts/`](../src/contracts/) | schema export、生成快照审查 | `experimental` | 落盘、跨语言或跨模块读回的数据逐步迁移到单一 model |
| JSON Schema 快照 | [`src/contracts/schemas/`](../src/contracts/schemas/) | schema export + snapshot diff review | `operational` | model 是源，快照是提交审查面；字段变化必须出现在生成后的 diff 中 |
| 运行产物 | `logs/`, `.chroma/`, `frontend/dist/` | 可重新生成 | `operational` | 不进入版本库，也不能作为唯一决策记录 |
| 冻结订单 fixture | [`data/orders.json`](../data/orders.json), [`src/eval/l2/judge.py`](../src/eval/l2/judge.py) | SHA-256 guard | `operational` | 修改前复核所有状态相关 golden；哈希更新表示复核完成，而非绕过检查 |

## Frontend and Distribution

| Capability | Code | Verification / Evidence | Capability Status | Design Contract |
|------------|------|-------------------------|-------------------|-----------------|
| React 工作台 | [`frontend/src/`](../frontend/src/) | `npm run build` | `operational` | TypeScript API 类型集中在 `frontend/src/api.ts`；Vite dev server 代理后端接口 |
| FastAPI 静态托管 | [`src/api.py`](../src/api.py) | production build path | `operational` | 后端从 `frontend/dist` 提供 SPA 和 dashboard routes |
| Docker / Render | [`Dockerfile`](../Dockerfile), [`render.yaml`](../render.yaml) | container build | `operational` | 多阶段构建前端，Python 依赖通过已提交的 `uv.lock` 安装；运行时密钥由环境注入 |
