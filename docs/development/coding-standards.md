# Coding Standards

## Python

### Naming and typing

- 模块、函数、方法和变量使用 `snake_case`。
- 类使用 `PascalCase`；常量使用 `UPPER_SNAKE_CASE`。
- 新增或修改的公共函数、跨模块入口和数据模型应提供参数与返回值类型。

### Dependency boundaries

- 外部 client、recorder、tool registry 等需要替换或测试隔离的依赖，优先通过构造参数注入。
- FastAPI `Depends` 只在确有 request-scoped 依赖、复用或生命周期管理需求时引入，不作为形式要求。
- 当前没有 Repository layer。只有当数据源替换、测试隔离或重复访问逻辑形成明确问题时才引入，并通过规格定义接口和迁移边界。

### Sync, async, and streaming

- 保持调用链与底层依赖一致：同步依赖使用普通 `def`，不要仅为形式改成 `async def`。
- 只有存在真实异步 I/O 或并发收益，并且调用方能正确 `await` 时才使用 `async def`。
- 流式接口在确认取消、超时、背压、错误和审计语义后使用 `AsyncIterator[T]`；未实现流式链路前不提前承诺该类型。

### Errors and return values

- 不强制引入全局 `Result` 类型。成功数据使用明确返回类型；预期的 HTTP 输入错误在 API 边界转换为合适的 `HTTPException`。
- 只捕获能够补充上下文、转换边界错误或执行降级的异常。宽泛捕获必须保留审计信息，且不得泄露敏感数据。
- 工具失败要保持调用级审计可追溯；不要把失败伪装成成功业务事实。

## React and TypeScript

- React 组件和 TypeScript 类型使用 `PascalCase`；变量与函数使用 `camelCase`；Hook 使用 `useXxx`。
- API 请求、响应类型和通用错误处理集中在 `frontend/src/api.ts`；页面和组件不重复实现 fetch wrapper。
- 服务端数据读取优先通过 `frontend/src/hooks.ts` 或同层受控 Hook 暴露 loading、refreshing 和 error 状态。
- 组件不直接篡改共享状态；通过 state setter、reducer、Hook 或 store 暴露的受控 action 更新。
- 不原地修改 props、查询结果或共享对象；需要变更时创建新对象或数组。
- 新增页面必须覆盖加载中、空数据、刷新失败和首次加载失败等与其数据路径相关的状态。

## Contracts and data changes

落盘、跨语言或跨模块读回的数据属于跨边界数据，必须使用 `src/contracts/` 下明确的 Pydantic model；
仅在进程内传递的 `dict` 不受此约束。

派生量由 model 根据原始字段统一计算，不保存为可能与原始数据分叉的普通字段：

- 使用 `@computed_field` 表达 `flag`、`pass_rate` 等可计算字段；
- 比率类指标保留可复核的分子和分母，由 model 计算比率；
- 写侧和读侧复用同一份 model 构造或派生逻辑，不重复实现同一指标。

契约修改、schema 导出、快照审查和旧产物处理流程见
[`CONTRIBUTING.md`](../../CONTRIBUTING.md#修改跨边界数据契约)。

## Verification

- Python 确定性测试：`make test`
- 前端类型检查与构建：`make frontend-build`
- 模型、prompt、工具或 judge 行为变化：按 `CONTRIBUTING.md` 运行最小相关评估，非确定性结论默认 `N≥4`

当前测试收集会导入模型配置，但确定性测试不应发起远程模型请求，因此可使用上述非敏感占位值。需要模型或
embedding 的评估必须改用本地环境中的有效配置。

只运行受影响边界所需的最小验证；合并前再执行该变更要求的完整确定性检查。
