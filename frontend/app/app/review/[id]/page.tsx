"use client";

import { clsx } from "clsx";
import { AlertTriangle, ArrowLeft } from "lucide-react";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";
import useSWR from "swr";

import { BrandScoreGauge } from "@/components/BrandScore";
import { Tour, type TourStep } from "@/components/Tour";
import { ActionBar } from "@/components/review/ActionBar";
import { AiDisclosure } from "@/components/review/AiDisclosure";
import { ClaimLedger } from "@/components/review/ClaimLedger";
import { ClearanceStamp } from "@/components/review/ClearanceStamp";
import { Comments } from "@/components/review/Comments";
import { PreflightChecklist } from "@/components/review/PreflightChecklist";
import { ProofDesk } from "@/components/review/ProofDesk";
import { VisualDesk } from "@/components/review/VisualDesk";
import { Revisions } from "@/components/review/Revisions";
import { SourceProvider } from "@/components/review/SourcePanel";
import { type StreamState, useReviewStream } from "@/components/review/useReviewStream";
import { ErrorSheet } from "@/components/ErrorSheet";
import { Chip, ErrorState, NextStep, Skeleton } from "@/components/ui";
import type { ApiError } from "@/lib/api";
import { CHANNEL_LABEL, STATE_STYLE } from "@/lib/format";
import { useSession } from "@/lib/session";
import type { Review } from "@/lib/types";

const TABS = ["Proof", "Claim Ledger", "Revisions", "Comments", "AI disclosure"] as const;
type Tab = (typeof TABS)[number];

const TOUR: TourStep[] = [
  { target: "draft", title: "Your draft, as a proof", text: "Flagged text carries a proof mark: wavy red for critical, amber underline for major, blue dots for minor. Click a mark to bring its margin note forward." },
  { target: "brand-score", title: "Brand Score", text: "Starts at 100 and drops 25 per critical, 10 per major and 3 per minor open finding. It rises as you fix things." },
  { target: "findings", title: "Margin notes you can act on", text: "Each note names its rule and source page (click the tag to read it), shows evidence and confidence, and offers a minimal fix with a drift score. Accept, Edit, Dispute or Escalate." },
  { target: "progress", title: "The preflight checklist", text: "Seven checkers run in parallel. The Claim Ledger checks every factual claim against approved facts with a local NLI model, exact numbers and a quote check." },
  { target: "actions", title: "Re-check, then submit", text: "Re-check applies your accepted changes as a new revision. Submit unlocks once no critical finding is open. Then switch to abhi4 (Approver) in the top right to clear it." },
];

function nextStep(
  review: Review,
  isAuthor: boolean,
  canApprove: boolean,
  pending: boolean,
  stream: StreamState,
): { tone: "ink" | "signal" | "cleared"; text: string } {
  const { submission, gate, pending_edits: edits, revision } = review;
  const position = stream.queue?.position ?? review.queue_position;
  if (pending && stream.stalled)
    return { tone: "signal", text: "No progress for a minute. The engine may be busy or waking up. Preflight stops any review after two minutes so you can re-check it; you can also keep waiting." };
  if (pending && position)
    return { tone: "ink", text: position === 1 ? "Your review is next in the queue. It starts as soon as the current one finishes." : `Your review is number ${position} in the queue; ${position - 1} ahead of it.` };
  if (pending) return { tone: "ink", text: "Preflight is checking the draft. Notes appear in the margin as each check finishes." };
  if (revision.review_status === "failed") return { tone: "signal", text: `${revision.report.error ?? "This check failed."} Press Re-check to run it again.` };
  switch (submission.state) {
    case "draft":
    case "changes_requested":
      if (!isAuthor) return { tone: "ink", text: `Waiting for ${submission.author.name} to work through the margin notes.` };
      if (["image", "scan"].includes(revision.source_format) && !gate.can_submit)
        return { tone: "signal", text: "Fix the design, then upload the corrected file as a new version. Or dispute a note with a reason." };
      if (edits > 0) return { tone: "ink", text: `Re-check to apply your ${edits} change${edits > 1 ? "s" : ""} as revision ${revision.number + 1}.` };
      if (!gate.can_submit) return { tone: "signal", text: `Fix or dispute the ${gate.blocking.length} critical note${gate.blocking.length === 1 ? "" : "s"} marked in red, then re-check.` };
      return { tone: "ink", text: "No critical notes are open. Submit for approval." };
    case "in_review":
      return canApprove
        ? { tone: "ink", text: "Read the proof, then Approve or Request changes. Critical overrides need a written reason." }
        : { tone: "ink", text: "Holding for an approver. Switch to abhi4 (Approver) in the top right to clear it." };
    case "approved":
      return { tone: "cleared", text: "Cleared. Open the Clearance Certificate, or mark it published once it is live." };
    default:
      return { tone: "cleared", text: "Published. The certificate stays verifiable from its link." };
  }
}

