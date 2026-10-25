"use client";

import { clsx } from "clsx";
import { AlertTriangle, ArrowLeft, FileText } from "lucide-react";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";
import useSWR from "swr";

import { BrandScoreGauge } from "@/components/BrandScore";
import { Tour, type TourStep } from "@/components/Tour";
import { ActionBar } from "@/components/review/ActionBar";
import { AiDisclosure } from "@/components/review/AiDisclosure";
import { CheckerProgress } from "@/components/review/CheckerProgress";
import { ClaimLedger } from "@/components/review/ClaimLedger";
import { Comments } from "@/components/review/Comments";
import { DraftView } from "@/components/review/DraftView";
import { FindingsPanel } from "@/components/review/FindingsPanel";
import { Revisions } from "@/components/review/Revisions";
import { useReviewStream } from "@/components/review/useReviewStream";
import { Chip, ErrorState, Skeleton } from "@/components/ui";
import { CHANNEL_LABEL, STATE_STYLE } from "@/lib/format";
import { useSession } from "@/lib/session";
import type { Review } from "@/lib/types";

const TABS = ["Findings", "Claim Ledger", "Revisions", "Comments", "AI disclosure"] as const;
type Tab = (typeof TABS)[number];

const TOUR: TourStep[] = [
  { target: "draft", title: "Your draft, annotated", text: "Each highlight is a finding, coloured by severity: red critical, amber major, blue minor. Click one to jump to its explanation." },
  { target: "brand-score", title: "Brand Score", text: "Starts at 100 and drops 25 per critical, 10 per major and 3 per minor open finding. It rises as you fix things." },
  { target: "findings", title: "Cited, explainable findings", text: "Every finding names its rule and source page, shows evidence and confidence, and offers a minimal fix with a drift score. You decide: Accept, Edit, Dispute or Escalate." },
  { target: "tabs", title: "The Claim Ledger", text: "Every factual claim is checked against approved facts by a local NLI model, exact numbers and a quote check. Green rows show what Preflight confirmed, not just what it flagged." },
  { target: "actions", title: "Re-check, then submit", text: "Re-check applies your accepted changes as a new revision. Submit unlocks once no critical finding is open. Then switch to abhi4 (Approver) in the top right to approve and get the receipt." },
];

