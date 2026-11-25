export type FindingStatus = "open" | "approved" | "rejected";

export interface FindingSummary {
  id: number;
  cusip: string;
  asset_class: string;
  description: string;
  as_of: string;
  screen_run_id: number;
  extraction_id: number;
  income_impact_usd: number;
  run_rate_gap_usd: number;
  headline: string;
  rules: string[];
  status: FindingStatus;
  extraction_status: string | null;
  created_by: string;
  created_at: string;
}

export interface ComparisonRow {
  field: string;
  vendor: string;
  document: string;
  match: boolean;
  page: number | null;
  excerpt: string | null;
  citation_status: string | null;
}

export interface Metric {
  label: string;
  value: number | null;
  fmt: "num4" | "num2" | "pct" | "usd";
  emphasis: boolean;
}

export interface FindingDetail extends FindingSummary {
  narrative: {
    vendor_says: string;
    document_says: string;
    correct_treatment: string;
    impact: string;
    extraction_status: string;
    extraction_problems: string[];
    metrics: Metric[];
    schedule: Record<string, string | number | null>[];
    schedule_label: string;
    notes: string[];
  };
  comparison: ComparisonRow[];
  positions: {
    holding_id: number;
    par: number;
    unbooked_income_usd: number;
    run_rate_gap_usd: number;
    unbooked_window_usd: number | null;
    computation_id: number;
  }[];
}

export interface ReviewActionT {
  id: number;
  finding_id: number;
  action: string;
  from_status: string;
  to_status: string;
  comment: string | null;
  actor: string;
  at: string;
}

export interface CitationCheck {
  field: string;
  status: string;
  page: number | null;
  score: number;
  found_on_page: number | null;
  value_in_excerpt: boolean | null;
  ok: boolean;
}

export interface Extraction {
  id: number;
  document_id: number;
  cusip: string;
  status: string;
  model_requested: string;
  model_served: string | null;
  prompt_version: string;
  terms: Record<string, unknown> | null;
  citation_checks: CitationCheck[] | null;
  interest_terms: Record<string, unknown> | null;
  problems: string[] | null;
  page_selection: { pages: number[]; total_pages: number; truncated: boolean } | null;
  error: string | null;
  created_by: string;
  created_at: string;
}

export interface Flag {
  rule: string;
  severity: number;
  message: string;
  inputs?: Record<string, unknown>;
  computed?: Record<string, unknown>;
}

export interface FlaggedCusip {
  cusip: string;
  description: string;
  par: number;
  price: number;
  price_convention: string | null;
  coupon: number | null;
  accrual_type: string | null;
  vendor_yield: number | null;
  rating: string | null;
  sector: string | null;
  asset_class: string;
  max_severity: number;
  flags: Flag[];
  document_id: number | null;
  extraction_id: number | null;
  extraction_status: string | null;
  finding_id: number | null;
  finding_status: FindingStatus | null;
  income_impact_usd: number | null;
}

export interface Batch {
  id: number;
  kind: "holdings" | "vendor_secondary" | "price_history";
  vendor: string | null;
  filename: string;
  sha256: string;
  row_count: number;
  uploaded_by: string;
  uploaded_at: string;
}

export interface ScreenRunT {
  id: number;
  as_of: string;
  holdings_batch_id: number;
  secondary_batch_id: number | null;
  history_batch_id: number | null;
  config: Record<string, unknown>;
  started_by: string;
  started_at: string;
  finished_at: string | null;
  flag_count: number;
}

export interface AuditEvent {
  id: number;
  ts: string;
  actor: string;
  event_type: string;
  entity_type: string;
  entity_id: string;
  payload: Record<string, unknown>;
  prev_hash: string;
  hash: string;
}
