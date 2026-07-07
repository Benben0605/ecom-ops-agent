import { useEffect, useMemo, useState } from "react";

import { saveL2RootCauseAnnotation } from "../api";
import type {
  FaithfulnessAxisItem,
  JsonValue,
  L2Case,
  L2DashboardData,
  L2RootCauseAnnotation,
  RootCauseOption,
  SaveL2RootCauseAnnotationPayload,
} from "../api";
import BucketTable from "../components/BucketTable";
import CaseDrawer from "../components/CaseDrawer";
import MarkdownContent from "../components/MarkdownContent";
import MetricCard from "../components/MetricCard";
import VerdictBadge from "../components/VerdictBadge";

interface QualityProps {
  query: {
    data: L2DashboardData | null;
    loading: boolean;
    error: string | null;
    refetch: () => Promise<void>;
  };
}

type Issue = "miss" | "unsupported";
type SaveAnnotation = (
  payload: SaveL2RootCauseAnnotationPayload,
) => Promise<L2RootCauseAnnotation>;
type AnnotationContext = Pick<SaveL2RootCauseAnnotationPayload, "exp_id" | "variant" | "run_index">;

const FALLBACK_ROOT_CAUSE_OPTIONS: RootCauseOption[] = [
  {
    value: "agent_hallucination",
    label: "agent越界，凭空加戏",
    description: "answer 补充了 tool output 中没有的业务事实、政策或操作结论。",
  },
];
const CUSTOM_ROOT_CAUSE_VALUE = "__custom_root_cause__";

const percent = (value: number | null) =>
  value == null ? "—" : `${(value * 100).toFixed(value === 0 || value === 1 ? 0 : 2)}%`;
const count = (value: number) => Number.isInteger(value) ? String(value) : value.toFixed(2);

const showJson = (value: JsonValue) =>
  typeof value === "string" ? value : JSON.stringify(value, null, 2);

const optionLabel = (options: RootCauseOption[], value: string) =>
  options.find((option) => option.value === value)?.label ?? value;

const isPresetRootCause = (options: RootCauseOption[], value: string) =>
  options.some((option) => option.value === value);

const initialRootCauseMode = (options: RootCauseOption[], value?: string) => {
  if (value && isPresetRootCause(options, value)) return value;
  if (value) return CUSTOM_ROOT_CAUSE_VALUE;
  return options[0]?.value ?? "";
};

function buildRootCauseSummary(
  caseId: string,
  axis: FaithfulnessAxisItem,
  options: RootCauseOption[],
  rootCause: string,
  rootCauseNote: string,
) {
  const label = rootCause ? optionLabel(options, rootCause) : "未标注";
  const note = rootCauseNote.trim();
  const cause = note ? `${label}；说明：${note}` : label;
  return [
    `${caseId} | L2 忠实轴 | ${axis.verdict.toUpperCase()}`,
    `断言：“${axis.assertion}”`,
    `根因：${cause}`,
  ].join("\n");
}

async function copyText(text: string) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }

  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "true");
  textarea.style.position = "fixed";
  textarea.style.opacity = "0";
  document.body.appendChild(textarea);
  textarea.select();
  const copied = document.execCommand("copy");
  textarea.remove();
  if (!copied) throw new Error("复制失败");
}

