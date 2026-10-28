"use client";

import { clsx } from "clsx";
import { Bell, ChevronDown, Cpu, HelpCircle } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import useSWR from "swr";

import { fetcher, post } from "@/lib/api";
import { timeAgo } from "@/lib/format";
import { ROLE_LABEL, useSession } from "@/lib/session";
import type { Health, Notification, UserRef } from "@/lib/types";

import { Logo } from "./Logo";
import { Tip } from "./ui";

const NAV = [
  { href: "/app", label: "Dashboard", exact: true },
  { href: "/app/review/new", label: "New review" },
  { href: "/app/queue", label: "Queue", permission: "approve" },
  { href: "/app/rulebook", label: "Rulebook" },
  { href: "/app/governance", label: "Governance" },
  { href: "/app/insights", label: "Insights", permission: "view_insights" },
  { href: "/app/evaluation", label: "Evaluation" },
  { href: "/app/settings", label: "Settings" },
];

function useOutside(onOutside: () => void) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const handle = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onOutside();
    };
    document.addEventListener("mousedown", handle);
    return () => document.removeEventListener("mousedown", handle);
  }, [onOutside]);
  return ref;
}

function AiMode() {
  const { data } = useSWR<Health>("/health", fetcher, { refreshInterval: 30_000 });
  const hosted = data && data.llm_provider !== "none";
  return (
    <Tip text={hosted ? `Hosted LLM (${data?.llm_provider}) for claim extraction, tone and wording; local NLI model decides verdicts. Confidential terms are masked first.` : "Deterministic only: no external AI calls. Rules, local NLI and lexicon checks still run."}>
      <span className={clsx("hidden items-center gap-1 border px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-wide lg:inline-flex", hosted ? "border-teal/40 text-teal-700" : "border-rule text-graphite")}>
        <Cpu className="h-3 w-3" aria-hidden="true" /> {hosted ? "Hosted LLM" : "Deterministic only"}
      </span>
    </Tip>
  );
}

