import { useMemo, useState } from "react";

import type {
  FixtureAnchor,
  FixtureAnchorRun,
  FixtureCase,
  FixtureIssueType,
  JsonValue,
  L2FixturesDashboardData,
} from "../api";
import CaseDrawer from "../components/CaseDrawer";
import MarkdownContent from "../components/MarkdownContent";
import MetricCard from "../components/MetricCard";

interface JudgeFixturesProps {
  query: {
    data: L2FixturesDashboardData | null;
    loading: boolean;
    error: string | null;
    refetch: () => Promise<void>;
  };
  experimentsLoading: boolean;
}

const percent = (value: number | null | undefined) =>
  value == null ? "—" : `${(value * 100).toFixed(value === 0 || value === 1 ? 0 : 2)}%`;

const showJson = (value: JsonValue) =>
  typeof value === "string" ? value : JSON.stringify(value, null, 2);

const issueLabel: Record<FixtureIssueType, string> = {
  false_positive: "false positive",
  false_negative: "false negative",
};

function IssuePill({ issue }: { issue: FixtureIssueType }) {
  return <span className={`fixture-issue ${issue}`}>{issueLabel[issue]}</span>;
}

function RunVerdict({ run }: { run: FixtureAnchorRun }) {
  const label = run.run_verdict === "not_extracted" ? "not extracted" : run.run_verdict;
  return <span className={`fixture-run-verdict ${run.run_verdict}`}>{label}</span>;
}

function AnchorDetail({ anchor }: { anchor: FixtureAnchor }) {
  return (
    <details className={`fixture-anchor ${anchor.flag}`} open={!anchor.ok_run_rate || anchor.ok_run_rate < 1}>
      <summary>
        <div>
          <b>{anchor.anchor_id}</b>
          <span className={`fixture-expect ${anchor.expect}`}>expect {anchor.expect}</span>
          {anchor.flag !== "pass" && <IssuePill issue={anchor.flag} />}
        </div>
        <strong>pass {percent(anchor.ok_run_rate)}</strong>
      </summary>
      <div className="fixture-anchor-body">
        <dl className="fixture-definition">
          <dt>match</dt><dd><code>{anchor.match}</code></dd>
          <dt>note</dt><dd>{anchor.note || "—"}</dd>
          <dt>N 跑</dt>
          <dd>
            unsupported {anchor.unsupported_runs} · supported {anchor.supported_runs} · not extracted {anchor.not_extracted_runs}
          </dd>
        </dl>
        <div className="fixture-run-list">
          {anchor.runs.map((run) => (
            <details className={`fixture-run ${run.ok ? "ok" : "bad"}`} key={run.run_index}>
              <summary>
                <b>Run #{run.run_index}</b>
                <RunVerdict run={run} />
                <span>{run.ok ? "✓ pass" : "✗ fail"}</span>
              </summary>
              <div className="fixture-matches">
                {run.matched.map((matched, index) => (
                  <div className={`fixture-match ${matched.verdict}`} key={`${matched.assertion}-${index}`}>
                    <span>{matched.verdict}</span>
                    <div>
                      <p>{matched.assertion}</p>
                      <small>evidence</small>
                      <pre>{showJson(matched.evidence)}</pre>
                    </div>
                  </div>
                ))}
                {!run.matched.length && <div className="empty-inline">该 run 未抽取到匹配断言</div>}
              </div>
            </details>
          ))}
        </div>
      </div>
    </details>
  );
}

