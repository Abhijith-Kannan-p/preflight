"use client";

import { BadgeCheck, Copy, KeyRound, Loader2, RotateCcw, Send, ShieldAlert, Trash2, Webhook as WebhookIcon } from "lucide-react";
import { useState } from "react";
import useSWR from "swr";

import { Chip, EmptyState, ErrorState, PageHeader, Skeleton } from "@/components/ui";
import { API_URL, ApiError, api, post } from "@/lib/api";
import { timeAgo } from "@/lib/format";
import { useSession } from "@/lib/session";

interface AiStatus {
  provider: string;
  model: string | null;
  mode: "llm" | "deterministic" | "degraded";
  masking_enabled: boolean;
  timeout_seconds: number;
}

interface ApiKeyRow {
  id: string;
  name: string;
  prefix: string;
  created_at: string;
  last_used_at: string | null;
  revoked_at: string | null;
}

interface Attempt {
  at: string;
  status_code: number | null;
  error: string | null;
  latency_ms: number;
  ok: boolean;
}

interface Delivery {
  id: number;
  event: string;
  status: "delivered" | "retrying" | "failed";
  status_code: number | null;
  latency_ms: number;
  ok: boolean;
  error: string | null;
  attempts: number;
  attempt_log: Attempt[];
  resent_from: number | null;
  created_at: string;
}

const EVENTS: { id: string; label: string }[] = [
  { id: "submission.approved", label: "Approved" },
  { id: "review.published", label: "Published" },
  { id: "finding.critical", label: "Critical finding" },
];

const DELIVERY_STYLE: Record<Delivery["status"], string> = {
  delivered: "text-teal-700",
  retrying: "text-amber-700",
  failed: "text-danger-700",
};

interface Hook {
  id: string;
  url: string;
  slack_format: boolean;
  events: string[];
  active: boolean;
  secret: string;
  deliveries: Delivery[];
}

const MODE_TEXT: Record<AiStatus["mode"], string> = {
  llm: "Hosted LLM active",
  deterministic: "Deterministic only (no LLM key)",
  degraded: "Circuit breaker open: deterministic for 60 s",
};

function Section({ title, description, children }: { title: string; description: string; children: React.ReactNode }) {
  return (
    <section className="card p-6">
      <h2 className="text-lg font-semibold">{title}</h2>
      <p className="mb-4 mt-1 text-sm text-navy-500">{description}</p>
      {children}
    </section>
  );
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button type="button" className="btn-ghost py-1 text-xs" onClick={async () => { await navigator.clipboard.writeText(text); setCopied(true); }}>
      <Copy className="h-3.5 w-3.5" aria-hidden="true" /> {copied ? "Copied" : "Copy"}
    </button>
  );
}

function AiSection({ admin }: { admin: boolean }) {
  const { data, mutate } = useSWR<AiStatus>("/api/settings/ai");
  const [error, setError] = useState<string | null>(null);
  if (!data) return <Skeleton className="h-40" />;
  return (
    <Section title="AI and privacy" description="The hosted LLM only proposes claims, scores tone and words suggestions. Verdicts come from the local NLI model and exact comparisons.">
      <dl className="grid gap-4 text-sm sm:grid-cols-3">
        <div><dt className="label">Provider</dt><dd className="font-semibold">{data.provider === "none" ? "None" : `${data.provider} · ${data.model}`}</dd></div>
        <div><dt className="label">Status</dt><dd><Chip className={data.mode === "llm" ? "bg-teal-50 text-teal-700 ring-teal/30" : "bg-amber-50 text-amber-700 ring-amber/30"}>{MODE_TEXT[data.mode]}</Chip></dd></div>
        <div><dt className="label">Timeout</dt><dd className="font-semibold">{data.timeout_seconds} s, one retry, then fallback</dd></div>
      </dl>
      <label className="mt-5 flex items-start gap-3 rounded-xl bg-paper-100 p-3 text-sm">
        <input
          type="checkbox"
          className="mt-1"
          checked={data.masking_enabled}
          disabled={!admin}
          onChange={async (e) => {
            setError(null);
            try {
              await api("/api/settings/masking", { method: "PUT", body: JSON.stringify({ enabled: e.target.checked }) });
              await mutate();
            } catch (err) {
              setError(err instanceof Error ? err.message : "Could not change masking.");
            }
          }}
        />
        <span>
          <strong>Mask confidential data before any external AI call</strong> (recommended, on by default)
          <span className="block text-navy-500">Confidential terms from the Rulebook, emails, phone numbers and ₹ amounts become tokens such as [CONFIDENTIAL_1] and are restored afterwards.{!admin && " Only the admin can change this."}</span>
        </span>
      </label>
      {error && <div className="mt-3"><ErrorState message={error} /></div>}
    </Section>
  );
}

