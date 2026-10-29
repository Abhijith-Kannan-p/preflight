"use client";

import { clsx } from "clsx";
import { ArrowRight, Loader2, RefreshCw, Sparkles } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import useSWR from "swr";

import { type CoachProfile, TipCard } from "@/components/CoachTips";
import { FactTag, RuleTag, SourceProvider } from "@/components/review/SourcePanel";
import { EmptyState, ErrorState, InfoTip, Modal, NextStep, PageHeader, Skeleton } from "@/components/ui";
import { ApiError, api, post } from "@/lib/api";
import { pct, timeAgo } from "@/lib/format";
import { useSession } from "@/lib/session";

// --- types ------------------------------------------------------------------------------

interface Rates {
  raised: number;
  disputed: number;
  overridden: number;
  accepted: number;
  dispute_rate: number | null;
  override_rate: number | null;
  acceptance_rate: number | null;
  ambiguity: number | null;
}

interface RuleHealth {
  code: string;
  title: string;
  description: string;
  severity: string;
  version: number;
  source_ref: string;
  source_doc: string;
  source_page: number | null;
  config: Record<string, unknown>;
  current: Rates;
  overall: Rates;
  flagged: boolean;
  reason_groups: { count: number; examples: string[] }[];
  versions: (Rates & { version: number; title: string; since: string; status: string })[];
  dispute_change: { from_version: number; to_version: number; before: number; after: number; relative: number } | null;
}

interface HealthReport {
  window_days: number;
  formula: string;
  rules: RuleHealth[];
}

interface Rewording {
  code: string;
  version: number;
  title: string;
  description: string;
  rationale: string;
  source: "llm" | "deterministic";
  config: Record<string, unknown>;
}

interface RadarEntry {
  submission_id: string;
  title: string;
  state: string;
  cleared_at: string | null;
  sentence: string;
  fact_id: string;
  change: "superseded" | "edited" | "retired" | "expired";
  old_value: string;
  new_fact_id: string | null;
  new_value: string | null;
  changed_at: string;
}

interface RadarReport {
  indexed_items: number;
  indexed_dependencies: number;
  facts_relied_on: string[];
  entries: RadarEntry[];
}

const TABS = ["Guideline Health", "Stale-Content Radar", "Creator Coach"] as const;
type Tab = (typeof TABS)[number];

const rate = (v: number | null) => (v == null ? "–" : pct(v));

// --- Guideline Health ---------------------------------------------------------------------

function Metric({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div>
      <p className="label mb-0 flex items-center gap-1">
        {label}
        {hint && <InfoTip text={hint} />}
      </p>
      <p className="font-serif text-[30px] font-medium leading-tight text-ink tabular-nums">{value}</p>
    </div>
  );
}

