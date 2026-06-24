import { useMemo, useState } from "react";

import type { EvalDashboardData, JsonValue, RoutingCase } from "../api";
import BucketTable from "../components/BucketTable";
import CaseDrawer from "../components/CaseDrawer";
import MarkdownContent from "../components/MarkdownContent";
import MetricCard from "../components/MetricCard";
import VerdictBadge from "../components/VerdictBadge";

interface RoutingProps {
  query: {
    data: EvalDashboardData | null;
    loading: boolean;
    error: string | null;
    refetch: () => Promise<void>;
  };
}

const percent = (value: number) => `${(value * 100).toFixed(value === 0 || value === 1 ? 0 : 2)}%`;
const showJson = (value: JsonValue | Record<string, JsonValue> | undefined) => value == null ? "—" : typeof value === "string" ? value : JSON.stringify(value, null, 2);
const tools = (values: string[]) => values.length ? values.join(" + ") : "—";

function L1Drawer({ item, onClose }: { item: RoutingCase | null; onClose: () => void }) {
  const maxDuration = item ? Math.max(...item.audits.map((audit) => Number(audit.tool_duration_ms) || 0), 1) : 1;
  return <CaseDrawer open={Boolean(item)} title={item ? `${item.case_id} · ${item.bucket}` : ""} subtitle={item && <div className="badge-row">{item.route_error && <VerdictBadge verdict="route_error" />}{item.is_misfire && <VerdictBadge verdict="misfire" />}{item.not_run && <VerdictBadge verdict="not_run" />}</div>} onClose={onClose}>
    {item && <>
      <section className="drawer-question"><span>评估问题</span><p>{item.question}</p><div className="badge-row">{item.missing_tools.map((tool) => <span className="tool-badge missing" key={`missing-${tool}`}>missing · {tool}</span>)}{item.unexpected_tools.map((tool) => <span className="tool-badge unexpected" key={`unexpected-${tool}`}>unexpected · {tool}</span>)}</div></section>
      <details className="drawer-section" open><summary><span>01</span>评估期望 <small>{item.expected_calls.length} calls</small></summary><div className="details-content">
        <div className="definition-grid"><span>should_call_tool</span><b>{String(item.should_call_tool)}</b><span>trap</span><p>{item.trap || "—"}</p></div>
        {item.expected_calls.length ? item.expected_calls.map((call, index) => <div className="audit-card" key={`${call.tool_name}-${index}`}><div className="audit-head"><b>{call.tool_name}</b><span>expected</span></div><pre>{showJson(call.tool_params)}</pre></div>) : <div className="empty-inline">期望不调用工具</div>}
      </div></details>
      <details className="drawer-section" open><summary><span>02</span>工具审计 <small>{item.audit_count} records · {item.tool_duration_ms}ms</small></summary><div className="details-content">
        {item.audits.length ? <>{item.audits.map((audit, index) => <div className="audit-card" key={`${audit.session_id}-${index}`}><div className="audit-head"><b>{audit.tool_name}</b><span className={audit.tool_error ? "text-danger" : "text-success"}>{Number(audit.tool_duration_ms || 0).toFixed(2)}ms · {audit.tool_error ? "error" : "ok"}</span></div><label>params</label><pre>{showJson(audit.tool_params)}</pre>{audit.tool_output != null && <><label>output</label><pre>{showJson(audit.tool_output)}</pre></>}{audit.tool_error != null && <><label>error</label><pre className="pre-error">{showJson(audit.tool_error)}</pre></>}</div>)}<div className="duration-profile"><p>耗时画像</p>{item.audits.map((audit, index) => <div className="duration-row" key={`duration-${index}`}><span>{audit.tool_name}</span><i><b style={{ width: `${Math.max((Number(audit.tool_duration_ms || 0) / maxDuration) * 100, 1)}%` }} /></i><em>{Number(audit.tool_duration_ms || 0).toFixed(2)}ms</em></div>)}</div></> : <div className="empty-inline">没有工具审计记录</div>}
      </div></details>
      <details className="drawer-section" open><summary><span>03</span>会话消息 <small>{item.session_ids.length} sessions</small></summary><div className="details-content session-groups">
        {Object.entries(item.messages_by_session).map(([sessionId, messages]) => <div className="session-group" key={sessionId}><div className="session-id">session · {sessionId}</div>{messages.map((message, index) => <div className={`trace-message trace-${message.role}`} key={`${message.role}-${index}`}><b>{message.role}</b>{message.role === "assistant" && typeof message.content === "string" ? <MarkdownContent content={message.content} /> : <pre>{showJson(message.content)}</pre>}</div>)}</div>)}
        {!Object.keys(item.messages_by_session).length && <div className="empty-inline">没有会话消息</div>}
      </div></details>
    </>}
  </CaseDrawer>;
}