function KeysSection() {
  const { data, error, mutate } = useSWR<ApiKeyRow[]>("/api/settings/keys");
  const [name, setName] = useState("CMS publish hook");
  const [created, setCreated] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const curl = `curl -X POST ${API_URL}/api/v1/preflight \\
  -H "X-API-Key: ${created ?? "pf_live_…"}" \\
  -H "Content-Type: application/json" \\
  -d '{"content": "PayWise is 100% secure!", "channel": "linkedin"}'`;
  return (
    <Section title="API keys" description="Let a CMS or pipeline call Preflight before publishing: POST /api/v1/preflight returns findings, the Claim Ledger, the Brand Score and a `blocking` flag. Rate limit: 30 requests per minute per key.">
      {error && <ErrorState message={error.message} onRetry={() => mutate()} />}
      <div className="flex flex-wrap gap-2">
        <input className="input max-w-xs" value={name} onChange={(e) => setName(e.target.value)} aria-label="Key name" />
        <button
          type="button"
          className="btn-teal"
          onClick={async () => {
            setFormError(null);
            try {
              const key = await post<{ key: string }>("/api/settings/keys", { name });
              setCreated(key.key);
              await mutate();
            } catch (e) {
              setFormError(e instanceof ApiError ? e.message : "Could not create the key.");
            }
          }}
        >
          <KeyRound className="h-4 w-4" aria-hidden="true" /> Create key
        </button>
      </div>
      {formError && <div className="mt-3"><ErrorState message={formError} /></div>}
      {created && (
        <div className="mt-3 rounded-xl border border-teal/30 bg-teal-50 p-3 text-sm">
          <p className="font-semibold text-teal-700">Copy this key now. It is shown only once.</p>
          <div className="mt-2 flex items-center gap-2"><code className="flex-1 break-all rounded bg-raised px-2 py-1 font-mono text-xs">{created}</code><CopyButton text={created} /></div>
        </div>
      )}
      <ul className="mt-4 divide-y divide-paper-200 text-sm">
        {data?.map((k) => (
          <li key={k.id} className="flex flex-wrap items-center gap-3 py-2">
            <span className="font-medium">{k.name}</span>
            <code className="font-mono text-xs text-navy-500">{k.prefix}…</code>
            <span className="text-xs text-navy-500">created {timeAgo(k.created_at)} · {k.last_used_at ? `last used ${timeAgo(k.last_used_at)}` : "never used"}</span>
            {k.revoked_at ? (
              <Chip className="ml-auto bg-paper-100 text-navy-500 ring-paper-200">Revoked</Chip>
            ) : (
              <button type="button" className="btn-ghost ml-auto py-1 text-xs" onClick={async () => { await api(`/api/settings/keys/${k.id}`, { method: "DELETE" }); void mutate(); }}>Revoke</button>
            )}
          </li>
        ))}
        {data && !data.length && <li className="py-2 text-navy-500">No keys yet.</li>}
      </ul>
      <div className="mt-4">
        <div className="mb-1 flex items-center justify-between"><span className="label">Try it</span><CopyButton text={curl} /></div>
        <pre tabIndex={0} aria-label="curl example" className="overflow-x-auto rounded-xl bg-navy p-3 text-xs leading-relaxed text-paper-50">{curl}</pre>
        <p className="mt-2 text-xs text-navy-500">Full reference: <a className="font-medium text-teal-700 underline" href={`${API_URL}/docs`} target="_blank" rel="noreferrer">OpenAPI docs</a>. A runnable CMS example is in <code>examples/cms_hook.py</code> on GitHub.</p>
      </div>
    </Section>
  );
}

function attemptText(a: Attempt): string {
  return a.status_code != null ? `HTTP ${a.status_code}` : (a.error ?? "no response");
}

function EventChoices({ value, onChange, idPrefix, disabled }: { value: string[]; onChange: (events: string[]) => void; idPrefix: string; disabled?: boolean }) {
  return (
    <fieldset className="flex flex-wrap items-center gap-3 text-sm" disabled={disabled}>
      <legend className="sr-only">Events</legend>
      {EVENTS.map((e) => (
        <label key={e.id} htmlFor={`${idPrefix}-${e.id}`} className="flex items-center gap-1.5">
          <input
            id={`${idPrefix}-${e.id}`}
            type="checkbox"
            checked={value.includes(e.id)}
            onChange={(ev) => {
              const next = ev.target.checked ? [...value, e.id] : value.filter((x) => x !== e.id);
              if (next.length) onChange(next);
            }}
          />
          {e.label} <code className="font-mono text-[11px] text-navy-500">{e.id}</code>
        </label>
      ))}
    </fieldset>
  );
}

