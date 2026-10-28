"use client";

// The seven checkers as a preflight checklist: queued → checking → done, with time and count.
// The Claim Ledger row lists claims as they are verified.

import { clsx } from "clsx";
import { AlertTriangle, Check, Circle, Loader2 } from "lucide-react";

import { VERDICT_STYLE } from "@/lib/format";
import type { CheckerRun, Claim } from "@/lib/types";

import { CHECKERS, type StreamState, VISUAL_CHECKERS } from "./useReviewStream";

type RowState = "queued" | "checking" | "done" | "failed";

const GLYPH: Record<RowState, React.ReactNode> = {
  queued: <Circle className="h-3.5 w-3.5 text-rule" strokeWidth={1.75} aria-hidden="true" />,
  checking: <Loader2 className="h-3.5 w-3.5 animate-spin text-slate" strokeWidth={1.75} aria-hidden="true" />,
  done: <Check className="h-3.5 w-3.5 text-cleared" strokeWidth={2} aria-hidden="true" />,
  failed: <AlertTriangle className="h-3.5 w-3.5 text-amber" strokeWidth={1.75} aria-hidden="true" />,
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
            <div className="grid grid-cols-[1.5rem_1.25rem_1fr_auto_auto] items-center gap-2">
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
