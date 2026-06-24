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
}

export interface EvalDashboardData {
  generated_at: string;
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
}

export interface SaveL2RootCauseAnnotationPayload {
  case_id: string;
  issue_id: string;
  assertion: string;
  verdict: "unsupported";
  root_cause: string;
  root_cause_note: string;
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
}

export interface L2DashboardData {
  generated_at: string;
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

export const fetchEvalDashboard = () =>
  request<EvalDashboardData>("/api/eval-dashboard");

export const fetchL2Dashboard = () =>
  request<L2DashboardData>("/api/l2-eval-dashboard");

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