function FixtureDrawer({ item, onClose }: { item: FixtureCase | null; onClose: () => void }) {
  return (
    <CaseDrawer
      open={Boolean(item)}
      width="wide"
      title={item ? `${item.case_id} · ${item.bucket}` : ""}
      subtitle={item && (
        <div className="badge-row">
          <span>n={item.n}</span>
          <span>anchor pass {percent(item.anchor_pass_rate)}</span>
          {item.issue_types.map((issue) => <IssuePill issue={issue} key={issue} />)}
        </div>
      )}
      onClose={onClose}
    >
      {item && (
        <>
          <section className="drawer-question">
            <span>Fixture question</span>
            <p>{item.input.question}</p>
          </section>
          <section className="five-part answer-part">
            <span>Frozen answer</span>
            <MarkdownContent content={item.input.answer} />
          </section>
          <details className="drawer-section" open>
            <summary><span>01</span>锚点判定 <small>{item.anchor_count} anchors</small></summary>
            <div className="details-content fixture-anchor-list">
              {item.anchors.map((anchor) => <AnchorDetail anchor={anchor} key={anchor.anchor_id} />)}
            </div>
          </details>
          <details className="drawer-section">
            <summary><span>02</span>完整 Judge 输出 <small>{item.experiment_runs.length} runs</small></summary>
            <div className="details-content fixture-full-runs">
              {item.experiment_runs.map((run) => (
                <details className="nested-section" key={run.run_index}>
                  <summary>Run #{run.run_index}</summary>
                  <div className="details-content">
                    <b className="fixture-axis-label">命中轴</b>
                    {run.hit_axis.map((axis, index) => (
                      <div className={`fixture-match ${axis.verdict}`} key={`hit-${index}`}>
                        <span>{axis.verdict}</span><div><p>{axis.point}</p><pre>{showJson(axis.evidence ?? "")}</pre></div>
                      </div>
                    ))}
                    <b className="fixture-axis-label">忠实轴</b>
                    {run.faithfulness_axis.map((axis, index) => (
                      <div className={`fixture-match ${axis.verdict}`} key={`faith-${index}`}>
                        <span>{axis.verdict}</span><div><p>{axis.assertion}</p><pre>{showJson(axis.evidence)}</pre></div>
                      </div>
                    ))}
                  </div>
                </details>
              ))}
            </div>
          </details>
          <details className="drawer-section">
            <summary><span>03</span>Fixture 上下文</summary>
            <div className="details-content">
              <b className="fixture-axis-label">Tool outputs</b>
              {item.input.tool_outputs.map((output, index) => <pre className="fixture-raw" key={index}>{showJson(output)}</pre>)}
              <b className="fixture-axis-label">Golden points</b>
              {item.input.golden_points.map((point, index) => <pre className="fixture-raw" key={index}>{showJson(point)}</pre>)}
            </div>
          </details>
        </>
      )}
    </CaseDrawer>
  );
}

