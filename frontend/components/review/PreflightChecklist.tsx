"use client";

// The seven checkers as a preflight checklist: queued → checking → done, with time and count.
// The Claim Ledger row lists claims as they are verified.

import { clsx } from "clsx";
import { AlertTriangle, Check, Circle, Loader2 } from "lucide-react";

import { VERDICT_STYLE } from "@/lib/format";
import type { CheckerRun, Claim } from "@/lib/types";

import { CHECKERS, type StreamState, VISUAL_CHECKERS } from "./useReviewStream";

type RowState = "queued" | "checking" | "done" | "failed";

const chip = "inline-flex h-5 w-5 items-center justify-center rounded-full";
const GLYPH: Record<RowState, React.ReactNode> = {
  queued: (
    <span className={clsx(chip, "border border-rule")} aria-hidden="true">
      <Circle className="h-2 w-2 text-rule" strokeWidth={3} />
    </span>
  ),
  checking: (
    <span className={clsx(chip, "bg-slate-50 text-slate-700")} aria-hidden="true">
      <Loader2 className="h-3 w-3 animate-spin" strokeWidth={2} />
    </span>
  ),
  done: (
    <span className={clsx(chip, "animate-tick bg-cleared-50 text-cleared-700")} aria-hidden="true">
      <Check className="h-3 w-3" strokeWidth={2.5} />
    </span>
  ),
  failed: (
    <span className={clsx(chip, "bg-amber-50 text-amber-700")} aria-hidden="true">
      <AlertTriangle className="h-3 w-3" strokeWidth={2} />
    </span>
  ),
};

const STATUS: Record<RowState, string> = { queued: "Queued", checking: "Checking", done: "Done", failed: "Fallback" };

export function PreflightChecklist({
  stream,
  report,
  pending,
  claims,
  visual = false,
}: {
  stream: StreamState;
  report?: CheckerRun[];
  pending: boolean;
  claims: Claim[];
  /** An image or scan: the OCR and visual steps run first. */
  visual?: boolean;
}) {
  const stored: Record<string, CheckerRun> = Object.fromEntries((report ?? []).map((r) => [r.name, r]));
  const rows = visual ? [...VISUAL_CHECKERS, ...CHECKERS] : CHECKERS;
  return (
    <ol className="w-full divide-y divide-rule border-y border-rule text-sm" aria-label="Preflight checklist" data-tour="progress">
      {rows.map((c, index) => {
        const live = stream.checkers[c.name];
        const run = stored[c.name];
        const state: RowState = pending
          ? live?.state === "running"
            ? "checking"
            : live?.state === "waiting" || !live
              ? "queued"
              : live.state
          : run
            ? run.ok
              ? "done"
              : "failed"
            : "done";
        const ms = pending ? live?.ms : run?.ms;
        const count = pending ? live?.findings : run?.findings;
        const liveClaims = c.name === "claims" ? (pending ? stream.claims : claims.map((cl) => ({ text: cl.text, verdict: cl.verdict }))) : [];
        return (
          <li key={c.name} className="py-1.5">
            <div className="grid grid-cols-[1.5rem_1.5rem_1fr_auto_auto] items-center gap-2">
              <span className="font-mono text-[11px] text-graphite">{String(index + 1).padStart(2, "0")}</span>
              {GLYPH[state]}
              <span className={clsx(state === "queued" ? "text-graphite" : "text-ink")}>{c.label}</span>
              <span className="font-mono text-[11px] text-graphite">{ms != null && state !== "queued" && state !== "checking" ? `${(ms / 1000).toFixed(1)} s` : STATUS[state]}</span>
              <span className="w-14 text-right font-mono text-[11px] text-graphite">{count != null && state !== "queued" && state !== "checking" ? `${count} found` : ""}</span>
            </div>
            {c.name === "claims" && liveClaims.length > 0 && (
              <ul className="ml-[3.25rem] mt-1 space-y-0.5" aria-label="Claims verified">
                {liveClaims.slice(0, 6).map((cl, i) => (
                  <li key={i} className="flex items-baseline gap-2 text-xs">
                    <span className={clsx("shrink-0 rounded-sm border px-1 font-mono text-[10px] uppercase", VERDICT_STYLE[cl.verdict].chip)}>{VERDICT_STYLE[cl.verdict].label}</span>
                    <span className="truncate text-graphite">“{cl.text}”</span>
                  </li>
                ))}
                {liveClaims.length > 6 && <li className="font-mono text-[11px] text-graphite">+{liveClaims.length - 6} more in the Claim Ledger tab</li>}
              </ul>
            )}
          </li>
        );
      })}
    </ol>
  );
}
