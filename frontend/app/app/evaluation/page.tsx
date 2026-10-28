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

function ClaimsEvaluation() {
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
      <div className="mb-5 flex flex-wrap items-end justify-between gap-4">
        <p className="max-w-[70ch] text-sm leading-relaxed text-graphite">
          Preflight&apos;s signature check, measured honestly. 150 hand-labelled PayWise claims cover all five verdicts; each run sends them through the real pipeline (retrieval, local NLI, numeric and quote checks) and compares the verdicts.
        </p>
        <button type="button" className="btn-teal" onClick={run} disabled={starting || data?.running}>
          {data?.running || starting ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Play className="h-4 w-4" aria-hidden="true" />}
          {data?.running ? "Running… (about 30 s)" : "Run the test set"}
        </button>
      </div>
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

interface VisualCheck {
  tp: number;
  fp: number;
  fn: number;
  tn: number;
  precision: number | null;
  recall: number | null;
}

interface VisualRun {
  n_items: number;
  metrics: { precision: number; recall: number; ocr_word_recall: number; per_check: Record<string, VisualCheck> };
  latency_s: { p50: number; p95: number; max: number };
  failures: { file: string; check: string; error: "fp" | "fn"; ocr: string }[];
  environment: { machine: string; processor: string; python: string };
  created_at: string;
  precomputed: boolean;
}

const CHECK_LABEL: Record<string, string> = {
  "VIS-01": "Off-palette colour",
  "VIS-02": "Stretched or squashed logo",
  "VIS-03": "Logo clear space",
  "ACC-01": "Text contrast (WCAG 2.2)",
  logo: "Logo found",
  "CLM-01": "Superlative read from the image",
  "CLM-04": "Absolute security claim read from the image",
  "TRM-02": "Misspelt product name read from the image",
};

const fmt = (v: number | null) => (v == null ? "–" : pct(v));

function VisualEvaluation() {
  const { data, error, mutate } = useSWR<VisualRun>("/api/eval/visual");
  if (error) return <ErrorState message={error.message} onRetry={() => mutate()} />;
  if (!data) return <Skeleton className="h-96" />;
  const m = data.metrics;
  return (
    <div className="space-y-6">
      <p className="max-w-[75ch] text-sm leading-relaxed text-graphite">
        100 labelled visual assets: 96 generated from PayWise templates with known injected issues (off-palette colours, stretched logos, crowded clear space, low-contrast text,
        risky claims in the image) and four composed samples. Every asset goes through the same OCR, visual checks and text checkers as a review; a check counts as positive when it
        raises at least one finding on the asset.
      </p>
      <p className="border-l-2 border-amber bg-sheet px-3 py-2 text-xs text-ink">
        Precomputed run ({data.environment.processor}, Python {data.environment.python}, {new Date(data.created_at).toLocaleDateString("en-GB", { dateStyle: "medium" })}), not
        computed live: reading 100 images would occupy the 0.1-CPU host for about ten minutes. Run it yourself with <span className="font-mono">python -m app.eval.visual</span>. The
        set is synthetic, so real-world banners (photos, unusual fonts) will score lower.
      </p>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Tile label="Precision" value={pct(m.precision)} hint="Of the issues Preflight raised, the share that were really there." target={{ met: m.precision >= 0.9, text: "plan target ≥ 90%" }} />
        <Tile label="Recall" value={pct(m.recall)} hint="Of the issues injected, the share Preflight raised." />
        <Tile label="OCR words read" value={pct(m.ocr_word_recall)} hint="Share of the words in the images that OCR read correctly." />
        <Tile label="Time per image" value={`${data.latency_s.p50.toFixed(1)} s`} hint={`Median on the machine above (95th percentile ${data.latency_s.p95.toFixed(1)} s). On Render's 0.1 CPU the OCR step takes about 7 s per banner.`} />
      </div>
      <section className="sheet overflow-x-auto p-5" aria-labelledby="per-check">
        <h2 id="per-check" className="label">Per check</h2>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-rule text-left">
              <th scope="col" className="label py-2 font-normal">Check</th>
              <th scope="col" className="label py-2 text-right font-normal">Precision</th>
              <th scope="col" className="label py-2 text-right font-normal">Recall</th>
              <th scope="col" className="label hidden py-2 text-right font-normal sm:table-cell">TP / FP / FN / TN</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-rule">
            {Object.entries(m.per_check).map(([check, c]) => (
              <tr key={check}>
                <td className="py-2">
                  <span className="tag mr-2">{check}</span>
                  {CHECK_LABEL[check] ?? check}
                </td>
                <td className="py-2 text-right font-mono">{fmt(c.precision)}</td>
                <td className="py-2 text-right font-mono">{fmt(c.recall)}</td>
                <td className="hidden py-2 text-right font-mono text-xs text-graphite sm:table-cell">
                  {c.tp} / {c.fp} / {c.fn} / {c.tn}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
      <section className="sheet p-5" aria-labelledby="visual-failures">
        <h2 id="visual-failures" className="label">Failure cases ({data.failures.length})</h2>
        {data.failures.length === 0 ? (
          <p className="text-sm text-graphite">None on this set.</p>
        ) : (
          <ul className="divide-y divide-rule text-sm">
            {data.failures.map((f) => (
              <li key={`${f.file}-${f.check}`} className="py-2">
                <span className="font-mono text-xs">{f.file}</span> · <span className="tag">{f.check}</span> {f.error === "fn" ? "missed" : "raised but not there"}
                <span className="mt-1 block text-xs text-graphite">OCR read: “{f.ocr.replace(/\n+/g, " / ").slice(0, 160)}”</span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

interface CompilerScore {
  labelled: number;
  candidates: number;
  found: number;
  recall: number;
  precision: number;
  exact: number;
  accepted_without_edits: number;
  page_correct: number;
  missed: string[];
  needs_edit: string[];
  unlabelled: string[];
}

interface CompilerRun {
  source: string;
  generated_at: string;
  runs: {
    structured_only: CompilerScore;
    structured_and_llm?: CompilerScore & { model: string; llm_seconds: number; trials: { recall: number; precision: number; accepted_without_edits: number; found: number; exact: number }[] };
  };
  decisions: { accepted: number; edited: number; rejected: number; accepted_without_edits: number | null };
}

function CompilerEvaluation() {
  const { data, error, mutate } = useSWR<CompilerRun>("/api/eval/compiler");
  if (error) return <ErrorState message={error.message} onRetry={() => mutate()} />;
  if (!data) return <Skeleton className="h-96" />;
  const llm = data.runs.structured_and_llm;
  const base = data.runs.structured_only;
  const rows: [string, CompilerScore][] = [["Structured extraction only (LLM down)", base], ...(llm ? [[`Structured + ${llm.model}, mean of ${llm.trials.length} runs`, llm] as [string, CompilerScore]] : [])];
  const d = data.decisions;
  return (
    <div className="space-y-6">
      <p className="max-w-[75ch] text-sm leading-relaxed text-graphite">
        The sample PayWise Brand Book was labelled by hand: {base.labelled} rules, each with its page and exact values. Recall is the share of labelled rules that come out as a candidate;
        precision, the share of candidates that match a labelled rule. A candidate counts as acceptable without edits when its values equal the label. Guidance rules are free text, so
        they match on page, category and a keyword.
      </p>
      <p className="border-l-2 border-amber bg-sheet px-3 py-2 text-xs text-ink">
        Precomputed on {new Date(data.generated_at).toLocaleDateString("en-GB", { dateStyle: "medium" })} with <span className="font-mono">python -m app.eval.compiler</span>. LLM output
        varies between calls, so the LLM run is repeated and averaged. Two labels were added after the first LLM run found rules the labelling had missed (pages 4 and 8).
      </p>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Tile label="Recall" value={pct((llm ?? base).recall)} hint="Labelled rules that came out as a candidate." />
        <Tile label="Precision" value={pct((llm ?? base).precision)} hint="Candidates that match a labelled rule." />
        <Tile label="Acceptable without edits" value={pct((llm ?? base).accepted_without_edits)} hint="Matched candidates whose values equal the label." target={{ met: (llm ?? base).accepted_without_edits >= 0.8, text: "target ≥ 80%" }} />
        <Tile
          label="Your decisions"
          value={d.accepted_without_edits == null ? "–" : pct(d.accepted_without_edits)}
          hint={`Accepted without edits in this workspace: ${d.accepted} accepted as extracted, ${d.edited} edited, ${d.rejected} rejected. Live, from the Compiler review queue.`}
        />
      </div>
      <section className="sheet overflow-x-auto p-5" aria-labelledby="compiler-runs">
        <h2 id="compiler-runs" className="label">Runs</h2>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-rule text-left">
              <th scope="col" className="label py-2 font-normal">Run</th>
              <th scope="col" className="label py-2 text-right font-normal">Recall</th>
              <th scope="col" className="label py-2 text-right font-normal">Precision</th>
              <th scope="col" className="label py-2 text-right font-normal">Without edits</th>
              <th scope="col" className="label py-2 text-right font-normal">Right page</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-rule">
            {rows.map(([name, r]) => (
              <tr key={name}>
                <td className="py-2">{name}</td>
                <td className="py-2 text-right font-mono">{pct(r.recall)}</td>
                <td className="py-2 text-right font-mono">{pct(r.precision)}</td>
                <td className="py-2 text-right font-mono">{pct(r.accepted_without_edits)}</td>
                <td className="py-2 text-right font-mono">{pct(r.page_correct)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
      <section className="sheet p-5" aria-labelledby="compiler-misses">
        <h2 id="compiler-misses" className="label">What each run missed or got wrong</h2>
        {rows.map(([name, r]) => (
          <div key={name} className="mb-3 text-sm">
            <p className="font-medium">{name}</p>
            <p className="text-graphite">Missed: {r.missed.length ? r.missed.join("; ") : "none"}</p>
            <p className="text-graphite">Needed an edit: {r.needs_edit.length ? r.needs_edit.join("; ") : "none"}</p>
            {r.unlabelled.length > 0 && <p className="text-graphite">Not in the labels: {r.unlabelled.join("; ")}</p>}
          </div>
        ))}
      </section>
    </div>
  );
}

const EVAL_TABS = ["Claim Ledger", "Visual review", "Rulebook Compiler"] as const;

export default function EvaluationPage() {
  const [tab, setTab] = useState<(typeof EVAL_TABS)[number]>("Claim Ledger");
  return (
    <div className="animate-fade-in">
      <PageHeader eyebrow="Measured, not claimed" title="Evaluation" subtitle="Each check is run against a labelled set and reported with its failures." />
      <div role="tablist" aria-label="Evaluations" className="mb-5 flex gap-6 overflow-x-auto border-b border-rule">
        {EVAL_TABS.map((t) => (
          <button key={t} role="tab" type="button" aria-selected={tab === t} onClick={() => setTab(t)} className={`-mb-px whitespace-nowrap border-b-2 pb-2 pt-1 text-sm ${tab === t ? "border-ink font-medium text-ink" : "border-transparent text-graphite hover:text-ink"}`}>
            {t}
          </button>
        ))}
      </div>
      {tab === "Claim Ledger" ? <ClaimsEvaluation /> : tab === "Visual review" ? <VisualEvaluation /> : <CompilerEvaluation />}
    </div>
  );
}
