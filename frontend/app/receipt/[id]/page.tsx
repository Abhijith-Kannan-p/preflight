"use client";

import { Download, Link2, Printer } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import QRCode from "qrcode";
import { useEffect, useState } from "react";
import useSWR from "swr";

import { Logo } from "@/components/Logo";
import { Stamp, stampTime } from "@/components/review/ClearanceStamp";
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

const fmt = (iso: string | null) => (iso ? `${new Date(iso).toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short", timeZone: "UTC" })} UTC` : "—");
const pad = (n: number | null) => (n == null ? "––" : String(n).padStart(2, "0"));

const KIND: Record<string, string> = {
  submit: "Submitted for approval",
  approve: "Cleared for publication",
  request_changes: "Changes requested",
  publish: "Marked as published",
  dispute: "Disputed a finding",
  escalate: "Escalated a finding",
  override: "Overrode a critical finding",
};

function Field({ label, value, mono = false }: { label: string; value: React.ReactNode; mono?: boolean }) {
  return (
    <div className="min-w-0">
      <p className="label mb-0.5">{label}</p>
      <p className={mono ? "font-mono text-sm text-ink" : "break-words text-sm font-medium text-ink"}>{value}</p>
    </div>
  );
}

function Qr({ value }: { value: string }) {
  const [svg, setSvg] = useState("");
  useEffect(() => {
    void QRCode.toString(value, { type: "svg", margin: 0, errorCorrectionLevel: "M", color: { dark: "#1B2A4A", light: "#FFFDF8" } }).then(setSvg);
  }, [value]);
  return <div role="img" aria-label="QR code linking to this certificate" className="h-28 w-28 [&>svg]:h-full [&>svg]:w-full" dangerouslySetInnerHTML={{ __html: svg }} />;
}

