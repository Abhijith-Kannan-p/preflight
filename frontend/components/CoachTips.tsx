"use client";

// The Creator Coach's tips, shared by the Governance page and the New review page.

import Link from "next/link";
import useSWR from "swr";

import { api } from "@/lib/api";
import { useSession } from "@/lib/session";

import { RuleTag } from "./review/SourcePanel";

export interface CoachTip {
  rule: string;
  title: string;
  times: number;
  guidance: string;
  approved_wording: string | null;
  your_example: string | null;
  your_fix: string | null;
  source_ref: string;
}

export interface CoachProfile {
  user: { id: string; name: string; title: string };
  submissions: number;
  repeat_rate: number | null;
  baseline_rate: number | null;
  recent_rate: number | null;
  trend: string;
  recurring: { rule: string; title: string; drafts: number }[];
  tips: CoachTip[];
  weekly: { week: string; drafts: number; findings_per_draft: number }[];
}

export function TipCard({ tip }: { tip: CoachTip }) {
  return (
    <li className="border-l-2 border-teal bg-sheet px-3 py-2 text-sm">
      <p className="flex flex-wrap items-center gap-2">
        <RuleTag id={tip.rule} source={tip.source_ref} />
        <span className="font-medium text-ink">{tip.title}</span>
        <span className="font-mono text-[11px] text-graphite">in {tip.times} of your drafts</span>
      </p>
      <p className="mt-1 text-graphite">{tip.guidance}</p>
      {tip.approved_wording && (
        <p className="mt-1">
          <span className="label mb-0 inline">Approved wording</span> <span className="text-ink">{tip.approved_wording}</span>
        </p>
      )}
      {tip.your_example && (
        <p className="mt-1 text-xs">
          Last time you wrote <span className="font-serif text-ink line-through decoration-graphite">{tip.your_example}</span>
          {tip.your_fix && (
            <>
              {" "}
              and changed it to <span className="font-serif text-ink">{tip.your_fix}</span>
            </>
          )}
          {/[.!?]$/.test(tip.your_fix ?? tip.your_example) ? "" : "."}
        </p>
      )}
    </li>
  );
}

/** A compact "before you write" panel: the author's top two recurring rules, with tips. */
export function CoachPanel() {
  const { user } = useSession();
  const { data } = useSWR<CoachProfile>(user ? ["/api/coach/me", user.id] : null, ([path]: [string]) => api<CoachProfile>(path));
  if (!data || data.tips.length === 0) return null;
  return (
    <section aria-labelledby="coach-panel" className="mb-6 border border-rule bg-sheet p-4">
      <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="coach-panel" className="label mb-0">Your coach · before you write</h2>
        <Link href="/app/governance?tab=creator" className="text-xs text-ink underline decoration-rule underline-offset-4 hover:decoration-ink">
          Full coach
        </Link>
      </div>
      <ul className="grid gap-2 md:grid-cols-2">
        {data.tips.slice(0, 2).map((t) => (
          <TipCard key={t.rule} tip={t} />
        ))}
      </ul>
    </section>
  );
}
