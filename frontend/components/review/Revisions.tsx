"use client";

import { diffWords } from "diff";
import { GitCompare } from "lucide-react";
import { useEffect, useState } from "react";
import useSWR from "swr";

import { timeAgo } from "@/lib/format";
import type { Finding, RevisionSummary } from "@/lib/types";

import { ScorePill } from "../BrandScore";
import { EmptyState, ErrorState, Skeleton } from "../ui";

interface DiffOut {
  from_number: number;
  to_number: number;
  from_text: string;
  to_text: string;
  from_score: number | null;
  to_score: number | null;
  resolved: Finding[];
  introduced: Finding[];
}

export function Revisions({ reviewId, revisions }: { reviewId: string; revisions: RevisionSummary[] }) {
  const latest = revisions.at(-1)?.number ?? 1;
  const [pair, setPair] = useState<[number, number]>([Math.max(1, latest - 1), latest]);
  useEffect(() => setPair([Math.max(1, latest - 1), latest]), [latest]);
  const { data, error, mutate } = useSWR<DiffOut>(revisions.length > 1 ? `/api/reviews/${reviewId}/diff?from=${pair[0]}&to=${pair[1]}` : null);

  if (revisions.length < 2) {
    return (
      <EmptyState
        icon={<GitCompare className="h-8 w-8" />}
        title="Only one revision so far"
        text="Accept or edit suggestions, then press Re-check. Each re-check creates a new revision you can compare here, with the findings it resolved."
      />
    );
  }
  return (
    <div className="space-y-4">
      <ol className="flex flex-wrap gap-2">
        {revisions.map((r) => (
          <li key={r.id} className="flex items-center gap-2 rounded-xl border border-paper-200 bg-paper-50 px-3 py-1.5 text-xs">
            <span className="font-semibold">Revision {r.number}</span>
            <ScorePill score={r.brand_score} />
            <span className="text-navy-500">{timeAgo(r.created_at)}</span>
          </li>
        ))}
      </ol>
      <div className="flex flex-wrap items-center gap-2 text-sm">
        Compare
        {[0, 1].map((side) => (
          <select
            key={side}
            aria-label={side === 0 ? "From revision" : "To revision"}
            className="input w-auto py-1"
            value={pair[side]}
            onChange={(e) => setPair((p) => (side === 0 ? [Number(e.target.value), p[1]] : [p[0], Number(e.target.value)]))}
          >
            {revisions.map((r) => (
              <option key={r.number} value={r.number}>
                Revision {r.number}
              </option>
            ))}
          </select>
        ))}
      </div>
      {error && <ErrorState message={error.message} onRetry={() => mutate()} />}
      {!data && !error && <Skeleton className="h-40" />}
      {data && (
        <>
          <div className="card p-4 text-[15px] leading-relaxed" aria-label="Word-level difference">
            {diffWords(data.from_text, data.to_text).map((part, i) =>
              part.added ? (
                <ins key={i} className="rounded bg-teal-100 px-0.5 no-underline">{part.value}</ins>
              ) : part.removed ? (
                <del key={i} className="rounded bg-paper-100 px-0.5 text-navy-500">{part.value}</del>
              ) : (
                <span key={i} className="whitespace-pre-wrap">{part.value}</span>
              ),
            )}
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="card p-4">
              <p className="label">Resolved by this change ({data.resolved.length})</p>
              <ul className="space-y-1 text-sm">
                {data.resolved.map((f) => (
                  <li key={f.id}>
                    <span className="font-mono text-xs font-semibold text-teal-700">{f.rule.id}</span> “{f.text}”
                  </li>
                ))}
                {!data.resolved.length && <li className="text-navy-500">None</li>}
              </ul>
            </div>
            <div className="card p-4">
              <p className="label">New in revision {data.to_number} ({data.introduced.length})</p>
              <ul className="space-y-1 text-sm">
                {data.introduced.map((f) => (
                  <li key={f.id}>
                    <span className="font-mono text-xs font-semibold text-ink">{f.rule.id}</span> “{f.text}”
                  </li>
                ))}
                {!data.introduced.length && <li className="text-navy-500">None</li>}
              </ul>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
