import type { EvalDashboardData, L2DashboardData } from "../api";
import MethodologyCard from "../components/MethodologyCard";
import MetricCard from "../components/MetricCard";
import MisfireCurve from "../components/MisfireCurve";

interface Query<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
}

interface OverviewProps {
  evalQuery: Query<EvalDashboardData>;
  l2Query: Query<L2DashboardData>;
}

const percent = (value: number | null | undefined) => value == null ? "—" : `${(value * 100).toFixed(value === 0 || value === 1 ? 0 : 2)}%`;

function LoadError({ message, retry }: { message: string; retry: () => void }) {
  return <div className="error-banner"><span>接口拉取失败：{message}</span><button type="button" onClick={retry}>重试</button></div>;
}

export default function Overview({ evalQuery, l2Query }: OverviewProps) {
  if (evalQuery.loading || l2Query.loading) return <div className="skeleton-page"><div className="skeleton hero-skeleton" /><div className="skeleton chart-skeleton" /><div className="skeleton method-skeleton" /></div>;
  const warnings = [
    ...(evalQuery.data?.context?.warnings ?? []),
    ...(l2Query.data?.context?.warnings ?? []),
  ].filter((warning, index, list) => list.indexOf(warning) === index);

  return (
    <div className="overview-page page-stack">
      {evalQuery.error && <LoadError message={evalQuery.error} retry={() => void evalQuery.refetch()} />}
      {l2Query.error && <LoadError message={l2Query.error} retry={() => void l2Query.refetch()} />}
      {warnings.map((warning) => <div className="source-warning" key={warning}>{warning}</div>)}
      {evalQuery.data && l2Query.data && <>
        <section className="hero-metrics" aria-label="核心指标">
          <MetricCard label="路由准确率" value={percent(evalQuery.data.metrics.routing_accuracy)} detail={`${evalQuery.data.metrics.route_hit_count} / ${evalQuery.data.metrics.positive_case_count}`} note="分母=正样本：期望工具命中比例" />
          <MetricCard label="误触发率" value={percent(evalQuery.data.metrics.misfire_rate)} detail={`${evalQuery.data.metrics.misfire_count} / ${evalQuery.data.metrics.evaluated_case_count}`} note="分母=全集：调了期望外工具的占比" />
          <MetricCard label="L2 命中率" value={percent(l2Query.data.metrics.hit_rate)} detail={`${l2Query.data.metrics.hit_ok} / ${l2Query.data.metrics.hit_total}`} note="golden point 要点命中" />
          <MetricCard label="L2 忠实率" value={percent(l2Query.data.metrics.faithfulness_rate)} detail={`${l2Query.data.metrics.faith_ok} / ${l2Query.data.metrics.faith_total}`} note="answer 断言对 tool output 忠实" />
          <MetricCard label="评估覆盖率" value={percent(evalQuery.data.metrics.coverage_rate)} detail={`${evalQuery.data.metrics.evaluated_case_count} / ${evalQuery.data.metrics.case_count}`} note={`已评 / 总 ${evalQuery.data.metrics.case_count}`} />
        </section>
        <MisfireCurve />
        <section className="methodology-grid" aria-label="评估方法论">
          <MethodologyCard index="01" title="两个正交指标"><p><b>准确率</b> 分母只数正样本；<b>误触发率</b> 分母覆盖全集。两个 headline 口径互不污染。</p></MethodologyCard>
          <MethodologyCard index="02" title="双闸门难样本准入"><p>闸门 A：label 站得住；闸门 B：写得出模型会栽在哪的 trap。两闸都过才有鉴别力。</p></MethodologyCard>
          <MethodologyCard index="03" title="分歧落两种介质"><p><b>模型对 → 改数据</b>；<b>模型错 → 改 Agent</b>。每次修改后跑完整回归网。</p></MethodologyCard>
        </section>
      </>}
    </div>
  );
}
