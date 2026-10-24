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
  { href: "/app/queue", label: "Approval queue", permission: "approve" },
  { href: "/app/rulebook", label: "Rulebook" },
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
      <span className={clsx("hidden items-center gap-1 rounded-full px-2 py-1 text-[11px] font-semibold ring-1 ring-inset lg:inline-flex", hosted ? "bg-teal-50 text-teal-700 ring-teal/30" : "bg-paper-100 text-navy-500 ring-paper-200")}>
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
        className="relative rounded-lg p-2 text-navy-500 hover:bg-paper-100 hover:text-navy"
      >
        <Bell className="h-4 w-4" />
        {unread > 0 && <span className="absolute right-1 top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-danger px-1 text-[10px] font-bold text-white">{unread}</span>}
      </button>
      {open && (
        <div className="absolute right-0 z-50 mt-2 w-80 rounded-2xl border border-paper-200 bg-paper-50 p-2 shadow-lift">
          <p className="px-2 py-1 text-xs font-semibold uppercase tracking-wide text-navy-500">Notifications</p>
          {!data?.length && <p className="px-2 py-4 text-sm text-navy-500">Nothing yet. You will hear about submissions, change requests and approvals here.</p>}
          <ul className="max-h-80 overflow-auto">
            {data?.map((n) => (
              <li key={n.id}>
                <Link href={n.submission_id ? `/app/review/${n.submission_id}` : "/app"} onClick={() => setOpen(false)} className="block rounded-xl px-2 py-2 text-sm hover:bg-paper-100">
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
  const { user, switchUser } = useSession();
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
        className="flex items-center gap-2 rounded-xl border border-paper-200 bg-paper-50 py-1 pl-1 pr-2 text-left text-sm hover:bg-paper-100"
      >
        <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-navy text-xs font-bold text-paper-50">{user ? initials(user.name) : "…"}</span>
        <span className="hidden leading-tight sm:block">
          <span className="block text-xs font-semibold">{user?.name ?? "Signing in…"}</span>
          <span className="block text-[11px] text-navy-500">{user ? ROLE_LABEL[user.role] : ""}</span>
        </span>
        <ChevronDown className="h-3.5 w-3.5 text-navy-500" aria-hidden="true" />
      </button>
      {open && (
        <div role="listbox" className="absolute right-0 z-50 mt-2 w-72 rounded-2xl border border-paper-200 bg-paper-50 p-2 shadow-lift">
          <p className="px-2 py-1 text-xs text-navy-500">Switch demo user. Each role sees and can do different things.</p>
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
              className={clsx("flex w-full items-center justify-between rounded-xl px-2 py-2 text-left text-sm hover:bg-paper-100", u.id === user?.id && "bg-teal-50")}
            >
              <span>
                <span className="block font-semibold">{u.name}</span>
                <span className="block text-xs text-navy-500">{u.title}</span>
              </span>
              <span className="rounded-full bg-paper-100 px-2 py-0.5 text-[11px] font-semibold text-navy-500">{ROLE_LABEL[u.role]}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export function AppHeader({ onHelp }: { onHelp: () => void }) {
  const pathname = usePathname();
  const { can } = useSession();
  return (
    <header className="sticky top-0 z-40 border-b border-paper-200 bg-paper/90 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-7xl items-center gap-4 px-4 sm:px-6">
        <Link href="/" aria-label="Preflight home">
          <Logo />
        </Link>
        <nav className="hidden flex-1 items-center gap-1 overflow-x-auto md:flex" aria-label="Main">
          {NAV.filter((n) => !n.permission || can(n.permission)).map((n) => {
            const active = n.exact ? pathname === n.href : pathname.startsWith(n.href);
            return (
              <Link key={n.href} href={n.href} aria-current={active ? "page" : undefined} className={clsx("whitespace-nowrap rounded-lg px-3 py-1.5 text-sm font-medium", active ? "bg-navy text-paper-50" : "text-navy-500 hover:bg-paper-100 hover:text-navy")}>
                {n.label}
              </Link>
            );
          })}
        </nav>
        <div className="ml-auto flex items-center gap-2">
          <AiMode />
          <Tip text="Demo mode: no passwords. Use the switcher to act as any seeded PayWise user. All data is fictional.">
            <span className="hidden rounded-full bg-amber-50 px-2 py-1 text-[11px] font-semibold text-amber-700 ring-1 ring-inset ring-amber/30 sm:inline-flex">Demo mode</span>
          </Tip>
          <button type="button" onClick={onHelp} aria-label="Help and keyboard shortcuts" className="rounded-lg p-2 text-navy-500 hover:bg-paper-100 hover:text-navy">
            <HelpCircle className="h-4 w-4" />
          </button>
          <Notifications />
          <RoleSwitcher />
        </div>
      </div>
      <nav className="flex gap-1 overflow-x-auto border-t border-paper-200 px-4 py-1 md:hidden" aria-label="Main (mobile)">
        {NAV.filter((n) => !n.permission || can(n.permission)).map((n) => (
          <Link key={n.href} href={n.href} className="whitespace-nowrap rounded-lg px-2 py-1 text-xs font-medium text-navy-500">
            {n.label}
          </Link>
        ))}
      </nav>
    </header>
  );
}
