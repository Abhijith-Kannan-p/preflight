"use client";

// Proof Desk primitives: layered surfaces, soft corners, theme tokens. Colour means state.

import { clsx } from "clsx";
import { AlertTriangle, ArrowRight, BookOpen, ChevronDown, Compass, FileCheck2, Gauge, Inbox, Info, RotateCcw, Settings2, X } from "lucide-react";
import { usePathname } from "next/navigation";
import { useEffect, useRef } from "react";

/** A small status label. Pass a tone class such as SEVERITY_STYLE.critical.chip. */
export function Chip({ className, children }: { className?: string; children: React.ReactNode }) {
  return (
    <span className={clsx("inline-flex items-center gap-1 whitespace-nowrap rounded-sm border px-1.5 py-px font-mono text-[11px] font-medium uppercase tracking-[0.04em]", className)}>
      {children}
    </span>
  );
}

/** Accessible tooltip: shows on hover and on keyboard focus. */
export function Tip({ text, children, className, below = false }: { text: string; children: React.ReactNode; className?: string; below?: boolean }) {
  return (
    <span className={clsx("group relative inline-flex", className)}>
      {children}
      <span
        role="tooltip"
        className={clsx(
          "pointer-events-none absolute left-1/2 z-50 hidden w-max max-w-[260px] -translate-x-1/2 rounded bg-ink px-3 py-2 text-xs font-normal leading-snug text-sheet dark:border dark:border-rule dark:bg-raised dark:text-ink group-focus-within:block group-hover:block",
          below ? "top-full mt-2" : "bottom-full mb-2",
        )}
      >
        {text}
      </span>
    </span>
  );
}

export function InfoTip({ text }: { text: string }) {
  return (
    <Tip text={text}>
      <button type="button" aria-label={text} className="inline-flex text-graphite/70 hover:text-ink">
        <Info className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden="true" />
      </button>
    </Tip>
  );
}

export function Modal({
  open,
  title,
  onClose,
  children,
  footer,
}: {
  open: boolean;
  title: string;
  onClose: () => void;
  children: React.ReactNode;
  footer?: React.ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);
  return (
    <dialog
      ref={ref}
      onClose={onClose}
      onClick={(e) => e.target === ref.current && onClose()}
      className="w-[min(560px,calc(100vw-2rem))] rounded border border-rule bg-sheet p-0 text-ink shadow-lift backdrop:bg-ink/25"
    >
      {open && (
        <div>
          <div className="flex items-start justify-between gap-4 border-b border-rule px-6 py-4">
            <h2 className="font-serif text-xl font-medium">{title}</h2>
            <button type="button" onClick={onClose} aria-label="Close" className="rounded p-1 text-graphite hover:bg-paper hover:text-ink">
              <X className="h-4 w-4" strokeWidth={1.75} />
            </button>
          </div>
          <div className="px-6 py-5">{children}</div>
          {footer && <div className="flex justify-end gap-2 border-t border-rule px-6 py-4">{footer}</div>}
        </div>
      )}
    </dialog>
  );
}

