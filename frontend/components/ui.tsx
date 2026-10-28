"use client";

// Proof Desk primitives: hairline surfaces, square corners, mono labels. Colour means state.

import { clsx } from "clsx";
import { AlertTriangle, ArrowRight, Info, RotateCcw, X } from "lucide-react";
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
export function Tip({ text, children, className }: { text: string; children: React.ReactNode; className?: string }) {
  return (
    <span className={clsx("group relative inline-flex", className)}>
      {children}
      <span
        role="tooltip"
        className="pointer-events-none absolute bottom-full left-1/2 z-50 mb-2 hidden w-max max-w-[260px] -translate-x-1/2 rounded bg-ink px-3 py-2 text-xs font-normal leading-snug text-sheet group-focus-within:block group-hover:block"
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

/** Every empty list says what it is for and offers the next action. */
export function EmptyState({ icon, title, text, action }: { icon?: React.ReactNode; title: string; text: string; action?: React.ReactNode }) {
  return (
    <div className="flex flex-col items-start gap-2 border border-dashed border-rule bg-sheet px-6 py-8">
      {icon && <div className="text-graphite">{icon}</div>}
      <p className="font-serif text-lg">{title}</p>
      <p className="max-w-[56ch] text-sm text-graphite">{text}</p>
      {action && <div className="mt-2">{action}</div>}
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

/** Serif page title, one line on what the screen is for, and its primary action. */
export function PageHeader({ title, subtitle, actions, eyebrow }: { title: string; subtitle?: string; actions?: React.ReactNode; eyebrow?: string }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4 border-b border-rule pb-5">
      <div>
        {eyebrow && <p className="label mb-1">{eyebrow}</p>}
        <h1 className="page-title">{title}</h1>
        {subtitle && <p className="mt-1.5 max-w-[72ch] text-sm text-graphite">{subtitle}</p>}
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
