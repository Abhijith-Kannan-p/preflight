"use client";

import { AlertOctagon, FileText } from "lucide-react";
import Link from "next/link";

import { CHANNEL_LABEL, STATE_STYLE, timeAgo } from "@/lib/format";
import type { ReviewListItem } from "@/lib/types";

import { ScorePill } from "./BrandScore";
import { Chip, EmptyState, Skeleton } from "./ui";

export function ReviewList({ items, empty, showAuthor = true }: { items: ReviewListItem[] | undefined; empty: React.ReactNode; showAuthor?: boolean }) {
  if (!items) {
    return (
      <div className="space-y-2">
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} className="h-16" />
        ))}
      </div>
    );
  }
  if (!items.length) return <>{empty}</>;
  return (
    <ul className="divide-y divide-paper-200 overflow-hidden rounded-2xl border border-paper-200 bg-paper-50">
      {items.map((item) => (
        <li key={item.id}>
          <Link href={`/app/review/${item.id}`} className="flex flex-wrap items-center gap-4 px-4 py-3 hover:bg-paper-100">
            <ScorePill score={item.review_status === "complete" ? item.brand_score : null} />
            <div className="min-w-0 flex-1">
              <p className="truncate font-semibold">{item.title}</p>
              <p className="text-xs text-navy-500">
                {CHANNEL_LABEL[item.channel] ?? item.channel} · revision {item.revision}
                {showAuthor && ` · ${item.author.name}`} · {timeAgo(item.updated_at)}
              </p>
            </div>
            {item.open_criticals > 0 && (
              <Chip className="bg-danger-50 text-danger-700 ring-danger/30">
                <AlertOctagon className="h-3 w-3" aria-hidden="true" /> {item.open_criticals} critical
              </Chip>
            )}
            <Chip className={STATE_STYLE[item.state].chip}>{STATE_STYLE[item.state].label}</Chip>
          </Link>
        </li>
      ))}
    </ul>
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
