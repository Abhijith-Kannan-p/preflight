"use client";

import { useState } from "react";
import useSWR from "swr";

import { VoiceRadar } from "@/components/charts";
import { ErrorState, InfoTip, Modal, Skeleton } from "@/components/ui";
import { ApiError, post } from "@/lib/api";
import { pct } from "@/lib/format";

const TRAITS = ["formal", "warm", "confident", "playful", "technical"] as const;

interface RateRow {
  version: number;
  raised: number;
  disputed: number;
  rate: number | null;
}

export interface Fingerprint {
  items: number;
  min_items: number;
  ready: boolean;
  confidence: "low" | "medium" | "high";
  score_sources: Record<string, number>;
  targets: Record<string, number>;
  learned: Record<string, { value: number; median: number; spread: number; std_error: number }>;
  lexical: Record<string, { median: number; mean: number }>;
  profile: { version: number; source: string; adopted_at: string | null };
  history: { version?: number; traits: Record<string, number>; source?: string; adopted_at?: string }[];
  dispute_rate: { by_version: RateRow[]; before: RateRow; after: RateRow | null; min_sample: number };
  replay: {
    drafts: number;
    threshold: number;
    flagged_with_current: number;
    flagged_with_learned: number;
    disputed: number;
    disputed_no_longer_flagged: number;
  } | null;
}

const LEXICAL: Record<string, { label: string; book?: string }> = {
  sentence_words: { label: "Words per sentence", book: "30 or fewer (p6)" },
  exclamations_per_100: { label: "Exclamation marks per 100 words", book: "1 or fewer (p5)" },
  second_person_per_100: { label: "“You” and “your” per 100 words" },
  superlatives_per_100: { label: "Superlatives per 100 words", book: "need an approved fact (p13)" },
};

const rate = (r: RateRow | null) => (r == null ? "–" : r.rate == null ? `${r.disputed} of ${r.raised}` : pct(r.rate));

