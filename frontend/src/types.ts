export type DashboardSummary = {
  total_machines: number;
  online_machines: number;
  offline_machines: number;
  high_risk_machines: number;
  low_utilization_machines: number;
  repeated_fault_machines: number;
};

export type CacheStatus = {
  exists: boolean;
  data_source: string;
  updated_at: string | null;
  age_seconds: number | null;
  ttl_seconds: number;
  fresh: boolean;
  latest_successful_sync: SyncLog | null;
};

export type DatabaseStatus = {
  provider: string;
  path: string;
  exists: boolean;
  tables: Record<string, number>;
  postgresql_ready: boolean;
  note: string;
};

export type AutoSyncStatus = {
  enabled: boolean;
  running: boolean;
  interval_seconds: number;
  last_run_at: string | null;
  next_run_at: string | null;
  last_result: SyncLog | null;
  error: string | null;
};

export type FleetTrendPoint = {
  captured_at: string;
  total_machines: number;
  online_machines: number;
  offline_machines: number;
  low_fuel_machines: number;
  low_utilization_machines: number;
  fault_records: number;
  average_fuel_percent: number | null;
  average_operating_hours: number | null;
  source: string;
};

export type FleetTrends = {
  days: number;
  points: FleetTrendPoint[];
  point_count: number;
  latest: FleetTrendPoint | null;
  deltas: Record<string, number | null>;
  has_history: boolean;
  summary: string[];
};

export type SyncLog = {
  created_at?: string;
  sync_type: string;
  status: string;
  records?: number;
  error?: string | null;
  finished_at?: string;
};

export type Machine = {
  machine_id: string;
  serial_number: string;
  model: string;
  machine_type: string;
  customer: string;
  location: string;
  latitude?: number | null;
  longitude?: number | null;
  last_seen_at: string;
  engine_status?: string;
  fuel_remaining_percent?: number | null;
  operating_hours?: number | null;
  fault_count?: number;
  risk_level?: string;
  risk_explanation?: string[];
};

export type TelemetrySnapshot = {
  machine_id: string;
  operating_hours: number | null;
  idle_hours: number | null;
  fuel_remaining_percent: number | null;
  engine_status: string | null;
  latitude: number | null;
  longitude: number | null;
  recorded_at: string;
};

export type FaultCode = {
  machine_id: string;
  spn: number | null;
  fmi: number | null;
  fault_code: string;
  description: string;
  severity: string;
  occurred_at: string;
  status: string;
};

export type MachinePromptResponse = {
  machine_id: string;
  prompt: string;
};

export type FleetPromptResponse = {
  prompt: string;
};

export type AiReportResponse = {
  provider: string;
  model: string;
  prompt_used: string;
  ai_report_markdown: string;
  generated_at: string;
  error: string | null;
};

export type AiProvider = "deepseek" | "gemini" | "ollama_local";

export type ViewKey =
  | "dashboard"
  | "fleet"
  | "machine-health"
  | "service-parts"
  | "ai-assistant"
  | "sync-cache"
  | "reports"
  | "settings";

export type AskResponse = {
  question: string;
  intent: string;
  answer?: string;
  answer_markdown: string;
  used_data: unknown;
  data_source: string;
  provider: string;
  model: string;
  error: string | null;
  query_plan?: unknown;
  intent_plan?: unknown;
  data_summary?: {
    source?: string;
    machines_scanned?: number;
    telemetry_records?: number;
    fault_records?: number;
    records_used?: number;
    fallback_used?: boolean;
    api_error?: string | null;
    cache_updated_at?: string | null;
    cache_age_seconds?: number | null;
    cache_fresh?: boolean;
  };
  missing_fields?: string[];
  fallback_used?: boolean;
  api_error?: string | null;
  structured_context?: unknown;
  quality_validation?: {
    valid: boolean;
    issues: string[];
  };
  analysis_mode?: string;
  risk_ranking?: Array<Record<string, unknown>>;
  service_recommendations?: Array<Record<string, unknown>>;
};

export type SyncFleetResponse = {
  sync_type: string;
  status: string;
  records: number;
  error?: string | null;
  finished_at: string;
};
