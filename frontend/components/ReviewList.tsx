"use client";

import { AlertOctagon, FileText } from "lucide-react";
import Link from "next/link";

import { CHANNEL_LABEL, STATE_STYLE, timeAgo } from "@/lib/format";
import type { ReviewListItem } from "@/lib/types";

import { ScorePill } from "./BrandScore";
import { EmptyState, Skeleton } from "./ui";

const BOARD: Record<ReviewListItem["state"], string> = {
  draft: "text-graphite",
  in_review: "text-slate-700",
  changes_requested: "text-amber-700",
  approved: "text-cleared-700",
  published: "text-ink",
};

/** Reviews as a departures board: one ruled row per draft, status in board capitals. */
export function ReviewList({ items, empty, showAuthor = true }: { items: ReviewListItem[] | undefined; empty: React.ReactNode; showAuthor?: boolean }) {
  if (!items) {
    return (
      <div className="space-y-2">
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} className="h-12" />
        ))}
      </div>
    );
  }
  if (!items.length) return <>{empty}</>;
  return (
    <div className="overflow-x-auto border-y border-ink">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-rule text-left">
            <th scope="col" className="label w-14 py-2 pr-3 font-normal">Score</th>
            <th scope="col" className="label py-2 pr-3 font-normal">Draft</th>
            <th scope="col" className="label hidden py-2 pr-3 font-normal md:table-cell">Channel</th>
            <th scope="col" className="label hidden py-2 pr-3 font-normal sm:table-cell">Rev</th>
            {showAuthor && <th scope="col" className="label hidden py-2 pr-3 font-normal lg:table-cell">Author</th>}
            <th scope="col" className="label hidden py-2 pr-3 font-normal md:table-cell">Updated</th>
            <th scope="col" className="label py-2 text-right font-normal">Status</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-rule">
          {items.map((item) => (
            <tr key={item.id} className="relative hover:bg-sheet">
              <td className="py-2.5 pr-3 align-top">
                <ScorePill score={item.review_status === "complete" ? item.brand_score : null} />
              </td>
              <td className="max-w-0 py-2.5 pr-3 align-top">
                <Link href={`/app/review/${item.id}`} className="block truncate font-medium text-ink after:absolute after:inset-0 focus-visible:outline-none focus-visible:after:outline focus-visible:after:outline-2 focus-visible:after:outline-ink">
                  {item.title}
                </Link>
                {item.open_criticals > 0 && (
                  <span className="mt-0.5 inline-flex items-center gap-1 font-mono text-[11px] text-signal-700">
                    <AlertOctagon className="h-3 w-3" aria-hidden="true" /> {item.open_criticals} critical open
                  </span>
                )}
              </td>
              <td className="hidden py-2.5 pr-3 align-top text-graphite md:table-cell">{CHANNEL_LABEL[item.channel] ?? item.channel}</td>
              <td className="hidden py-2.5 pr-3 align-top font-mono text-graphite sm:table-cell">{String(item.revision).padStart(2, "0")}</td>
              {showAuthor && <td className="hidden py-2.5 pr-3 align-top text-graphite lg:table-cell">{item.author.name}</td>}
              <td className="hidden whitespace-nowrap py-2.5 pr-3 align-top font-mono text-xs text-graphite md:table-cell">{timeAgo(item.updated_at)}</td>
              <td className={`whitespace-nowrap py-2.5 text-right align-top font-mono text-xs font-medium uppercase tracking-wider ${BOARD[item.state]}`}>
                {STATE_STYLE[item.state].label}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function NoReviews() {
  return (
    <EmptyState
      icon={<FileText className="h-8 w-8" />}
      title="No reviews yet"
      text="Try a sample draft: the LinkedIn post from our Round 1 plan has six problems for Preflight to find."
      action={
        <Link href="/app/review/new?sample=sample_linkedin&tour=1" className="btn-teal">
          Try a sample draft
        </Link>
      }
    />
  );
}
