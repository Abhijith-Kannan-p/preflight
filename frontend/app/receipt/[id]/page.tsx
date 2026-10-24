"use client";

import { BadgeCheck, Download, Link2, Printer, ShieldAlert } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import useSWR from "swr";

import { Logo } from "@/components/Logo";
import { ErrorState, Skeleton } from "@/components/ui";
import { API_URL, fetcher } from "@/lib/api";
import { CHANNEL_LABEL, SEVERITY_STYLE } from "@/lib/format";
import type { CheckerRun, Severity, UserRef } from "@/lib/types";

interface ReceiptDecision {
  kind: string;
  actor: UserRef;
  reason: string;
  rule: string | null;
  created_at: string;
}

interface Receipt {
  id: string;
  title: string;
  channel: string;
  state: string;
  author: UserRef;
  approver: UserRef | null;
  created_at: string;
  approved_at: string | null;
  revisions: number;
  first_score: number | null;
  final_score: number | null;
  final_text: string;
  checks: CheckerRun[];
  findings_first: Record<string, number>;
  findings_final: { rule_id: string; rule_source: string; severity: Severity; text: string; status: string; explanation: string; needs_review: boolean }[];
  claims: Record<string, number>;
  overrides: ReceiptDecision[];
  timeline: ReceiptDecision[];
  ai: { mode?: string; provider?: string | null; model?: string | null; purposes?: string[]; nli_model?: string | null; embedding_model?: string | null; masked_count?: number; masking_enabled?: boolean };
  audit_intact: boolean;
  audit_message: string;
  audit_events: number;
  receipt_hash: string | null;
}

const fmt = (iso: string | null) => (iso ? new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }) : "—");

const KIND: Record<string, string> = {
  submit: "Submitted for approval",
  approve: "Approved",
  request_changes: "Changes requested",
  publish: "Marked as published",
  dispute: "Disputed a finding",
  escalate: "Escalated a finding",
  override: "Overrode a critical finding",
};