function RootCauseEditor({
  caseId,
  axis,
  options,
  context,
  onSave,
}: {
  caseId: string;
  axis: FaithfulnessAxisItem;
  options: RootCauseOption[];
  context?: AnnotationContext;
  onSave: SaveAnnotation;
}) {
  const [rootCauseMode, setRootCauseMode] = useState(
    initialRootCauseMode(options, axis.annotation?.root_cause),
  );
  const [customRootCause, setCustomRootCause] = useState(
    axis.annotation?.root_cause && !isPresetRootCause(options, axis.annotation.root_cause)
      ? axis.annotation.root_cause
      : "",
  );
  const [rootCauseNote, setRootCauseNote] = useState(axis.annotation?.root_cause_note ?? "");
  const [lastSaved, setLastSaved] = useState<L2RootCauseAnnotation | null>(axis.annotation ?? null);
  const [status, setStatus] = useState<"idle" | "saving" | "saved" | "copied" | "error">("idle");
  const [error, setError] = useState("");

  useEffect(() => {
    const nextAnnotation = axis.annotation ?? null;
    const nextRootCause = nextAnnotation?.root_cause ?? "";
    setRootCauseMode(initialRootCauseMode(options, nextRootCause));
    setCustomRootCause(
      nextRootCause && !isPresetRootCause(options, nextRootCause) ? nextRootCause : "",
    );
    setRootCauseNote(nextAnnotation?.root_cause_note ?? "");
    setLastSaved(nextAnnotation);
    setStatus("idle");
    setError("");
  }, [axis.issue_id, axis.annotation, options]);

  const rootCause = rootCauseMode === CUSTOM_ROOT_CAUSE_VALUE
    ? customRootCause.trim()
    : rootCauseMode;
  const selectedOption = options.find((option) => option.value === rootCauseMode);
  const summary = buildRootCauseSummary(caseId, axis, options, rootCause, rootCauseNote);

  const save = async () => {
    if (!rootCause) {
      setError("请选择根因");
      setStatus("error");
      return;
    }
    setStatus("saving");
    setError("");
    try {
      const saved = await onSave({
        case_id: caseId,
        issue_id: axis.issue_id,
        assertion: axis.assertion,
        verdict: "unsupported",
        root_cause: rootCause,
        root_cause_note: rootCauseNote,
        ...context,
      });
      setLastSaved(saved);
      setStatus("saved");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "保存失败");
      setStatus("error");
    }
  };

  const copySummary = async () => {
    try {
      await copyText(summary);
      setStatus("copied");
      setError("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "复制失败");
      setStatus("error");
    }
  };

  return (
    <div className="root-cause-editor">
      <div className="root-cause-header">
        <b>根因标注</b>
        {lastSaved && <span>已标注 · {lastSaved.updated_at}</span>}
      </div>
      <div className="root-cause-grid">
        <label>
          <span>root cause</span>
          <select value={rootCauseMode} onChange={(event) => setRootCauseMode(event.target.value)}>
            {options.map((option) => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
            <option value={CUSTOM_ROOT_CAUSE_VALUE}>手动输入...</option>
          </select>
          {rootCauseMode === CUSTOM_ROOT_CAUSE_VALUE && (
            <input
              value={customRootCause}
              placeholder="输入自定义根因，例如：prompt 约束缺失"
              onChange={(event) => setCustomRootCause(event.target.value)}
            />
          )}
        </label>
        <label>
          <span>note</span>
          <textarea
            value={rootCauseNote}
            rows={2}
            placeholder="可选：补一句具体原因，例如：Agent 把未发货订单的取消规则凭空补全。"
            onChange={(event) => setRootCauseNote(event.target.value)}
          />
        </label>
      </div>
      {selectedOption && <p className="root-cause-description">{selectedOption.description}</p>}
      {rootCauseMode === CUSTOM_ROOT_CAUSE_VALUE && <p className="root-cause-description">自定义根因会按输入内容原样保存，并进入摘要。</p>}
      <div className="summary-preview">
        <b>摘要预览</b>
        <pre>{summary}</pre>
      </div>
      <div className="root-cause-actions">
        <button className="primary-button" type="button" disabled={status === "saving"} onClick={() => void save()}>
          {status === "saving" ? "保存中..." : "保存根因"}
        </button>
        <button className="secondary-button" type="button" onClick={() => void copySummary()}>
          复制摘要
        </button>
        {status === "saved" && <span className="save-state ok">已保存</span>}
        {status === "copied" && <span className="save-state ok">已复制</span>}
        {status === "error" && <span className="save-state error">{error}</span>}
      </div>
    </div>
  );
}

function AnnotationRollup({ summaries }: { summaries: string[] }) {
  const [status, setStatus] = useState<"idle" | "copied" | "error">("idle");
  if (!summaries.length) return null;

  const text = summaries.join("\n\n");
  const copy = async () => {
    try {
      await copyText(text);
      setStatus("copied");
    } catch {
      setStatus("error");
    }
  };

  return (
    <details className="drawer-section root-cause-rollup" open>
      <summary><span>R</span>root cause 摘要 <small>{summaries.length} items</small></summary>
      <div className="details-content">
        <pre>{text}</pre>
        <div className="root-cause-actions">
          <button className="secondary-button" type="button" onClick={() => void copy()}>
            复制本 case 摘要
          </button>
          {status === "copied" && <span className="save-state ok">已复制</span>}
          {status === "error" && <span className="save-state error">复制失败</span>}
        </div>
      </div>
    </details>
  );
}

function L2ExperimentRuns({
  item,
  rootCauseOptions,
  onSaveAnnotation,
}: {
  item: L2Case;
  rootCauseOptions: RootCauseOption[];
  onSaveAnnotation: SaveAnnotation;
}) {
  return (
    <div className="experiment-run-list">
      {item.experiment_runs?.map((run, index) => (
        <details className={`drawer-section experiment-run ${run.passed ? "ok" : "bad"}`} key={run.run_index} open={!run.passed || index === 0}>
          <summary>
            <span>{run.run_index}</span>
            run_{run.run_index}
            <small>
              {run.passed ? "pass" : "fail"} · 命中 {run.score.hit_ok}/{run.score.hit_total} · 忠实 {run.score.faith_ok}/{run.score.faith_total}
            </small>
          </summary>
          <div className="details-content">
            <section className="five-part answer-part compact-answer">
              <span>Answer</span>
              <MarkdownContent content={run.answer || "—"} />
            </section>
            <div className="axis-list run-axis">
              <b>命中轴</b>
              {run.hit_axis.map((axis, axisIndex) => (
                <div className={`axis-item axis-${axis.verdict}`} key={`${axis.point}-${axisIndex}`}>
                  <VerdictBadge verdict={axis.verdict} />
                  <div>
                    <p>{axis.point}</p>
                    {axis.evidence != null && (
                      <>
                        <small>evidence</small>
                        <pre>{showJson(axis.evidence)}</pre>
                      </>
                    )}
                  </div>
                </div>
              ))}
              {!run.hit_axis.length && <div className="empty-inline">没有命中轴裁决</div>}
            </div>
            <div className="axis-list run-axis">
              <b>忠实轴</b>
              {run.faithfulness_axis.map((axis, axisIndex) => (
                <div className={`axis-item axis-${axis.verdict}`} key={axis.issue_id || `${axis.assertion}-${axisIndex}`}>
                  <VerdictBadge verdict={axis.verdict} />
                  <div>
                    <p>{axis.assertion}</p>
                    <small>evidence</small>
                    <pre>{showJson(axis.evidence)}</pre>
                    {axis.verdict === "unsupported" && (
                      <RootCauseEditor
                        caseId={item.case_id}
                        axis={axis}
                        options={rootCauseOptions}
                        context={{ run_index: run.run_index }}
                        onSave={onSaveAnnotation}
                      />
                    )}
                  </div>
                </div>
              ))}
              {!run.faithfulness_axis.length && <div className="empty-inline">没有忠实轴裁决</div>}
            </div>
            <details className="drawer-section nested-section">
              <summary><span>T</span>tool_outputs <small>{run.tool_outputs.length} items</small></summary>
              <div className="details-content raw-list">
                {run.tool_outputs.map((output, outputIndex) => <pre key={outputIndex}>{showJson(output)}</pre>)}
              </div>
            </details>
          </div>
        </details>
      ))}
    </div>
  );
}

function L2Drawer({
  item,
  rootCauseOptions,
  annotationContext,
  onSaveAnnotation,
  onClose,
}: {
  item: L2Case | null;
  rootCauseOptions: RootCauseOption[];
  annotationContext?: Omit<AnnotationContext, "run_index">;
  onSaveAnnotation: SaveAnnotation;
  onClose: () => void;
}) {
  const summaries = item?.experiment_runs?.flatMap((run) =>
    run.faithfulness_axis.flatMap((axis) => axis.annotation?.summary ? [axis.annotation.summary] : []),
  ) ?? item?.faithfulness_axis.flatMap((axis) =>
    axis.annotation?.summary ? [axis.annotation.summary] : [],
  ) ?? [];
  const isExperiment = Boolean(item?.experiment_runs?.length);

  return (
    <CaseDrawer
      open={Boolean(item)}
      title={item ? `${item.case_id} · ${item.bucket}` : ""}
      subtitle={item && (
        <div className="score-summary">
          <span>命中 <b>{item.score.hit_ok}/{item.score.hit_total}</b></span>
          <span>忠实 <b>{item.score.faith_ok}/{item.score.faith_total}</b></span>
          {(item.annotation_count ?? 0) > 0 && <span>根因 <b>{item.annotation_count}</b></span>}
        </div>
      )}
      width="wide"
      onClose={onClose}
    >
      {item && (
        <div className="l2-detail">
          <section className="five-part"><span>Question</span><p>{item.question}</p></section>
          {!isExperiment && <section className="five-part answer-part"><span>Answer</span><MarkdownContent content={item.answer || "—"} /></section>}
          {isExperiment && (
            <>
              <section className="five-part experiment-summary">
                <span>Experiment summary</span>
                <p>pass {percent(item.pass_rate ?? null)} · n={item.n ?? item.experiment_runs?.length ?? 0} · 命中 {percent(item.hit_rate ?? item.score.hit_rate)} · 忠实 {percent(item.faithfulness_rate ?? item.score.faithfulness_rate)}</p>
              </section>
              <L2ExperimentRuns
                item={item}
                rootCauseOptions={rootCauseOptions}
                onSaveAnnotation={async (payload) => onSaveAnnotation({ ...payload, ...(annotationContext ?? {}) })}
              />
            </>
          )}
          {!isExperiment && (
            <>
          <details className="drawer-section axis-section" open>
            <summary><span>H</span>命中轴 · golden point <small>{item.score.hit_ok} / {item.score.hit_total}</small></summary>
            <div className="details-content axis-list">
              {item.hit_axis.map((axis, index) => (
                <div className={`axis-item axis-${axis.verdict}`} key={`${axis.point}-${index}`}>
                  <VerdictBadge verdict={axis.verdict} />
                  <div>
                    <p>{axis.point}</p>
                    {axis.evidence != null && (
                      <>
                        <small>evidence</small>
                        <pre>{showJson(axis.evidence)}</pre>
                      </>
                    )}
                  </div>
                </div>
              ))}
              {!item.hit_axis.length && <div className="empty-inline">没有命中轴裁决</div>}
            </div>
          </details>
          <details className="drawer-section axis-section" open>
            <summary><span>F</span>忠实轴 · answer vs tool output <small>{item.score.faith_ok} / {item.score.faith_total}</small></summary>
            <div className="details-content axis-list">
              {item.faithfulness_axis.map((axis, index) => (
                <div className={`axis-item axis-${axis.verdict}`} key={axis.issue_id || `${axis.assertion}-${index}`}>
                  <VerdictBadge verdict={axis.verdict} />
                  <div>
                    <p>{axis.assertion}</p>
                    <small>evidence</small>
                    <pre>{showJson(axis.evidence)}</pre>
                    {axis.verdict === "unsupported" && (
                      <RootCauseEditor
                        caseId={item.case_id}
                        axis={axis}
                        options={rootCauseOptions}
                        context={annotationContext}
                        onSave={onSaveAnnotation}
                      />
                    )}
                  </div>
                </div>
              ))}
              {!item.faithfulness_axis.length && <div className="empty-inline">没有忠实轴裁决</div>}
            </div>
          </details>
          <AnnotationRollup summaries={summaries} />
          <details className="drawer-section">
            <summary><span>T</span>tool_outputs <small>{item.tool_outputs.length} items</small></summary>
            <div className="details-content raw-list">
              {item.tool_outputs.map((output, index) => <pre key={index}>{showJson(output)}</pre>)}
            </div>
          </details>
          <details className="drawer-section">
            <summary><span>G</span>golden_points <small>{item.golden_points.length} items</small></summary>
            <div className="details-content numbered-list">
              {item.golden_points.map((point, index) => (
                <div key={index}><b>{String(index + 1).padStart(2, "0")}</b><p>{showJson(point)}</p></div>
              ))}
            </div>
          </details>
            </>
          )}
          {isExperiment && <AnnotationRollup summaries={summaries} />}
        </div>
      )}
    </CaseDrawer>
  );
}

export default function QualityL2({ query }: QualityProps) {
  const [showAll, setShowAll] = useState(false);
  const [filters, setFilters] = useState<Set<Issue>>(new Set());
  const [selectedCaseId, setSelectedCaseId] = useState<string | null>(null);

  const list = useMemo(() => {
    if (!query.data) return [];
    const source = showAll ? query.data.cases : query.data.issue_cases;
    if (!filters.size) return source;
    return source.filter((item) => [...filters].some((filter) => item.issue_types.includes(filter)));
  }, [query.data, showAll, filters]);

  const selected = useMemo(() => {
    if (!query.data || !selectedCaseId) return null;
    return query.data.cases.find((item) => item.case_id === selectedCaseId) ?? null;
  }, [query.data, selectedCaseId]);

  const toggleFilter = (filter: Issue) => setFilters((current) => {
    const next = new Set(current);
    if (next.has(filter)) next.delete(filter);
    else next.add(filter);
    return next;
  });

  if (query.loading) return <div className="skeleton-page"><div className="skeleton compact-skeleton" /><div className="skeleton table-skeleton" /><div className="skeleton table-skeleton" /></div>;
  if (query.error && !query.data) return <div className="error-state"><h2>接口拉取失败</h2><p>{query.error}</p><button type="button" onClick={() => void query.refetch()}>重试</button></div>;
  if (!query.data) return null;

  const { data } = query;
  const isExperiment = data.context?.mode === "experiment";
  const rootCauseOptions = data.annotations?.root_cause_options?.length
    ? data.annotations.root_cause_options
    : FALLBACK_ROOT_CAUSE_OPTIONS;
  const annotationContext = isExperiment
    ? { exp_id: data.context?.exp_id, variant: data.context?.variant }
    : undefined;

  const saveAnnotation: SaveAnnotation = async (payload) => {
    const annotation = await saveL2RootCauseAnnotation(payload);
    void query.refetch();
    return annotation;
  };

  return (
    <div className="page-stack">
      {query.error && <div className="error-banner"><span>刷新失败：{query.error}</span><button type="button" onClick={() => void query.refetch()}>重试</button></div>}
      {data.context?.warnings?.map((warning) => <div className="source-warning" key={warning}>{warning}</div>)}
      <section className="compact-metrics three">
        <MetricCard compact label="L2 命中率" value={percent(data.metrics.hit_rate)} note={`${data.metrics.hit_ok} / ${data.metrics.hit_total} golden points`} />
        <MetricCard compact label="L2 忠实率" value={percent(data.metrics.faithfulness_rate)} note={`${data.metrics.faith_ok} / ${data.metrics.faith_total} assertions`} />
        <MetricCard compact label="Case 通过率" value={percent(data.metrics.case_pass_rate)} note={`${count(data.metrics.passed_case_count)} / ${data.metrics.case_count} cases`} />
      </section>
      <section className="panel">
        <div className="panel-heading">
          <div><span className="section-kicker">Breakdown 01</span><h2>按 bucket 拆解</h2></div>
          <p>事实桶 · 命中与忠实双轴</p>
        </div>
        <BucketTable kind="l2" rows={data.breakdowns.by_bucket} />
      </section>
      <section className="panel">
        <div className="panel-heading case-heading">
          <div><span className="section-kicker">Quality trace</span><h2>问题 case</h2></div>
          <div className="filter-controls">
            <div className="segmented">
              <button type="button" className={!showAll ? "active" : ""} onClick={() => setShowAll(false)}>问题 <b>{data.issue_cases.length}</b></button>
              <button type="button" className={showAll ? "active" : ""} onClick={() => setShowAll(true)}>全部 <b>{data.cases.length}</b></button>
            </div>
            <div className="chips">
              <button type="button" className={!filters.size ? "active" : ""} onClick={() => setFilters(new Set())}>全部 issue</button>
              <button type="button" className={filters.has("miss") ? "active danger" : ""} onClick={() => toggleFilter("miss")}>miss</button>
              <button type="button" className={filters.has("unsupported") ? "active danger" : ""} onClick={() => toggleFilter("unsupported")}>unsupported</button>
            </div>
          </div>
        </div>
        <div className="table-scroll case-table">
          <table>
            <thead><tr><th>case</th><th>bucket</th><th className="question-column">问题</th><th>命中</th><th>忠实</th><th>issue</th><th /></tr></thead>
            <tbody>
              {list.map((item) => (
                <tr className="clickable-row" key={item.case_id} onClick={() => setSelectedCaseId(item.case_id)}>
                  <td><b className="case-id">{item.case_id}</b></td>
                  <td><span className="bucket-name">{item.bucket}</span></td>
                  <td className="truncate-cell" title={item.question}>{item.question}</td>
                  <td className={item.has_hit_issue ? "text-danger" : "text-success"}>{isExperiment ? percent(item.hit_rate ?? item.score.hit_rate) : `${item.score.hit_ok}/${item.score.hit_total}`}</td>
                  <td className={item.has_faith_issue ? "text-danger" : "text-success"}>{isExperiment ? percent(item.faithfulness_rate ?? item.score.faithfulness_rate) : `${item.score.faith_ok}/${item.score.faith_total}`}</td>
                  <td>
                    <div className="badge-row">
                      {isExperiment && <span className={item.pass_rate === 1 ? "rate-pill good" : "rate-pill bad"}>pass {percent(item.pass_rate ?? null)}</span>}
                      {item.issue_types.map((issue) => <VerdictBadge key={issue} verdict={issue} />)}
                      {(item.annotation_count ?? 0) > 0 && <span className="annotation-pill">root cause {item.annotation_count}</span>}
                      {!item.issue_types.length && <span className="muted">—</span>}
                    </div>
                  </td>
                  <td className="row-arrow">›</td>
                </tr>
              ))}
            </tbody>
          </table>
          {!list.length && <div className="empty-state"><span>✓</span><b>当前筛选下没有问题 case</b><p>可切换“全部”检查已通过的回复。</p></div>}
        </div>
      </section>
      <L2Drawer
        item={selected}
        rootCauseOptions={rootCauseOptions}
        annotationContext={annotationContext}
        onSaveAnnotation={saveAnnotation}
        onClose={() => setSelectedCaseId(null)}
      />
    </div>
  );
}