function Workspace() {
  const { id } = useParams<{ id: string }>();
  const params = useSearchParams();
  const { user, can } = useSession();
  const { data, error, mutate } = useSWR<Review>(`/api/reviews/${id}`);
  const [tab, setTab] = useState<Tab>("Findings");
  const [focused, setFocused] = useState<string | null>(null);
  const pending = data?.revision.review_status === "pending";
  const refresh = useCallback(() => void mutate(), [mutate]);
  const reload = useCallback(() => mutate(), [mutate]);
  const stream = useReviewStream(id, data?.revision.number, Boolean(pending), refresh);

  useEffect(() => {
    if (!pending) return;
    // Safety net if the event stream is blocked by a proxy: poll until the review finishes.
    const timer = window.setInterval(refresh, 4000);
    return () => window.clearInterval(timer);
  }, [pending, refresh]);

  if (error) return <ErrorState message={error.message} onRetry={refresh} />;
  if (!data) {
    return (
      <div className="grid gap-6 lg:grid-cols-[1.1fr_1fr]">
        <Skeleton className="h-96" />
        <Skeleton className="h-96" />
      </div>
    );
  }

  const { submission, revision, findings, claims } = data;
  const isAuthor = can("submit_content") && (user?.role !== "creator" || submission.author.id === user?.id);
  const editable = submission.state === "draft" || submission.state === "changes_requested";
  const openCount = findings.filter((f) => ["open", "escalated", "disputed"].includes(f.status) && !f.needs_review).length;
  const latest = data.revisions.at(-1)?.number ?? revision.number;

  return (
    <div className="animate-fade-in">
      <Link href="/app" className="mb-3 inline-flex items-center gap-1 text-sm text-navy-500 hover:text-navy">
        <ArrowLeft className="h-4 w-4" aria-hidden="true" /> Dashboard
      </Link>
      <div className="mb-4 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">{submission.title}</h1>
          <p className="mt-1 flex flex-wrap items-center gap-2 text-sm text-navy-500">
            <Chip className={STATE_STYLE[submission.state].chip}>{STATE_STYLE[submission.state].label}</Chip>
            <span>{CHANNEL_LABEL[submission.channel] ?? submission.channel}</span>·<span>by {submission.author.name}</span>·<span>revision {revision.number}</span>
            {revision.report.cached_from && <span title="Same content, rulebook and facts as an earlier review">· instant (cached)</span>}
          </p>
        </div>
        <ActionBar review={data} onChanged={refresh} onRechecked={refresh} />
      </div>

      {revision.degraded && (
        <div role="status" className="mb-4 flex items-center gap-2 rounded-xl border border-amber/30 bg-amber-50 px-3 py-2 text-sm text-amber-700">
          <AlertTriangle className="h-4 w-4" aria-hidden="true" /> AI checks temporarily limited. Deterministic checks and the local Claim Ledger still ran; tone and wording used offline fallbacks.
        </div>
      )}
      {pending && stream.degraded && !revision.degraded && (
        <div role="status" className="mb-4 rounded-xl border border-amber/30 bg-amber-50 px-3 py-2 text-sm text-amber-700">AI checks temporarily limited: {stream.degraded}</div>
      )}
      {revision.review_status === "failed" && <div className="mb-4"><ErrorState message="This review failed. Press Re-check to try again." /></div>}

      <div className="grid gap-6 lg:grid-cols-[1.1fr_1fr]">
        <section className="card h-fit p-6 lg:sticky lg:top-20" aria-label="Draft">
          <div className="mb-4 flex items-center justify-between text-xs text-navy-500">
            <span className="inline-flex items-center gap-1">
              <FileText className="h-3.5 w-3.5" aria-hidden="true" /> {revision.source_format.toUpperCase()} · {revision.content.length.toLocaleString()} characters
            </span>
          </div>
          <DraftView blocks={revision.blocks} findings={findings} focused={focused} onFocus={(f) => { setTab("Findings"); setFocused(f); }} />
          <div className="mt-6 flex flex-wrap gap-3 border-t border-paper-200 pt-4 text-[11px] text-navy-500">
            <span className="inline-flex items-center gap-1"><span className="h-2 w-3 rounded bg-danger-100" /> Critical</span>
            <span className="inline-flex items-center gap-1"><span className="h-2 w-3 rounded bg-amber-100" /> Major</span>
            <span className="inline-flex items-center gap-1"><span className="h-2 w-3 rounded bg-info-100" /> Minor</span>
            <span className="ml-auto">J / K to move · A accept · D dispute · ? help</span>
          </div>
        </section>

        <section aria-label="Review results">
          <div className="card mb-4 flex flex-wrap items-center gap-6 p-4">
            <BrandScoreGauge score={revision.brand_score} pending={pending} />
            <div className="min-w-[220px] flex-1">
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-navy-500">
                {pending ? `Checking… ${stream.findingsSoFar} finding(s) so far` : `${openCount} open finding(s) · ${claims.length} claim(s) checked`}
              </p>
              <CheckerProgress stream={stream} report={revision.report.checkers} pending={pending} />
            </div>
          </div>

          <div role="tablist" aria-label="Review sections" className="mb-4 flex gap-1 overflow-x-auto rounded-xl bg-paper-100 p-1" data-tour="tabs">
            {TABS.map((t) => (
              <button key={t} role="tab" type="button" aria-selected={tab === t} onClick={() => setTab(t)} className={clsx("whitespace-nowrap rounded-lg px-3 py-1.5 text-sm font-medium", tab === t ? "bg-paper-50 text-navy shadow-card" : "text-navy-500 hover:text-navy")}>
                {t}
                {t === "Findings" && !pending && <span className="ml-1 font-mono text-xs text-navy-500">{findings.length}</span>}
                {t === "Claim Ledger" && !pending && <span className="ml-1 font-mono text-xs text-navy-500">{claims.length}</span>}
              </button>
            ))}
          </div>

          <div role="tabpanel">
            {pending && tab !== "Comments" ? (
              <div className="space-y-3">
                <Skeleton className="h-28" />
                <Skeleton className="h-28" />
                <Skeleton className="h-28" />
              </div>
            ) : (
              <>
                {tab === "Findings" && <FindingsPanel findings={findings} focused={focused} onFocus={setFocused} canDecide={isAuthor && editable && revision.number === latest} canEscalate={can("escalate")} onChanged={reload} />}
                {tab === "Claim Ledger" && <ClaimLedger claims={claims} />}
                {tab === "Revisions" && <Revisions reviewId={id} revisions={data.revisions} />}
                {tab === "Comments" && <Comments reviewId={id} decisions={data.decisions} />}
                {tab === "AI disclosure" && <AiDisclosure ai={revision.report.ai} tone={revision.report.tone} />}
              </>
            )}
          </div>
        </section>
      </div>
      <Tour steps={TOUR} autoStart={params.get("tour") === "1"} ready={!pending} />
    </div>
  );
}

export default function ReviewPage() {
  return (
    <Suspense fallback={<Skeleton className="h-96" />}>
      <Workspace />
    </Suspense>
  );
}
