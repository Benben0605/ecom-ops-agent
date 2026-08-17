# 分层规格包规范与索引

本目录说明何时、如何创建和维护规格包，并提供索引。当前架构边界与能力状态见
[`docs/architecture.md`](../architecture.md)；实现现状仍须以代码、测试和实验结果为证。项目级协作、验证与
发布规则分别见 [`AGENTS.md`](../../AGENTS.md) 和 [`CONTRIBUTING.md`](../../CONTRIBUTING.md)，本页不复制
这些规则。

## 什么变化需要规格包

中大型、跨边界或需要独立验收的变化，应使用 `docs/specs/<stable-kebab-topic>/` 规格包。出现以下任一变化时，
需要新增或更新规格包：

- 新增重要业务能力，或改变已有能力的目标、非目标和用户可见行为；
- 改变系统边界、模块职责、默认执行路径或多个模块之间的协作方式；
- 改变工具/API/跨边界数据契约，以及相应的兼容、迁移或回滚策略；
- 改变身份、权限、隐私、安全或人工转接边界；
- 改变审计语义、L1/L2 评估口径或验收标准。

局部重构、在既有契约内修复 bug、单次实验记录和纯操作说明通常不单独建立规格包；它们分别由代码与测试、
Issue/PR、[`CONTRIBUTING.md`](../../CONTRIBUTING.md) 或
[`Coding Standards`](../development/coding-standards.md) 承载。如果一次局部变更暴露出未定义的系统边界，
仍应补规格包。是否建包取决于决策和验收边界，不取决于改动行数。

## 规格包结构

一个完整规格包包含以下标准产物；它们按 Gate 顺序逐步形成，不应提前填充后层文档来模拟完成：

```text
docs/specs/<stable-kebab-topic>/
├── SPEC.md
├── DESIGN.md
├── TEST.md
├── TASKS.md
└── PROGRESS.md
```

包内可选建 `README.md`，但它只能作为导航页，链接上述产物、相关 ADR/Issue/PR/实验；不得复制状态、需求、设计、
验收或进度，从而形成第二个事实源。

各层只有一个主要职责：

| 产物 | 唯一职责与权威边界 |
|------|--------------------|
| `SPEC.md` | 定义问题、目标、非目标、可观察行为、契约、不变量、失败行为和验收标准，回答 **what/why**。不得规定文件拆分、类名或任务顺序；它是本规格包 `Spec Status` 的事实源。 |
| `DESIGN.md` | 在已接受的 `SPEC.md` 约束内定义实现方案、模块职责、调用链、接口、数据流、备选与取舍、兼容、迁移和回滚。不得擅自新增或改变需求。 |
| `TEST.md` | 把需求和验收标准映射到确定性测试、集成测试、必要实验和人工验证，写明命令、预期结果与应保存的证据。不得用测试方便性反向改写需求。 |
| `TASKS.md` | 把已审核的设计与验证计划拆成依赖有序、可独立验证的实施任务。不得成为新的需求或设计事实源。 |
| `PROGRESS.md` | 记录实施期间的事实、证据、发现、偏离、阻塞和下一步。它是事实日志，不得静默改写上游决策，也不得把计划写成完成事实。 |

若层与层冲突，以更上游、已通过人工 Gate 的产物为约束，并退回冲突处修订；代码描述现状，但不能自行覆盖已接受
规格。长期且高影响的架构取舍仍写入 `docs/decisions/` 下的 ADR，并从 `DESIGN.md` 链接。

## 命名、索引与生命周期

- 目录名使用稳定的 kebab-case 业务或架构主题，例如 `session-persistence/`；不得包含日期、作者、`phase`、
  `draft` 等生命周期信息。
- 一个规格包聚焦一个可独立验收的边界。若两个部分可以独立决策、实施或回滚，应拆成两个规格包并互相链接。
- 根 `docs/specs/README.md` 维护规格包索引并同步展示 `SPEC.md` 中的 `Spec Status`；`SPEC.md` 才是该状态的
  事实源。索引不推断实现或能力成熟度。
- `SPEC.md` 记录 `Supersedes` / `Superseded by`，并链接相关 ADR、Issue、PR 和实验；`DESIGN.md` 记录兼容、
  迁移与回滚关系。被替代的材料保留历史内容和证据，不原地改写结论。