function RewordDialog({ rule, onClose, onPublished }: { rule: RuleHealth; onClose: () => void; onPublished: () => void }) {
  const [draft, setDraft] = useState<Rewording | null>(null);
  const [busy, setBusy] = useState<"suggest" | "publish" | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function suggest() {
    setBusy("suggest");
    setError(null);
    try {
      setDraft(await post<Rewording>(`/api/governance/rules/${rule.code}/suggest`));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not draft a rewording.");
    } finally {
      setBusy(null);
    }
  }

  async function publish() {
    if (!draft) return;
    setBusy("publish");
    setError(null);
    try {
      await api(`/api/rulebook/rules/${rule.code}`, {
        method: "PUT",
        body: JSON.stringify({ title: draft.title, description: draft.description, severity: rule.severity, config: rule.config, source_doc: rule.source_doc, source_page: rule.source_page }),
        idempotencyKey: `${rule.code}:publish:v${rule.version}`,
      });
      onPublished();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not publish the new version.");
      setBusy(null);
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      title={`Clearer wording for ${rule.code}`}
      footer={
        <>
          <button type="button" className="btn-ghost" onClick={onClose}>
            Cancel
          </button>
          <button type="button" className="btn-teal" disabled={!draft || busy !== null || !draft.title.trim() || draft.description.trim().length < 10} onClick={publish}>
            {busy === "publish" && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />} Publish as version {rule.version + 1}
          </button>
        </>
      }
    >
      <div className="space-y-4 text-sm">
        <div className="border-l-2 border-rule pl-3">
          <p className="label mb-0">Version {rule.version} today</p>
          <p className="font-medium text-ink">{rule.title}</p>
          <p className="text-graphite">{rule.description}</p>
        </div>
        {!draft ? (
          <button type="button" className="btn-primary" onClick={suggest} disabled={busy !== null}>
            {busy === "suggest" ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Sparkles className="h-4 w-4" aria-hidden="true" />}
            Suggest clearer wording from the {rule.current.disputed || rule.overall.disputed} dispute reasons
          </button>
        ) : (
          <>
            <p className={clsx("border-l-2 px-3 py-1 text-xs", draft.source === "llm" ? "border-teal text-teal-700" : "border-rule text-graphite")}>
              {draft.source === "llm" ? "Drafted by the hosted LLM from the rule and the dispute reasons. Edit freely; nothing changes until you publish." : "The LLM is unavailable: this is a deterministic draft that quotes the most common objection. Edit it into a clear exception before publishing."}
            </p>
            <div>
              <label htmlFor="reword-title" className="label">New title</label>
              <input id="reword-title" className="input" value={draft.title} maxLength={200} onChange={(e) => setDraft({ ...draft, title: e.target.value })} />
            </div>
            <div>
              <label htmlFor="reword-description" className="label">New description</label>
              <textarea id="reword-description" className="input" rows={5} value={draft.description} onChange={(e) => setDraft({ ...draft, description: e.target.value })} />
            </div>
            <div>
              <p className="label">Why this is clearer</p>
              <p className="text-graphite">{draft.rationale}</p>
            </div>
            <p className="text-xs text-graphite">Publishing retires version {rule.version} and creates version {rule.version + 1} (audit-logged). Guideline Health then compares dispute rates per version.</p>
          </>
        )}
        {error && <ErrorState message={error} />}
      </div>
    </Modal>
  );
}

function HealthTab() {
  const { can } = useSession();
  const { data, error, mutate } = useSWR<HealthReport>("/api/governance/health");
  const [rewording, setRewording] = useState<RuleHealth | null>(null);
  if (error) return <ErrorState message={error.message} onRetry={() => mutate()} />;
  if (!data) return <Skeleton className="h-96" />;
  const flagged = data.rules.filter((r) => r.flagged);
  const reworded = data.rules.filter((r) => r.dispute_change);
  const measured = data.rules.filter((r) => r.overall.raised > 0);
  return (
    <div className="space-y-8">
      <p className="max-w-[75ch] text-sm text-graphite">
        Rules people keep pushing back on are usually unclear, not ignored. Over the last {data.window_days} days: <span className="font-mono text-xs text-ink">{data.formula}</span>. Each finding counts once per review.
      </p>

      <section aria-labelledby="flagged">
        <h2 id="flagged" className="label">Flagged as ambiguous ({flagged.length})</h2>
        {flagged.length === 0 ? (
          <EmptyState title="No ambiguous rules right now" text="No rule's current version is disputed or overridden often enough to flag. Disputes with written reasons build this board." />
        ) : (
          <div className="space-y-4">
            {flagged.map((rule) => (
              <article key={rule.code} className="sheet grid gap-4 p-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
                <div>
                  <p className="flex flex-wrap items-center gap-2">
                    <RuleTag id={rule.code} source={rule.source_ref} /> <span className="font-mono text-xs text-graphite">v{rule.version} · {rule.severity}</span>
                  </p>
                  <h3 className="mt-2 font-serif text-xl text-ink">{rule.title}</h3>
                  <p className="mt-1 text-sm text-graphite">{rule.description}</p>
                  <div className="mt-4 grid grid-cols-4 gap-3 border-t border-rule pt-3">
                    <Metric label="Ambiguity" value={rate(rule.current.ambiguity)} hint={data.formula} />
                    <Metric label="Disputed" value={rate(rule.current.dispute_rate)} hint={`${rule.current.disputed} of ${rule.current.raised} findings`} />
                    <Metric label="Overridden" value={rate(rule.current.override_rate)} hint={`${rule.current.overridden} of ${rule.current.raised} findings`} />
                    <Metric label="Accepted" value={rate(rule.current.acceptance_rate)} hint="Suggestions accepted or edited" />
                  </div>
                  {can("edit_rulebook") ? (
                    <button type="button" className="btn-teal mt-4" onClick={() => setRewording(rule)}>
                      <Sparkles className="h-4 w-4" aria-hidden="true" /> Suggest clearer wording
                    </button>
                  ) : (
                    <p className="mt-4 text-xs text-graphite">The brand manager (abhi3) can reword this rule from here.</p>
                  )}
                </div>
                <div>
                  <p className="label">What writers said, grouped</p>
                  <ul className="space-y-2">
                    {rule.reason_groups.map((g, i) => (
                      <li key={i} className="border-l-2 border-rule bg-sheet pl-3 text-sm">
                        <span className="font-mono text-[11px] text-graphite">{g.count}×</span> <span className="font-serif text-ink">“{g.examples[0]}”</span>
                        {g.examples.length > 1 && <span className="block text-xs text-graphite">also: {g.examples.slice(1).map((e) => `“${e}”`).join(" · ")}</span>}
                      </li>
                    ))}
                  </ul>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>

      {reworded.length > 0 && (
        <section aria-labelledby="reworded">
          <h2 id="reworded" className="label">After rewording: disputes per finding, by version (target −30%)</h2>
          <ul className="divide-y divide-rule border-y border-rule">
            {reworded.map((rule) => {
              const c = rule.dispute_change!;
              return (
                <li key={rule.code} className="grid items-center gap-3 py-3 sm:grid-cols-[auto_1fr_auto]">
                  <RuleTag id={rule.code} source={rule.source_ref} />
                  <span className="text-sm">
                    {rule.title}
                    <span className="block font-mono text-xs text-graphite">
                      v{c.from_version} {pct(c.before)} ({rule.versions.find((v) => v.version === c.from_version)?.raised} findings) <ArrowRight className="inline h-3 w-3" aria-hidden="true" /> v{c.to_version} {pct(c.after)} ({rule.versions.find((v) => v.version === c.to_version)?.raised} findings)
                    </span>
                  </span>
                  <span className={clsx("font-mono text-sm", c.relative <= -0.3 ? "text-cleared-700" : "text-ink")}>
                    {c.relative > 0 ? "+" : ""}
                    {Math.round(c.relative * 100)}% {c.relative <= -0.3 ? "· target met" : ""}
                  </span>
                </li>
              );
            })}
          </ul>
        </section>
      )}

      <section aria-labelledby="all-rules">
        <h2 id="all-rules" className="label">Every rule that raised findings</h2>
        <div className="overflow-x-auto border-y border-ink">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-rule text-left">
                {["Rule", "Findings", "Disputed", "Overridden", "Accepted", "Ambiguity"].map((h, i) => (
                  <th key={h} scope="col" className={clsx("label py-2 font-normal", i > 0 && "text-right")}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-rule">
              {measured.map((r) => (
                <tr key={r.code}>
                  <td className="py-2">
                    <RuleTag id={r.code} source={r.source_ref} /> <span className="ml-1">{r.title}</span> <span className="font-mono text-[11px] text-graphite">v{r.version}</span>
                  </td>
                  <td className="py-2 text-right font-mono">{r.overall.raised}</td>
                  <td className="py-2 text-right font-mono">{rate(r.overall.dispute_rate)}</td>
                  <td className="py-2 text-right font-mono">{rate(r.overall.override_rate)}</td>
                  <td className="py-2 text-right font-mono">{rate(r.overall.acceptance_rate)}</td>
                  <td className={clsx("py-2 text-right font-mono", r.flagged && "font-semibold text-ink")}>{rate(r.current.ambiguity)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      {rewording && (
        <RewordDialog
          rule={rewording}
          onClose={() => setRewording(null)}
          onPublished={() => {
            setRewording(null);
            void mutate();
          }}
        />
      )}
    </div>
  );
}

// --- Stale-Content Radar ------------------------------------------------------------------

const CHANGE_LABEL: Record<RadarEntry["change"], string> = { superseded: "Superseded", edited: "Edited", retired: "Retired", expired: "Expired" };

function RadarTab() {
  const router = useRouter();
  const { can } = useSession();
  const { data, error, mutate } = useSWR<RadarReport>("/api/radar");
  const [busy, setBusy] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  async function simulate() {
    setBusy("simulate");
    setProblem(null);
    try {
      await post("/api/radar/simulate", undefined, "radar:simulate:F-087");
      await mutate();
    } catch (e) {
      setProblem(e instanceof ApiError ? e.message : "Could not simulate the fact update.");
    } finally {
      setBusy(null);
    }
  }

  async function recheck(entry: RadarEntry) {
    setBusy(entry.submission_id);
    setProblem(null);
    try {
      const created = await post<{ id: string }>(`/api/radar/${entry.submission_id}/recheck`, undefined, `radar:recheck:${entry.submission_id}:${entry.fact_id}:${entry.changed_at}`);
      router.push(`/app/review/${created.id}`);
    } catch (e) {
      setProblem(e instanceof ApiError ? e.message : "Could not start the re-check.");
      setBusy(null);
    }
  }

  if (error) return <ErrorState message={error.message} onRetry={() => mutate()} />;
  if (!data) return <Skeleton className="h-96" />;
  const items = new Set(data.entries.map((e) => e.submission_id)).size;
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <p className="max-w-[70ch] text-sm text-graphite">
          Every cleared item is indexed by the facts its claims relied on: {data.indexed_items} items, {data.indexed_dependencies} claim → fact links across {data.facts_relied_on.length} facts. When a fact is superseded, edited, retired or
          expires, the items that relied on it appear here at once, and their authors and the brand manager are notified.
        </p>
        {can("edit_rulebook") ? (
          <button type="button" className="btn-primary" onClick={simulate} disabled={busy !== null}>
            {busy === "simulate" ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <RefreshCw className="h-4 w-4" aria-hidden="true" />}
            Simulate fact update on F-087
          </button>
        ) : (
          <p className="text-xs text-graphite">Switch to abhi3 (Brand Manager) to simulate a fact update.</p>
        )}
      </div>
      {problem && <ErrorState message={problem} />}
      {data.entries.length === 0 ? (
        <EmptyState
          title="Nothing stale"
          text="Every cleared item still matches the current approved facts. Try “Simulate fact update on F-087”: it supersedes the settlement-time fact (under 10 seconds) in your own demo workspace, as editing it in the Rulebook would."
        />
      ) : (
        <>
          <NextStep tone="signal">
            {items} cleared item{items === 1 ? "" : "s"} now quote{items === 1 ? "s" : ""} a fact that changed. Re-check each one against today&apos;s facts.
          </NextStep>
          <ul className="divide-y divide-rule border-y border-ink">
            {data.entries.map((e) => (
              <li key={`${e.submission_id}-${e.fact_id}-${e.sentence}`} className="grid gap-3 py-3 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1.4fr)_auto] lg:items-center">
                <div>
                  <a href={`/app/review/${e.submission_id}`} className="font-medium text-ink underline decoration-rule underline-offset-4 hover:decoration-ink">
                    {e.title}
                  </a>
                  <p className="font-mono text-[11px] uppercase text-graphite">
                    {e.state} {e.cleared_at ? `· cleared ${timeAgo(e.cleared_at)}` : ""}
                  </p>
                  <p className="mt-1 font-serif text-sm text-ink">“{e.sentence}”</p>
                </div>
                <div className="text-sm">
                  <p className="flex flex-wrap items-center gap-2">
                    <FactTag id={e.fact_id} /> <span className="tag border-ink/40 text-ink">{CHANGE_LABEL[e.change]}</span>
                    {e.new_fact_id && (
                      <>
                        <ArrowRight className="h-3 w-3" aria-hidden="true" /> <FactTag id={e.new_fact_id} />
                      </>
                    )}
                  </p>
                  <p className="mt-1 text-graphite line-through decoration-graphite">{e.old_value}</p>
                  {e.new_value && <p className="text-ink">{e.new_value}</p>}
                </div>
                {can("submit_content") ? (
                  <button type="button" className="btn-teal" onClick={() => recheck(e)} disabled={busy !== null}>
                    {busy === e.submission_id && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />} Re-check now
                  </button>
                ) : (
                  <span className="text-xs text-graphite">Authors re-check</span>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

// --- Creator Coach --------------------------------------------------------------------------

function CoachView({ profile }: { profile: CoachProfile }) {
  const target = profile.baseline_rate != null ? profile.baseline_rate * 0.75 : null;
  const peak = Math.max(1, ...profile.weekly.map((w) => w.findings_per_draft));
  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-4">
        <Metric label="Drafts reviewed" value={String(profile.submissions)} />
        <Metric label="Repeat-mistake rate" value={rate(profile.repeat_rate)} hint="First-draft findings on a rule that already flagged one of your earlier first drafts, as a share of all your first-draft findings." />
        <Metric label="Older half → newer half" value={`${rate(profile.baseline_rate)} → ${rate(profile.recent_rate)}`} hint={target != null ? `Target: newer half at or below ${pct(target)} (25% under the baseline).` : "Needs a few more drafts."} />
        <Metric label="Trend" value={profile.trend} />
      </div>
      <section aria-labelledby="tips">
        <h3 id="tips" className="label">Before your next draft</h3>
        {profile.tips.length === 0 ? <p className="text-sm text-graphite">No mistake has come up twice yet. Keep going.</p> : <ul className="space-y-2">{profile.tips.map((t) => <TipCard key={t.rule} tip={t} />)}</ul>}
      </section>
      {profile.weekly.length > 0 && (
        <section aria-labelledby="weekly">
          <h3 id="weekly" className="label">Findings per first draft, by week</h3>
          <ol className="flex h-28 items-end gap-2 border-b border-rule" aria-label="Findings per first draft by week">
            {profile.weekly.map((w) => (
              <li key={w.week} className="flex flex-1 flex-col items-center justify-end gap-1" title={`${w.week}: ${w.findings_per_draft} findings per draft over ${w.drafts} drafts`}>
                <span className="font-mono text-[10px] text-graphite">{w.findings_per_draft}</span>
                <span className="w-full max-w-10 bg-ink/80" style={{ height: `${(w.findings_per_draft / peak) * 72}px` }} aria-hidden="true" />
              </li>
            ))}
          </ol>
          <ol className="mt-1 flex gap-2">
            {profile.weekly.map((w) => (
              <li key={w.week} className="flex-1 text-center font-mono text-[10px] text-graphite">
                {w.week.slice(5)}
              </li>
            ))}
          </ol>
        </section>
      )}
      {profile.recurring.length > 0 && (
        <p className="text-xs text-graphite">
          Recurring: {profile.recurring.map((r) => `${r.rule} ${r.title} (${r.drafts} drafts)`).join(" · ")}
        </p>
      )}
    </div>
  );
}

function CoachTab() {
  const { can, user } = useSession();
  const mine = useSWR<CoachProfile>(user ? ["/api/coach/me", user.id] : null, ([path]: [string]) => api<CoachProfile>(path));
  const team = useSWR<CoachProfile[]>(can("view_insights") ? "/api/coach" : null);
  const [selected, setSelected] = useState<string | null>(null);
  if (can("view_insights")) {
    if (team.error) return <ErrorState message={team.error.message} onRetry={() => team.mutate()} />;
    if (!team.data) return <Skeleton className="h-96" />;
    const current = team.data.find((p) => p.user.id === selected) ?? team.data[0];
    return (
      <div className="space-y-5">
        <p className="text-sm text-graphite">Each author&apos;s recurring mistakes and the tips they see before writing. Tips come from the rulebook&apos;s own wording and the author&apos;s past fixes; no LLM is involved.</p>
        <div role="tablist" aria-label="Authors" className="flex flex-wrap gap-2">
          {team.data.map((p) => (
            <button key={p.user.id} type="button" role="tab" aria-selected={p.user.id === current?.user.id} onClick={() => setSelected(p.user.id)} className={clsx("tag px-2 py-1 text-xs", p.user.id === current?.user.id && "border-teal")}>
              {p.user.name} · {p.user.title}
            </button>
          ))}
        </div>
        {current ? <CoachView profile={current} /> : <EmptyState title="No authors yet" text="Authors appear once they have reviewed a draft." />}
      </div>
    );
  }
  if (mine.error) return <ErrorState message={mine.error.message} onRetry={() => mine.mutate()} />;
  if (!mine.data) return <Skeleton className="h-96" />;
  return mine.data.submissions === 0 ? <EmptyState title="Your coach starts after your first review" text="Run a draft through Preflight and the Coach will track which rules come up for you." /> : <CoachView profile={mine.data} />;
}

// --- page ---------------------------------------------------------------------------------

function Governance() {
  // The section is chosen in the header's Governance row (?tab=guideline|stale|creator).
  const params = useSearchParams();
  const wanted = params.get("tab");
  const tab: Tab = (wanted && TABS.find((t) => t.toLowerCase().startsWith(wanted))) || "Guideline Health";
  return (
    <SourceProvider>
      <div className="animate-fade-in">
        <PageHeader eyebrow="Governance intelligence" title="Guidelines, facts and writers over time" subtitle="Which rules are unclear, which approved content went stale, and what each writer keeps tripping on." />
        <h2 className="sr-only">{tab}</h2>
        {tab === "Guideline Health" && <HealthTab />}
        {tab === "Stale-Content Radar" && <RadarTab />}
        {tab === "Creator Coach" && <CoachTab />}
      </div>
    </SourceProvider>
  );
}

export default function GovernancePage() {
  return (
    <Suspense fallback={<Skeleton className="h-96" />}>
      <Governance />
    </Suspense>
  );
}
