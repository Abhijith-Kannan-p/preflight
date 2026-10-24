"use client";

import { MessageCircle, Send } from "lucide-react";
import { useState } from "react";
import useSWR from "swr";

import { post } from "@/lib/api";
import { ROLE_LABEL, useSession } from "@/lib/session";
import { timeAgo } from "@/lib/format";
import type { Comment, Decision } from "@/lib/types";

import { EmptyState, ErrorState } from "../ui";

const DECISION_TEXT: Record<string, string> = {
  accept: "accepted a suggestion",
  edit: "edited a finding",
  dispute: "disputed a finding",
  escalate: "escalated a finding",
  reopen: "reopened a finding",
  submit: "submitted for approval",
  request_changes: "requested changes",
  approve: "approved",
  publish: "marked as published",
  override: "overrode a critical finding",
};

export function Comments({ reviewId, decisions }: { reviewId: string; decisions: Decision[] }) {
  const { can } = useSession();
  const { data, error, mutate } = useSWR<Comment[]>(`/api/reviews/${reviewId}/comments`);
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);
  const [postError, setPostError] = useState<string | null>(null);

  async function send() {
    setBusy(true);
    setPostError(null);
    try {
      await post(`/api/reviews/${reviewId}/comments`, { body });
      setBody("");
      await mutate();
    } catch (e) {
      setPostError(e instanceof Error ? e.message : "Could not post the comment.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <section>
        <h3 className="label">Comments</h3>
        {error && <ErrorState message={error.message} onRetry={() => mutate()} />}
        {data && !data.length && <EmptyState icon={<MessageCircle className="h-8 w-8" />} title="No comments yet" text="Reviewers and approvers can leave notes here. Change requests also appear in this thread." />}
        <ul className="space-y-3">
          {data?.map((c) => (
            <li key={c.id} className="card p-3 text-sm">
              <p className="text-xs text-navy-500">
                <span className="font-semibold text-navy">{c.author.name}</span> · {ROLE_LABEL[c.author.role]} · {timeAgo(c.created_at)}
              </p>
              <p className="mt-1 whitespace-pre-wrap">{c.body}</p>
            </li>
          ))}
        </ul>
        {can("comment") ? (
          <div className="mt-4">
            <label htmlFor="comment" className="sr-only">Add a comment</label>
            <textarea id="comment" className="input" rows={3} value={body} onChange={(e) => setBody(e.target.value)} placeholder="Add a comment…" maxLength={4000} />
            {postError && <div className="mt-2"><ErrorState message={postError} /></div>}
            <button type="button" className="btn-primary mt-2" disabled={busy || !body.trim()} onClick={send}>
              <Send className="h-4 w-4" aria-hidden="true" /> Post comment
            </button>
          </div>
        ) : (
          <p className="mt-4 text-xs text-navy-500">Your role cannot comment. Creators, reviewers, brand managers and approvers can.</p>
        )}
      </section>
      <section>
        <h3 className="label">Decision history</h3>
        {!decisions.length && <p className="text-sm text-navy-500">No decisions yet.</p>}
        <ol className="space-y-2 border-l border-paper-200 pl-4 text-sm">
          {[...decisions].reverse().map((d) => (
            <li key={d.id} className="relative">
              <span className="absolute -left-[21px] top-1.5 h-2.5 w-2.5 rounded-full bg-teal ring-4 ring-paper" aria-hidden="true" />
              <p>
                <span className="font-semibold">{d.actor.name}</span> {DECISION_TEXT[d.kind] ?? d.kind}
                {typeof d.payload.rule === "string" && <span className="font-mono text-xs"> {d.payload.rule}</span>}
              </p>
              {d.reason && <p className="text-xs text-navy-500">“{d.reason}”</p>}
              <p className="text-xs text-navy-300">{timeAgo(d.created_at)}</p>
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
}