export default function ReceiptPage() {
  const { id } = useParams<{ id: string }>();
  const { data, error, mutate } = useSWR<Receipt>(`/api/receipts/${id}`, fetcher);
  const [copied, setCopied] = useState(false);

  return (
    <div className="min-h-screen bg-paper py-8 print:bg-white print:py-0">
      <div className="mx-auto max-w-3xl px-4 print:max-w-none print:px-0">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-2 print:hidden">
          <Link href={`/app/review/${id}`} className="text-sm text-navy-500 hover:text-navy">← Back to the review</Link>
          <div className="flex gap-2">
            <button
              type="button"
              className="btn-ghost"
              onClick={async () => {
                await navigator.clipboard.writeText(window.location.href);
                setCopied(true);
              }}
            >
              <Link2 className="h-4 w-4" aria-hidden="true" /> {copied ? "Link copied" : "Copy share link"}
            </button>
            <button type="button" className="btn-ghost" onClick={() => window.print()}>
              <Printer className="h-4 w-4" aria-hidden="true" /> Print
            </button>
            <a href={`${API_URL}/api/receipts/${id}/pdf`} className="btn-primary">
              <Download className="h-4 w-4" aria-hidden="true" /> Download PDF
            </a>
          </div>
        </div>

        {error && <ErrorState message={error.message} onRetry={() => mutate()} />}
        {!data && !error && <Skeleton className="h-[80vh]" />}
        {data && (
          <article className="card space-y-6 p-8 print:border-0 print:shadow-none">
            <header className="flex flex-wrap items-start justify-between gap-4 border-b border-paper-200 pb-5">
              <div>
                <Logo />
                <p className="mt-3 text-xs font-semibold uppercase tracking-[0.25em] text-teal-700">Review Receipt</p>
                <h1 className="mt-1 text-2xl font-bold tracking-tight">{data.title}</h1>
                <p className="mt-1 text-sm text-navy-500">
                  {CHANNEL_LABEL[data.channel] ?? data.channel} · receipt {data.id}
                </p>
              </div>
              <div className={`flex items-center gap-2 rounded-xl px-3 py-2 text-sm font-semibold ${data.audit_intact ? "bg-teal-50 text-teal-700" : "bg-danger-50 text-danger-700"}`}>
                {data.audit_intact ? <BadgeCheck className="h-5 w-5" aria-hidden="true" /> : <ShieldAlert className="h-5 w-5" aria-hidden="true" />}
                {data.audit_intact ? "Audit chain verified" : "Audit chain broken"}
              </div>
            </header>

            <section className="grid gap-4 sm:grid-cols-4">
              {[
                ["Author", data.author.name],
                ["Approved by", data.approver?.name ?? "—"],
                ["Approved", fmt(data.approved_at)],
                ["Brand Score", `${data.first_score ?? "—"} → ${data.final_score ?? "—"}`],
              ].map(([label, value]) => (
                <div key={label}>
                  <p className="label">{label}</p>
                  <p className="font-semibold">{value}</p>
                </div>
              ))}
            </section>

            {data.overrides.length > 0 && (
              <section className="rounded-xl border-2 border-danger/40 bg-danger-50 p-4">
                <p className="font-semibold text-danger-700">Critical findings overridden by the approver ({data.overrides.length})</p>
                <ul className="mt-2 space-y-1 text-sm">
                  {data.overrides.map((o, i) => (
                    <li key={i}>
                      <span className="font-mono text-xs font-semibold">{o.rule}</span> · {o.actor.name}: “{o.reason}”
                    </li>
                  ))}
                </ul>
              </section>
            )}

            <section>
              <p className="label">Approved text (revision {data.revisions})</p>
              <div className="whitespace-pre-wrap rounded-xl bg-paper-100 p-4 text-sm leading-relaxed">{data.final_text}</div>
            </section>

            <section className="grid gap-6 sm:grid-cols-2">
              <div>
                <p className="label">Checks run</p>
                <ul className="space-y-1 text-sm">
                  {data.checks.map((c) => (
                    <li key={c.name} className="flex justify-between">
                      <span>{c.ok ? "✓" : "⚠"} {c.label}</span>
                      <span className="font-mono text-xs text-navy-500">{c.findings} finding(s)</span>
                    </li>
                  ))}
                </ul>
              </div>
              <div>
                <p className="label">Claim Ledger (final revision)</p>
                <ul className="space-y-1 text-sm">
                  {Object.entries(data.claims).map(([verdict, n]) => (
                    <li key={verdict} className="flex justify-between capitalize">
                      <span>{verdict.replace("_", " ")}</span>
                      <span className="font-mono text-xs">{n}</span>
                    </li>
                  ))}
                  {!Object.keys(data.claims).length && <li className="text-navy-500">No factual claims.</li>}
                </ul>
                <p className="label mt-4">Findings in the first draft</p>
                <p className="text-sm">
                  {(["critical", "major", "minor"] as Severity[]).map((s) => `${data.findings_first[s] ?? 0} ${s}`).join(" · ")}
                </p>
              </div>
            </section>

            {data.findings_final.length > 0 && (
              <section>
                <p className="label">Findings remaining at approval</p>
                <ul className="space-y-1 text-sm">
                  {data.findings_final.map((f, i) => (
                    <li key={i}>
                      <span className={`mr-2 rounded px-1.5 py-0.5 text-[10px] font-bold uppercase ${SEVERITY_STYLE[f.severity].chip}`}>{f.severity}</span>
                      <span className="font-mono text-xs">{f.rule_id}</span> “{f.text}” · <span className="text-navy-500">{f.needs_review ? "needs a human look (not scored)" : f.status}</span>
                    </li>
                  ))}
                </ul>
              </section>
            )}

            <section>
              <p className="label">Decisions</p>
              <ol className="space-y-1 text-sm">
                {data.timeline.map((d, i) => (
                  <li key={i}>
                    <span className="text-navy-500">{fmt(d.created_at)}</span> · <strong>{d.actor.name}</strong> {KIND[d.kind] ?? d.kind}
                    {d.rule && <span className="font-mono text-xs"> {d.rule}</span>}
                    {d.reason && <span className="text-navy-500"> · “{d.reason}”</span>}
                  </li>
                ))}
              </ol>
            </section>

            <section className="rounded-xl bg-paper-100 p-4 text-xs leading-relaxed text-navy-500">
              <p className="font-semibold text-navy">AI used in this review</p>
              <p>
                {data.ai.purposes?.length ? `${data.ai.purposes.join(", ").replace(/_/g, " ")} via ${data.ai.provider}/${data.ai.model}. ` : "No hosted LLM (deterministic mode). "}
                Verification by local NLI model {data.ai.nli_model ?? "(fallback)"}; embeddings {data.ai.embedding_model ?? "(BM25 only)"}.{" "}
                {data.ai.masking_enabled ? `Confidential values masked before external calls: ${data.ai.masked_count ?? 0}.` : "Masking was off."} The AI suggested; people decided.
              </p>
              <p className="mt-2 font-mono">
                {data.audit_message} Receipt hash {data.receipt_hash?.slice(0, 16)}…
              </p>
            </section>
          </article>
        )}
      </div>
    </div>
  );
}