- 尚未迁移到分层结构的历史单文件 Spec、计划或调研可以留在原位，不因本规范自动获得 `accepted`、
  `implementing` 或 `verified` 状态。后续发生实质变化时，应经人工裁决后迁移到稳定命名的规格包，或从新规格包
  明确链接为来源；不得仅改文件名伪造生命周期。

ADR 命名仍采用 `docs/decisions/ADR-NNN-short-title.md`。

## 生成与人工审核顺序

标准流程如下：

```text
source / Issue / roadmap
  → SPEC draft
  → 人工 accepted
  → DESIGN
  → TEST
  → TASKS
  → 初始化 PROGRESS
  → 实施与持续记录
  → convergence / 最终验收
```

`TEST.md` 可能暴露不可测试的要求、遗漏的失败行为或设计缺口。此时必须回改 `SPEC.md` / `DESIGN.md`，并按影响
范围重新经过人工审核，然后才能继续；不能只在 `TEST.md`、`TASKS.md` 或 `PROGRESS.md` 中补上隐含需求。

每个 Gate 都由人工给出通过或退回结论，并在对应产物中记录审核人、日期和裁决/证据链接；未获明确通过时保持
`pending human review`，不能以“无人反对”视为通过。

| Gate | 人工审核要点 | 通过后 | 退回规则 |
|------|--------------|--------|----------|
| 来源与立项 | 业务问题、失败 case 或契约缺口是否明确，是否值得建立规格包 | 允许起草 `SPEC.md`，状态为 `draft` | 补充来源证据、缩小范围，或改由 Issue/PR 承载小改动 |
| `SPEC.md` | what/why、边界、契约、不变量、失败行为和验收标准是否可裁决 | 人工把 `Spec Status` 推进到 `accepted` | 保持 `draft`；按意见修订。实质修改已接受内容时也退回 `draft` 并重新接受 |
| `DESIGN.md` | 方案是否完整覆盖需求，接口、取舍、兼容、迁移和回滚是否可行 | 标记设计审核通过，允许制定证据计划 | 若发现新需求或改变验收，退回 `SPEC.md`；否则修订设计后重新审核 |
| `TEST.md` | 每项需求/验收是否有足够证据，命令、预期结果和实验范围是否明确 | 标记验证计划审核通过 | 测试缺口留在本层修订；需求或方案缺口回到对应上游层并重新审核 |
| `TASKS.md` | 依赖是否有序，每项是否可独立验证并覆盖已批准设计与测试 | 标记实施计划审核通过 | 拆分或重排任务；任何隐藏需求/设计决定必须退回上游，不在任务层补写 |
| `PROGRESS.md` 初始化 | 上游 Gate、基线、首批任务和证据位置是否明确 | 人工授权进入实施；开始后记录事实 | 上游未收口则不实施；补齐对应 Gate 后重新确认 |
| 实施与偏离 | 变更是否仍在已接受边界内，证据是否与任务和验收可追踪 | 人工可据实际开始将 Spec 推进到 `implementing` | 设计偏离回 `DESIGN.md`；需求/验收变化回 `SPEC.md`，并重新经过下游 Gate |
| convergence / 最终验收 | 所有 AC 是否有足够证据，迁移/回滚/开放缺口是否已裁决 | 只能由人工将 Spec 推进到 `verified`，或决定继续实施/退回 | 缺证据回 `TEST.md`/实施；行为不符回设计或规格；不再采用则按替代关系处理 |

Agent 可以起草、分析、执行已授权任务和整理证据，但不得自行把 Spec 从 `draft` 提升为 `accepted`，不得自行
宣称 `verified`，也不得代替人工裁决设计、验证计划、偏离或状态迁移。文档中的 `Review Gate` 只记录人工审核
结果；任务勾选和日志更新只表示实施进度，均不等同于规格状态变化。

## 可追踪性

每个规格包建议使用稳定、包内唯一且不因排序变化而重编号的 ID：

- `R-xxx`：需求、契约或不变量；
- `AC-xxx`：可判定的验收标准；
- `D-xxx`：实现设计决定；
- `T-xxx`：测试、实验或人工验证项；
- `K-xxx`：实施任务。

