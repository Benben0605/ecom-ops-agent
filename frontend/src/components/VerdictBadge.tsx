type Verdict = "hit" | "supported" | "miss" | "unsupported" | "route_error" | "misfire" | "not_run";

const labels: Record<Verdict, string> = {
  hit: "hit",
  supported: "supported",
  miss: "miss",
  unsupported: "unsupported",
  route_error: "route error",
  misfire: "misfire",
  not_run: "not run",
};

export default function VerdictBadge({ verdict }: { verdict: Verdict }) {
  return <span className={`verdict verdict-${verdict}`}>{labels[verdict]}</span>;
}