export default function ReceiptPage() {
  const { id } = useParams<{ id: string }>();
  const { data, error, mutate } = useSWR<Receipt>(`/api/receipts/${id}`, fetcher);
  const [copied, setCopied] = useState(false);
  const [url, setUrl] = useState("");
  useEffect(() => setUrl(window.location.href), []);

  return (
    <div className="min-h-screen bg-paper py-8 print:bg-white print:py-0">
      <div className="mx-auto max-w-4xl px-4 print:max-w-none print:px-0">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-2 print:hidden">
          <Link href={`/app/review/${id}`} className="font-mono text-xs uppercase tracking-wide text-graphite hover:text-ink">← Back to the proof</Link>
          <div className="flex flex-wrap gap-2">
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
          <article className="sheet print:shadow-none" aria-label="Clearance Certificate">
            {/* Boarding-pass head: the pass on the left, a tear-off stub on the right. */}
            <div className="grid md:grid-cols-[minmax(0,1fr)_13rem]">
              <div className="relative p-6 sm:p-8">
                <div className="flex items-center justify-between gap-4">
                  <Logo />
                  <p className="label mb-0">Clearance Certificate</p>
                </div>
                <div className="mt-6 flex flex-wrap items-center justify-between gap-x-6 gap-y-4">
                  <h1 className="font-serif text-[28px] leading-tight text-ink">{data.title}</h1>
                  {data.approver && data.approved_at && (
                    <Stamp tone="cleared" title="Cleared for publication" lines={[`By ${data.approver.name} · ${stampTime(data.approved_at)}`, `Hash ${data.receipt_hash?.slice(0, 8) ?? "—"}`]} className="mr-2 text-[0.9em]" />
                  )}
                </div>
                <div className="mt-6 flex items-center gap-4 border-y border-rule py-4">
                  <div>
                    <p className="label mb-0">From</p>
                    <p className="font-mono text-2xl text-ink">DRAFT</p>
                    <p className="font-mono text-xs text-graphite">score {pad(data.first_score)}</p>
                  </div>
                  <div className="relative h-px flex-1 border-t border-dashed border-graphite" aria-hidden="true">
                    <span className="absolute -top-2.5 left-1/2 -translate-x-1/2 bg-sheet px-2 font-mono text-[11px] text-graphite">{data.revisions} revision{data.revisions === 1 ? "" : "s"}</span>
                  </div>
                  <div className="text-right">
                    <p className="label mb-0">To</p>
                    <p className="font-mono text-2xl text-cleared">{data.state === "published" ? "PUBLISHED" : "CLEARED"}</p>
                    <p className="font-mono text-xs text-graphite">score {pad(data.final_score)}</p>
                  </div>
                </div>
                <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-4">
                  <Field label="Channel" value={CHANNEL_LABEL[data.channel] ?? data.channel} />
                  <Field label="Author" value={data.author.name} />
                  <Field label="Approver" value={data.approver?.name ?? "—"} />
                  <Field label="Cleared" value={fmt(data.approved_at)} />
                </div>
              </div>

              <aside className="relative flex flex-col items-start gap-3 border-t-2 border-dashed border-rule p-6 md:border-l-2 md:border-t-0" aria-label="Certificate stub">
                <span className="absolute -left-3 -top-3 hidden h-6 w-6 rounded-full bg-paper md:block" aria-hidden="true" />
                <span className="absolute -bottom-3 -left-3 hidden h-6 w-6 rounded-full bg-paper md:block" aria-hidden="true" />
                {url && <div className="self-center"><Qr value={url} /></div>}
                <Field label="Certificate" value={data.id} mono />
                <Field label="Hash" value={data.receipt_hash ? `${data.receipt_hash.slice(0, 8)}…` : "—"} mono />
                <p className={`w-full border-l-2 pl-2 text-xs font-medium ${data.audit_intact ? "border-cleared text-cleared-700" : "border-signal text-signal-700"}`}>
                  {data.audit_intact ? "Audit chain verified" : "Audit chain broken"}
                  <span className="block font-mono font-normal text-graphite">{data.audit_events} events</span>
                </p>
              </aside>
            </div>

            {/* Perforation between the pass and the record. */}
            <div className="relative border-t-2 border-dashed border-rule" aria-hidden="true">
              <span className="absolute -left-3 -top-3 h-6 w-6 rounded-full bg-paper print:hidden" />
              <span className="absolute -right-3 -top-3 h-6 w-6 rounded-full bg-paper print:hidden" />
            </div>

            <div className="space-y-7 p-6 sm:p-8">
              {data.overrides.length > 0 && (
                <section className="border-l-2 border-amber pl-4">
                  <Stamp tone="amber" title="Override noted" lines={[`${data.overrides.length} critical finding${data.overrides.length === 1 ? "" : "s"}`]} className="mb-3 rotate-[3deg]" />
                  <ul className="space-y-1 text-sm">
                    {data.overrides.map((o, i) => (
                      <li key={i}>
                        <span className="tag mr-1">{o.rule}</span> {o.actor.name}: “{o.reason}”
                      </li>
                    ))}
                  </ul>
                </section>
              )}

              <section>
                <p className="label">Cleared text · revision {data.revisions}</p>
                <div className="whitespace-pre-wrap border-l-2 border-ink pl-4 font-serif text-[16px] leading-relaxed text-ink">{data.final_text}</div>
              </section>

              <section className="grid gap-8 sm:grid-cols-2">
                <div>
                  <p className="label">Checks run</p>
                  <ul className="divide-y divide-rule border-y border-rule text-sm">
                    {data.checks.map((c) => (
                      <li key={c.name} className="flex justify-between py-1.5">
                        <span>{c.ok ? "✓" : "!"} {c.label}</span>
                        <span className="font-mono text-xs text-graphite">{c.findings} found</span>
                      </li>
                    ))}
                  </ul>
                </div>
                <div>
                  <p className="label">Claim Ledger · final revision</p>
                  <ul className="divide-y divide-rule border-y border-rule text-sm">
                    {Object.entries(data.claims).map(([verdict, n]) => (
                      <li key={verdict} className="flex justify-between py-1.5 capitalize">
                        <span>{verdict.replace("_", " ")}</span>
                        <span className="font-mono text-xs">{n}</span>
                      </li>
                    ))}
                    {!Object.keys(data.claims).length && <li className="py-1.5 text-graphite">No factual claims.</li>}
                  </ul>
                  <p className="label mt-4">Findings in the first draft</p>
                  <p className="font-mono text-sm">{(["critical", "major", "minor"] as Severity[]).map((s) => `${data.findings_first[s] ?? 0} ${s}`).join(" · ")}</p>
                </div>
              </section>

              {data.findings_final.length > 0 && (
                <section>
                  <p className="label">Findings remaining at clearance</p>
                  <ul className="space-y-1 text-sm">
                    {data.findings_final.map((f, i) => (
                      <li key={i}>
                        <span className={`mr-2 rounded-sm border px-1 font-mono text-[10px] uppercase ${SEVERITY_STYLE[f.severity].chip}`}>{f.severity}</span>
                        <span className="font-mono text-xs">{f.rule_id}</span> “{f.text}” · <span className="text-graphite">{f.needs_review ? "needs a human look (not scored)" : f.status}</span>
                      </li>
                    ))}
                  </ul>
                </section>
              )}

              <section>
                <p className="label">Decisions</p>
                <ol className="divide-y divide-rule border-y border-rule text-sm">
                  {data.timeline.map((d, i) => (
                    <li key={i} className="grid gap-x-4 py-1.5 sm:grid-cols-[10rem_1fr]">
                      <span className="font-mono text-xs text-graphite">{fmt(d.created_at)}</span>
                      <span>
                        <strong className="font-medium">{d.actor.name}</strong> {KIND[d.kind] ?? d.kind}
                        {d.rule && <span className="font-mono text-xs"> {d.rule}</span>}
                        {d.reason && <span className="text-graphite"> · “{d.reason}”</span>}
                      </span>
                    </li>
                  ))}
                </ol>
              </section>

              <section className="border-t border-rule pt-4 text-xs leading-relaxed text-graphite">
                <p className="label">AI used in this review</p>
                <p>
                  {data.ai.purposes?.length ? `${data.ai.purposes.join(", ").replace(/_/g, " ")} via ${data.ai.provider}/${data.ai.model}. ` : "No hosted LLM (deterministic mode). "}
                  Verification by local NLI model {data.ai.nli_model ?? "(fallback)"}; embeddings {data.ai.embedding_model ?? "(BM25 only)"}.{" "}
                  {data.ai.masking_enabled ? `Confidential values masked before external calls: ${data.ai.masked_count ?? 0}.` : "Masking was off."} The AI suggested; people decided.
                </p>
                <p className="mt-2 font-mono">
                  {data.audit_message} Certificate hash {data.receipt_hash?.slice(0, 16)}…
                </p>
              </section>
            </div>
          </article>
        )}
      </div>
    </div>
  );
}