function Notifications() {
  const [open, setOpen] = useState(false);
  const ref = useOutside(() => setOpen(false));
  const { user } = useSession();
  const { data, mutate } = useSWR<Notification[]>(user ? ["/api/notifications", user.id] : null, ([path]: [string]) => fetcher<Notification[]>(path), { refreshInterval: 15_000 });
  const unread = data?.filter((n) => !n.read).length ?? 0;
  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        aria-label={`Notifications${unread ? `, ${unread} unread` : ""}`}
        onClick={() => {
          setOpen((o) => !o);
          if (unread) void post("/api/notifications/read").then(() => mutate());
        }}
        className="relative rounded p-2 text-graphite hover:bg-paper-100 hover:text-ink"
      >
        <Bell className="h-4 w-4" />
        {unread > 0 && <span className="absolute right-1 top-1 flex h-4 min-w-4 items-center justify-center bg-signal px-1 font-mono text-[10px] text-white">{unread}</span>}
      </button>
      {open && (
        <div className="absolute right-0 z-50 mt-2 w-80 border border-rule bg-sheet p-2 shadow-sheet">
          <p className="label px-2 py-1">Notifications</p>
          {!data?.length && <p className="px-2 py-4 text-sm text-navy-500">Nothing yet. You will hear about submissions, change requests and approvals here.</p>}
          <ul className="max-h-80 overflow-auto">
            {data?.map((n) => (
              <li key={n.id}>
                <Link href={n.submission_id ? `/app/review/${n.submission_id}` : "/app"} onClick={() => setOpen(false)} className="block border-b border-rule px-2 py-2 text-sm hover:bg-paper">
                  <span className={clsx(!n.read && "font-semibold")}>{n.message}</span>
                  <span className="block text-xs text-navy-500">{timeAgo(n.created_at)}</span>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

/** "abhi3" -> "A3", "Jane Doe" -> "JD". */
function initials(name: string): string {
  const parts = name.trim().split(/\s+/);
  if (parts.length > 1) return (parts[0][0] + parts[1][0]).toUpperCase();
  const digit = name.match(/\d+$/)?.[0] ?? "";
  return (name[0] + digit).toUpperCase().slice(0, 3);
}

function RoleSwitcher() {
  const { user, switchUser, resetSandbox } = useSession();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const ref = useOutside(() => setOpen(false));
  const { data: users } = useSWR<UserRef[]>("/api/users", fetcher);
  return (
    <div ref={ref} className="relative" data-tour="role-switcher">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="listbox"
        aria-expanded={open}
        className="flex items-center gap-2 rounded border border-rule bg-sheet py-1 pl-1 pr-2 text-left text-sm hover:bg-paper"
      >
        <span className="flex h-7 w-7 items-center justify-center rounded-sm bg-ink font-mono text-[11px] font-medium text-sheet">{user ? initials(user.name) : "…"}</span>
        <span className="hidden leading-tight sm:block">
          <span className="block text-xs font-semibold">{user?.name ?? "Signing in…"}</span>
          <span className="block text-[11px] text-navy-500">{user ? ROLE_LABEL[user.role] : ""}</span>
        </span>
        <ChevronDown className="h-3.5 w-3.5 text-navy-500" aria-hidden="true" />
      </button>
      {open && (
        <div role="listbox" className="absolute right-0 z-50 mt-2 w-72 border border-rule bg-sheet p-2 shadow-sheet">
          <p className="px-2 py-1 text-xs text-graphite">Switch demo user. Each role sees and can do different things.</p>
          {users?.map((u) => (
            <button
              key={u.id}
              type="button"
              role="option"
              aria-selected={u.id === user?.id}
              disabled={busy}
              onClick={async () => {
                setBusy(true);
                setOpen(false);
                try {
                  await switchUser(u.id);
                } finally {
                  setBusy(false);
                }
              }}
              className={clsx("flex w-full items-center justify-between border-l-2 px-2 py-2 text-left text-sm hover:bg-paper", u.id === user?.id ? "border-teal bg-paper" : "border-transparent")}
            >
              <span>
                <span className="block font-semibold">{u.name}</span>
                <span className="block text-xs text-navy-500">{u.title}</span>
              </span>
              <span className="font-mono text-[10px] uppercase tracking-wide text-graphite">{ROLE_LABEL[u.role]}</span>
            </button>
          ))}
          <div className="mt-1 border-t border-rule px-2 pt-2">
            <p className="text-xs text-graphite">This is your private copy of the PayWise workspace. Nobody else sees it; it is deleted after 24 hours without use.</p>
            <button
              type="button"
              disabled={busy}
              className="mt-1 text-xs text-ink underline decoration-rule underline-offset-2 hover:decoration-ink"
              onClick={async () => {
                if (!window.confirm("Reset your demo workspace to its starting state?")) return;
                setBusy(true);
                setOpen(false);
                try {
                  await resetSandbox();
                } finally {
                  setBusy(false);
                }
              }}
            >
              Reset my demo workspace
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export function AppHeader({ onHelp }: { onHelp: () => void }) {
  const pathname = usePathname();
  const { can } = useSession();
  return (
    <header className="sticky top-0 z-40 border-b border-rule bg-paper">
      <div className="mx-auto flex h-14 max-w-7xl items-center gap-4 px-4 sm:px-6">
        <Link href="/" aria-label="Preflight home">
          <Logo />
        </Link>
        <nav className="hidden h-14 flex-1 items-stretch gap-1 overflow-x-auto md:flex" aria-label="Main">
          {NAV.filter((n) => !n.permission || can(n.permission)).map((n) => {
            const active = n.exact ? pathname === n.href : pathname.startsWith(n.href);
            return (
              <Link key={n.href} href={n.href} aria-current={active ? "page" : undefined} className={clsx("-mb-px whitespace-nowrap border-b-2 px-2.5 py-4 text-sm", active ? "border-ink font-medium text-ink" : "border-transparent text-graphite hover:text-ink")}>
                {n.label}
              </Link>
            );
          })}
        </nav>
        <div className="ml-auto flex items-center gap-2">
          <AiMode />
          <Tip text="Demo mode: you have a private copy of the fictional PayWise workspace. Use the switcher to act as any of its five users. Nothing you do is visible to other visitors.">
            <span className="hidden border border-amber/50 px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-wide text-amber-700 sm:inline-flex">Demo mode</span>
          </Tip>
          <button type="button" onClick={onHelp} aria-label="Help and keyboard shortcuts" className="rounded p-2 text-graphite hover:bg-paper-100 hover:text-ink">
            <HelpCircle className="h-4 w-4" />
          </button>
          <Notifications />
          <RoleSwitcher />
        </div>
      </div>
      <nav className="flex gap-1 overflow-x-auto border-t border-rule px-4 py-1 md:hidden" aria-label="Main (mobile)">
        {NAV.filter((n) => !n.permission || can(n.permission)).map((n) => (
          <Link key={n.href} href={n.href} className="whitespace-nowrap px-2 py-1 text-xs text-graphite">
            {n.label}
          </Link>
        ))}
      </nav>
    </header>
  );
}
