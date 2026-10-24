"use client";

import { Inbox, Plus } from "lucide-react";
import Link from "next/link";
import useSWR from "swr";

import { ReviewList, NoReviews } from "@/components/ReviewList";
import { EmptyState, ErrorState, PageHeader } from "@/components/ui";
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
        <div className="mb-8 grid gap-4 sm:grid-cols-3">
          <div className="card p-5">
            <p className="label">My reviews</p>
            <p className="text-3xl font-bold">{mine.data?.length ?? "…"}</p>
          </div>
          <div className="card p-5">
            <p className="label">Average Brand Score</p>
            <p className="text-3xl font-bold">{average ?? "—"}</p>
          </div>
          <div className="card p-5">
            <p className="label">Waiting for approval</p>
            <p className="text-3xl font-bold">{mine.data?.filter((r) => r.state === "in_review").length ?? "…"}</p>
          </div>
        </div>
      )}

      {can("approve") && (
        <section className="mb-8" aria-labelledby="queue">
          <div className="mb-3 flex items-center justify-between">
            <h2 id="queue" className="text-lg font-semibold">Approval queue</h2>
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
          <h2 id="mine" className="mb-3 text-lg font-semibold">My reviews</h2>
          {mine.error ? <ErrorState message={mine.error.message} onRetry={() => mine.mutate()} /> : <ReviewList items={mine.data} empty={<NoReviews />} showAuthor={false} />}
        </section>
      ) : (
        !can("approve") && (
          <section aria-labelledby="all">
            <h2 id="all" className="mb-3 text-lg font-semibold">All reviews</h2>
            <ReviewList items={all.data} empty={<EmptyState title="No reviews yet" text="Reviews created by creators and brand managers appear here." />} />
          </section>
        )
      )}
    </div>
  );
}