最小追踪链是 `R → AC → D → T → K → 实施证据`：

| 层 | 必须建立的映射 |
|----|----------------|
| `SPEC.md` | 每个 `R-xxx` 映射至少一个 `AC-xxx`；每个 AC 指回它判定的需求 |
| `DESIGN.md` | 每个 `D-xxx` 列出覆盖的 `R-xxx` / `AC-xxx`；未覆盖项必须明确说明原因并回到 Spec 裁决 |
| `TEST.md` | 每个 `T-xxx` 指向 `R-xxx` / `AC-xxx`，写明证据类型、命令、预期结果和产物位置；每个 AC 至少有一条足以裁决的证据路径 |
| `TASKS.md` | 每个 `K-xxx` 指向相关 `D-xxx` 和 `T-xxx`，并声明完成后如何独立验证 |
| `PROGRESS.md` | 按 `K-xxx` 记录实际 diff/PR、测试或实验结果、人工验证与裁决链接；失败、偏离和未覆盖项同样要记录 |

不能跳过上游只在后层补事实。后层发现新用户行为、契约、不变量或验收要求时，先修订 `SPEC.md`；发现实现方案
变化时，先修订 `DESIGN.md`；随后更新所有受影响映射并重新经过相应人工 Gate。

## 两条独立的状态轴

`Spec Status` 回答“这份规格走到哪一步”，`Capability Status` 回答“受影响能力当前有多少实现与证据”。两条轴
分别推进，不能由其中一条推断另一条：Spec 被接受不表示能力已经实现，能力已有运行代码也不表示当前 Spec 已
完成验收。

### Spec Status：规格生命周期

默认生命周期是 `draft` → `accepted` → `implementing` → `verified` → `superseded`。

| Spec Status | 含义 | 进入条件 |
|-------------|------|----------|
| `draft` | 问题、边界或验收仍在讨论，不能作为已接受目标 | 建立 `SPEC.md`，给出可评审的问题、范围和验收草案 |
| `accepted` | 规格意图、边界和验收标准已经人工评审接受；设计和实现可以尚未开始 | 关键需求已裁决，剩余开放问题不阻塞设计或验收 |
| `implementing` | 正按已接受的规格及已审核的下游计划实施，但尚未完成全部验收 | 已有可追踪的实施 Issue/PR 或迁移产物，并开始产生实现证据 |
| `verified` | 实现已满足 `SPEC.md` 的验收标准，相关确定性检查和必要实验均有可追踪证据 | 人工完成最终验收，证据链完整，且不存在未裁决的验收缺口 |
| `superseded` | 该规格已被后续规格包或 ADR 取代，不再作为当前目标 | 人工裁决替代关系，并在 `SPEC.md` 填写 `Superseded by`，保留历史证据 |

`verified` 只证明实现符合本 `SPEC.md` 已声明的验收标准，不自动表示所有受影响能力均为 `operational`。若验收
条件因新失败 case 或契约变化而失效，应由人工把 Spec 退回适当阶段并记录原因；若规格意图发生实质变化，优先
建立替代规格包并将旧 Spec 标记为 `superseded`，避免改写历史结论。

### Capability Status：能力成熟度

默认成熟路径是 `planned` → `experimental` → `operational` → `deprecated`。
[`docs/architecture.md`](../architecture.md) 是 Capability Status 的事实源；规格包只链接并同步投影，不自行定义
能力状态。

| Capability Status | 含义 | 进入条件 |
|-------------------|------|----------|
| `planned` | 只有设计意图，尚不能从代码推断为可用 | 尚无可运行实现，或实现尚未形成可验证入口 |
| `experimental` | 已有可运行实现，但非默认、迁移未完成、证据有限或结果依赖非确定性裁判 | 至少有受控入口和最小边界验证，且限制已明确记录 |
| `operational` | 默认或受支持路径已存在，并有测试、评估或运行证据 | 已满足支持范围内的验收要求，权限、审计、回滚和已知限制均已确认 |
| `deprecated` | 能力仍可能存在，但已不再推荐继续采用，正等待迁移或移除 | 已明确替代路径、受影响调用方、迁移窗口和移除条件 |

