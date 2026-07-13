import { useCallback, useEffect, useMemo, useState } from "react";

import {
  fetchCompare,
  fetchExperiments,
  type CaseDiffRow,
  type CompareData,
  type ExperimentManifest,
  type FlipStatus,
  type JsonValue,
  type MetricDelta,
} from "../api";
import CaseDrawer from "../components/CaseDrawer";

const LAYERS = ["L1", "L2", "RAG"] as const;
type Layer = (typeof LAYERS)[number];

// 越低越好的指标：误触发率 delta 为正反而是退步
const LOWER_BETTER = new Set(["misfire_rate"]);

const pct = (v: number | null | undefined) =>
  v == null ? "—" : `${(v * 100).toFixed(v === 0 || v === 1 ? 0 : 2)}%`;
const signed = (v: number | null | undefined) =>
  v == null ? "—" : `${v >= 0 ? "+" : ""}${(v * 100).toFixed(2)}%`;
const showJson = (v: JsonValue | undefined) =>
  v == null ? "—" : typeof v === "string" ? v : JSON.stringify(v, null, 2);

function deltaTone(metric: string, delta: number | null): string {
  if (delta == null || delta === 0) return "tone-flat";
  const better = LOWER_BETTER.has(metric) ? delta < 0 : delta > 0;
  return better ? "tone-up" : "tone-down";
}

function DeltaCard({ metric, d }: { metric: string; d: MetricDelta }) {
  return (
    <article className={`metric-card ab-delta-card ${deltaTone(metric, d.delta)}`}>
      <span className="metric-label">{metric}</span>
      <div className="ab-delta-row">
        <span className="ab-ab">{pct(d.a)}</span>
        <em>→</em>
        <span className="ab-ab">{pct(d.b)}</span>
      </div>
      <strong className="ab-delta-value">{signed(d.delta)}</strong>
    </article>
  );
}

function StatusPill({ status }: { status?: FlipStatus }) {
  if (!status || status === "na") return <span className="ab-pill flat">—</span>;
  const txt = status === "improved" ? "▲ 变好" : status === "regressed" ? "▼ 变差" : "持平";
  return <span className={`ab-pill ${status}`}>{txt}</span>;
}

// agent 轨：单变体 L1+L2 明细（按 N 次 run 展开）
interface L1Run { called_tools?: string[]; is_hit?: boolean | null; is_misfire?: boolean }
interface L2Run {
  answer?: JsonValue;
  passed?: boolean;
  score?: Record<string, number>;
  verdict?: { hit_axis?: Array<Record<string, JsonValue>>; faithfulness_axis?: Array<Record<string, JsonValue>> };
}
interface VariantSide {
  l1?: { n?: number; pass_rate?: number; spec_tool?: string[] | null; runs?: L1Run[] } | null;
  l2?: { n?: number; pass_rate?: number; runs?: L2Run[] } | null;
}

function VariantDetail({ side }: { side: VariantSide | null }) {
  const l1 = side?.l1 ?? null;
  const l2 = side?.l2 ?? null;
  return (
    <div className="ab-variant-col">
      {l1 ? (
        <div className="ab-block">
          <label>L1 路由 · 通过率 {pct(l1.pass_rate)}（n={l1.n}）· 期望 {l1.spec_tool?.join(" + ") || "—"}</label>
          <div className="ab-runs">
            {(l1.runs ?? []).map((run, i) => {
              const ok = Boolean(run.is_hit) && !run.is_misfire;
              return (
                <div className={`ab-run ${ok ? "ok" : "bad"}`} key={i}>
                  <span>#{i + 1}</span>
                  <b>{(run.called_tools ?? []).join(" + ") || "—"}</b>
                  {run.is_misfire && <em className="bad-tag">misfire</em>}
                  {run.is_hit === false && <em className="bad-tag">miss</em>}
                </div>
              );
            })}
          </div>
        </div>
      ) : (
        <div className="ab-block empty-inline">无 L1 记录</div>
      )}
      {l2 ? (
        <div className="ab-block">
          <label>L2 回答 · 通过率 {pct(l2.pass_rate)}（n={l2.n}）</label>
          {(l2.runs ?? []).map((run, i) => {
            const v = run.verdict ?? {};
            return (
              <details className="ab-run-l2" key={i} open={i === 0}>
                <summary>
                  <span>#{i + 1}</span> {run.passed ? "✓ pass" : "✗ fail"} · 命中 {run.score?.hit_ok}/{run.score?.hit_total} · 忠实 {run.score?.faith_ok}/{run.score?.faith_total}
                </summary>
                <pre className="ab-answer">{showJson(run.answer)}</pre>
                <div className="ab-axis">
                  {(v.hit_axis ?? []).map((h, j) => (
                    <div className={`ab-axis-row ${h.verdict === "hit" ? "ok" : "bad"}`} key={`h-${j}`}>
                      <span>{h.verdict === "hit" ? "✓" : "✗"} 命中</span><p>{String(h.point)}</p>
                    </div>
                  ))}
                  {(v.faithfulness_axis ?? []).map((a, j) => (
                    <div className={`ab-axis-row ${a.verdict === "supported" ? "ok" : "bad"}`} key={`f-${j}`}>
                      <span>{a.verdict === "supported" ? "✓" : "✗"} 忠实</span><p>{String(a.assertion)}</p>
                    </div>
                  ))}
                </div>
              </details>
            );
          })}
        </div>
      ) : (
        <div className="ab-block empty-inline">无 L2 记录（非事实桶或 judge 失败）</div>
      )}
    </div>
  );
}

