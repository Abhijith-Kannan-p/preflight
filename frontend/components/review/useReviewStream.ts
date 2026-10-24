"use client";

// Live checker progress over Server-Sent Events. The backend replays earlier events, so
// opening the page mid-review still shows every step.

import { useEffect, useState } from "react";

import { API_URL, getToken } from "@/lib/api";

export type CheckerState = "waiting" | "running" | "done" | "failed";

export const CHECKERS: { name: string; label: string }[] = [
  { name: "terminology", label: "Terminology and product names" },
  { name: "disclaimer", label: "Required disclaimers" },
  { name: "channel", label: "Channel limits" },
  { name: "readability", label: "Readability" },
  { name: "style", label: "Punctuation and capitals" },
  { name: "tone", label: "Tone of voice" },
  { name: "claims", label: "Claim Ledger" },
  { name: "suggestions", label: "Suggestions" },
];

export interface StreamState {
  checkers: Record<string, { state: CheckerState; findings?: number; ms?: number }>;
  findingsSoFar: number;
  degraded: string | null;
  done: boolean;
  failed: string | null;
}

const initial = (): StreamState => ({
  checkers: Object.fromEntries(CHECKERS.map((c) => [c.name, { state: "waiting" as CheckerState }])),
  findingsSoFar: 0,
  degraded: null,
  done: false,
  failed: null,
});

export function useReviewStream(reviewId: string, revisionNumber: number | undefined, active: boolean, onComplete: () => void) {
  const [state, setState] = useState<StreamState>(initial);

  useEffect(() => {
    if (!active || revisionNumber === undefined) return;
    setState(initial());
    const token = getToken();
    if (!token) return;
    const source = new EventSource(`${API_URL}/api/reviews/${reviewId}/events?token=${encodeURIComponent(token)}&revision=${revisionNumber}`);
    const update = (fn: (s: StreamState) => StreamState) => setState((s) => fn(s));

    source.addEventListener("checker_started", (e) => {
      const { checker } = JSON.parse((e as MessageEvent).data);
      update((s) => ({ ...s, checkers: { ...s.checkers, [checker]: { state: "running" } } }));
    });
    source.addEventListener("checker_done", (e) => {
      const run = JSON.parse((e as MessageEvent).data);
      update((s) => ({ ...s, checkers: { ...s.checkers, [run.name]: { state: run.ok ? "done" : "failed", findings: run.findings, ms: run.ms } } }));
    });
    source.addEventListener("finding", () => update((s) => ({ ...s, findingsSoFar: s.findingsSoFar + 1 })));
    source.addEventListener("degraded", (e) => {
      const { reason } = JSON.parse((e as MessageEvent).data);
      update((s) => ({ ...s, degraded: reason ?? "AI checks temporarily limited" }));
    });
    source.addEventListener("review_complete", (e) => {
      const data = JSON.parse((e as MessageEvent).data);
      update((s) => ({ ...s, done: true, failed: data.ok ? null : data.error }));
      source.close();
      onComplete();
    });
    source.onerror = () => {
      // The browser reconnects automatically; if the review already finished, refresh once.
      if (source.readyState === EventSource.CLOSED) onComplete();
    };
    return () => source.close();
  }, [reviewId, revisionNumber, active, onComplete]);

  return state;
}