一个规格包可能影响多个且成熟度不同的 capability，因此不得给整个包填写一个统一 `Capability Status`。
`SPEC.md` 应使用逐能力状态映射，逐行链接 `docs/architecture.md` 中的准确能力，并抄录其当前状态与拟议影响；
若两者不一致，以架构能力地图为准并先解决差异。能力状态和 Spec 状态的每次迁移都需要人工裁决与可追踪证据，
但两者分别更新，不为让状态“看起来一致”而联动升级。

常见的合法组合包括：Spec 已 `accepted`，相关能力仍为 `planned`；Spec 正在 `implementing`，部分既有能力为
`operational`、新增路径仍为 `experimental`；Spec 已 `verified`，能力仍因发布策略或支持证据不足保持
`experimental`。反过来，为既有 `operational` 能力起草下一版变化时，新 Spec 仍从 `draft` 开始。

人工推进 Spec 状态后，应同步 `SPEC.md` 元数据和本页索引；人工推进能力状态后，应先更新
[`docs/architecture.md`](../architecture.md)，再同步各相关 `SPEC.md` 的逐能力映射。两种同步都必须链接本次裁决
证据。

## 模板

以下模板是最小骨架，可按主题增加小节，但不能跨越各层权威边界。包内文件链接均相对于规格包目录。人工通过
Gate 时，把对应审核字段更新为 `approved by <reviewer> on YYYY-MM-DD` 并附裁决链接。

### `SPEC.md`

```markdown
# <Spec title>

- Spec Status: draft
- Owners: <team or owner>
- Last updated: YYYY-MM-DD
- Source: <Issue / roadmap / failure case links>
- Related: <ADR / Issue / PR / experiment links>
- Supersedes: <optional package link>
- Superseded by: <optional package link>

## Problem and evidence

描述可观察的问题、当前行为、受影响对象和已有证据。

## Goals and non-goals

- Goals: ...
- Non-goals: ...

## Capability status mapping

| Capability | Current status from architecture | Intended impact | Evidence / decision |
|------------|----------------------------------|-----------------|---------------------|
| [<exact capability>](../../architecture.md#<anchor>) | planned / experimental / operational / deprecated | <不变或拟议变化> | <link> |

## Requirements and invariants

| ID | Requirement / contract / invariant | Rationale |
|----|------------------------------------|-----------|
| R-001 | ... | ... |

## Observable behavior and failure modes

描述成功、拒绝、降级、澄清、转人工以及权限/隐私边界；不写类名、文件拆分或任务顺序。

## Acceptance criteria

| ID | Requirement | Observable pass condition |
|----|-------------|---------------------------|
| AC-001 | R-001 | ... |

## Open questions

只保留尚未人工裁决、会影响范围或验收的问题。
```

### `DESIGN.md`

```markdown
# <Topic> design

- Spec: [SPEC.md](./SPEC.md)
- Review Gate: pending human review
- Last updated: YYYY-MM-DD
- Related ADRs: <links or none>

## Proposed approach

描述方案如何满足已接受规格，不新增需求。

## Responsibilities, call chain, and data flow

说明模块职责、调用顺序、状态所有权和数据流。

## Interfaces and contracts

说明内部/跨边界接口、schema 版本、权限和失败传播。

## Design decisions and traceability

| ID | Decision | Covers | Alternatives / trade-off |
|----|----------|--------|--------------------------|
| D-001 | ... | R-001, AC-001 | ... |

## Compatibility, migration, and rollback

说明调用方、旧数据/产物、发布顺序、回滚条件和恢复路径。

## Design risks and open questions

列出待人工裁决项；若改变需求或验收，退回 SPEC.md。
```

### `TEST.md`

```markdown
# <Topic> evidence plan

- Spec: [SPEC.md](./SPEC.md)
- Design: [DESIGN.md](./DESIGN.md)
- Review Gate: pending human review
- Last updated: YYYY-MM-DD

## Evidence strategy

确定性检查优先；说明哪些边界需要集成测试、实验或人工验证，以及原因。

## Acceptance-to-evidence mapping

| ID | Covers | Evidence type | Command / procedure | Expected result | Evidence location |
|----|--------|---------------|---------------------|-----------------|-------------------|
| T-001 | R-001, AC-001 | deterministic test | `<command>` | ... | <path / PR / artifact> |

## Required experiments

仅在变更涉及模型、prompt、工具描述/schema、路由或 judge，或确定性测试不足以裁决时运行最小相关评估。记录
可证伪假设、数据集版本、参数、结果和裁决；非确定性实验默认 `N≥4`，单次运行不能裁决。

## Manual verification

列出无法合理自动化的步骤、预期结果和审核人；无则写 `None`。

## Exit criteria

说明全部证据何时足以进入 convergence；缺口必须回到对应上游层。
```

