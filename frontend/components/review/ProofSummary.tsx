"use client";

// The bar above a proof: is it ready, how many open notes of each severity (also filters),
// "Accept all suggested fixes", and the proof-mark legend in a small popover.

import { clsx } from "clsx";
import { CheckCheck, CircleCheck, HelpCircle, Loader2, OctagonX } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { SEVERITY_STYLE } from "@/lib/format";
import type { Finding, Severity } from "@/lib/types";

import { SEVERITY_ICON } from "./MarginNote";

export const SEVERITIES: Severity[] = ["critical", "major", "minor"];
const OPEN = new Set(["open", "escalated", "disputed"]);

function Legend() {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !ref.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
    };
  }, [open]);
  return (
    <div ref={ref} className="relative">
      <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open} aria-label="How to read the proof marks" className="rounded p-1.5 text-graphite transition-colors duration-150 hover:bg-raised hover:text-ink">
        <HelpCircle className="h-4 w-4" aria-hidden="true" />
      </button>
      {open && (
        <div role="dialog" aria-label="Proof marks" className="paper-scope absolute right-0 z-30 mt-2 w-72 rounded-lg border border-rule bg-sheet p-3 text-sm shadow-lift">
          <p className="font-medium text-ink">Proof marks</p>
          <ul className="mt-2 space-y-1.5 text-graphite">
            <li><span className="mark-critical font-serif text-ink">wavy</span> critical: blocks approval</li>
            <li><span className="mark-major font-serif text-ink">underline</span> major</li>
            <li><span className="mark-minor font-serif text-ink">dotted</span> minor</li>
            <li><span className="mark-settled font-serif text-ink">thin</span> settled: accepted, edited or disputed</li>
          </ul>
          <p className="mt-3 border-t border-rule pt-2 text-xs text-graphite">The number beside a mark is its note. J / K move between notes · A accept · E edit · D dispute · ? help</p>
        </div>
      )}
    </div>
  );
}

export function ProofSummary({
  findings,
  hidden,
  onToggle,
  canDecide,
  busy,
  onAcceptAll,
}: {
  findings: Finding[];
  /** Severities filtered out of the proof. */
  hidden: Set<Severity>;
  onToggle: (s: Severity) => void;
  canDecide: boolean;
  busy: boolean;
  onAcceptAll?: () => void;
}) {
  const open = findings.filter((f) => OPEN.has(f.status));
  const count = (s: Severity) => open.filter((f) => f.severity === s).length;
  const critical = count("critical");
  const fixable = findings.filter((f) => f.status === "open" && f.suggestion).length;
  const [label, tone, Icon] =
    critical > 0
      ? ["Not ready to publish", "text-signal-700", OctagonX]
      : open.length > 0
        ? ["No blockers · notes still open", "text-amber-700", SEVERITY_ICON.major]
        : ["Clean proof · nothing open", "text-cleared-700", CircleCheck];
  return (
    <div className="mb-4 flex flex-wrap items-center gap-x-4 gap-y-2 rounded-lg border border-rule bg-sheet px-4 py-2.5" role="region" aria-label="Proof summary">
      <p className={clsx("inline-flex items-center gap-2 text-[15px] font-semibold", tone)}>
        <Icon className="h-4 w-4" aria-hidden="true" />
        {label}
      </p>
      <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label="Show notes by severity">
        {SEVERITIES.map((s) => {
          const on = !hidden.has(s);
          const SevIcon = SEVERITY_ICON[s];
          return (
            <button
              key={s}
              type="button"
              aria-pressed={on}
              onClick={() => onToggle(s)}
              className={clsx(
                "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs transition-colors duration-150",
                on ? SEVERITY_STYLE[s].chip : "border-rule bg-transparent text-graphite line-through decoration-graphite/60",
              )}
            >
              <SevIcon className="h-3.5 w-3.5" aria-hidden="true" />
              {count(s)} {s}
            </button>
          );
        })}
      </div>
      <div className="ml-auto flex items-center gap-2">
        {canDecide && onAcceptAll && fixable > 0 && (
          <button type="button" className="btn-teal py-1.5 text-sm" disabled={busy} onClick={onAcceptAll}>
            {busy ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <CheckCheck className="h-4 w-4" aria-hidden="true" />}
            Accept all suggested fixes
            <span className="rounded-full bg-on-action/15 px-1.5 text-xs tabular-nums">{fixable}</span>
          </button>
        )}
        <Legend />
      </div>
    </div>
  );
}
