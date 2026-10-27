import Link from "next/link";

import { API_URL, GITHUB_URL } from "@/lib/api";

export function Footer() {
  return (
    <footer className="border-t border-rule bg-paper">
      <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 px-6 py-5 text-xs text-graphite">
        <span>Preflight · CodeAxis · team kabhijith447</span>
        <nav className="flex flex-wrap items-center gap-x-4 gap-y-1">
          <span>Demo data is fictional (PayWise is not a real company)</span>
          <span aria-hidden="true">·</span>
          <Link href="/ai-disclosure" className="underline-offset-2 hover:underline">AI disclosure</Link>
          <span aria-hidden="true">·</span>
          <a href={`${API_URL}/docs`} target="_blank" rel="noreferrer" className="underline-offset-2 hover:underline">API docs</a>
          <span aria-hidden="true">·</span>
          <a href={GITHUB_URL} target="_blank" rel="noreferrer" className="underline-offset-2 hover:underline">GitHub</a>
        </nav>
      </div>
    </footer>
  );
}