### `TASKS.md`

```markdown
# <Topic> implementation tasks

- Spec: [SPEC.md](./SPEC.md)
- Design: [DESIGN.md](./DESIGN.md)
- Test plan: [TEST.md](./TEST.md)
- Review Gate: pending human review
- Last updated: YYYY-MM-DD

| Done | ID | Task | Depends on | Trace | Independent verification |
|------|----|------|------------|-------|--------------------------|
| [ ] | K-001 | ... | None | D-001, T-001 | `<command>` → <expected result> |

任务只执行已审核决定。若任务需要新需求或新设计，停止并退回对应上游文档。
```

### `PROGRESS.md`

```markdown
# <Topic> progress

- Spec: [SPEC.md](./SPEC.md)
- Tasks: [TASKS.md](./TASKS.md)
- Initialization Gate: pending human review
- Task Progress: not started | in progress | blocked | convergence review
- Last updated: YYYY-MM-DD

## Baseline and approved gates

记录开始时的 commit/分支、人工 Gate 结论和已知限制；不在此复制上游内容。

## Fact log

| Date | Task | Fact / change | Evidence | Result / next step |
|------|------|---------------|----------|--------------------|
| YYYY-MM-DD | K-001 | ... | <diff / PR / T-xxx result> | ... |

## Discoveries, deviations, and blockers

记录发现及其影响。需求/验收变化退回 SPEC.md；方案变化退回 DESIGN.md，并链接人工裁决。

## Convergence evidence

按 AC-xxx 汇总最终证据与未解决缺口，提交人工验收；不得自行宣称 verified。
```

验证命令及实验生命周期以 [`CONTRIBUTING.md`](../../CONTRIBUTING.md#验证与文档更新) 为准；跨边界契约规则见
[`Coding Standards`](../development/coding-standards.md#contracts-and-data-changes)。模板只要求记录本规格包实际需要的
验证，不机械复制项目级命令。

## 规格包索引

当前没有按本分层规范登记的规格包。新增包时，应在 `SPEC.md` 建立为 `draft` 后登记，并同步检查架构能力地图；
进入索引不表示该规格已被接受、实现或验证，也不表示相关能力可用。

| 规格包 | Spec Status（同步值） | 受影响能力 | 关系 |
|--------|-----------------------|------------|------|
| _None_ | — | — | — |

## 与 ADR、Issue、PR 和实验的关系

| 产物 | 负责回答 | 不应替代 |
|------|----------|----------|
| 规格包 | 系统应如何工作、为何需要、如何实现与验收，各层事实如何追踪 | 实现 diff、实验流水账 |
| ADR | 为什么选择一个长期且高影响的架构方案，包括备选与取舍 | 能力的完整行为规格 |
| Issue / roadmap | 哪个问题、失败 case 或目标触发变化，假设是什么、如何裁决 | 稳定的系统契约 |
| PR | 具体实现 diff、测试结果和审查记录 | 问题背景或长期设计理由 |
| 实验 | 假设在给定数据集、参数和运行次数下是否成立 | 单次结果不能定义长期行为 |

通常由 Issue 记录问题与可证伪假设；需要稳定行为和验收边界时建立规格包，需要保留重大取舍时增加 ADR；PR
关联实现与确定性验证；实验按 [`CONTRIBUTING.md`](../../CONTRIBUTING.md#一次实验的生命周期) 运行并把结果与
裁决回写 Issue/PR 及 `PROGRESS.md`。最终由人工分别裁决 `SPEC.md` 的生命周期、
[`docs/architecture.md`](../architecture.md) 的逐项能力状态，以及适用时的 `CHANGELOG.md`。完成任务、实现或验证
不会自动推进任一状态轴。
