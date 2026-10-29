"use client";

import { Modal } from "./ui";

export const TOUR_EVENT = "preflight:tour";

const SHORTCUTS = [
  ["J / K", "Next / previous finding"],
  ["A", "Accept the focused suggestion"],
  ["E", "Edit the focused finding"],
  ["D", "Dispute the focused finding"],
  ["?", "Open this help"],
];

const GLOSSARY = [
  ["Brand Score", "100 minus 25 per critical, 10 per major and 3 per minor open finding. Findings waiting for a human look do not count yet."],
  ["Severity", "Critical findings block approval. Major findings should be fixed. Minor findings are polish."],
  ["Confidence", "How sure Preflight is. Below 60% a finding goes to “Needs a human look” instead of the main list."],
  ["Drift", "How far a suggestion moves the meaning of the sentence (1 − cosine similarity). Low drift keeps your intent."],
  ["Claim Ledger", "Every factual claim, checked against the approved-facts registry with a local NLI model, exact numbers and a verbatim quote."],
];

export function HelpPanel({ open, onClose }: { open: boolean; onClose: () => void }) {
  return (
    <Modal
      open={open}
      title="Help"
      onClose={onClose}
      footer={
        <button
          type="button"
          className="btn-teal"
          onClick={() => {
            onClose();
            window.dispatchEvent(new Event(TOUR_EVENT));
          }}
        >
          Restart the guided tour
        </button>
      }
    >
      <h3 className="label">Keyboard shortcuts (review page)</h3>
      <dl className="mb-5 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
        {SHORTCUTS.map(([key, text]) => (
          <div key={key} className="contents">
            <dt>
              <kbd className="rounded-md border border-paper-200 bg-raised px-1.5 py-0.5 font-mono text-xs">{key}</kbd>
            </dt>
            <dd className="text-navy-500">{text}</dd>
          </div>
        ))}
      </dl>
      <h3 className="label">What the numbers mean</h3>
      <dl className="space-y-2 text-sm">
        {GLOSSARY.map(([term, text]) => (
          <div key={term}>
            <dt className="font-semibold">{term}</dt>
            <dd className="text-navy-500">{text}</dd>
          </div>
        ))}
      </dl>
    </Modal>
  );
}
