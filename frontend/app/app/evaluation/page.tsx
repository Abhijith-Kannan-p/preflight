"use client";

import { FlaskConical, Loader2, Play } from "lucide-react";
import { useState } from "react";
import useSWR from "swr";

import { EmptyState, ErrorState, InfoTip, PageHeader, Skeleton } from "@/components/ui";
import { post } from "@/lib/api";
import { VERDICT_STYLE, pct, timeAgo } from "@/lib/format";
import type { Verdict } from "@/lib/types";

interface LabelMetrics {
  precision: number;
  recall: number;
  f1: number;
  support: number;
}

interface EvalRun {
  id: string;
  created_at: string;
  n_items: number;
  metrics: {
    per_label: Record<Verdict, LabelMetrics>;
    accuracy: number;
    macro_recall: number;
    problem_recall: number;
    problem_precision: number;
    detection_rate: number;
  };
  confusion: Record<Verdict, Record<string, number>>;
  failures: { id: string; claim: string; expected: Verdict; predicted: string; expected_fact: string | null; predicted_fact: string | null; note: string }[];
  latency_ms_p50: number;
  latency_ms_p95: number;
  config: { nli_model: string; embedding_model: string | null; eval_date: string; dataset: string };
}

interface Status {
  running: boolean;
  latest: EvalRun | null;
  runs: { id: string; created_at: string; accuracy: number; macro_recall: number }[];
}

const VERDICTS: Verdict[] = ["supported", "outdated", "contradicted", "unsupported", "needs_review"];
const COLUMNS = [...VERDICTS, "not_detected"];
const TARGETS = { unsupportedPrecision: 0.9, recall: 0.85 };

function Tile({ label, value, hint, target }: { label: string; value: string; hint: string; target?: { met: boolean; text: string } }) {
  return (
    <div className="card p-5">
      <p className="label flex items-center gap-1">{label} <InfoTip text={hint} /></p>
      <p className="text-3xl font-bold">{value}</p>
      {target && <p className={`mt-1 text-xs font-medium ${target.met ? "text-teal-700" : "text-amber-700"}`}>{target.met ? "✓ " : "Below target · "}{target.text}</p>}
    </div>
  );
}