/** Our own line drawing for empty states: a blank proof sheet with a pencilled tick. */
function EmptyArt() {
  return (
    <svg width="72" height="64" viewBox="0 0 72 64" fill="none" aria-hidden="true" className="shrink-0">
      <rect x="10" y="6" width="40" height="52" rx="2" className="fill-paper stroke-graphite" strokeWidth="1.5" />
      <path d="M17 18h26M17 25h22M17 32h26M17 39h14" className="stroke-graphite-light" strokeWidth="1.5" strokeLinecap="round" />
      <circle cx="52" cy="44" r="12" className="fill-sheet stroke-teal" strokeWidth="1.5" />
      <path d="m46.5 44 3.8 3.6L57.5 40" className="stroke-teal" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/** Every empty list says what it is for and offers the next action. */
export function EmptyState({ icon, title, text, action }: { icon?: React.ReactNode; title: string; text: string; action?: React.ReactNode }) {
  return (
    <div className="flex flex-col items-start gap-4 rounded-lg border border-dashed border-rule bg-sheet px-6 py-7 sm:flex-row sm:items-center">
      {icon ? <div className="text-graphite">{icon}</div> : <EmptyArt />}
      <div className="space-y-1.5">
      <p className="font-serif text-xl text-ink">{title}</p>
      <p className="max-w-[56ch] text-sm text-graphite">{text}</p>
      {action && <div className="pt-1">{action}</div>}
      </div>
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="flex items-start gap-3 border-l-2 border-signal bg-signal-50 px-4 py-3 text-sm text-signal-700">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" strokeWidth={1.75} aria-hidden="true" />
      <div className="flex-1">
        <p className="font-medium">That did not work</p>
        <p className="mt-0.5 text-ink">{message}</p>
      </div>
      {onRetry && (
        <button type="button" onClick={onRetry} className="btn-ghost py-1 text-xs">
          <RotateCcw className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden="true" /> Try again
        </button>
      )}
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={clsx("skeleton", className)} aria-hidden="true" />;
}

/** Each section's icon. Sections stay quiet (teal on a neutral chip) so colour keeps meaning severity. */
const SECTIONS: { prefix: string; icon: typeof BookOpen }[] = [
  { prefix: "/app/queue", icon: Inbox },
  { prefix: "/app/rulebook", icon: BookOpen },
  { prefix: "/app/governance", icon: Compass },
  { prefix: "/app/insights", icon: Compass },
  { prefix: "/app/evaluation", icon: Gauge },
  { prefix: "/app/settings", icon: Settings2 },
  { prefix: "/app", icon: FileCheck2 },
];

/** Serif page title, one sentence on what the screen is for, the rest under "How this works",
 * and the page's primary action. */
export function PageHeader({ title, subtitle, actions, eyebrow }: { title: string; subtitle?: string; actions?: React.ReactNode; eyebrow?: string }) {
  const pathname = usePathname() ?? "";
  const section = SECTIONS.find((s) => pathname.startsWith(s.prefix));
  const Icon = section?.icon;
  const split = subtitle?.match(/^(.+?[.!?])\s+([\s\S]+)$/);
  const lead = split ? split[1] : subtitle;
  const more = split?.[2];
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4 border-b border-rule pb-5">
      <div className="flex min-w-0 items-start gap-3">
        {Icon && (
          <span className={clsx("mt-1 hidden h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-paper-100 text-teal-700 sm:inline-flex")} aria-hidden="true">
            <Icon className="h-5 w-5" strokeWidth={1.75} />
          </span>
        )}
        <div className="min-w-0">
          {eyebrow && <p className="kicker">{eyebrow}</p>}
          <h1 className="page-title">{title}</h1>
          {lead && <p className="mt-1.5 max-w-[72ch] text-[15px] text-graphite">{lead}</p>}
          {more && (
            <details className="group mt-1.5 max-w-[72ch] text-sm text-graphite">
              <summary className="inline-flex cursor-pointer list-none items-center gap-1 rounded text-ink underline decoration-rule underline-offset-4 hover:decoration-ink [&::-webkit-details-marker]:hidden">
                How this works
                <ChevronDown className="h-3.5 w-3.5 transition-transform duration-150 group-open:rotate-180" aria-hidden="true" />
              </summary>
              <p className="mt-1.5">{more}</p>
            </details>
          )}
        </div>
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

/** The persistent "what to do next" line in a flow. */
export function NextStep({ children, tone = "ink" }: { children: React.ReactNode; tone?: "ink" | "signal" | "cleared" }) {
  const colour = tone === "signal" ? "border-signal text-signal-700" : tone === "cleared" ? "border-cleared text-cleared-700" : "border-ink text-ink";
  return (
    <p role="status" className={clsx("flex items-center gap-2 border-l-2 bg-sheet py-1.5 pl-3 pr-2 text-sm", colour)}>
      <ArrowRight className="h-3.5 w-3.5 shrink-0" strokeWidth={1.75} aria-hidden="true" />
      <span>
        <span className="label mr-2 inline text-current">Next step</span>
        {children}
      </span>
    </p>
  );
}
