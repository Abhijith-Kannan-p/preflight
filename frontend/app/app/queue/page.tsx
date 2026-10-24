"use client";

import { Inbox } from "lucide-react";
import useSWR from "swr";

import { ReviewList } from "@/components/ReviewList";
import { EmptyState, ErrorState, PageHeader } from "@/components/ui";
import { useSession } from "@/lib/session";
import type { ReviewListItem } from "@/lib/types";

export default function QueuePage() {
  const { can } = useSession();
  const queue = useSWR<ReviewListItem[]>(can("approve") ? "/api/reviews?scope=queue" : null, { refreshInterval: 8000 });

  if (!can("approve")) {
    return <ErrorState message="Only approvers and brand managers can approve content. Switch to abhi4 (Approver) in the top right." />;
  }
  return (
    <div className="animate-fade-in">
      <PageHeader title="Approval queue" subtitle="Drafts waiting for your decision. Open one to see its findings, approve it, or request changes with a comment. Critical findings must be resolved or overridden with a written reason." />
      {queue.error ? (
        <ErrorState message={queue.error.message} onRetry={() => queue.mutate()} />
      ) : (
        <ReviewList
          items={queue.data}
          empty={<EmptyState icon={<Inbox className="h-8 w-8" />} title="The queue is empty" text="Switch to abhi1, run a sample draft, fix its critical findings and press Submit. It will appear here." />}
        />
      )}
    </div>
  );
}
