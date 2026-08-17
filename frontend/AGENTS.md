# Frontend Agent Instructions

## Scope and precedence

本文件适用于 `frontend/**`。根目录 [`AGENTS.md`](../AGENTS.md) 与
[`docs/development/coding-standards.md`](../docs/development/coding-standards.md) 仍然有效；发生冲突时，优先遵守
项目级业务、安全、数据契约与验证要求。

以下界面规则改编自
[Vercel Web Interface Guidelines](https://github.com/vercel-labs/web-interface-guidelines)。上游规则会变化；更新本文件时应审查差异，
不要直接覆盖本项目约束。

实现或修改界面时应用相关规则。执行 UI、UX 或可访问性审查时，检查全部规则，并按“审查输出”报告发现。

## Accessibility

- 纯图标按钮必须提供有意义的 `aria-label`；装饰图标使用 `aria-hidden="true"`。
- 表单控件必须有 `<label>` 或可访问名称，且点击标签可以聚焦对应控件。
- 操作使用 `<button>`，导航使用 `<a>` 或 `<Link>`；不要用带点击事件的 `<div>` 或 `<span>` 模拟。
- 所有流程必须可通过键盘完成，交互控件必须有清晰的 `:focus-visible` 状态。
- 除非提供等效焦点样式，否则不得移除 `outline`；组合控件按需使用 `:focus-within`。
- 图片必须有准确的 `alt`；纯装饰图片使用空 `alt`。
- toast、异步校验等动态更新使用合适的 `aria-live="polite"`。
- 优先使用原生语义元素，再考虑 ARIA；标题保持 `<h1>` 至 `<h6>` 的合理层级，并提供跳到主要内容的入口。
- 锚点标题设置合适的 `scroll-margin-top`。
- 不得通过 `user-scalable=no`、`maximum-scale=1` 等方式禁用浏览器缩放。

## Forms and feedback

- 输入项提供有意义的 `name`、`autocomplete`、正确的 `type` 和 `inputMode`。
- 不得阻止粘贴。邮箱、验证码、用户名等字段按需关闭拼写检查。
- 复选框和单选框的标签与控件应组成同一个足够大的点击区域，不留交互死区。
- 提交按钮在请求真正开始前保持可用；请求期间防止重复提交，并保留原标签及加载指示。
- 校验错误显示在对应字段附近；提交失败时将焦点移动到第一个错误。
- placeholder 使用示例或格式提示并以 `…` 结尾；不要把 placeholder 当作标签。
- 用户可能丢失未保存内容时，在离开页面前提供警告。
- 加载、空数据、刷新失败、首次加载失败和成功状态都必须有明确设计，错误信息应给出下一步。

## Interaction and navigation

- 链接必须保留 Cmd/Ctrl+Click、中键和“在新标签页打开”等标准浏览器行为。
- 筛选、标签页、分页、展开面板等需要分享、刷新或前进后退恢复的状态应进入 URL。
- 危险操作必须提供确认步骤或可撤销窗口，不得单击后立即执行不可逆操作。
- 可点击区域与视觉目标一致；小图标扩大命中区域，移动端目标至少约 `44px`。
- 控件按需设置 `touch-action: manipulation`，并有意设置点击高亮样式。
- modal、drawer 或 sheet 按需设置 `overscroll-behavior: contain`，正确管理和归还焦点。
- 自动聚焦仅用于桌面端单一主输入场景，避免在移动端无故唤起键盘。
- 拖拽期间避免文本选择和意外交互；动画与交互必须可被用户输入打断。

## Animation

- 尊重 `prefers-reduced-motion`，提供减弱或禁用动画的变体。
- 优先使用 CSS，并尽量只动画 `transform` 和 `opacity`。
- 禁止 `transition: all`；明确列出需要过渡的属性。
- 设置符合视觉来源的 `transform-origin`。
- SVG 变换优先作用于 `<g>` 包装层，并按需设置 `transform-box: fill-box` 与正确的变换原点。
- 动画用于解释因果关系或提供有意图的反馈，避免无目的自动播放。

## Layout and content

- 使用 flex、grid 和内在尺寸完成布局，避免在渲染期间读取 DOM 尺寸或依赖 JavaScript 测量布局。
- 覆盖移动端、常见桌面宽度和超宽屏；全宽布局考虑 `env(safe-area-inset-*)`。
- 修复内容溢出的根因，避免无意义的横向或嵌套滚动条。
- 文本容器必须处理空、短、普通和极长内容；flex 子项需要截断时设置 `min-width: 0`。
- 标题按需使用 `text-wrap: balance` 或 `text-wrap: pretty`，数值比较使用 `font-variant-numeric: tabular-nums`。
- 界面文案使用 `…`，不要使用三个句点；加载状态写作“加载中…”等形式。
- 状态不能只依靠颜色表达；图标含义同时提供文本或可访问名称。
- 日期、时间、数字和货币使用 `Intl.DateTimeFormat`、`Intl.NumberFormat` 等本地化 API，不硬编码展示格式。
- 品牌名、商品名、代码 token 和技术标识符按需使用 `translate="no"`，避免自动翻译破坏内容。

## Images, performance, and theming

- `<img>` 提供明确的 `width` 和 `height` 以避免布局偏移。
- 首屏关键图片可预加载；非首屏图片使用 `loading="lazy"`，不要无差别预加载资源。
- 超过约 50 项且渲染成本明显的列表考虑虚拟化或 `content-visibility: auto`。
- 不在 render 中调用 `getBoundingClientRect`、读取 `offsetHeight`、`offsetWidth` 或 `scrollTop`；批量安排 DOM 读写。
- 优先使用非受控输入；受控输入必须保持每次按键更新足够轻量。
- 只为确有收益的外部资源设置 `preconnect`；关键字体预加载时配合 `font-display: swap`。
- 深色主题在 `<html>` 上声明正确的 `color-scheme`，并让 `theme-color` 与页面背景一致。
- 原生 `<select>` 明确设置背景色和文字色，避免 Windows 深色模式对比度问题。
- hover、active 和 focus 状态应比静止状态更清晰，并满足可访问对比度要求。

## Copy

- 使用简洁、主动、面向操作的文案，并保持同一概念的命名一致。
- 按钮标签描述具体动作，例如“保存 API Key”，避免含糊的“继续”。
- 错误文案不仅说明问题，还要告诉用户如何恢复或继续。
- 数量优先使用数字；数字与单位之间保留空格，必要时使用不换行空格。
- Vercel 特有的英文大小写和措辞偏好不是本项目业务要求；中文产品文案应优先保持本项目既有语言和术语一致性。

## Review output

用户明确要求 UI、UX 或可访问性审查时，按文件分组，以可点击的 `file:line` 形式输出问题。说明问题与位置；
仅在修复方式不明显时补充解释。没有问题的文件标记为 `✓ pass`。示例：

```text
## frontend/src/components/Button.tsx

frontend/src/components/Button.tsx:42 - 纯图标按钮缺少 aria-label
frontend/src/components/Button.tsx:67 - transition: all，应明确列出过渡属性
```

## Verification

修改前端代码后，至少运行：

```bash
make frontend-build
```

需要交互、响应式或视觉验证的改动还应在浏览器中检查相关状态；构建成功不能替代可访问性与交互验证。