export function VoiceTab({ canEdit }: { canEdit: boolean }) {
  const { data, error, mutate } = useSWR<Fingerprint>("/api/voice/fingerprint");
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  if (error) return <ErrorState message={error.message} onRetry={() => mutate()} />;
  if (!data) return <Skeleton className="h-96" />;

  const chart = TRAITS.map((t) => ({ trait: t, target: data.targets[t] ?? 0, learned: data.learned[t]?.value ?? 0 }));
  const heuristic = data.score_sources.heuristic ?? 0;
  const replay = data.replay;

  async function adopt() {
    setBusy(true);
    setProblem(null);
    try {
      await post("/api/voice/adopt");
      setConfirming(false);
      await mutate();
    } catch (e) {
      setProblem(e instanceof ApiError ? e.message : "Could not adopt the fingerprint.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <p className="max-w-[75ch] text-sm leading-relaxed text-graphite">
        The Voice Fingerprint is the voice PayWise actually publishes. It is learned from the tone scores of every approved item, alongside a few lexical habits, and compared with the
        hand-set targets the tone check (TON-01) uses today. Adopting it creates a new voice-profile version; the old one stays in the history.
      </p>

      <div className="grid gap-4 sm:grid-cols-3">
        <div className="sheet p-4">
          <p className="label mb-0">Approved items learned from</p>
          <p className="display-number mt-1">{data.items}</p>
          <p className="text-xs text-graphite">At least {data.min_items} are needed to adopt.</p>
        </div>
        <div className="sheet p-4">
          <p className="label mb-0 flex items-center gap-1">
            Confidence <InfoTip text="High from 15 items with every trait's standard error at most 0.05; medium from 8 items; low below that." />
          </p>
          <p className="display-number mt-1 capitalize">{data.confidence}</p>
          <p className="text-xs text-graphite">Largest standard error {Math.max(0, ...Object.values(data.learned).map((l) => l.std_error)).toFixed(3)}</p>
        </div>
        <div className="sheet p-4">
          <p className="label mb-0">Voice profile in use</p>
          <p className="display-number mt-1">v{data.profile.version}</p>
          <p className="text-xs text-graphite">{data.profile.source}</p>
        </div>
      </div>

      {heuristic > 0 && (
        <p className="border-l-2 border-amber bg-sheet px-3 py-2 text-xs text-ink">
          {heuristic} of {data.items} items were scored by the offline tone heuristic (the demo history is generated without the LLM), so these traits are estimates. Items reviewed with the
          LLM add LLM scores.
        </p>
      )}

      <section className="sheet grid gap-6 p-5 lg:grid-cols-[1.1fr_1fr]" aria-labelledby="voice-compare">
        <div>
          <h2 id="voice-compare" className="label">Hand-set targets and learned fingerprint</h2>
          <VoiceRadar data={chart} />
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <caption className="sr-only">Voice traits: hand-set target, learned value and spread</caption>
            <thead>
              <tr className="border-b border-rule text-left">
                <th scope="col" className="label py-2 font-normal">Trait</th>
                <th scope="col" className="label py-2 text-right font-normal">Target</th>
                <th scope="col" className="label py-2 text-right font-normal">Learned</th>
                <th scope="col" className="label py-2 text-right font-normal">Median</th>
                <th scope="col" className="label py-2 text-right font-normal">± s.e.</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-rule">
              {TRAITS.map((t) => {
                const l = data.learned[t];
                const gap = l ? Math.abs(l.value - (data.targets[t] ?? 0)) : 0;
                return (
                  <tr key={t}>
                    <th scope="row" className="py-2 text-left font-normal capitalize">{t}</th>
                    <td className="py-2 text-right font-mono">{data.targets[t]?.toFixed(2) ?? "–"}</td>
                    <td className={`py-2 text-right font-mono ${gap > (replay?.threshold ?? 0.3) ? "font-semibold text-signal-700" : ""}`}>{l ? l.value.toFixed(2) : "–"}</td>
                    <td className="py-2 text-right font-mono text-graphite">{l ? l.median.toFixed(2) : "–"}</td>
                    <td className="py-2 text-right font-mono text-graphite">{l ? l.std_error.toFixed(3) : "–"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <p className="mt-2 text-xs text-graphite">Learned values are means over approved items. Bold: further from the target than the tone check allows ({(replay?.threshold ?? 0.3).toFixed(1)}).</p>

          <h3 className="label mt-5">Lexical habits of approved content</h3>
          <dl className="divide-y divide-rule text-sm">
            {Object.entries(data.lexical).map(([key, v]) => (
              <div key={key} className="flex items-baseline justify-between gap-3 py-1.5">
                <dt>
                  {LEXICAL[key]?.label ?? key}
                  {LEXICAL[key]?.book && <span className="block text-xs text-graphite">Brand book: {LEXICAL[key].book}</span>}
                </dt>
                <dd className="font-mono">
                  {v.mean.toFixed(2)} <span className="text-xs text-graphite">mean · median {v.median.toFixed(2)}</span>
                </dd>
              </div>
            ))}
          </dl>
        </div>
      </section>

      <section className="sheet p-5" aria-labelledby="voice-effect">
        <h2 id="voice-effect" className="label flex items-center gap-1">
          Tone disputes per finding, by voice-profile version
          <InfoTip text={`TON-01 findings the writer disputed, divided by TON-01 findings raised (once per submission, including "needs a human look"). A rate is shown from ${data.dispute_rate.min_sample} findings; below that, the counts.`} />
        </h2>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-rule text-left">
              <th scope="col" className="label py-2 font-normal">Version</th>
              <th scope="col" className="label py-2 text-right font-normal">Findings</th>
              <th scope="col" className="label py-2 text-right font-normal">Disputed</th>
              <th scope="col" className="label py-2 text-right font-normal">Dispute rate</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-rule">
            {data.dispute_rate.by_version.map((row) => (
              <tr key={row.version}>
                <td className="py-2">v{row.version}{row.version === data.profile.version ? " (in use)" : ""}</td>
                <td className="py-2 text-right font-mono">{row.raised}</td>
                <td className="py-2 text-right font-mono">{row.disputed}</td>
                <td className="py-2 text-right font-mono">{rate(row)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {data.dispute_rate.after && data.dispute_rate.after.raised < data.dispute_rate.min_sample && (
          <p className="mt-2 text-xs text-graphite">The version in use has too few tone findings for a rate yet. It fills in as new drafts are reviewed.</p>
        )}
        {replay && (
          <p className="mt-4 border-l-2 border-rule pl-3 text-sm">
            <span className="label mr-2 inline">Projection</span>
            Re-comparing the stored tone scores of {replay.drafts} earlier first drafts with the learned values: {replay.flagged_with_current} are flagged with the targets in use,{" "}
            {replay.flagged_with_learned} would be with the fingerprint. {replay.disputed_no_longer_flagged} of the {replay.disputed} drafts whose tone finding was disputed would no
            longer be flagged. This replays saved scores; it is not a new review.
          </p>
        )}
      </section>

      {canEdit && (
        <div className="flex flex-wrap items-center gap-3">
          <button type="button" className="btn-teal" disabled={!data.ready} onClick={() => setConfirming(true)}>
            Adopt as targets
          </button>
          {!data.ready && <span className="text-sm text-graphite">Needs at least {data.min_items} approved items with tone scores.</span>}
        </div>
      )}

      {data.history.length > 0 && (
        <section aria-labelledby="voice-history">
          <h2 id="voice-history" className="label">Earlier voice profiles</h2>
          <ul className="divide-y divide-rule border-y border-rule text-sm">
            {[...data.history].reverse().map((h, i) => (
              <li key={i} className="py-2">
                <span className="font-mono">v{h.version ?? 1}</span> · {h.source ?? "brand book (hand-set)"}
                <span className="block font-mono text-xs text-graphite">{TRAITS.map((t) => `${t} ${h.traits[t]?.toFixed(2) ?? "–"}`).join(" · ")}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <Modal
        open={confirming}
        title="Adopt the learned voice as targets?"
        onClose={() => setConfirming(false)}
        footer={
          <>
            <button type="button" className="btn-ghost" onClick={() => setConfirming(false)}>Cancel</button>
            <button type="button" className="btn-teal" disabled={busy} onClick={adopt}>{busy ? "Adopting…" : `Create voice profile v${data.profile.version + 1}`}</button>
          </>
        }
      >
        <p className="text-sm">
          Tone checks will compare drafts with these values from the next review on. The change is audit-logged and v{data.profile.version} stays in the history.
        </p>
        <p className="mt-2 font-mono text-xs text-graphite">{TRAITS.map((t) => `${t} ${data.targets[t]?.toFixed(2)} → ${data.learned[t]?.value.toFixed(2)}`).join(" · ")}</p>
        {problem && <p className="mt-2 text-sm text-signal-700">{problem}</p>}
      </Modal>
    </div>
  );
}
