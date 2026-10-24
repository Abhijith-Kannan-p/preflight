"use client";

import { clsx } from "clsx";
import { AlertTriangle, Check, Circle, Loader2 } from "lucide-react";

import type { CheckerRun } from "@/lib/types";

import { CHECKERS, type StreamState } from "./useReviewStream";

/** Each checker ticks green as it finishes. Uses the live stream while running and the
 * stored report once complete. */
export function CheckerProgress({ stream, report, pending }: { stream: StreamState; report?: CheckerRun[]; pending: boolean }) {
  const stored = Object.fromEntries((report ?? []).map((r) => [r.name, r]));
  return (
    <ul className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-xs" aria-label="Checker progress" data-tour="progress">
      {CHECKERS.map((c) => {
        const live = stream.checkers[c.name];
        const run = stored[c.name];
        const state = pending ? live?.state ?? "waiting" : run ? (run.ok ? "done" : "failed") : "done";
        const count = pending ? live?.findings : run?.findings;
        return (
          <li key={c.name} className="flex items-center gap-2">
            {state === "done" && <Check className="h-3.5 w-3.5 text-teal" aria-hidden="true" />}
            {state === "running" && <Loader2 className="h-3.5 w-3.5 animate-spin text-info" aria-hidden="true" />}
            {state === "waiting" && <Circle className="h-3.5 w-3.5 text-paper-200" aria-hidden="true" />}
            {state === "failed" && <AlertTriangle className="h-3.5 w-3.5 text-amber" aria-hidden="true" />}
            <span className={clsx("truncate", state === "waiting" ? "text-navy-300" : "text-navy")}>{c.label}</span>
            {count != null && state !== "waiting" && <span className="ml-auto font-mono text-[10px] text-navy-500">{count}</span>}
          </li>
        );
      })}
    </ul>
  );
}
