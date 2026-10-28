"use client";

import { clsx } from "clsx";
import { Check, Download, FileText, Loader2, Pencil, Upload, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import useSWR from "swr";

import { Chip, EmptyState, ErrorState, Skeleton } from "@/components/ui";
import { API_URL, ApiError, api, getToken } from "@/lib/api";
import { timeAgo } from "@/lib/format";

type Payload = Record<string, unknown>;

interface Candidate {
  id: string;
  kind: string;
  key: string;
  payload: Payload;
  extracted: Payload;
  source_page: number;
  excerpt: string;
  origin: "deterministic" | "llm";
  match_status: "new" | "update" | "duplicate";
  match_ref: string | null;
  match_note: string;
  decision: "pending" | "accepted" | "edited" | "rejected";
  applied_ref: string | null;
}

interface Report {
  error?: string;
  pages?: number;
  timings_ms?: Record<string, number>;
  llm?: { llm: "ok" | "failed" | "not configured"; returned: number; dropped: number };
  structured?: number;
  from_llm?: number;
  candidates?: number;
  by_status?: Record<string, number>;
}

interface Job {
  id: string;
  filename: string;
  status: "running" | "ready" | "failed";
  created_at: string;
  report: Report | null;
  summary: { decided: number; accepted: number; accepted_without_edits: number; rejected: number };
  stages: { stage: string; label: string }[];
  candidates: Candidate[];
}

const KIND_LABEL: Record<string, string> = {
  term: "Product name",
  word: "Word to avoid",
  pattern: "Claim pattern",
  disclaimer: "Disclaimer",
  colour: "Palette colour",
  channel: "Channel limits",
  threshold: "Limit",
  voice: "Voice targets",
  guidance: "Guidance rule",
};

const MATCH_STYLE: Record<Candidate["match_status"], string> = {
  new: "border-teal text-teal-700",
  update: "border-amber text-ink",
  duplicate: "border-rule text-graphite",
};

type StageState = Record<string, { state: "running" | "done"; ms?: number; found?: number | null }>;

/** Live stages over SSE while a job runs; calls `onDone` when it finishes. */
function useCompileStream(jobId: string | null, running: boolean, onDone: () => void) {
  const [stages, setStages] = useState<StageState>({});
  // A ref, so a new callback on each render does not reopen the stream.
  const done = useRef(onDone);
  done.current = onDone;
  useEffect(() => {
    if (!jobId || !running) return;
    const token = getToken();
    if (!token) return;
    setStages({});
    const source = new EventSource(`${API_URL}/api/compiler/jobs/${jobId}/events?token=${encodeURIComponent(token)}`);
    source.addEventListener("stage_started", (e) => {
      const d = JSON.parse((e as MessageEvent).data);
      setStages((s) => ({ ...s, [d.stage]: { state: "running" } }));
    });
    source.addEventListener("stage_done", (e) => {
      const d = JSON.parse((e as MessageEvent).data);
      setStages((s) => ({ ...s, [d.stage]: { state: "done", ms: d.ms, found: d.found } }));
    });
    source.addEventListener("review_complete", () => {
      source.close();
      done.current();
    });
    // If the stream drops, polling the job (below) still notices when it finishes.
    source.onerror = () => source.readyState === EventSource.CLOSED && done.current();
    return () => source.close();
  }, [jobId, running]);
  return stages;
}

function Value({ value }: { value: unknown }) {
  if (value == null || value === "") return <span className="text-graphite">–</span>;
  if (Array.isArray(value)) return <>{value.join(", ")}</>;
  if (typeof value === "object")
    return (
      <>
        {Object.entries(value as Record<string, unknown>)
          .map(([k, v]) => `${k} ${typeof v === "number" ? v.toFixed(2) : String(v)}`)
          .join(" · ")}
      </>
    );
  if (typeof value === "string" && /^#[0-9A-F]{6}$/i.test(value))
    return (
      <span className="inline-flex items-center gap-1.5">
        <span className="h-3.5 w-3.5 border border-ink/15" style={{ background: value }} aria-hidden="true" />
        {value}
      </span>
    );
  return <>{String(value)}</>;
}

function PayloadEditor({ payload, onChange }: { payload: Payload; onChange: (p: Payload) => void }) {
  return (
    <div className="space-y-2">
      {Object.entries(payload).map(([key, value]) => {
        const id = `edit-${key}`;
        if (value && typeof value === "object" && !Array.isArray(value)) {
          const traits = value as Record<string, number>;
          return (
            <fieldset key={key} className="grid grid-cols-2 gap-2 sm:grid-cols-5">
              <legend className="label">{key}</legend>
              {Object.entries(traits).map(([t, v]) => (
                <label key={t} className="text-xs">
                  {t}
                  <input className="input mt-0.5 font-mono" type="number" step="0.05" min={0} max={1} value={v} onChange={(e) => onChange({ ...payload, [key]: { ...traits, [t]: Number(e.target.value) } })} />
                </label>
              ))}
            </fieldset>
          );
        }
        const text = Array.isArray(value) ? value.join(", ") : value == null ? "" : String(value);
        return (
          <div key={key}>
            <label htmlFor={id} className="label">
              {key.replace(/_/g, " ")}
              {Array.isArray(value) && " (comma-separated)"}
            </label>
            <input
              id={id}
              className="input font-mono"
              value={text}
              onChange={(e) => {
                const raw = e.target.value;
                const next = Array.isArray(value)
                  ? raw.split(",").map((v) => v.trim()).filter(Boolean)
                  : typeof value === "number" || (value == null && /max|value|chars|hashtags/.test(key))
                    ? raw === "" ? null : Number(raw)
                    : raw;
                onChange({ ...payload, [key]: next });
              }}
            />
          </div>
        );
      })}
    </div>
  );
}

function CandidateRow({ c, canEdit, onDecided }: { c: Candidate; canEdit: boolean; onDecided: () => void }) {
  const [editing, setEditing] = useState<Payload | null>(null);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  async function decide(action: "accept" | "reject", payload?: Payload) {
    setBusy(true);
    setProblem(null);
    try {
      await api(`/api/compiler/candidates/${c.id}/decision`, { method: "POST", body: JSON.stringify({ action, payload }), idempotencyKey: `${c.id}-${action}` });
      setEditing(null);
      onDecided();
    } catch (e) {
      setProblem(e instanceof ApiError ? e.message : "Could not save the decision.");
    } finally {
      setBusy(false);
    }
  }

  const decided = c.decision !== "pending";
  return (
    <li className={clsx("grid gap-4 py-4 md:grid-cols-2", decided && "opacity-75")}>
      <figure className="border-l-2 border-rule pl-3">
        <figcaption className="label mb-1 flex flex-wrap items-center gap-2">
          <FileText className="h-3.5 w-3.5" aria-hidden="true" /> Page {c.source_page}
          <Chip className="border-rule text-graphite">{c.origin === "llm" ? "LLM" : "Structured"}</Chip>
        </figcaption>
        <blockquote className="text-sm leading-relaxed text-ink-soft">{c.excerpt || "From a table on this page."}</blockquote>
      </figure>
      <div>
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <span className="font-medium">{KIND_LABEL[c.kind] ?? c.kind}</span>
          <Chip className={MATCH_STYLE[c.match_status]}>{c.match_status}</Chip>
          {c.match_ref && <span className="tag">{c.match_ref}</span>}
          {decided && (
            <Chip className={c.decision === "rejected" ? "border-rule text-graphite" : "border-cleared text-cleared-700"}>
              {c.decision}
              {c.applied_ref ? ` → ${c.applied_ref}` : ""}
            </Chip>
          )}
        </div>
        <p className="mb-2 text-xs text-graphite">{c.match_note}</p>
        {editing ? (
          <PayloadEditor payload={editing} onChange={setEditing} />
        ) : (
          <dl className="grid grid-cols-[max-content_1fr] gap-x-3 gap-y-0.5 text-sm">
            {Object.entries(c.payload).map(([k, v]) => (
              <div key={k} className="contents">
                <dt className="text-graphite">{k.replace(/_/g, " ")}</dt>
                <dd className="font-mono text-xs leading-5">
                  <Value value={v} />
                </dd>
              </div>
            ))}
          </dl>
        )}
        {canEdit && !decided && (
          <div className="mt-3 flex flex-wrap gap-2">
            {editing ? (
              <>
                <button type="button" className="btn-teal py-1.5 text-xs" disabled={busy} onClick={() => decide("accept", editing)}>
                  <Check className="h-3.5 w-3.5" aria-hidden="true" /> Save and accept
                </button>
                <button type="button" className="btn-ghost py-1.5 text-xs" onClick={() => setEditing(null)}>Cancel</button>
              </>
            ) : (
              <>
                <button type="button" className="btn-teal py-1.5 text-xs" disabled={busy} onClick={() => decide("accept")}>
                  <Check className="h-3.5 w-3.5" aria-hidden="true" /> Accept
                </button>
                <button type="button" className="btn-ghost py-1.5 text-xs" disabled={busy} onClick={() => setEditing(structuredClone(c.payload))}>
                  <Pencil className="h-3.5 w-3.5" aria-hidden="true" /> Edit
                </button>
                <button type="button" className="btn-ghost py-1.5 text-xs" disabled={busy} onClick={() => decide("reject")}>
                  <X className="h-3.5 w-3.5" aria-hidden="true" /> Reject
                </button>
              </>
            )}
          </div>
        )}
        {problem && <p className="mt-2 text-sm text-signal-700">{problem}</p>}
      </div>
    </li>
  );
}

function JobView({ jobId, canEdit, onChanged }: { jobId: string; canEdit: boolean; onChanged: () => void }) {
  const { data, error, mutate } = useSWR<Job>(`/api/compiler/jobs/${jobId}`, { refreshInterval: (j) => (j?.status === "running" ? 4000 : 0) });
  const [showDuplicates, setShowDuplicates] = useState(false);
  const stages = useCompileStream(jobId, data?.status === "running", () => {
    void mutate();
    onChanged();
  });
  if (error) return <ErrorState message={error.message} onRetry={() => mutate()} />;
  if (!data) return <Skeleton className="h-64" />;
  const r = data.report ?? {};
  const doneMs = (s: string) => stages[s]?.ms ?? r.timings_ms?.[s];
  const visible = data.candidates.filter((c) => showDuplicates || c.match_status !== "duplicate");
  const duplicates = data.candidates.length - data.candidates.filter((c) => c.match_status !== "duplicate").length;
  const pending = visible.filter((c) => c.decision === "pending").length;

  return (
    <div className="space-y-5">
      <ol className="grid gap-2 sm:grid-cols-5" aria-label="Compiler stages">
        {data.stages.map(({ stage, label }) => {
          const ms = doneMs(stage);
          const running = data.status === "running" && stages[stage]?.state === "running";
          return (
            <li key={stage} className={clsx("border-t-2 pt-2 text-xs", ms != null ? "border-teal" : running ? "border-amber" : "border-rule")}>
              <span className="block font-medium text-ink">{label}</span>
              <span className="text-graphite">
                {running ? (
                  <span className="inline-flex items-center gap-1">
                    <Loader2 className="h-3 w-3 animate-spin" aria-hidden="true" /> working
                  </span>
                ) : ms != null ? (
                  `${(ms / 1000).toFixed(1)} s${stages[stage]?.found != null ? ` · ${stages[stage].found}` : ""}`
                ) : data.status === "failed" ? (
                  "stopped"
                ) : (
                  "waiting"
                )}
              </span>
            </li>
          );
        })}
      </ol>

      {data.status === "failed" && <ErrorState message={r.error ?? "The compiler could not read this document."} />}
      {data.status === "ready" && r.llm && r.llm.llm !== "ok" && (
        <p role="status" className="border-l-2 border-amber bg-sheet px-3 py-2 text-sm">
          {r.llm.llm === "failed" ? "The LLM did not answer in time" : "No LLM is configured on this server"}, so only structured extraction ran: tables, word lists, colours, limits
          and quoted phrases. Rules written only as prose (logo, accessibility, facts) are missing; compile again later to add them.
        </p>
      )}
      {data.status === "ready" && (
        <p className="text-sm text-graphite">
          {r.pages} pages · {r.structured} structured candidates{r.llm?.llm === "ok" ? `, ${r.from_llm} from the LLM (${r.llm.dropped} dropped by the schema check)` : ""} ·{" "}
          {r.by_status?.new ?? 0} new, {r.by_status?.update ?? 0} updates, {r.by_status?.duplicate ?? 0} already in the rulebook · Decided {data.summary.decided}: {data.summary.accepted}{" "}
          accepted ({data.summary.accepted_without_edits} without edits), {data.summary.rejected} rejected
        </p>
      )}

      {data.status === "ready" && (
        <section aria-labelledby="review-queue">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-rule pb-2">
            <h2 id="review-queue" className="label mb-0">
              Review queue · {pending} waiting
            </h2>
            {duplicates > 0 && (
              <label className="flex items-center gap-2 text-xs text-graphite">
                <input type="checkbox" checked={showDuplicates} onChange={(e) => setShowDuplicates(e.target.checked)} /> Show {duplicates} already in the rulebook
              </label>
            )}
          </div>
          {visible.length === 0 ? (
            <p className="py-4 text-sm text-graphite">Everything this document says is already in the rulebook.</p>
          ) : (
            <ul className="divide-y divide-rule">
              {visible.map((c) => (
                <CandidateRow key={c.id} c={c} canEdit={canEdit} onDecided={() => void mutate()} />
              ))}
            </ul>
          )}
        </section>
      )}
    </div>
  );
}

export function CompilerTab({ canEdit }: { canEdit: boolean }) {
  const { data: jobs, error, mutate } = useSWR<Omit<Job, "candidates" | "summary" | "stages">[]>("/api/compiler/jobs");
  const [selected, setSelected] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const input = useRef<HTMLInputElement>(null);
  if (error) return <ErrorState message={error.message} onRetry={() => mutate()} />;
  if (!jobs) return <Skeleton className="h-48" />;
  const current = selected ?? jobs[0]?.id ?? null;

  async function start(file?: File) {
    const form = new FormData();
    if (file) form.set("file", file);
    else form.set("use_sample", "true");
    setStarting(true);
    setProblem(null);
    try {
      const { id } = await api<{ id: string }>("/api/compiler/jobs", { method: "POST", body: form });
      setSelected(id);
      await mutate();
    } catch (e) {
      setProblem(e instanceof ApiError ? e.message : "Could not start the compiler.");
    } finally {
      setStarting(false);
      if (input.current) input.current.value = "";
    }
  }

  return (
    <div className="space-y-5">
      <p className="max-w-[75ch] text-sm leading-relaxed text-graphite">
        The Rulebook Compiler reads a brand book and drafts typed rules with the page each came from. Tables, word lists, colours and numeric limits are read directly; prose rules are
        extracted by the LLM and checked against the rule schema. Each candidate is compared with your rulebook. Nothing changes until a brand manager accepts it: accepted rules become new
        rule versions, cited to the page, and the change is audit-logged.
      </p>
      <div className="flex flex-wrap items-center gap-2">
        {canEdit && (
          <>
            <button type="button" className="btn-teal" disabled={starting} onClick={() => start()}>
              {starting ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <FileText className="h-4 w-4" aria-hidden="true" />} Compile the sample brand book
            </button>
            <button type="button" className="btn-ghost" disabled={starting} onClick={() => input.current?.click()}>
              <Upload className="h-4 w-4" aria-hidden="true" /> Upload a PDF or DOCX
            </button>
            <input ref={input} type="file" accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document" className="hidden" onChange={(e) => e.target.files?.[0] && start(e.target.files[0])} />
          </>
        )}
        <a href={`${API_URL}/api/compiler/sample`} className="btn-ghost text-xs" target="_blank" rel="noreferrer">
          <Download className="h-3.5 w-3.5" aria-hidden="true" /> The sample: PayWise Brand Book (fictional, 20 pages)
        </a>
      </div>
      {problem && <ErrorState message={problem} />}

      {jobs.length > 1 && (
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <label htmlFor="compile-job" className="label mb-0">Run</label>
          <select id="compile-job" className="input w-auto py-1 text-xs" value={current ?? ""} onChange={(e) => setSelected(e.target.value)}>
            {jobs.map((j) => (
              <option key={j.id} value={j.id}>
                {j.filename} · {timeAgo(j.created_at)} · {j.status}
              </option>
            ))}
          </select>
        </div>
      )}

      {current ? (
        <JobView key={current} jobId={current} canEdit={canEdit} onChanged={() => void mutate()} />
      ) : (
        <EmptyState title="No brand book compiled yet" text={canEdit ? "Compile the sample brand book to see the review queue." : "A brand manager can compile a brand book here."} />
      )}
    </div>
  );
}