export default function ABCompare() {
  const [experiments, setExperiments] = useState<ExperimentManifest[]>([]);
  const [expId, setExpId] = useState<string>("");
  const [variantA, setVariantA] = useState<string>("");
  const [variantB, setVariantB] = useState<string>("");
  const [data, setData] = useState<CompareData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [layerFilter, setLayerFilter] = useState<Layer | "ALL">("ALL");
  const [selected, setSelected] = useState<CaseDiffRow | null>(null);

  const manifest = useMemo(
    () => experiments.find((e) => e.exp_id === expId) ?? null,
    [experiments, expId],
  );

  useEffect(() => {
    fetchExperiments()
      .then((list) => {
        const comparable = list.filter((item) => item.track === "agent" || item.track === "retrieval");
        setExperiments(comparable);
        if (comparable.length) {
          setExpId(comparable[0].exp_id);
          const vs = comparable[0].variants;
          setVariantA(vs[0]?.name ?? "");
          setVariantB(vs[1]?.name ?? "");
        }
        setLoading(false);
      })
      .catch((e) => {
        setError(e instanceof Error ? e.message : "拉取实验列表失败");
        setLoading(false);
      });
  }, []);

  // 切实验：重置变体为该实验的前两个
  const onPickExp = useCallback(
    (id: string) => {
      setExpId(id);
      const m = experiments.find((e) => e.exp_id === id);
      if (m) {
        setVariantA(m.variants[0]?.name ?? "");
        setVariantB(m.variants[1]?.name ?? "");
      }
    },
    [experiments],
  );

  useEffect(() => {
    if (!expId || !variantA || !variantB || variantA === variantB) return;
    setError(null);
    fetchCompare(expId, variantA, variantB)
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : "拉取对比失败"));
  }, [expId, variantA, variantB]);

  if (loading) return <div className="skeleton-page"><div className="skeleton compact-skeleton" /><div className="skeleton table-skeleton" /></div>;
  if (!experiments.length)
    return (
      <div className="empty-state">
        <span>∅</span>
        <b>还没有实验</b>
        <p>先跑：<code>uv run python -m src.experiment</code></p>
      </div>
    );

  const layersInData = data ? LAYERS.filter((l) => l in data.headline_delta) : [];
  const visibleLayers: Layer[] = layerFilter === "ALL" ? layersInData : [layerFilter];
  const rows = (data?.case_diff ?? []).filter((r) =>
    visibleLayers.some((l) => r[l]),
  );

  return (
    <div className="page-stack">
      {error && <div className="error-banner"><span>{error}</span></div>}

      <section className="panel">
        <div className="panel-heading">
          <div>
            <span className="section-kicker">Experiment</span>
            <h2>A/B 对比</h2>
          </div>
          <div className="ab-controls">
            <label>实验
              <select value={expId} onChange={(e) => onPickExp(e.target.value)}>
                {experiments.map((e) => (
                  <option key={e.exp_id} value={e.exp_id}>{e.exp_id}（{e.track}）</option>
                ))}
              </select>
            </label>
            <label>A
              <select value={variantA} onChange={(e) => setVariantA(e.target.value)}>
                {manifest?.variants.map((v) => <option key={v.name} value={v.name}>{v.name}</option>)}
              </select>
            </label>
            <label>B
              <select value={variantB} onChange={(e) => setVariantB(e.target.value)}>
                {manifest?.variants.map((v) => <option key={v.name} value={v.name}>{v.name}</option>)}
              </select>
            </label>
          </div>
        </div>
        {manifest && (
          <p className="ab-provenance">
            commit <code>{manifest.provenance.git_commit.slice(0, 8)}</code> ·
            {" "}{manifest.provenance.timestamp} · n={manifest.provenance.n}
          </p>
        )}
        {variantA === variantB && <div className="empty-inline">请选择两个不同的变体</div>}
      </section>

      {data && (
        <>
          <section className="panel">
            <div className="panel-heading">
              <div><span className="section-kicker">Headline</span><h2>关键指标 delta</h2></div>
              <div className="segmented">
                <button type="button" className={layerFilter === "ALL" ? "active" : ""} onClick={() => setLayerFilter("ALL")}>全部</button>
                {layersInData.map((l) => (
                  <button type="button" key={l} className={layerFilter === l ? "active" : ""} onClick={() => setLayerFilter(l)}>{l}</button>
                ))}
              </div>
            </div>
            <div className="compact-metrics ab-cards">
              {visibleLayers.flatMap((layer) =>
                Object.entries(data.headline_delta[layer] ?? {}).map(([metric, d]) => (
                  <DeltaCard key={`${layer}-${metric}`} metric={metric} d={d} />
                )),
              )}
            </div>
          </section>

          <section className="panel">
            <div className="panel-heading case-heading">
              <div><span className="section-kicker">Drill-down</span><h2>样本下钻 {layerFilter !== "ALL" && `· ${layerFilter}`}</h2></div>
              <p>{rows.length} 样本 · 点行看 A/B 明细</p>
            </div>
            <div className="table-scroll case-table">
              <table>
                <thead>
                  <tr><th>case</th><th>bucket</th>{visibleLayers.map((l) => <th key={l}>{l}</th>)}<th /></tr>
                </thead>
                <tbody>
                  {rows.map((r) => {
                    const flipped = visibleLayers.some((l) => ["improved", "regressed"].includes(r[l]?.status ?? ""));
                    return (
                      <tr className={`clickable-row${flipped ? " ab-flip" : ""}`} key={r.case_id} onClick={() => setSelected(r)}>
                        <td><b className="case-id">{r.case_id}</b></td>
                        <td><span className="bucket-name">{r.bucket}</span></td>
                        {visibleLayers.map((l) => {
                          const cell = r[l];
                          return (
                            <td key={l}>
                              {cell ? (
                                <div className="ab-cell">
                                  <StatusPill status={cell.status} />
                                  <span className="ab-cell-rate">{pct(cell.a)}→{pct(cell.b)}</span>
                                </div>
                              ) : <StatusPill />}
                            </td>
                          );
                        })}
                        <td className="row-arrow">›</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              {!rows.length && <div className="empty-state"><span>✓</span><b>该层没有样本</b></div>}
            </div>
          </section>
        </>
      )}

      <CaseDrawer
        open={Boolean(selected)}
        width="wide"
        title={selected ? `${selected.case_id} · ${selected.bucket}` : ""}
        subtitle={selected && data && (
          <div className="badge-row">
            {LAYERS.filter((l) => selected[l]).map((l) => (
              <span key={l} className="badge-row"><b style={{ marginRight: 4 }}>{l}</b><StatusPill status={selected[l]?.status} /></span>
            ))}
          </div>
        )}
        onClose={() => setSelected(null)}
      >
        {selected && data && (
          <>
            <section className="drawer-question">
              <span>问题</span>
              <p>{data.detail[selected.case_id]?.question || "—"}</p>
            </section>
            <div className="ab-variant-grid">
              <div>
                <div className="ab-col-head">{data.variant_a}（A）</div>
                <VariantDetail side={data.detail[selected.case_id]?.a as unknown as VariantSide} />
              </div>
              <div>
                <div className="ab-col-head">{data.variant_b}（B）</div>
                <VariantDetail side={data.detail[selected.case_id]?.b as unknown as VariantSide} />
              </div>
            </div>
          </>
        )}
      </CaseDrawer>
    </div>
  );
}
