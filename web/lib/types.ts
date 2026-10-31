// Mirrors api/schemas.py and PLAN.md §3.3–§3.5. Keep in sync with the backend.

export type Verdict = "ELIGIBLE" | "CHECK_DOCS" | "NOT_ELIGIBLE";
export type AgentName = "gem" | "cppp" | "haryana" | "corrigenda" | "all";
// update: a late document parse changed a match. settled: background document reading finished.
export type EventType = "started" | "step" | "result" | "error" | "done" | "update" | "settled";

export interface Profile {
  id: number;
  name: string;
  phone: string | null;
  email: string | null;
  products: string[];
  keywords: string[];
  hsn_codes: string[];
  annual_turnover: number | null;
  years_in_business: number | null;
  certifications: string[];
  states_served: string[];
}

export type ProfileInput = Omit<Profile, "id">;

export interface StepEvent {
  sweep_id: string;
  agent: AgentName;
  type: EventType;
  step: number;
  message: string;
  count: number | null;
  direct_url: string | null;
  pending?: number | null;     // on all/done: documents still being read in the background
  tender_id?: number | null;   // on all/update
  ts: string;
}

export interface Tender {
  id: number;
  portal: string;
  bid_no: string;
  title: string;
  item: string | null;
  buyer: string | null;
  quantity: string | null;
  est_value: number | null;
  end_date: string;
  source_url: string;
  doc_url: string | null;
}

export interface Excerpt {
  text: string;
  highlight_start: number;
  highlight_end: number;
  prefix_truncated: boolean;
  suffix_truncated: boolean;
}

export interface Reason {
  kind: "ok" | "info" | "warn" | "fail";
  criterion: string;
  text: string;
  source_clause: string | null;
  source_url?: string | null;
  excerpt?: Excerpt | null;
}

export interface MatchSummary {
  id: number;
  profile_id: number;
  verdict: Verdict;
  fit_score: number | null;
  relevant: boolean;
  reasons: Reason[];
  missing_docs: string[];
  alerted_at: string | null;
  tender: Tender;
}

export interface Corrigendum {
  bid_no: string;
  summary: string;
  source_url: string;
  new_end_date?: string | null;
  extends_to?: string | null;
  found_at?: string;
}

/** Where each part of a verdict came from (api/main.py provenance). */
export interface Provenance {
  found_by: string;                                   // "TinyFish agent on GeM" / "recorded TinyFish run on GeM"
  portal: string;
  doc_source: "fetch" | "direct" | "fixture" | null;  // null: no document text
  eligibility_by: string | null;                      // "LLM (openai/gpt-oss-120b)" / "recorded parse"
  verdict_by: string;
}

export interface MatchDetail extends MatchSummary {
  eligibility: Record<string, { value: unknown; source_clause: string | null }> | null;
  corrigenda: Corrigendum[];
  provenance?: Provenance;
}

export interface Health {
  db: boolean;
  redis: boolean;
  fallback_mode: boolean;
  next_corrigenda_check: string | null;
  now: string;                                   // the API's clock (frozen demo clock in fallback mode)
  clock: "real" | "DEMO_NOW" | "fixture recorded_at";
}

/** GET /alerts/status: which channels are set up (no secrets). */
export interface AlertStatus {
  whatsapp: boolean;
  email: boolean;
  auto_alert: boolean;
  auto_alert_max: number;
  whatsapp_to: string | null;   // masked, e.g. +91•••••4321
  email_to: string | null;
}

export interface AlertResult {
  match_id: number;
  sent: boolean;
  channels: { whatsapp: string; email: string };
  preview: string;
}
