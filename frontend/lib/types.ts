// Mirrors backend/app/schemas. Kept hand-written and small on purpose.

export type Severity = "critical" | "major" | "minor";
export type Verdict = "supported" | "outdated" | "contradicted" | "unsupported" | "needs_review";
export type State = "draft" | "in_review" | "changes_requested" | "approved" | "published";
export type FindingStatus = "open" | "accepted" | "edited" | "disputed" | "escalated" | "resolved";

export interface UserRef {
  id: string;
  name: string;
  role: string;
  title: string;
}

export interface Evidence {
  fact_id: string;
  quote: string;
  nli: "entailment" | "neutral" | "contradiction" | null;
  score: number | null;
}

export interface Finding {
  id: string;
  type: string;
  span: { block: number; start: number; end: number };
  text: string;
  rule: { id: string; source: string };
  evidence: Evidence[];
  severity: Severity;
  confidence: number;
  explanation: string;
  suggestion: { text: string; drift: number | null } | null;
  detector: "rules" | "llm" | "nli";
  status: FindingStatus;
  needs_review: boolean;
  related: string[];
  applied_text: string | null;
}

export interface Claim {
  id: string;
  text: string;
  span: { block: number; start: number; end: number };
  claim_type: string;
  verdict: Verdict;
  fact_id: string | null;
  current_fact_id: string | null;
  quote: string | null;
  scores: Record<string, number | string | null>;
  confidence: number;
  steps: string[];
}

export interface Block {
  id: number;
  text: string;
  start_offset: number;
}

export interface CheckerRun {
  name: string;
  label: string;
  ok: boolean;
  findings: number;
  ms: number;
  error?: string | null;
}

export interface AiSummary {
  mode: "llm" | "deterministic" | "degraded";
  provider: string | null;
  model: string | null;
  purposes: string[];
  failed_purposes: string[];
  calls: number;
  masking_enabled: boolean;
  masked_count: number;
  nli_model: string | null;
  embedding_model: string | null;
}

export interface ToneProfile {
  source: "llm" | "heuristic";
  scores: Record<string, number>;
  targets: Record<string, number>;
  evidence: Record<string, string>;
}

export interface Report {
  checkers?: CheckerRun[];
  score_breakdown?: { finding_id: string; rule_id: string; severity: Severity; points: number }[];
  tone?: ToneProfile | null;
  ai?: AiSummary;
  cached_from?: string;
}

export interface RevisionSummary {
  id: string;
  number: number;
  brand_score: number | null;
  review_status: "pending" | "complete" | "failed";
  created_at: string;
}

export interface Revision extends RevisionSummary {
  content: string;
  blocks: Block[];
  source_format: string;
  degraded: boolean;
  report: Report;
  completed_at: string | null;
}

export interface Decision {
  id: string;
  kind: string;
  reason: string;
  payload: Record<string, unknown>;
  finding_id: string | null;
  revision_id: string | null;
  actor: UserRef;
  created_at: string;
}

export interface Review {
  submission: {
    id: string;
    title: string;
    channel: string;
    state: State;
    author: UserRef;
    approved_by: UserRef | null;
    approved_at: string | null;
    created_at: string;
    updated_at: string;
  };
  revision: Revision;
  revisions: RevisionSummary[];
  findings: Finding[];
  claims: Claim[];
  decisions: Decision[];
  gate: { can_submit: boolean; can_approve: boolean; blocking: string[]; message: string };
  pending_edits: number;
  permissions: string[];
}

export interface ReviewListItem {
  id: string;
  title: string;
  channel: string;
  state: State;
  author: UserRef;
  brand_score: number | null;
  open_criticals: number;
  open_findings: number;
  revision: number;
  review_status: string;
  updated_at: string;
}

export interface Sample {
  id: string;
  label: string;
  title: string;
  channel: string;
  format: string;
  filename: string | null;
  content: string;
  description: string;
}

export interface Channel {
  id: string;
  name: string;
  max_chars: number | null;
  max_hashtags: number | null;
  subject_max_chars: number | null;
  consumer: boolean;
  rule_code: string | null;
}

export interface Comment {
  id: string;
  body: string;
  finding_id: string | null;
  author: UserRef;
  created_at: string;
}

export interface Notification {
  id: string;
  kind: string;
  message: string;
  submission_id: string | null;
  read: boolean;
  created_at: string;
}

export interface Health {
  status: "ok" | "degraded" | "starting";
  database: boolean;
  models_ready: boolean;
  embedding_model: string | null;
  nli_model: string | null;
  llm_provider: string;
  version: string;
}
