"use client";

import { BarChart3 } from "lucide-react";
import useSWR from "swr";

import { HBar, ScoreTrend } from "@/components/charts";
import { EmptyState, ErrorState, InfoTip, PageHeader, Skeleton } from "@/components/ui";
import { useSession } from "@/lib/session";

interface Insights {
  totals: { reviews: number; approved: number; findings: number; critical_caught: number; avg_improvement: number };
  by_type: { type: string; count: number }[];
  top_rules: { rule: string; title: string; count: number; severity: string | null }[];
  dispute_rates: { rule: string; title: string; raised: number; disputed: number; rate: number }[];
  trend: { date: string; first: number; final: number; reviews: number }[];
  authors: { author: string; reviews: number; findings: number; avg_first_score: number | null }[];
}

const TYPE_LABEL: Record<string, string> = {
  unsupported_claim: "Unsupported claim",
  outdated_fact: "Outdated fact",
  contradicted_claim: "Contradicted claim",
  terminology: "Terminology",
  banned_phrase: "Banned phrase",
  tone: "Tone",
  disclaimer: "Missing disclaimer",
  channel: "Channel limit",
  readability: "Readability",
};

function Stat({ label, value, hint }: { label: string; value: string | number; hint: string }) {
  return (
    <div className="card p-5">
      <p className="label flex items-center gap-1">{label} <InfoTip text={hint} /></p>
      <p className="display-number mt-1">{value}</p>
    </div>
  );
}

export default function InsightsPage() {
  const { can } = useSession();
  const { data, error, mutate } = useSWR<Insights>(can("view_insights") ? "/api/insights" : null, { refreshInterval: 30_000 });

  if (!can("view_insights")) {
    return <ErrorState message="Insights are for reviewers, brand managers, approvers and admins. Switch to abhi3 (Brand Manager) or abhi4 (Approver) in the top right." />;
  }
  if (error) return <ErrorState message={error.message} onRetry={() => mutate()} />;

  return (
    <div className="animate-fade-in">
      <PageHeader title="Governance insights" subtitle="What goes wrong in first drafts, which rules fire, which ones people dispute, and whether Brand Scores improve. Based on every review in this workspace, including the fictional demo history." />
      {!data ? (
        <div className="grid gap-4 md:grid-cols-2">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-64" />)}</div>
      ) : data.totals.reviews === 0 ? (
        <EmptyState icon={<BarChart3 className="h-8 w-8" />} title="No reviews yet" text="Insights fill in as drafts are reviewed. The demo history is generated a minute after the engine starts; refresh shortly, or run a sample draft yourself." />
      ) : (
        <div className="space-y-6">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Stat label="Reviews" value={data.totals.reviews} hint="Drafts checked by Preflight in this workspace." />
            <Stat label="Approved" value={data.totals.approved} hint="Drafts an approver signed off, each with a Review Receipt." />
            <Stat label="Critical issues caught" value={data.totals.critical_caught} hint="Critical findings in first drafts, before anyone published them." />
            <Stat label="Avg. score gain" value={`+${data.totals.avg_improvement}`} hint="Average Brand Score of the final revision minus the first draft." />
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <section className="card p-5" aria-labelledby="trend">
              <h2 id="trend" className="mb-1 font-semibold">Brand Score over time</h2>
              <p className="mb-3 text-xs text-navy-500">Average per day: the first draft, and the latest revision after fixes.</p>
              <ScoreTrend data={data.trend} />
            </section>
            <section className="card p-5" aria-labelledby="types">
              <h2 id="types" className="mb-1 font-semibold">Findings by type</h2>
              <p className="mb-3 text-xs text-navy-500">In first drafts. Low-confidence findings waiting for a human look are excluded.</p>
              <HBar data={data.by_type.map((t) => ({ ...t, label: TYPE_LABEL[t.type] ?? t.type }))} label="label" value="count" />
            </section>
            <section className="card p-5" aria-labelledby="rules">
              <h2 id="rules" className="mb-1 font-semibold">Most violated rules</h2>
              <p className="mb-3 text-xs text-navy-500">Where authors need guidance most. Candidates for training or clearer wording.</p>
              <HBar data={data.top_rules.map((r) => ({ count: r.count, label: `${r.rule} · ${r.title.length > 20 ? `${r.title.slice(0, 19)}…` : r.title}` }))} label="label" value="count" />
            </section>
            <section className="card p-5" aria-labelledby="disputes">
              <h2 id="disputes" className="mb-1 font-semibold">Dispute rate per rule</h2>
              <p className="mb-3 text-xs text-navy-500">Share of a rule&apos;s findings that authors disputed. A high rate can mean the rule is ambiguous.</p>
              <HBar data={data.dispute_rates.map((d) => ({ label: d.rule, rate: Math.round(d.rate * 100) }))} label="label" value="rate" unit="%" />
            </section>
          </div>

          <section className="card p-5" aria-labelledby="authors">
            <h2 id="authors" className="mb-3 font-semibold">Findings per author</h2>
            <table className="w-full text-left text-sm">
              <thead className="text-xs uppercase tracking-wide text-navy-500">
                <tr><th className="py-2">Author</th><th className="py-2 text-right">Reviews</th><th className="py-2 text-right">Findings in first drafts</th><th className="py-2 text-right">Avg. first-draft score</th></tr>
              </thead>
              <tbody className="divide-y divide-paper-200">
                {data.authors.map((a) => (
                  <tr key={a.author}>
                    <td className="py-2 font-medium">{a.author}</td>
                    <td className="py-2 text-right font-mono">{a.reviews}</td>
                    <td className="py-2 text-right font-mono">{a.findings}</td>
                    <td className="py-2 text-right font-mono">{a.avg_first_score ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          <p className="border-t border-rule pt-4 text-sm text-graphite">
            Which rules are ambiguous, which approved content went stale, and each writer&apos;s recurring mistakes:{" "}
            <a href="/app/governance" className="text-ink underline decoration-rule underline-offset-4 hover:decoration-ink">Governance</a>.
          </p>
        </div>
      )}
    </div>
  );
}
