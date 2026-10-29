"use client";

import { Inbox, Plus } from "lucide-react";
import Link from "next/link";
import useSWR from "swr";

import { ReviewList, NoReviews } from "@/components/ReviewList";
import { EmptyState, ErrorState, NextStep, PageHeader } from "@/components/ui";
import { ROLE_LABEL, useSession } from "@/lib/session";
import type { ReviewListItem } from "@/lib/types";

export default function Dashboard() {
  const { user, can } = useSession();
  const mine = useSWR<ReviewListItem[]>("/api/reviews?scope=mine", { refreshInterval: 10_000 });
  const queue = useSWR<ReviewListItem[]>(can("approve") ? "/api/reviews?scope=queue" : null, { refreshInterval: 10_000 });
  const all = useSWR<ReviewListItem[]>(!can("submit_content") ? "/api/reviews?scope=all" : null);
  const scored = mine.data?.filter((r) => r.brand_score != null) ?? [];
  const average = scored.length ? Math.round(scored.reduce((s, r) => s + (r.brand_score ?? 0), 0) / scored.length) : null;

  return (
    <div className="animate-fade-in">
      <PageHeader
        eyebrow="The desk"
        title={`Welcome, ${user?.name.split(" ")[0]}`}
        subtitle={`You are signed in as ${ROLE_LABEL[user?.role ?? "creator"]}. Switch roles from the top right to see the approver's side.`}
        actions={
          can("submit_content") && (
            <Link href="/app/review/new" className="btn-teal">
              <Plus className="h-4 w-4" aria-hidden="true" /> New review
            </Link>
          )
        }
      />

      {can("submit_content") && (
        <>
          <dl className="mb-6 grid grid-cols-3 divide-x divide-rule border-y border-rule">
            {[
              ["My reviews", mine.data ? String(mine.data.length) : "…"],
              ["Average Brand Score", average != null ? String(average) : "––"],
              ["Holding for approval", mine.data ? String(mine.data.filter((r) => r.state === "in_review").length) : "…"],
            ].map(([label, value]) => (
              <div key={label} className="px-4 py-3 first:pl-0">
                <dt className="label">{label}</dt>
                <dd className="display-number mt-1">{value}</dd>
              </div>
            ))}
          </dl>
          <div className="mb-8">
            <NextStep>
              {mine.data?.some((r) => r.state === "draft" || r.state === "changes_requested")
                ? "Open a draft below and work through its margin notes."
                : "Start a new review. The LinkedIn sample shows every kind of mark."}
            </NextStep>
          </div>
        </>
      )}

      {can("approve") && (
        <section className="mb-8" aria-labelledby="queue">
          <div className="mb-3 flex items-center justify-between">
            <h2 id="queue" className="font-serif text-xl text-ink">Approval queue</h2>
            <Link href="/app/queue" className="text-sm font-medium text-teal-700 hover:underline">Open queue</Link>
          </div>
          {queue.error ? (
            <ErrorState message={queue.error.message} onRetry={() => queue.mutate()} />
          ) : (
            <ReviewList
              items={queue.data}
              empty={<EmptyState icon={<Inbox className="h-8 w-8" />} title="Nothing to approve" text="When a creator submits a draft, it appears here. Switch to abhi1, run a sample and submit it to see the flow." />}
            />
          )}
        </section>
      )}

      {can("submit_content") ? (
        <section aria-labelledby="mine">
          <h2 id="mine" className="mb-3 font-serif text-xl text-ink">My reviews</h2>
          {mine.error ? <ErrorState message={mine.error.message} onRetry={() => mine.mutate()} /> : <ReviewList items={mine.data} empty={<NoReviews />} showAuthor={false} />}
        </section>
      ) : (
        !can("approve") && (
          <section aria-labelledby="all">
            <h2 id="all" className="mb-3 font-serif text-xl text-ink">All reviews</h2>
            <ReviewList items={all.data} empty={<EmptyState title="No reviews yet" text="Reviews created by creators and brand managers appear here." />} />
          </section>
        )
      )}
    </div>
  );
}
