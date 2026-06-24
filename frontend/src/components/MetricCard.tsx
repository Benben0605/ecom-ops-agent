interface MetricCardProps {
  label: string;
  value: string;
  note: string;
  detail?: string;
  compact?: boolean;
}

export default function MetricCard({ label, value, note, detail, compact }: MetricCardProps) {
  return (
    <article className={`metric-card${compact ? " metric-card-compact" : ""}`}>
      <span className="metric-label">{label}</span>
      <strong className="metric-value">{value}</strong>
      {detail && <span className="metric-detail">{detail}</span>}
      <p>{note}</p>
    </article>
  );
}