export default function RoutingL1({ query }: RoutingProps) {
  const [showAll, setShowAll] = useState(false);
  const [selected, setSelected] = useState<RoutingCase | null>(null);
  const failures = useMemo(() => {
    if (!query.data) return [];
    const merged = [...query.data.route_error_cases, ...query.data.misfire_cases];
    return merged.filter((item, index) => merged.findIndex((candidate) => candidate.case_id === item.case_id) === index);
  }, [query.data]);

  if (query.loading) return <div className="skeleton-page"><div className="skeleton compact-skeleton" /><div className="skeleton table-skeleton" /><div className="skeleton table-skeleton" /></div>;
  if (query.error && !query.data) return <div className="error-state"><h2>接口拉取失败</h2><p>{query.error}</p><button type="button" onClick={() => void query.refetch()}>重试</button></div>;
  if (!query.data) return null;
  const { data } = query;
  const maxActual = Math.max(...data.breakdowns.actual_tool_calls.map((item) => item.call_count), 1);
  const list = showAll ? data.cases : failures;

  return <div className="page-stack">
    {query.error && <div className="error-banner"><span>刷新失败：{query.error}</span><button type="button" onClick={() => void query.refetch()}>重试</button></div>}
    <section className="compact-metrics"><MetricCard compact label="评估覆盖率" value={percent(data.metrics.coverage_rate)} note={`${data.metrics.evaluated_case_count} / ${data.metrics.case_count}`} /><MetricCard compact label="路由准确率" value={percent(data.metrics.routing_accuracy)} note={`${data.metrics.route_hit_count} / ${data.metrics.positive_case_count}`} /><MetricCard compact label="误触发率" value={percent(data.metrics.misfire_rate)} note={`${data.metrics.misfire_count} / ${data.metrics.evaluated_case_count}`} /><MetricCard compact label="失败 case" value={String(data.metrics.failure_case_count)} note="route error 或 misfire" /></section>
    <section className="panel"><div className="panel-heading"><div><span className="section-kicker">Breakdown 01</span><h2>按 bucket 拆解</h2></div><p>难度轴 × 路由裁决</p></div><BucketTable kind="l1" rows={data.breakdowns.by_bucket} totals={data.metrics} /></section>
    <section className="tool-grid">
      <article className="panel tool-panel"><div className="panel-heading"><div><span className="section-kicker">Breakdown 02</span><h2>期望工具命中</h2></div></div><div className="bar-list">{data.breakdowns.by_expected_tool.map((item) => <div className="bar-item" key={item.tool_name}><div><b>{item.tool_name}</b><span>{item.route_hit_count}/{item.positive_case_count} · {percent(item.routing_accuracy)}</span></div><i><b style={{ width: `${item.routing_accuracy * 100}%` }} /></i></div>)}</div></article>
      <article className="panel tool-panel"><div className="panel-heading"><div><span className="section-kicker">Breakdown 03</span><h2>实际调用分布</h2></div></div><div className="bar-list neutral-bars">{data.breakdowns.actual_tool_calls.map((item) => <div className="bar-item" key={item.tool_name}><div><b>{item.tool_name}</b><span>{item.call_count} calls</span></div><i><b style={{ width: `${(item.call_count / maxActual) * 100}%` }} /></i></div>)}</div></article>
    </section>
    <section className="panel"><div className="panel-heading case-heading"><div><span className="section-kicker">Trace</span><h2>Case 追溯</h2></div><div className="segmented"><button type="button" className={!showAll ? "active" : ""} onClick={() => setShowAll(false)}>仅失败 <b>{failures.length}</b></button><button type="button" className={showAll ? "active" : ""} onClick={() => setShowAll(true)}>全部 <b>{data.cases.length}</b></button></div></div>
      <div className="table-scroll case-table"><table><thead><tr><th>case</th><th>bucket</th><th className="question-column">问题</th><th>裁决</th><th>期望 → 实际</th><th /></tr></thead><tbody>{list.map((item) => <tr className="clickable-row" key={item.case_id} onClick={() => setSelected(item)}><td><b className="case-id">{item.case_id}</b></td><td><span className="bucket-name">{item.bucket}</span></td><td className="truncate-cell" title={item.question}>{item.question}</td><td><div className="badge-row">{item.route_error && <VerdictBadge verdict="route_error" />}{item.is_misfire && <VerdictBadge verdict="misfire" />}{item.not_run && <VerdictBadge verdict="not_run" />}{item.is_hit && !item.is_misfire && <VerdictBadge verdict="hit" />}</div></td><td className="tool-route"><span>{tools(item.expected_tools)}</span><em>→</em><span>{tools(item.called_tools)}</span></td><td className="row-arrow">›</td></tr>)}</tbody></table>{!list.length && <div className="empty-state"><span>✓</span><b>当前筛选下没有失败 case</b><p>切换“全部”可浏览完整评估集。</p></div>}</div>
    </section>
    <L1Drawer item={selected} onClose={() => setSelected(null)} />
  </div>;
}
