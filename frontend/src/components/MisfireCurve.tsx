import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceDot,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import timeline from "../data/eval_timeline.json";

interface TimelinePoint {
  stage: string;
  stage_label: string;
  misfire_rate: number;
  headline: string;
  label: string;
}

const points = timeline as TimelinePoint[];

function PointLabel({ viewBox, index }: { viewBox?: { x?: number; y?: number }; index: number }) {
  if (!viewBox?.x || !viewBox?.y) return null;
  const point = points[index];
  const anchor = index === 0 ? "start" : index === 2 ? "end" : "middle";
  const dx = index === 0 ? -7 : index === 2 ? 8 : 0;
  const dy = index === 1 ? -22 : -18;
  return (
    <g transform={`translate(${viewBox.x + dx},${viewBox.y + dy})`}>
      <text textAnchor={anchor} className={`chart-label chart-label-${index}`}>{index === 1 ? "⚠ " : ""}{point.headline}</text>
      <text y="17" textAnchor={anchor} className="chart-value">{(point.misfire_rate * 100).toFixed(2)}%</text>
    </g>
  );
}

function CurveTooltip({ active, payload }: { active?: boolean; payload?: Array<{ payload: TimelinePoint }> }) {
  if (!active || !payload?.length) return null;
  const point = payload[0].payload;
  return <div className="chart-tooltip"><b>{point.headline}</b><span>{(point.misfire_rate * 100).toFixed(2)}% · {point.stage_label}</span><p>{point.label}</p></div>;
}

export default function MisfireCurve() {
  return (
    <article className="panel curve-panel">
      <div className="panel-heading curve-heading">
        <div><span className="section-kicker">Iteration narrative</span><h2>误触发率随迭代变化</h2></div>
        <p><span className="pulse-dot" /> 改进 → 反噬 → 再修，非单调才是真功夫</p>
      </div>
      <div className="curve-chart" aria-label="误触发率迭代曲线">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={points} margin={{ top: 48, right: 90, bottom: 5, left: 5 }}>
            <CartesianGrid stroke="#e8edf4" vertical={false} strokeDasharray="4 5" />
            <XAxis dataKey="stage_label" tickLine={false} axisLine={{ stroke: "#cbd5e1" }} tick={{ fill: "#64748b", fontSize: 12 }} dy={8} />
            <YAxis domain={[0, 0.12]} ticks={[0, 0.02, 0.04, 0.06, 0.08, 0.1, 0.12]} tickFormatter={(value: number) => `${Math.round(value * 100)}%`} tickLine={false} axisLine={false} tick={{ fill: "#94a3b8", fontSize: 11 }} width={38} />
            <Tooltip content={<CurveTooltip />} cursor={{ stroke: "#93c5fd", strokeDasharray: "4 4" }} />
            <Line type="monotone" dataKey="misfire_rate" stroke="#2563eb" strokeWidth={3} dot={false} activeDot={{ r: 6, fill: "#fff", stroke: "#2563eb", strokeWidth: 3 }} />
            {points.map((point, index) => <ReferenceDot key={point.stage} x={point.stage_label} y={point.misfire_rate} r={6} fill={index === 1 ? "#b45309" : "#2563eb"} stroke="#fff" strokeWidth={3} label={<PointLabel index={index} />} />)}
          </LineChart>
        </ResponsiveContainer>
      </div>
      <div className="curve-source">数据源 · data/eval_timeline.json <span>悬停数据点查看完整迭代说明</span></div>
    </article>
  );
}