function WebhooksSection() {
  const { data, error, mutate } = useSWR<Hook[]>("/api/settings/webhooks", {
    // Retries run in the background (2 s, then 4 s): refresh until they settle.
    refreshInterval: (hooks) => (hooks?.some((h) => h.deliveries.some((d) => d.status === "retrying")) ? 2000 : 0),
  });
  const [url, setUrl] = useState("");
  const [slack, setSlack] = useState(false);
  const [events, setEvents] = useState(EVENTS.map((e) => e.id));
  const [busy, setBusy] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);

  async function act(key: string, call: () => Promise<unknown>) {
    setBusy(key);
    setFormError(null);
    try {
      await call();
      await mutate();
    } catch (e) {
      setFormError(e instanceof ApiError ? e.message : "That did not work. Try again.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <Section
      title="Outgoing webhooks"
      description="Preflight POSTs a signed JSON event (header X-Preflight-Signature: sha256=HMAC of the body) when a submission is approved, when it is marked as published, and when a review finds a critical issue. Failed deliveries are retried twice, after 2 s and 4 s. Turn on Slack format to post straight into a Slack incoming webhook."
    >
      {error && <ErrorState message={error.message} onRetry={() => mutate()} />}
      <div className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <input className="input max-w-md" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://hooks.slack.com/services/… or https://webhook.site/…" aria-label="Webhook URL" />
          <label className="flex items-center gap-1.5 text-sm"><input type="checkbox" checked={slack} onChange={(e) => setSlack(e.target.checked)} /> Slack format</label>
          <button
            type="button"
            className="btn-teal"
            disabled={!url || busy === "add"}
            onClick={() =>
              act("add", async () => {
                await post("/api/settings/webhooks", { url, slack_format: slack, events });
                setUrl("");
              })
            }
          >
            <WebhookIcon className="h-4 w-4" aria-hidden="true" /> Add webhook
          </button>
        </div>
        <EventChoices value={events} onChange={setEvents} idPrefix="new-hook" />
      </div>
      {formError && <div className="mt-3"><ErrorState message={formError} /></div>}
      {data && !data.length && <div className="mt-4"><EmptyState title="No webhooks yet" text="Paste a URL from webhook.site to watch a signed event arrive, or a Slack incoming-webhook URL with Slack format on." /></div>}
      <div className="mt-4 space-y-4">
        {data?.map((h) => (
          <div key={h.id} className="rounded-xl border border-paper-200 p-4 text-sm">
            <div className="flex flex-wrap items-center gap-2">
              <code className="flex-1 break-all font-mono text-xs">{h.url}</code>
              {h.slack_format && <Chip className="bg-purple-50 text-purple-700 ring-purple/30">Slack</Chip>}
              <button type="button" className="btn-ghost py-1 text-xs" disabled={busy === h.id} onClick={() => act(h.id, () => post(`/api/settings/webhooks/${h.id}/test`, undefined, `test-${h.id}-${Date.now()}`))}>
                {busy === h.id ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Send className="h-3.5 w-3.5" aria-hidden="true" />} Send test event
              </button>
              <button type="button" aria-label="Delete webhook" className="rounded-lg p-1.5 text-navy-500 hover:bg-danger-50 hover:text-danger" onClick={() => act(`del-${h.id}`, () => api(`/api/settings/webhooks/${h.id}`, { method: "DELETE" }))}>
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </div>
            <div className="mt-2">
              <EventChoices
                value={h.events}
                idPrefix={h.id}
                disabled={busy === `events-${h.id}`}
                onChange={(next) => act(`events-${h.id}`, () => api(`/api/settings/webhooks/${h.id}`, { method: "PATCH", body: JSON.stringify({ events: next }) }))}
              />
            </div>
            <p className="mt-2 text-xs text-navy-500">Signing secret: <code className="font-mono">{h.secret.slice(0, 8)}…</code> <CopyButton text={h.secret} /></p>
            <div className="mt-3 overflow-x-auto">
              <table className="w-full text-xs">
                <caption className="sr-only">Delivery log for {h.url}</caption>
                <thead className="text-left text-navy-500">
                  <tr>
                    <th scope="col" className="py-1">Delivery</th>
                    <th scope="col" className="py-1">Status</th>
                    <th scope="col" className="py-1">Attempts</th>
                    <th scope="col" className="py-1 text-right"><span className="sr-only">Actions</span></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-paper-200">
                  {h.deliveries.map((d) => (
                    <tr key={d.id}>
                      <td className="py-1.5 pr-2">
                        {d.event} · {timeAgo(d.created_at)}
                        {d.resent_from && <span className="block text-navy-500">resend of #{d.resent_from}</span>}
                      </td>
                      <td className={`py-1.5 pr-2 font-mono ${DELIVERY_STYLE[d.status]}`}>
                        {d.status === "retrying" && <Loader2 className="mr-1 inline h-3 w-3 animate-spin" aria-hidden="true" />}
                        {d.status}
                        <span className="block text-navy-500">{d.status_code != null ? `HTTP ${d.status_code}` : d.error ?? ""} · {d.latency_ms} ms</span>
                      </td>
                      <td className="py-1.5 pr-2 font-mono" title={d.attempt_log.map((a, i) => `#${i + 1} ${attemptText(a)}`).join(" · ")}>
                        {d.attempts} / 3
                        <span className="block text-navy-500">{d.attempt_log.map(attemptText).join(" → ")}</span>
                      </td>
                      <td className="py-1.5 text-right">
                        {d.status !== "retrying" && (
                          <button
                            type="button"
                            className="btn-ghost py-1 text-xs"
                            disabled={busy === `resend-${d.id}`}
                            aria-label={`Resend delivery ${d.id}`}
                            onClick={() => act(`resend-${d.id}`, () => post(`/api/settings/webhooks/${h.id}/deliveries/${d.id}/resend`, undefined, `resend-${d.id}-${Date.now()}`))}
                          >
                            {busy === `resend-${d.id}` ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />} Resend
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                  {!h.deliveries.length && <tr><td className="py-1 text-navy-500" colSpan={4}>No deliveries yet. Send a test event.</td></tr>}
                </tbody>
              </table>
            </div>
          </div>
        ))}
      </div>
    </Section>
  );
}

function AuditSection() {
  const [result, setResult] = useState<{ intact: boolean; message: string } | null>(null);
  const [busy, setBusy] = useState(false);
  return (
    <Section title="Audit chain" description="Every decision is an append-only event whose hash includes the previous one. Verification recomputes the whole chain; any edit to history breaks it.">
      <button type="button" className="btn-primary" disabled={busy} onClick={async () => { setBusy(true); try { setResult(await api("/api/audit/verify")); } finally { setBusy(false); } }}>
        {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <BadgeCheck className="h-4 w-4" aria-hidden="true" />} Verify audit chain
      </button>
      {result && (
        <p role="status" className={`mt-3 flex items-center gap-2 text-sm font-medium ${result.intact ? "text-teal-700" : "text-danger-700"}`}>
          {result.intact ? <BadgeCheck className="h-4 w-4" aria-hidden="true" /> : <ShieldAlert className="h-4 w-4" aria-hidden="true" />} {result.message}
        </p>
      )}
    </Section>
  );
}

function ResetSection() {
  const { resetSandbox } = useSession();
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  return (
    <Section title="Reset demo data" description="Puts your private demo workspace back to its starting state: the PayWise rulebook, facts, personas and review history, with a fresh audit chain. API keys and webhooks you created are removed. Other visitors are not affected.">
      <button
        type="button"
        className="btn-danger"
        disabled={busy}
        onClick={async () => {
          if (!window.confirm("Reset all demo data? This cannot be undone.")) return;
          setBusy(true);
          try {
            await resetSandbox();
            setDone(true);
          } finally {
            setBusy(false);
          }
        }}
      >
        <RotateCcw className="h-4 w-4" aria-hidden="true" /> Reset demo data
      </button>
      {done && <p className="mt-3 text-sm text-teal-700">Done. The workspace is back to its starting state.</p>}
    </Section>
  );
}

export default function SettingsPage() {
  const { can } = useSession();
  const admin = can("administer");
  return (
    <div className="animate-fade-in space-y-6">
      <PageHeader title="Settings" subtitle="Integrations, AI and privacy, and the audit log." />
      {!admin && <p className="rounded-xl bg-amber-50 px-3 py-2 text-sm text-amber-700">API keys, webhooks, masking and the demo reset are managed by the admin. Switch to abhi5 (Admin) in the top right.</p>}
      <AiSection admin={admin} />
      {admin && <KeysSection />}
      {admin && <WebhooksSection />}
      <AuditSection />
      {admin && <ResetSection />}
    </div>
  );
}
