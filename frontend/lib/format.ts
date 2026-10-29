import type { Severity, State, Verdict } from "./types";

// Proof marks on the sheet and matching margin-note accents. Colour carries meaning only.
export const SEVERITY_STYLE: Record<Severity, { chip: string; mark: string; dot: string; rule: string; stroke: string; label: string; number: string; numberActive: string; text: string }> = {
  critical: { chip: "border-signal/40 bg-signal-50 text-signal-700", mark: "mark-critical", dot: "bg-signal", rule: "border-signal", stroke: "rgb(var(--signal))", label: "Critical", number: "border-signal-700 bg-signal-50 text-signal-700", numberActive: "!bg-signal-700 !text-sheet", text: "text-signal-700" },
  major: { chip: "border-amber/40 bg-amber-50 text-amber-700", mark: "mark-major", dot: "bg-amber", rule: "border-amber", stroke: "rgb(var(--amber))", label: "Major", number: "border-amber-700 bg-amber-50 text-amber-700", numberActive: "!bg-amber-700 !text-sheet", text: "text-amber-700" },
  minor: { chip: "border-slate/40 bg-slate-50 text-slate-700", mark: "mark-minor", dot: "bg-slate", rule: "border-slate", stroke: "rgb(var(--slate))", label: "Minor", number: "border-slate-700 bg-slate-50 text-slate-700", numberActive: "!bg-slate-700 !text-sheet", text: "text-slate-700" },
};

// Departures-board status codes.
export const STATE_STYLE: Record<State, { chip: string; label: string }> = {
  draft: { chip: "border-rule bg-paper text-graphite", label: "Draft" },
  in_review: { chip: "border-slate/40 bg-slate-50 text-slate-700", label: "Holding" },
  changes_requested: { chip: "border-amber/40 bg-amber-50 text-amber-700", label: "Changes requested" },
  approved: { chip: "border-cleared/40 bg-cleared-50 text-cleared-700", label: "Cleared" },
  published: { chip: "border-ink/30 bg-paper-100 text-ink", label: "Published" },
};

export const VERDICT_STYLE: Record<Verdict, { chip: string; label: string }> = {
  supported: { chip: "border-cleared/40 bg-cleared-50 text-cleared-700", label: "Supported" },
  outdated: { chip: "border-amber/40 bg-amber-50 text-amber-700", label: "Outdated" },
  contradicted: { chip: "border-signal/40 bg-signal-50 text-signal-700", label: "Contradicted" },
  unsupported: { chip: "border-signal/40 bg-signal-50 text-signal-700", label: "Unsupported" },
  needs_review: { chip: "border-slate/40 bg-slate-50 text-slate-700", label: "Needs review" },
};

export const CHANNEL_LABEL: Record<string, string> = {
  linkedin: "LinkedIn",
  x: "X",
  email: "Email",
  press_release: "Press release",
  blog: "Blog",
};

export function driftLabel(drift: number | null | undefined): { label: string; tone: string } {
  if (drift == null) return { label: "n/a", tone: "text-navy-500" };
  if (drift < 0.15) return { label: "Low drift", tone: "text-teal-700" };
  if (drift < 0.35) return { label: "Medium drift", tone: "text-amber-700" };
  return { label: "High drift", tone: "text-danger-700" };
}

export function scoreTone(score: number | null | undefined): string {
  if (score == null) return "text-navy-300";
  if (score >= 85) return "text-teal";
  if (score >= 60) return "text-amber";
  return "text-danger";
}

export function timeAgo(iso: string): string {
  const seconds = Math.max(1, Math.round((Date.now() - new Date(iso).getTime()) / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

export function pct(value: number): string {
  return `${Math.round(value * 100)}%`;
}
