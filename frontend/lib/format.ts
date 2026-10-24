import type { Severity, State, Verdict } from "./types";

export const SEVERITY_STYLE: Record<Severity, { chip: string; mark: string; dot: string; label: string }> = {
  critical: { chip: "bg-danger-50 text-danger-700 ring-danger/30", mark: "bg-danger-100 decoration-danger", dot: "bg-danger", label: "Critical" },
  major: { chip: "bg-amber-50 text-amber-700 ring-amber/30", mark: "bg-amber-100 decoration-amber", dot: "bg-amber", label: "Major" },
  minor: { chip: "bg-info-50 text-info-700 ring-info/30", mark: "bg-info-100 decoration-info", dot: "bg-info", label: "Minor" },
};

export const STATE_STYLE: Record<State, { chip: string; label: string }> = {
  draft: { chip: "bg-paper-100 text-navy-500 ring-paper-200", label: "Draft" },
  in_review: { chip: "bg-info-50 text-info-700 ring-info/30", label: "In review" },
  changes_requested: { chip: "bg-amber-50 text-amber-700 ring-amber/30", label: "Changes requested" },
  approved: { chip: "bg-teal-50 text-teal-700 ring-teal/30", label: "Approved" },
  published: { chip: "bg-purple-50 text-purple-700 ring-purple/30", label: "Published" },
};

export const VERDICT_STYLE: Record<Verdict, { chip: string; label: string }> = {
  supported: { chip: "bg-teal-50 text-teal-700 ring-teal/30", label: "Supported" },
  outdated: { chip: "bg-amber-50 text-amber-700 ring-amber/30", label: "Outdated" },
  contradicted: { chip: "bg-danger-50 text-danger-700 ring-danger/30", label: "Contradicted" },
  unsupported: { chip: "bg-danger-50 text-danger-700 ring-danger/30", label: "Unsupported" },
  needs_review: { chip: "bg-purple-50 text-purple-700 ring-purple/30", label: "Needs review" },
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
