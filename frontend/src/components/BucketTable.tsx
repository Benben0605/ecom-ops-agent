import type { L2DashboardData, RoutingBreakdown } from "../api";

const percent = (value: number | null) => value == null ? "—" : `${(value * 100).toFixed(value === 1 || value === 0 ? 0 : 1)}%`;

function RateCell({ value, kind }: { value: number | null; kind: "accuracy" | "misfire" | "faith" }) {
  if (value == null) return <span className="muted">—</span>;
  const state = kind === "misfire" ? (value === 0 ? "good" : "warn") : (value === 1 ? "good" : "bad");
  return (
    <div className={`rate-cell rate-${state}`}>
      <span className="rate-track"><i style={{ width: `${Math.max(value * 100, value > 0 ? 4 : 0)}%` }} /></span>
      <b>{percent(value)}</b>
    </div>
  );
}

interface L1Props {
  kind: "l1";
  rows: Array<RoutingBreakdown & { bucket: string }>;
  totals: {
    case_count: number;
    evaluated_case_count: number;
    positive_case_count: number;
    route_hit_count: number;
    routing_accuracy: number;
    misfire_rate: number;
  };
}

interface L2Props {
  kind: "l2";
  rows: L2DashboardData["breakdowns"]["by_bucket"];
}

export default function BucketTable(props: L1Props | L2Props) {
  if (props.kind === "l1") {
    return (
      <div className="table-scroll">
        <table>
          <thead><tr><th>bucket</th><th>case</th><th>已评</th><th>正样本</th><th>命中</th><th className="rate-column">准确率</th><th className="rate-column">误触发率</th></tr></thead>
          <tbody>
            {props.rows.map((row) => <tr key={row.bucket}>
              <td><span className="bucket-name">{row.bucket}</span></td><td>{row.case_count}</td><td>{row.evaluated_case_count}</td><td>{row.positive_case_count}</td><td>{row.positive_case_count ? row.route_hit_count : "—"}</td>
              <td><RateCell value={row.positive_case_count ? row.routing_accuracy : null} kind="accuracy" /></td>
              <td><RateCell value={row.misfire_rate} kind="misfire" /></td>
            </tr>)}
          </tbody>
          <tfoot><tr><td>合计</td><td>{props.totals.case_count}</td><td>{props.totals.evaluated_case_count}</td><td>{props.totals.positive_case_count}</td><td>{props.totals.route_hit_count}</td><td>{percent(props.totals.routing_accuracy)}</td><td>{percent(props.totals.misfire_rate)}</td></tr></tfoot>
        </table>
      </div>
    );
  }
  return (
    <div className="table-scroll">
      <table>
        <thead><tr><th>bucket</th><th>case</th><th>通过</th><th className="rate-column">命中率</th><th className="rate-column">忠实率</th><th>问题 (miss / unsupported)</th></tr></thead>
        <tbody>{props.rows.map((row) => <tr key={row.bucket}>
          <td><span className="bucket-name">{row.bucket}</span></td><td>{row.case_count}</td><td>{row.passed_case_count}</td>
          <td><RateCell value={row.hit_rate} kind="accuracy" /></td><td><RateCell value={row.faithfulness_rate} kind="faith" /></td><td><span className={row.hit_issue_case_count ? "text-danger" : ""}>{row.hit_issue_case_count}</span> / <span className={row.faith_issue_case_count ? "text-danger" : ""}>{row.faith_issue_case_count}</span></td>
        </tr>)}</tbody>
      </table>
    </div>
  );
}
