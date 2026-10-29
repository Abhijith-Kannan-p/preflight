"use client";

import { clsx } from "clsx";
import { Bell, ChevronDown, HelpCircle, Menu, X } from "lucide-react";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";
import useSWR from "swr";

import { API_URL, fetcher, getToken, post } from "@/lib/api";
import { timeAgo } from "@/lib/format";
import { ROLE_LABEL, useSession } from "@/lib/session";
import type { Health, Notification, UserRef } from "@/lib/types";

import { Logo } from "./Logo";
import { ThemeToggle } from "./ThemeToggle";
import { Tip } from "./ui";

interface NavItem {
  href: string;
  label: string;
  /** Paths that belong to this item (prefix match); defaults to href. */
  match?: string[];
  exact?: boolean;
  permission?: string;
}

interface NavGroup extends NavItem {
  /** Sub-pages, shown as a second row while the section is open. */
  children?: NavItem[];
}

export const NAV: NavGroup[] = [
  {
    href: "/app",
    label: "Review",
    match: ["/app/review"],
    exact: true,
    children: [
      { href: "/app", label: "Dashboard", exact: true },
      { href: "/app/review/new", label: "New review" },
    ],
  },
  { href: "/app/queue", label: "Queue", permission: "approve" },
  { href: "/app/rulebook", label: "Rulebook" },
  {
    href: "/app/governance",
    label: "Governance",
    match: ["/app/insights"],
    children: [
      { href: "/app/governance?tab=guideline", label: "Guideline Health", match: ["/app/governance"] },
      { href: "/app/governance?tab=stale", label: "Stale-Content Radar" },
      { href: "/app/governance?tab=creator", label: "Creator Coach" },
      { href: "/app/insights", label: "Insights", permission: "view_insights" },
    ],
  },
  { href: "/app/evaluation", label: "Evaluation" },
  { href: "/app/settings", label: "Settings" },
];

function inGroup(group: NavGroup, pathname: string): boolean {
  if (group.exact ? pathname === group.href : pathname.startsWith(group.href)) return true;
  return (group.match ?? []).some((m) => pathname.startsWith(m));
}

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

/** One pill for the demo workspace and the AI mode, with the details in a tooltip. */
function StatusPill({ className }: { className?: string }) {
  const { data } = useSWR<Health>("/health", fetcher, { refreshInterval: 30_000 });
  const hosted = data ? data.llm_provider !== "none" : null;
  const ai = hosted === null ? "" : hosted ? `Hosted LLM (${data?.llm_provider}) for claim extraction, tone and wording; the local NLI model decides verdicts and confidential terms are masked first.` : "AI off: no external calls. Rules, the local NLI model and lexicon checks still run.";
  return (
    <Tip below text={`Demo: your private copy of the fictional PayWise workspace; nobody else sees it. ${ai}`} className={className}>
      <span tabIndex={0} className="inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border border-rule bg-sheet px-2.5 py-1 text-xs text-graphite">
        <span className={clsx("h-1.5 w-1.5 rounded-full", hosted ? "bg-teal" : "bg-graphite-light")} aria-hidden="true" />
        Demo · AI {hosted === null ? "…" : hosted ? "on" : "off"}
      </span>
    </Tip>
  );
}

/** New notifications arrive over a live stream; while it is down the list is polled every 15 s
 * instead. Returns whether the stream is connected. */
function useLiveNotifications(userId: string | undefined, onNotification: () => void): boolean {
  const [live, setLive] = useState(false);
  const callback = useRef(onNotification);
  callback.current = onNotification;
  useEffect(() => {
    if (!userId) return;
    let source: EventSource | null = null;
    let retry = 0;
    let attempt = 0;
    let closed = false;
    const connect = () => {
      const token = getToken();
      if (!token || closed) return;
      source = new EventSource(`${API_URL}/api/notifications/stream?token=${encodeURIComponent(token)}`);
      source.addEventListener("ready", () => {
        attempt = 0;
        setLive(true);
        callback.current(); // catch up on anything missed while disconnected
      });
      source.addEventListener("notification", () => callback.current());
      source.onerror = () => {
        setLive(false);
        if (source?.readyState === EventSource.CLOSED && !closed) {
          retry = window.setTimeout(connect, Math.min(1000 * 2 ** attempt++, 60_000));
        }
      };
    };
    connect();
    return () => {
      closed = true;
      source?.close();
      window.clearTimeout(retry);
      setLive(false);
    };
  }, [userId]);
  return live;
}

