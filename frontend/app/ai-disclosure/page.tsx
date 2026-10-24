import Link from "next/link";

import { Footer } from "@/components/Footer";
import { Logo } from "@/components/Logo";

export const metadata = { title: "AI disclosure" };

const ROWS = [
  ["Claim verification", "Local NLI model cross-encoder/nli-deberta-v3-xsmall, plus exact number comparison and a verbatim quote check", "On the Preflight server"],
  ["Fact retrieval", "BAAI/bge-small-en-v1.5 embeddings (fastembed) fused with BM25", "On the Preflight server"],
  ["Claim detection", "Pattern rules, plus Google Gemini (gemini-3.5-flash-lite) proposals", "Gemini sees masked text only"],
  ["Tone scoring", "Gemini scores five voice traits with quotes; a lexicon heuristic is the offline fallback", "Gemini sees masked text only"],
  ["Suggestions", "Brand-approved wording from the rulebook first; Gemini only where none exists, limited to approved facts", "Gemini sees masked text only"],
  ["Building Preflight", "Claude Code (Anthropic) assisted with code, tests and documentation", "Development only"],
];

export default function AiDisclosurePage() {
  return (
    <>
      <div className="mx-auto max-w-3xl px-6 py-10">
        <Link href="/"><Logo /></Link>
        <h1 className="mt-8 text-3xl font-bold tracking-tight">AI disclosure</h1>
        <p className="mt-3 text-navy-500">
          Preflight uses AI to propose and explain, never to decide. Whether a claim is true is settled by retrieval, a local NLI model and exact comparisons against approved facts. People accept, edit, dispute or approve, and every decision is written to a hash-chained audit log.
        </p>
        <div className="mt-8 overflow-hidden rounded-2xl border border-paper-200">
          <table className="w-full text-left text-sm">
            <thead className="bg-paper-100 text-xs uppercase tracking-wide text-navy-500">
              <tr>
                <th className="px-4 py-2">Task</th>
                <th className="px-4 py-2">What is used</th>
                <th className="px-4 py-2">Where data goes</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-paper-200 bg-paper-50">
              {ROWS.map(([task, what, where]) => (
                <tr key={task} className="align-top">
                  <td className="px-4 py-3 font-semibold">{task}</td>
                  <td className="px-4 py-3 text-navy-500">{what}</td>
                  <td className="px-4 py-3 text-navy-500">{where}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <h2 className="mt-10 text-xl font-semibold">Privacy</h2>
        <p className="mt-2 text-navy-500">
          Before any external call, confidential terms from the Brand Knowledge Base (for example “Project Falcon”), email addresses, phone numbers and ₹ amounts are replaced with tokens such as [CONFIDENTIAL_1] and restored afterwards. With no LLM key configured, Preflight runs fully offline in deterministic mode. Every review has its own “AI used in this review” panel listing exactly what ran.
        </p>
      </div>
      <Footer />
    </>
  );
}
