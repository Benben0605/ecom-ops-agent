# 开发流程

本仓库围绕「评估驱动」开发：每次改动先立一个**可证伪的实验假设**，跑评估、用**数据裁决**，而不是凭感觉改。

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

- 生成答案 + 审计：`python -m src.eval_answer_runner`
- L1 路由判分（确定性）：`python -m src.eval_judge`
- L2 内容判分（LLM 裁判，慢 / 非确定 / 烧 token）：`python -m src.eval_l2_judge`
- 裁判回归用固定夹具 N 跑：`python -m src.eval_l2_fixtures`
- **别单 run**：裁判抽取是非确定的，单次结果会被抖动误导，结论一律 N≥4 取统计。
- `data/orders.json` 是**冻结的 eval fixture**：部分 golden 按订单状态 key（如已签收单不要求 eta）。改动数据后须复核相关 golden 并更新 `src/eval_l2_judge.py` 里的 `_ORDERS_FROZEN_SHA256`。

## 公开 vs 私有（约定）

- **公开物**（Issue / PR / commit message）：用自包含的工程语言，不挂内部代号或私有文档名。
- 私有笔记（不入库）可**单向**引用公开物（如「见 #1」）；**链接只从私有指向公开，不反向**。
