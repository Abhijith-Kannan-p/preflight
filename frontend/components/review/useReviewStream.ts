"use client";

// Live checker progress over Server-Sent Events. Reviews are server-side jobs and the backend
// replays earlier events, so reloading the page (or coming back to it) reattaches to the job.
// If the stream drops it is reopened with backoff; the page also polls as a fallback. When
// nothing arrives for a minute the review is reported as stalled instead of spinning forever.

import { useEffect, useState } from "react";

import { API_URL, getToken } from "@/lib/api";
import type { Verdict } from "@/lib/types";

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

export const STALL_MS = 60_000;

export interface StreamState {
  checkers: Record<string, { state: CheckerState; findings?: number; ms?: number }>;
  findingsSoFar: number;
  claims: { text: string; verdict: Verdict }[];
  queue: { position: number; ahead: number } | null;
  degraded: string | null;
  done: boolean;
  failed: string | null;
  /** True while the live connection is down and being retried. */
  reconnecting: boolean;
  /** No progress for STALL_MS while the review is still pending. */
  stalled: boolean;
}

const initial = (): StreamState => ({
  checkers: Object.fromEntries(CHECKERS.map((c) => [c.name, { state: "waiting" as CheckerState }])),
  findingsSoFar: 0,
  claims: [],
  queue: null,
  degraded: null,
  done: false,
  failed: null,
  reconnecting: false,
  stalled: false,
});

export function useReviewStream(reviewId: string, revisionNumber: number | undefined, active: boolean, onComplete: () => void) {
  const [state, setState] = useState<StreamState>(initial);

  useEffect(() => {
    if (!active || revisionNumber === undefined) return;
    setState(initial());
    let source: EventSource | null = null;
    let retryTimer = 0;
    let attempt = 0;
    let closed = false;
    let lastProgress = Date.now();
    const update = (fn: (s: StreamState) => StreamState) => setState((s) => fn(s));
    const progressed = () => {
      lastProgress = Date.now();
      update((s) => (s.stalled || s.reconnecting ? { ...s, stalled: false, reconnecting: false } : s));
    };

    const connect = () => {
      const token = getToken();
      if (!token || closed) return;
      // Replayed events rebuild the state from scratch on every (re)connection.
      setState((s) => ({ ...initial(), reconnecting: s.reconnecting }));
      source = new EventSource(`${API_URL}/api/reviews/${reviewId}/events?token=${encodeURIComponent(token)}&revision=${revisionNumber}`);
      const on = (name: string, handler: (data: Record<string, unknown>) => void) =>
        source!.addEventListener(name, (e) => {
          attempt = 0;
          progressed();
          handler(JSON.parse((e as MessageEvent).data));
        });

      on("queued", (d) => update((s) => ({ ...s, queue: { position: Number(d.position), ahead: Number(d.ahead) } })));
      on("review_started", () => update((s) => ({ ...s, queue: null })));
      on("checker_started", (d) => update((s) => ({ ...s, queue: null, checkers: { ...s.checkers, [String(d.checker)]: { state: "running" } } })));
      on("checker_done", (run) =>
        update((s) => ({ ...s, checkers: { ...s.checkers, [String(run.name)]: { state: run.ok ? "done" : "failed", findings: Number(run.findings), ms: Number(run.ms) } } })),
      );
      on("finding", () => update((s) => ({ ...s, findingsSoFar: s.findingsSoFar + 1 })));
      on("claim", (d) => update((s) => ({ ...s, claims: [...s.claims, { text: String(d.text), verdict: d.verdict as Verdict }] })));
      on("degraded", (d) => update((s) => ({ ...s, degraded: String(d.reason ?? "AI checks temporarily limited") })));
      on("review_complete", (d) => {
        closed = true;
        update((s) => ({ ...s, done: true, failed: d.ok ? null : String(d.error ?? "The review failed.") }));
        source?.close();
        onComplete();
      });
      source.onerror = () => {
        if (closed || !source) return;
        // The browser retries on its own while CONNECTING; once CLOSED we reopen with backoff.
        update((s) => ({ ...s, reconnecting: true }));
        if (source.readyState === EventSource.CLOSED) {
          source.close();
          onComplete(); // refresh once: the review may already have finished
          const delay = Math.min(1000 * 2 ** attempt, 15_000);
          attempt += 1;
          retryTimer = window.setTimeout(connect, delay);
        }
      };
    };

    connect();
    const watchdog = window.setInterval(() => {
      if (!closed && Date.now() - lastProgress > STALL_MS) update((s) => (s.stalled ? s : { ...s, stalled: true }));
    }, 5000);
    return () => {
      closed = true;
      source?.close();
      window.clearTimeout(retryTimer);
      window.clearInterval(watchdog);
    };
  }, [reviewId, revisionNumber, active, onComplete]);

  return state;
}