export default function EvaluationPage() {
  const { data, error, mutate } = useSWR<Status>("/api/eval", { refreshInterval: (s) => (s?.running ? 3000 : 0) });
  const [starting, setStarting] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);

  async function run() {
    setStarting(true);
    setRunError(null);
    try {
      await post("/api/eval/run");
      await mutate();
    } catch (e) {
      setRunError(e instanceof Error ? e.message : "Could not start the evaluation.");
    } finally {
      setStarting(false);
    }
  }

  if (error) return <ErrorState message={error.message} onRetry={() => mutate()} />;
  const latest = data?.latest;
  const m = latest?.metrics;
  const maxCell = latest ? Math.max(...VERDICTS.flatMap((v) => COLUMNS.map((c) => latest.confusion[v]?.[c] ?? 0))) : 1;

  return (
    <div className="animate-fade-in">
      <PageHeader
        title="Claim Ledger evaluation"
        subtitle="Preflight's signature check, measured honestly. 150 hand-labelled PayWise claims cover all five verdicts; each run sends them through the real pipeline (retrieval, local NLI, numeric and quote checks) and compares the verdicts."
        actions={
          <button type="button" className="btn-teal" onClick={run} disabled={starting || data?.running}>
            {data?.running || starting ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Play className="h-4 w-4" aria-hidden="true" />}
            {data?.running ? "Running… (about 30 s)" : "Run the test set"}
          </button>
        }
      />
      {runError && <div className="mb-4"><ErrorState message={runError} /></div>}
      {!data ? (
        <Skeleton className="h-96" />
      ) : !latest || !m ? (
        <EmptyState icon={<FlaskConical className="h-8 w-8" />} title={data.running ? "The first run is in progress" : "No evaluation yet"} text="Results are computed automatically after the engine starts. Press “Run the test set” to run it now." />
      ) : (
        <div className="space-y-6">
          <p className="text-xs text-navy-500">
            Latest run {timeAgo(latest.created_at)} · {latest.n_items} claims · NLI {latest.config.nli_model} · embeddings {latest.config.embedding_model ?? "none"} · validity evaluated on {latest.config.eval_date}
          </p>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Tile label="Accuracy" value={pct(m.accuracy)} hint="Share of claims whose verdict matches the label exactly." />
            <Tile label="Macro recall" value={pct(m.macro_recall)} hint="Average recall over the five verdicts." target={{ met: m.macro_recall >= TARGETS.recall, text: "plan target ≥ 85%" }} />
            <Tile label="Unsupported precision" value={pct(m.per_label.unsupported.precision)} hint="When Preflight says a claim has no approved fact, how often that is right." target={{ met: m.per_label.unsupported.precision >= TARGETS.unsupportedPrecision, text: "plan target ≥ 90%" }} />
            <Tile label="Problem claims caught" value={pct(m.problem_recall)} hint="Share of claims that must not be published unchanged (anything not supported) that Preflight flags." />
          </div>

          <div className="grid gap-4 lg:grid-cols-[1fr_1.2fr]">
            <section className="card p-5" aria-labelledby="per-verdict">
              <h2 id="per-verdict" className="mb-3 font-semibold">Per verdict</h2>
              <table className="w-full text-sm">
                <thead className="text-xs uppercase tracking-wide text-navy-500">
                  <tr><th className="py-2 text-left">Verdict</th><th className="py-2 text-right">Precision</th><th className="py-2 text-right">Recall</th><th className="py-2 text-right">F1</th><th className="py-2 text-right">n</th></tr>
                </thead>
                <tbody className="divide-y divide-paper-200 font-mono">
                  {VERDICTS.map((v) => (
                    <tr key={v}>
                      <td className="py-2 font-sans font-medium">{VERDICT_STYLE[v].label}</td>
                      <td className="py-2 text-right">{m.per_label[v].precision.toFixed(2)}</td>
                      <td className="py-2 text-right">{m.per_label[v].recall.toFixed(2)}</td>
                      <td className="py-2 text-right">{m.per_label[v].f1.toFixed(2)}</td>
                      <td className="py-2 text-right text-navy-500">{m.per_label[v].support}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="mt-3 text-xs text-navy-500">Latency per claim: p50 {latest.latency_ms_p50} ms · p95 {latest.latency_ms_p95} ms (CPU).</p>
            </section>

            <section className="card overflow-x-auto p-5" aria-labelledby="confusion">
              <h2 id="confusion" className="mb-1 font-semibold">Confusion matrix</h2>
              <p className="mb-3 text-xs text-navy-500">Rows: the label. Columns: what Preflight said. The diagonal is correct.</p>
              <table className="w-full border-separate border-spacing-0.5 text-center text-xs">
                <thead>
                  <tr>
                    <th />
                    {COLUMNS.map((c) => (
                      <th key={c} className="px-1 pb-1 font-medium text-navy-500">{c === "not_detected" ? "Missed" : VERDICT_STYLE[c as Verdict].label}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {VERDICTS.map((row) => (
                    <tr key={row}>
                      <th className="pr-2 text-right font-medium text-navy-500">{VERDICT_STYLE[row].label}</th>
                      {COLUMNS.map((col) => {
                        const n = latest.confusion[row]?.[col] ?? 0;
                        const strength = n / maxCell;
                        return (
                          <td
                            key={col}
                            title={`Labelled ${row}, predicted ${col}: ${n}`}
                            className={`h-10 min-w-12 rounded-md font-mono font-semibold ${strength > 0.55 ? "text-white" : "text-navy"} ${row === col ? "ring-1 ring-inset ring-navy/30" : ""}`}
                            style={{ background: n ? `rgba(18,165,148,${0.12 + 0.88 * strength})` : "#F6F1E3" }}
                          >
                            {n}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          </div>

          <section className="card p-5" aria-labelledby="failures">
            <h2 id="failures" className="mb-1 font-semibold">Failure cases ({latest.failures.length})</h2>
            <p className="mb-3 text-xs text-navy-500">Every mismatch, shown openly. Most are vague claims labelled “needs review” that Preflight calls unsupported; they land in the “Needs a human look” group in the app and cost no points.</p>
            <ul className="divide-y divide-paper-200 text-sm">
              {latest.failures.map((f) => (
                <li key={f.id} className="flex flex-wrap items-baseline gap-2 py-2">
                  <span className="font-mono text-xs text-navy-500">{f.id}</span>
                  <span className="flex-1">“{f.claim}”</span>
                  <span className="text-xs">
                    expected <strong>{f.expected.replace("_", " ")}</strong>, got <strong className="text-danger-700">{f.predicted.replace("_", " ")}</strong>
                    {f.predicted_fact && <span className="text-navy-500"> ({f.predicted_fact})</span>}
                  </span>
                </li>
              ))}
            </ul>
          </section>

          <p className="text-xs text-navy-500">
            Honest caveat: two similarity thresholds were calibrated on this same set; there is no held-out split yet. Dataset: <span className="font-mono">{latest.config.dataset}</span>. Earlier runs:{" "}
            {data.runs.slice(1, 5).map((r) => `${timeAgo(r.created_at)} (${pct(r.accuracy)})`).join(" · ") || "none"}.
          </p>
        </div>
      )}
    </div>
  );
}
