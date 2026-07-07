export type JsonValue =
  | string
  | number
  | boolean
  | null
  | JsonValue[]
  | { [key: string]: JsonValue };

export interface DashboardMetrics {
  routing_accuracy: number;
  misfire_rate: number;
  coverage_rate: number;
  failure_case_count: number;
  route_hit_count: number;
  route_error_count: number;
  positive_case_count: number;
  evaluated_case_count: number;
  case_count: number;
  misfire_count: number;
}

export interface DashboardContext {
  mode: "legacy" | "experiment";
  exp_id?: string;
  experiment_name?: string;
  variant?: string;
  track?: string;
  n?: number;
  provenance?: {
    git_commit?: string;
    timestamp?: string;
    entrypoint?: string;
    n?: number;
    track?: string;
    dataset_sha?: Record<string, string>;
  };
  dataset_sha_match?: boolean | null;
  dataset_sha_manifest?: string | null;
  dataset_sha_current?: string | null;
  warnings?: string[];
  source_paths?: string[];
  source_modified_at?: string | null;
}

export interface RoutingBreakdown {
  bucket?: string;
  tool_name?: string;
  case_count: number;
  evaluated_case_count: number;
  positive_case_count: number;
  route_hit_count: number;
  route_error_count: number;
  misfire_count: number;
  routing_accuracy: number;
  misfire_rate: number;
}

export interface ActualToolCall {
  tool_name: string;
  call_count: number;
}

export interface ExpectedCall {
  tool_name: string;
  tool_params: Record<string, JsonValue>;
}

export interface AuditRecord {
  tool_name: string;
  tool_params?: Record<string, JsonValue>;
  tool_duration_ms?: number;
  tool_output?: JsonValue;
  tool_error?: JsonValue;
  session_id?: string;
}

export interface SessionMessage {
  role: string;
  content: JsonValue;
}

export interface RoutingCase {
  case_id: string;
  bucket: string;
  question: string;
  trap: string;
  should_call_tool: boolean;
  expected_calls: ExpectedCall[];
  expected_tools: string[];
  called_tools: string[];
  missing_tools: string[];
  unexpected_tools: string[];
  is_hit: boolean | null;
  is_misfire: boolean;
  route_error: boolean;
  not_run: boolean;
  issue_types: Array<"not_run" | "route_error" | "misfire">;
  session_ids: string[];
  audit_count: number;
  tool_error_count: number;
  tool_duration_ms: number;
  last_assistant_message: string;
  audits: AuditRecord[];
  messages_by_session: Record<string, SessionMessage[]>;
  n?: number;
  pass_rate?: number | null;
  hit_rate?: number | null;
  misfire_rate?: number | null;
  experiment_runs?: L1ExperimentRun[];
}

export interface L1ExperimentRun {
  run_index: number;
  session_id?: string;
  called_tools: string[];
  missing_tools: string[];
  unexpected_tools: string[];
  is_hit: boolean | null;
  is_misfire: boolean;
  passed: boolean;
  audits: AuditRecord[];
  messages: SessionMessage[];
  last_assistant_message: string;
}

export interface EvalDashboardData {
  generated_at: string;
  context?: DashboardContext;
  metrics: DashboardMetrics;
  breakdowns: {
    by_bucket: Array<RoutingBreakdown & { bucket: string }>;
    by_expected_tool: Array<RoutingBreakdown & { tool_name: string }>;
    actual_tool_calls: ActualToolCall[];
  };
  cases: RoutingCase[];
  route_error_cases: RoutingCase[];
  misfire_cases: RoutingCase[];
}

export interface L2Stats {
  case_count: number;
  passed_case_count: number;
  issue_case_count: number;
  hit_issue_case_count: number;
  faith_issue_case_count: number;
  hit_ok: number;
  hit_total: number;
  faith_ok: number;
  faith_total: number;
  case_pass_rate: number | null;
  hit_rate: number | null;
  faithfulness_rate: number | null;
}

export interface HitAxisItem {
  point: string;
  verdict: "hit" | "miss";
  evidence?: JsonValue;
}

export interface FaithfulnessAxisItem {
  assertion: string;
  verdict: "supported" | "unsupported";
  evidence: JsonValue;
  issue_id: string;
  annotation?: L2RootCauseAnnotation;
}

export interface RootCauseOption {
  value: string;
  label: string;
  description: string;
}

export interface L2RootCauseAnnotation {
  issue_id: string;
  level: "L2";
  axis: "faithfulness";
  case_id: string;
  verdict: "unsupported";
  assertion: string;
  root_cause: string;
  root_cause_label: string;
  root_cause_note: string;
  updated_at: string;
  summary: string;
  hypothesis: string;
  exp_id?: string;
  variant?: string;
  run_index?: number;
}

export interface SaveL2RootCauseAnnotationPayload {
  case_id: string;
  issue_id: string;
  assertion: string;
  verdict: "unsupported";
  root_cause: string;
  root_cause_note: string;
  exp_id?: string;
  variant?: string;
  run_index?: number;
}