function Notifications() {
  const [open, setOpen] = useState(false);
  const ref = useOutside(() => setOpen(false));
  const { user } = useSession();
  const refresh = useRef<() => void>(() => {});
  const live = useLiveNotifications(user?.id, () => refresh.current());
  const { data, mutate } = useSWR<Notification[]>(user ? ["/api/notifications", user.id] : null, ([path]: [string]) => fetcher<Notification[]>(path), { refreshInterval: live ? 0 : 15_000 });
  refresh.current = () => void mutate();
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
        className="relative rounded p-2 text-graphite transition-colors duration-150 hover:bg-raised hover:text-ink"
      >
        <Bell className="h-4 w-4" />
        {unread > 0 && <span className="absolute right-0.5 top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-action px-1 font-mono text-[10px] text-on-action">{unread}</span>}
      </button>
      {open && (
        <div className="absolute right-0 z-50 mt-2 w-80 rounded-lg border border-rule bg-raised p-2 shadow-lift">
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
        className="flex items-center gap-2 rounded border border-rule bg-sheet py-1 pl-1 pr-2 text-left text-sm transition-colors duration-150 hover:bg-raised"
      >
        <span className="flex h-7 w-7 items-center justify-center rounded-sm bg-ink font-mono text-[11px] font-medium text-sheet dark:border dark:border-rule dark:bg-raised dark:text-ink">{user ? initials(user.name) : "…"}</span>
        <span className="hidden leading-tight sm:block lg:hidden xl:block">
          <span className="block text-xs font-semibold">{user?.name ?? "Signing in…"}</span>
          <span className="block text-[11px] text-navy-500">{user ? ROLE_LABEL[user.role] : ""}</span>
        </span>
        <ChevronDown className="h-3.5 w-3.5 text-navy-500" aria-hidden="true" />
      </button>
      {open && (
        <div role="listbox" className="absolute right-0 z-50 mt-2 w-72 rounded-lg border border-rule bg-raised p-2 shadow-lift">
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
              className={clsx("flex w-full items-center justify-between rounded-sm border-l-2 px-2 py-2 text-left text-sm transition-colors duration-150 hover:bg-paper", u.id === user?.id ? "border-teal bg-paper" : "border-transparent")}
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

function MenuDrawer({ open, onClose, onHelp, groups, pathname }: { open: boolean; onClose: () => void; onHelp: () => void; groups: NavGroup[]; pathname: string }) {
  const panel = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    panel.current?.querySelector<HTMLElement>("a, button")?.focus();
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 lg:hidden">
      <button type="button" aria-label="Close menu" className="absolute inset-0 h-full w-full cursor-default bg-black/40 animate-fade-in" onClick={onClose} tabIndex={-1} />
      <div ref={panel} role="dialog" aria-modal="true" aria-label="Menu" className="absolute right-0 top-0 flex h-full w-[min(20rem,88vw)] animate-slide-in flex-col gap-4 overflow-y-auto border-l border-rule bg-raised p-4 shadow-lift">
        <div className="flex items-center justify-between">
          <StatusPill />
          <button type="button" onClick={onClose} aria-label="Close menu" className="rounded p-2 text-graphite hover:bg-sheet hover:text-ink">
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>
        <nav aria-label="Main">
          <ul className="space-y-1">
            {groups.map((g) => {
              const active = inGroup(g, pathname);
              return (
                <li key={g.href}>
                  <Link href={g.href} onClick={onClose} aria-current={active ? "page" : undefined} className={clsx("flex items-center gap-2 rounded px-3 py-2 text-[15px] transition-colors duration-150", active ? "bg-sheet font-medium text-ink" : "text-graphite hover:bg-sheet hover:text-ink")}>
                    <span className={clsx("h-4 w-0.5 rounded-full", active ? "bg-teal" : "bg-transparent")} aria-hidden="true" />
                    {g.label}
                  </Link>
                  {g.children && (
                    <ul className="ml-6 border-l border-rule pl-2">
                      {g.children.map((c) => (
                        <li key={c.href}>
                          <Link href={c.href} onClick={onClose} className="block rounded px-2 py-1.5 text-sm text-graphite transition-colors duration-150 hover:bg-sheet hover:text-ink">
                            {c.label}
                          </Link>
                        </li>
                      ))}
                    </ul>
                  )}
                </li>
              );
            })}
          </ul>
        </nav>
        <div className="mt-auto space-y-1 border-t border-rule pt-3">
          <ThemeToggle withLabel />
          <button type="button" onClick={() => { onClose(); onHelp(); }} className="flex w-full items-center gap-2 rounded px-3 py-2 text-sm text-graphite transition-colors duration-150 hover:bg-sheet hover:text-ink">
            <HelpCircle className="h-4 w-4" aria-hidden="true" /> Help and keyboard shortcuts
          </button>
        </div>
      </div>
    </div>
  );
}

function SubNavRow({ group, pathname, tab }: { group: NavGroup; pathname: string; tab: string | null }) {
  const { can } = useSession();
  const items = (group.children ?? []).filter((c) => !c.permission || can(c.permission));
  if (items.length < 2) return null;
  const isActive = (c: NavItem) => {
    const [path, query] = c.href.split("?");
    if (query) {
      const wanted = new URLSearchParams(query).get("tab") ?? "";
      return pathname === path && (tab ? tab === wanted : (c.match ?? []).includes(path));
    }
    return c.exact ? pathname === path : pathname.startsWith(path);
  };
  return (
    <nav aria-label={`${group.label} sections`} className="border-t border-rule">
      <div className="mx-auto flex max-w-7xl gap-1 overflow-x-auto px-4 sm:px-6">
        {items.map((c) => {
          const active = isActive(c);
          return (
            <Link key={c.href} href={c.href} aria-current={active ? "page" : undefined} className={clsx("-mb-px whitespace-nowrap border-b-2 px-2.5 py-2 text-sm transition-colors duration-150", active ? "border-teal font-medium text-ink" : "border-transparent text-graphite hover:text-ink")}>
              {c.label}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}

/** Reading ?tab= makes this part client-rendered; the fallback is the same row (without the
 * tab's active mark), so it takes its space from the first paint and nothing shifts. */
function SubNav({ group, pathname }: { group: NavGroup; pathname: string }) {
  return (
    <Suspense fallback={<SubNavRow group={group} pathname={pathname} tab={null} />}>
      <SubNavWithTab group={group} pathname={pathname} />
    </Suspense>
  );
}

function SubNavWithTab({ group, pathname }: { group: NavGroup; pathname: string }) {
  const params = useSearchParams();
  return <SubNavRow group={group} pathname={pathname} tab={params.get("tab")} />;
}

export function AppHeader({ onHelp }: { onHelp: () => void }) {
  const pathname = usePathname();
  const { can } = useSession();
  const [menu, setMenu] = useState(false);
  const groups = NAV.filter((n) => !n.permission || can(n.permission));
  const current = groups.find((g) => inGroup(g, pathname));
  useEffect(() => setMenu(false), [pathname]);
  return (
    <header className="sticky top-0 z-40 border-b border-rule bg-paper/95 backdrop-blur supports-[backdrop-filter]:bg-paper/85">
      <div className={clsx("h-0.5", current ? "bg-teal" : "bg-transparent")} aria-hidden="true" />
      <div className="mx-auto flex h-14 max-w-7xl items-center gap-4 px-4 sm:px-6">
        <Link href="/" aria-label="Preflight home" className="shrink-0 rounded">
          <Logo />
        </Link>
        <nav className="hidden h-14 flex-1 items-stretch gap-0.5 lg:flex" aria-label="Main">
          {groups.map((g) => {
            const active = inGroup(g, pathname);
            return (
              <Link key={g.href} href={g.href} aria-current={active ? "page" : undefined} className={clsx("-mb-px flex items-center whitespace-nowrap border-b-2 px-3 text-[15px] transition-colors duration-150", active ? "border-teal font-medium text-ink" : "border-transparent text-graphite hover:text-ink")}>
                {g.label}
              </Link>
            );
          })}
        </nav>
        <div className="ml-auto flex items-center gap-1.5">
          <StatusPill className="hidden lg:inline-flex" />
          <span className="hidden lg:inline-flex">
            <ThemeToggle />
          </span>
          <button type="button" onClick={onHelp} aria-label="Help and keyboard shortcuts" className="hidden rounded p-2 text-graphite transition-colors duration-150 hover:bg-raised hover:text-ink lg:inline-flex">
            <HelpCircle className="h-4 w-4" />
          </button>
          <Notifications />
          <RoleSwitcher />
          <button type="button" onClick={() => setMenu(true)} aria-label="Open menu" aria-expanded={menu} className="rounded p-2 text-ink transition-colors duration-150 hover:bg-raised lg:hidden">
            <Menu className="h-5 w-5" aria-hidden="true" />
          </button>
        </div>
      </div>
      {current && <SubNav group={current} pathname={pathname} />}
      <MenuDrawer open={menu} onClose={() => setMenu(false)} onHelp={onHelp} groups={groups} pathname={pathname} />
    </header>
  );
}
