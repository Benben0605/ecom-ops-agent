# SDD 启动与代码整理计划

## 结论

有必要整理现有代码，但第一步不应是全仓搬目录，而是先建立可信基线。当前最优先的问题是：

- `make test` 因 4 个测试文件被删除而执行 0 个测试并失败；临时恢复后，原有 22 个测试全部通过。
- [docs/specs/README.md](/Users/dehao/.codex/worktrees/7086/ecom-ops-agent/docs/specs/README.md) 已定义 Spec 流程，但尚无真正的模块 Spec。
- [src/agent.py](/Users/dehao/.codex/worktrees/7086/ecom-ops-agent/src/agent.py) 混合模型客户端、prompt、工具注册、执行、审计、压缩和 Supervisor，确实需要定向拆分。
- [src/experiment/runner.py](/Users/dehao/.codex/worktrees/7086/ecom-ops-agent/src/experiment/runner.py) 和 `dashboard/experiment_adapter.py` 也是热点，但不应在第一轮一起重构。
- 前端构建当前通过。

## 实施顺序

1. **先收口 Agent Starter**
   - 恢复被删除且仍然通过的 4 个测试文件。
   - 将当前脚手架改动拆成“开发规范与文档”“uv/Docker/Makefile 工具链”“实验 provenance 行为变更”三个独立提交。
   - 验证 `uv sync --frozen`、`make test`、`make frontend-build` 和 Docker 构建。
   - 不在这一阶段移动业务代码。

2. **建立自动化质量门禁**
   - 在 `pyproject.toml` 加入 Ruff 开发依赖与最小规则，先覆盖格式、导入、未定义名称和明显错误。
   - 一次性格式化作为独立机械提交，避免与业务重构混合。
   - 让 `make check` 串联 lint、22 个现有测试和前端构建。
   - 增加 CI 执行 `make check`；严格类型检查暂缓，避免一次性处理全部历史类型债务。

3. **编写第一份实际 Spec**
   - 新建 `docs/specs/agent-runtime-boundary.md`，初始为 `Spec Status: draft`、`Capability Status: operational`。
   - 固化现有默认行为：单 Agent tool-calling loop、工具调用与消息配对、可信 `role/user_id` 注入、叶子工具审计、失败反馈、历史压缩和 Supervisor 仅作对照。
   - 明确本轮目标是“提高可读性和可测试性，保持用户行为、工具 schema、API 路由和评估口径不变”。
   - 为这些行为增加不调用真实模型的 characterization tests，作为重构前等价性基线。

4. **只重构核心运行时边界**
   - 将核心实现拆到 `src/runtime/`：会话循环、prompt、工具注册、Supervisor 分离。
   - 保留 `src/agent.py` 作为兼容门面，继续导出 `ChatSession` 和 `SupervisorAgent`，避免调用方批量迁移。
   - 为 `ChatSession` 增加可选模型客户端注入，默认仍使用当前 OpenAI 配置；测试使用 fake client。
   - 保持 `ChatSession.chat(str) -> str`、FastAPI 路由、工具 schema、审计字段和实验产物不变。
   - 不在本轮移动 `src/tools/`、`src/schemas/`，也不拆分 Dashboard；待第一项真实 SDD 需求触达相应边界时再做。

5. **单独清理实验入口**
   - 移除 `python -m src.experiment.runner` 无参数时自动运行付费实验的行为，改为显示帮助并退出。
   - 将 runner 底部历史实验样例移至开发文档或实验记录，runner 只保留执行与 CLI。
   - Dashboard 的 977 行 adapter 仅登记为后续候选，不在本轮顺手拆分。

## 验证

- Starter 收口后：现有 22 个 Python 测试全部通过，前端构建通过。
- Runtime characterization tests 覆盖：直接回复、单/多工具调用、未知或失败工具、审计、身份参数覆盖、压缩时 tool-call 配对、Supervisor 叶子审计。
- 重构前后运行同一确定性测试集；涉及 prompt 或工具描述的任何意外 diff 都视为越界。
- 本轮不主动改变模型行为，因此不要求付费 L1/L2 实验；若实际 diff 触及 prompt、schema、工具路由或 judge，则补最小相关评估且 `N≥4`。

## 默认假设

- 第一项业务 Spec 尚未确定，因此优先建设可安全演进的核心基线。
- 不进行全仓架构重写，不引入 Agent 框架、Repository layer 或新的多 Agent 默认路径。
- 现有测试删除视为脚手架未收口，而不是有意废弃。