export interface L2Case {
  case_id: string;
  bucket: string;
  question: string;
  answer: string;
  tool_outputs: JsonValue[];
  golden_points: JsonValue[];
  hit_axis: HitAxisItem[];
  faithfulness_axis: FaithfulnessAxisItem[];
  score: {
    hit_ok: number;
    hit_total: number;
    hit_rate: number | null;
    faith_ok: number;
    faith_total: number;
    faithfulness_rate: number | null;
  };
  miss_count: number;
  unsupported_count: number;
  annotation_count: number;
  has_hit_issue: boolean;
  has_faith_issue: boolean;
  has_issue: boolean;
  issue_types: Array<"miss" | "unsupported">;
  n?: number;
  pass_rate?: number | null;
  hit_rate?: number | null;
  faithfulness_rate?: number | null;
  experiment_runs?: L2ExperimentRun[];
}

export interface L2ExperimentRun {
  run_index: number;
  session_id?: string;
  answer: string;
  tool_outputs: JsonValue[];
  golden_points: JsonValue[];
  hit_axis: HitAxisItem[];
  faithfulness_axis: FaithfulnessAxisItem[];
  score: L2Case["score"];
  miss_count: number;
  unsupported_count: number;
  annotation_count: number;
  has_issue: boolean;
  issue_types: Array<"miss" | "unsupported">;
  passed: boolean;
}

export interface L2DashboardData {
  generated_at: string;
  context?: DashboardContext;
  metrics: L2Stats;
  breakdowns: {
    by_bucket: Array<L2Stats & { bucket: string }>;
  };
  annotations: {
    path: string;
    exists: boolean;
    count: number;
    root_cause_options: RootCauseOption[];
  };
  cases: L2Case[];
  issue_cases: L2Case[];
}

export interface ChatRequest {
  session_id: string;
  user_input: string;
}

export interface ChatResponse {
  session_id: string;
  assistant_message: string;
}

export interface DashboardSelection {
  source: "legacy" | "experiment";
  expId?: string;
  variant?: string;
}

function dashboardUrl(path: string, selection?: DashboardSelection) {
  if (selection?.source !== "experiment" || !selection.expId || !selection.variant) {
    return path;
  }
  const q = new URLSearchParams();
  q.set("exp_id", selection.expId);
  q.set("variant", selection.variant);
  return `${path}?${q.toString()}`;
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    let message = `请求失败 (${response.status})`;
    try {
      const body = await response.json() as { detail?: string };
      if (body.detail) message = body.detail;
    } catch {
      // keep generic message
    }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

export const fetchEvalDashboard = (selection?: DashboardSelection) =>
  request<EvalDashboardData>(dashboardUrl("/api/eval-dashboard", selection));

export const fetchL2Dashboard = (selection?: DashboardSelection) =>
  request<L2DashboardData>(dashboardUrl("/api/l2-eval-dashboard", selection));

export const saveL2RootCauseAnnotation = (payload: SaveL2RootCauseAnnotationPayload) =>
  request<L2RootCauseAnnotation>("/api/l2-root-cause-annotations", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

export const sendChat = (payload: ChatRequest) =>
  request<ChatResponse>("/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

// ===== A/B 实验对比 =====
export interface ExperimentManifest {
  exp_id: string;
  name: string;
  track: "agent" | "retrieval";
  variants: Array<{ name: string; config: Record<string, JsonValue> }>;
  provenance: {
    git_commit: string;
    timestamp: string;
    n: number;
    track: string;
    dataset_sha: Record<string, string>;
  };
}

export type FlipStatus = "improved" | "regressed" | "same" | "na";

export interface MetricDelta {
  a: number | null;
  b: number | null;
  delta: number | null;
}

export interface CaseDiffLayer {
  a: number | null; // per-run 通过率（N=1 时为 0/1）
  b: number | null;
  status: FlipStatus;
  a_mrr?: number | null;
  b_mrr?: number | null;
}

export interface CaseDiffRow {
  case_id: string;
  bucket: string | null;
  L1?: CaseDiffLayer;
  L2?: CaseDiffLayer;
  RAG?: CaseDiffLayer;
}

export interface CompareData {
  exp_id: string;
  track: "agent" | "retrieval";
  variant_a: string;
  variant_b: string;
  headline_delta: Record<string, Record<string, MetricDelta>>;
  case_diff: CaseDiffRow[];
  detail: Record<string, { question: string; a: JsonValue; b: JsonValue }>;
}

export const fetchExperiments = () =>
  request<ExperimentManifest[]>("/api/experiments");

export const fetchCompare = (expId: string, a?: string, b?: string) => {
  const q = new URLSearchParams();
  if (a) q.set("a", a);
  if (b) q.set("b", b);
  const qs = q.toString();
  return request<CompareData>(`/api/experiments/${expId}/compare${qs ? `?${qs}` : ""}`);
};
