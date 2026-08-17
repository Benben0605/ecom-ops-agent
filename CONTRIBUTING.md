# 开发流程

本仓库围绕「评估驱动」开发：每次改动先立一个**可证伪的实验假设**，跑评估、用**数据裁决**，而不是凭感觉改。

## 工程约定

- 当前系统架构及能力状态以 [`docs/architecture.md`](./docs/architecture.md) 为准。
- Python、React/TypeScript、错误处理、异步边界和验证要求见
  [`docs/development/coding-standards.md`](./docs/development/coding-standards.md)。
- 修改 `frontend/**` 前还必须阅读 [`frontend/AGENTS.md`](./frontend/AGENTS.md)；其中规定了前端的
  可访问性、交互、性能、文案和视觉验证要求。
- 规格描述意图，代码描述现状，测试与实验提供证据；三者冲突时先定位差异，不把规划中的能力描述为可用。

## 修改前与实现时的要求

1. 先定位相关规格、实现、调用方、数据契约与测试，说明发现的规格/实现差异。
2. 将改动收敛到一个可证伪假设或明确契约缺口；不得借机重写无关模块或增加没有业务问题、测试隔离需求或评估证据的抽象。
3. 新增或修改 Python 公共函数、跨模块入口和数据模型时补齐参数与返回值类型；同步/异步边界必须与实际 I/O 和调用链一致。
4. 外部 client、recorder、tool registry 等需要替换或隔离的依赖优先通过构造参数注入。捕获异常只用于补充上下文、转换边界错误或执行降级，且工具失败必须保留调用级审计，不能伪装成成功事实。
5. 前端请求和响应类型、通用错误处理统一放在 `frontend/src/api.ts`；服务端数据通过
   `frontend/src/hooks.ts` 或同层受控 Hook 暴露状态。新增页面必须覆盖其数据路径相关的加载中、空数据、刷新失败和首次加载失败状态。
6. 前端不得原地修改 props、查询结果或共享对象，也不得绕过受控 action 直接篡改共享状态。UI 改动还须遵守
   `frontend/AGENTS.md` 的语义、键盘可达、焦点、动态反馈、响应式与动效规则。

## 验证与文档更新

- 只先运行受影响边界所需的最小验证；合并前补齐本次变更要求的确定性检查。
- GitHub Actions 工作流中的外部 `uses:` 依赖必须固定到完整的 40 位 commit SHA，不得使用分支、tag 或缩写 SHA；
  在行尾保留对应 release tag 注释（例如 `# v7.0.0`）供审查和更新。升级时先从依赖的官方仓库核对 release tag
  对应的完整 SHA，再同时更新 SHA 与注释，并检查 `.github/workflows/` 下所有 `uses:` 引用。
- Python lint 与格式检查：`make lint`。
- Python 静态类型检查：`make typecheck`。
- Python 确定性测试：`make test`。
- 前端改动至少运行：`make frontend-build`。涉及交互、响应式或视觉表现时，还须在浏览器检查相关状态；构建成功不替代可访问性和交互验证。
- 合并前完整确定性质量门禁：`make check`。
- 修改模型、prompt、工具描述或 judge 时，运行最小相关评估；非确定性结论默认至少 `N≥4`，并记录假设、数据集版本、参数、结果和裁决。
- 系统边界、工具契约、权限、安全、评估口径或跨模块产物发生变化时，同步相关规格和索引；用户可见变化写入 `CHANGELOG.md`，长期架构取舍写入 `docs/decisions/` 下的 ADR。

## 分支模型

- `main`：已收口的里程碑（1.0 + 各 Phase）。
- `2.0`：当前开发分支（WIP）。每个 Phase 收口时 `git merge --no-ff 2.0` 合进 `main`（保留提交历史与日期）。

## 一次实验的生命周期

每一轮优化 = 一个 **Issue**（用「评估优化实验」模板），五段：

1. **问题 / 现象** — 哪些 case / 指标出问题，是否取证（对照 live tool output / golden）。
2. **假设 / 方案** — 怎么改、为什么。介质 = 改数据 / 改 agent / 改 judge / 改源。
3. **可证伪预期** — 写死的、可验证的结果（别含糊）。
4. **实验结果** — N 跑数字（在评论里滚动补）。
5. **裁决** — 达成 / 半解(model 边界) / 未达 + 关联 PR。

流程：

```
New issue(模板) + 打标签 + 加进 Project
  → git checkout -b <分支> → 改 → commit（正文写 #N）
  → PR 描述写 "Closes #N" → merge（diff 自动钉到 issue）
  → 本地跑评估(N≥4) → 数字贴进 issue → 填「裁决」→ 关闭
  → Project 字段更新（预期达成 / status）
```

分工：**Issue = 一次实验的完整弧；PR = diff 凭证；Project = 总览仪表盘。**

## 标签

`experiment` · `judge假阳` · `agent越界` · `judge边界` · `model边界` · `命中轴` · `忠实轴` · `phaseX`

## 评估怎么跑

- 生成答案 + 审计：`make eval-run`
- L1 路由判分（确定性）：`make eval-l1`
- L2 内容判分（LLM 裁判，慢 / 非确定 / 烧 token）：`make eval-l2`
- 裁判回归用固定夹具 N 跑：`make eval-fixtures`
- **别单 run**：裁判抽取是非确定的，单次结果会被抖动误导，结论一律 N≥4 取统计。
- `data/orders.json` 是**冻结的 eval fixture**：部分 golden 按订单状态 key（如已签收单不要求 eta）。改动数据后须复核相关 golden 并更新 `src/eval/l2/judge.py` 里的 `_ORDERS_FROZEN_SHA256`。

## 修改跨边界数据契约

跨边界数据与派生量的设计规则见
[`Coding Standards`](./docs/development/coding-standards.md#contracts-and-data-changes)。修改契约时按以下流程执行：

1. 修改或新增 `src/contracts/` 下的 Pydantic model；不兼容变化同时提升 `schema_version`。
2. 运行 `make schema-export` 重新生成 `src/contracts/schemas/*.schema.json`。
3. 审查生成的 JSON Schema 快照 diff，并随 model 变更一并提交。
4. 判断已有产物是否仍兼容；不兼容时明确选择重跑或删除旧产物，并在关联 Spec 或 PR 中记录处理策略。

旧产物因 `schema_version` 不兼容而读回失败是预期行为，不要用静默兼容层掩盖契约变化。

## 公开 vs 私有（约定）

- **公开物**（Issue / PR / commit message）：用自包含的工程语言，不挂内部代号或私有文档名。
- 私有笔记（不入库）可**单向**引用公开物（如「见 #1」）；**链接只从私有指向公开，不反向**。