export default function JudgeFixtures({ query, experimentsLoading }: JudgeFixturesProps) {
  const [showAll, setShowAll] = useState(false);
  const [filters, setFilters] = useState<Set<FixtureIssueType>>(new Set());
  const [selectedCaseId, setSelectedCaseId] = useState<string | null>(null);

  const list = useMemo(() => {
    if (!query.data) return [];
    const source = showAll ? query.data.cases : query.data.issue_cases;
    if (!filters.size) return source;
    return source.filter((item) => [...filters].some((filter) => item.issue_types.includes(filter)));
  }, [filters, query.data, showAll]);

  const selected = useMemo(
    () => query.data?.cases.find((item) => item.case_id === selectedCaseId) ?? null,
    [query.data, selectedCaseId],
  );

  const toggleFilter = (filter: FixtureIssueType) => setFilters((current) => {
    const next = new Set(current);
    if (next.has(filter)) next.delete(filter);
    else next.add(filter);
    return next;
  });

  if (experimentsLoading || query.loading) {
    return <div className="skeleton-page"><div className="skeleton compact-skeleton" /><div className="skeleton table-skeleton" /><div className="skeleton table-skeleton" /></div>;
  }
  if (query.error && !query.data) {
    return <div className="error-state"><h2>Judge 夹具接口拉取失败</h2><p>{query.error}</p><button type="button" onClick={() => void query.refetch()}>重试</button></div>;
  }
  if (!query.data) {
    return <div className="empty-state judge-empty"><span>∅</span><b>还没有 Judge 夹具实验</b><p>运行受限 case 的 l2_fixtures_judge 后即可在这里查看。</p></div>;
  }

  const { data } = query;
  return (
    <div className="page-stack judge-page">
      {query.error && <div className="error-banner"><span>刷新失败：{query.error}</span><button type="button" onClick={() => void query.refetch()}>重试</button></div>}
      {data.context.warnings?.map((warning) => <div className="source-warning" key={warning}>{warning}</div>)}

      <section className="compact-metrics fixture-metrics">
        <MetricCard compact label="红锚 Recall" value={percent(data.metrics.red_anchor_recall)} note={`${data.metrics.red_unsupported_runs} / ${data.metrics.red_runs} red runs`} />
        <MetricCard compact label="绿锚假阳率" value={percent(data.metrics.green_anchor_fp_rate)} note={`${data.metrics.green_unsupported_runs} / ${data.metrics.green_runs} green runs · 越低越好`} />
        <MetricCard compact label="Extract Rate" value={percent(data.metrics.extract_rate)} note={`${data.metrics.anchor_runs - data.metrics.not_extracted_runs} / ${data.metrics.anchor_runs} anchor runs`} />
        <MetricCard compact label="Anchor Pass" value={percent(data.metrics.anchor_pass_rate)} note={`${data.metrics.passed_anchor_count} / ${data.metrics.anchor_count} anchors`} />
      </section>

      <section className="panel">
        <div className="panel-heading">
          <div><span className="section-kicker">Breakdown 01</span><h2>按 bucket 拆解</h2></div>
          <p>{data.metrics.case_count} cases · n={data.metrics.n ?? data.context.n ?? "—"}</p>
        </div>
        <div className="table-scroll fixture-table">
          <table>
            <thead><tr><th>bucket</th><th>case</th><th>anchor</th><th>红锚 recall</th><th>绿锚 FP</th><th>extract</th><th>anchor pass</th></tr></thead>
            <tbody>{data.breakdowns.by_bucket.map((row) => (
              <tr key={row.bucket}>
                <td><span className="bucket-name">{row.bucket}</span></td><td>{row.case_count}</td><td>{row.anchor_count}</td>
                <td>{percent(row.red_anchor_recall)}</td><td>{percent(row.green_anchor_fp_rate)}</td><td>{percent(row.extract_rate)}</td><td>{percent(row.anchor_pass_rate)}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      </section>

      <section className="panel">
        <div className="panel-heading">
          <div><span className="section-kicker">Breakdown 02</span><h2>按锚点预期拆解</h2></div>
          <p>红锚期待 unsupported · 绿锚期待 supported</p>
        </div>
        <div className="table-scroll fixture-table">
          <table>
            <thead><tr><th>expect</th><th>anchor</th><th>anchor pass</th><th>unsupported</th><th>not extracted</th><th>extract rate</th></tr></thead>
            <tbody>{data.breakdowns.by_expect.map((row) => (
              <tr key={row.expect}>
                <td><span className={`fixture-expect ${row.expect}`}>{row.expect === "unsupported" ? "红锚 · unsupported" : "绿锚 · supported"}</span></td>
                <td>{row.anchor_count}</td><td>{percent(row.anchor_pass_rate)}</td><td>{percent(row.unsupported_run_rate)}</td><td>{row.not_extracted_runs} / {row.anchor_runs}</td><td>{percent(row.extract_rate)}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      </section>

      <section className="panel">
        <div className="panel-heading case-heading">
          <div><span className="section-kicker">Judge trace</span><h2>Fixture cases</h2></div>
          <div className="filter-controls">
            <div className="segmented">
              <button type="button" className={!showAll ? "active" : ""} onClick={() => setShowAll(false)}>问题 <b>{data.issue_cases.length}</b></button>
              <button type="button" className={showAll ? "active" : ""} onClick={() => setShowAll(true)}>全部 <b>{data.cases.length}</b></button>
            </div>
            <div className="chips">
              <button type="button" className={!filters.size ? "active" : ""} onClick={() => setFilters(new Set())}>全部 issue</button>
              <button type="button" className={filters.has("false_positive") ? "active danger" : ""} onClick={() => toggleFilter("false_positive")}>false positive</button>
              <button type="button" className={filters.has("false_negative") ? "active danger" : ""} onClick={() => toggleFilter("false_negative")}>false negative</button>
            </div>
          </div>
        </div>
        <div className="table-scroll case-table fixture-case-table">
          <table>
            <thead><tr><th>case</th><th>bucket</th><th className="question-column">问题</th><th>anchors</th><th>pass</th><th>issue</th><th /></tr></thead>
            <tbody>{list.map((item) => (
              <tr className="clickable-row" key={item.case_id} onClick={() => setSelectedCaseId(item.case_id)}>
                <td><b className="case-id">{item.case_id}</b></td><td><span className="bucket-name">{item.bucket}</span></td>
                <td className="truncate-cell" title={item.input.question}>{item.input.question}</td><td>{item.passed_anchor_count}/{item.anchor_count}</td>
                <td className={item.anchor_pass_rate === 1 ? "text-success" : "text-danger"}>{percent(item.anchor_pass_rate)}</td>
                <td><div className="badge-row">{item.issue_types.map((issue) => <IssuePill issue={issue} key={issue} />)}{!item.issue_types.length && <span className="muted">—</span>}</div></td>
                <td className="row-arrow">›</td>
              </tr>
            ))}</tbody>
          </table>
          {!list.length && <div className="empty-state"><span>✓</span><b>当前筛选下没有问题 case</b></div>}
        </div>
      </section>

      <FixtureDrawer item={selected} onClose={() => setSelectedCaseId(null)} />
    </div>
  );
}