function Workspace() {
  const { id } = useParams<{ id: string }>();
  const params = useSearchParams();
  const { user, can } = useSession();
  const { data, error, mutate } = useSWR<Review, ApiError>(`/api/reviews/${id}`);
  const [tab, setTab] = useState<Tab>("Proof");
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

  if (error?.status === 404) {
    return (
      <ErrorSheet
        code="404"
        stamp="Not found"
        title="This review is not in your workspace"
        text="Each visitor works in a private copy of PayWise, so a review link from another browser opens nothing here. Start a review of your own, or pick one from the desk."
      />
    );
  }
  if (error) return <ErrorState message={error.message} onRetry={refresh} />;
  if (!data) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-40" />
        <div className="grid gap-8 lg:grid-cols-[1fr_340px]">
          <Skeleton className="h-96" />
          <Skeleton className="h-96" />
        </div>
      </div>
    );
  }

  const { submission, revision, findings, claims } = data;
  const isAuthor = can("submit_content") && (user?.role !== "creator" || submission.author.id === user?.id);
  const editable = submission.state === "draft" || submission.state === "changes_requested";
  const openCount = findings.filter((f) => ["open", "escalated", "disputed"].includes(f.status) && !f.needs_review).length;
  const latest = data.revisions.at(-1)?.number ?? revision.number;
  const step = nextStep(data, isAuthor, can("approve"), pending, stream);
  const visual = revision.source_format === "image" || revision.source_format === "scan";
  const queued = stream.queue?.position ?? data.queue_position;

  return (
    <SourceProvider>
      <div className="animate-fade-in">
        <Link href="/app" className="mb-4 inline-flex items-center gap-1 font-mono text-xs uppercase tracking-wide text-graphite hover:text-ink">
          <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" /> Desk
        </Link>

        <header className="mb-5 flex flex-wrap items-end justify-between gap-4 border-b border-rule pb-4">
          <div className="min-w-0">
            <p className="label flex flex-wrap items-center gap-x-2">
              <span>{CHANNEL_LABEL[submission.channel] ?? submission.channel}</span>·<span>by {submission.author.name}</span>·<span className="normal-case">revision {revision.number}</span>
              {revision.report.cached_from && <span className="normal-case" title="Same content, rulebook and facts as an earlier review">· cached result</span>}
            </p>
            <h1 className="mt-1 flex flex-wrap items-center gap-3 font-serif text-[28px] leading-tight text-ink">
              {submission.title}
              <Chip className={STATE_STYLE[submission.state].chip}>{STATE_STYLE[submission.state].label}</Chip>
            </h1>
          </div>
          <ActionBar review={data} onChanged={refresh} onRechecked={refresh} />
        </header>

        <section className="card mb-5 grid items-center gap-6 p-4 md:grid-cols-[auto_minmax(0,1fr)] xl:grid-cols-[auto_minmax(0,1fr)_minmax(260px,320px)]" aria-label="Instruments">
          <BrandScoreGauge score={revision.brand_score} pending={pending} />
          <div className="min-w-0">
            <p className="label" aria-live="polite">
              {pending
                ? queued
                  ? `Queued · position ${queued}`
                  : `Checking · ${stream.findingsSoFar} found so far${stream.reconnecting ? " · reconnecting" : ""}`
                : `${openCount} open · ${claims.length} claims checked`}
            </p>
            <PreflightChecklist stream={stream} report={revision.report.checkers} pending={pending} claims={claims} visual={visual} />
          </div>
          <div className="space-y-3 md:col-span-2 xl:col-span-1">
            <NextStep tone={step.tone}>{step.text}</NextStep>
            {data.clearance && <ClearanceStamp clearance={data.clearance} className="pl-2 pt-2" />}
          </div>
        </section>

        {revision.degraded && (
          <div role="status" className="mb-4 flex items-center gap-2 border-l-2 border-teal bg-sheet px-3 py-2 text-sm text-ink">
            <AlertTriangle className="h-4 w-4" aria-hidden="true" /> AI checks temporarily limited. Deterministic checks and the local Claim Ledger still ran; tone and wording used offline fallbacks.
          </div>
        )}
        {pending && stream.degraded && !revision.degraded && (
          <div role="status" className="mb-4 border-l-2 border-teal bg-sheet px-3 py-2 text-sm text-ink">AI checks temporarily limited: {stream.degraded}</div>
        )}
        {revision.review_status === "failed" && (
          <div className="mb-4">
            <ErrorState message={`${revision.report.error ?? "This review failed."} Press Re-check to try again.`} />
          </div>
        )}

        <div role="tablist" aria-label="Review sections" className="mb-5 flex gap-6 overflow-x-auto border-b border-rule" data-tour="tabs">
          {TABS.map((t) => (
            <button key={t} role="tab" type="button" aria-selected={tab === t} onClick={() => setTab(t)} className={clsx("-mb-px whitespace-nowrap border-b-2 pb-2 pt-1 text-sm", tab === t ? "border-teal font-medium text-ink" : "border-transparent text-graphite hover:text-ink")}>
              {t}
              {t === "Proof" && !pending && <span className="ml-1.5 font-mono text-xs text-graphite">{findings.length}</span>}
              {t === "Claim Ledger" && !pending && <span className="ml-1.5 font-mono text-xs text-graphite">{claims.length}</span>}
            </button>
          ))}
        </div>

        <div role="tabpanel">
          {tab === "Proof" &&
            (visual ? (
              <VisualDesk
                blocks={revision.blocks}
                findings={findings}
                report={revision.report}
                pending={pending}
                focused={focused}
                onFocus={setFocused}
                canDecide={isAuthor && editable && revision.number === latest}
                canEscalate={can("escalate")}
                onChanged={reload}
                header={
                  <p className="mb-4 flex flex-wrap justify-between gap-2 border-b border-rule pb-3 font-mono text-[11px] uppercase tracking-wide text-graphite">
                    <span>{revision.source_format === "scan" ? "Scanned PDF" : "Image"} · visual and accessibility review</span>
                    <span>Proof {String(revision.number).padStart(2, "0")}</span>
                  </p>
                }
              />
            ) : (
              <ProofDesk
                blocks={revision.blocks}
                findings={findings}
                pending={pending}
                focused={focused}
                onFocus={setFocused}
                canDecide={isAuthor && editable && revision.number === latest}
                canEscalate={can("escalate")}
                onChanged={reload}
                header={
                  <p className="mb-6 flex flex-wrap justify-between gap-2 border-b border-rule pb-3 font-mono text-[11px] uppercase tracking-wide text-graphite">
                    <span>{revision.source_format} · {revision.content.length.toLocaleString()} characters</span>
                    <span>Proof {String(revision.number).padStart(2, "0")}</span>
                  </p>
                }
              />
            ))}
          {tab !== "Proof" && pending && tab !== "Comments" ? (
            <div className="space-y-3">
              <Skeleton className="h-28" />
              <Skeleton className="h-28" />
            </div>
          ) : (
            <>
              {tab === "Claim Ledger" && <ClaimLedger claims={claims} />}
              {tab === "Revisions" && <Revisions reviewId={id} revisions={data.revisions} />}
              {tab === "Comments" && <Comments reviewId={id} decisions={data.decisions} />}
              {tab === "AI disclosure" && <AiDisclosure ai={revision.report.ai} tone={revision.report.tone} />}
            </>
          )}
        </div>
        <Tour steps={TOUR} autoStart={params.get("tour") === "1"} ready={!pending} />
      </div>
    </SourceProvider>
  );
}

export default function ReviewPage() {
  return (
    <Suspense fallback={<Skeleton className="h-96" />}>
      <Workspace />
    </Suspense>
  );
}
