"use client";

import { clsx } from "clsx";
import { AlertTriangle, Info, RotateCcw, X } from "lucide-react";
import { useEffect, useRef } from "react";

export function Chip({ className, children }: { className?: string; children: React.ReactNode }) {
  return (
    <span className={clsx("inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2 py-0.5 text-[11px] font-semibold ring-1 ring-inset", className)}>
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
        className="pointer-events-none absolute bottom-full left-1/2 z-50 mb-2 hidden w-max max-w-[260px] -translate-x-1/2 rounded-lg bg-navy px-3 py-2 text-xs font-normal leading-snug text-paper-50 shadow-lift group-focus-within:block group-hover:block"
      >
        {text}
      </span>
    </span>
  );
}

export function InfoTip({ text }: { text: string }) {
  return (
    <Tip text={text}>
      <button type="button" aria-label={text} className="inline-flex text-navy-300 hover:text-navy">
        <Info className="h-3.5 w-3.5" aria-hidden="true" />
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
      className="w-[min(560px,calc(100vw-2rem))] rounded-2xl border border-paper-200 bg-paper-50 p-0 text-navy shadow-lift backdrop:bg-navy/30 backdrop:backdrop-blur-sm"
    >
      {open && (
        <div className="p-6">
          <div className="mb-4 flex items-start justify-between gap-4">
            <h2 className="text-lg font-semibold">{title}</h2>
            <button type="button" onClick={onClose} aria-label="Close" className="rounded-lg p-1 text-navy-500 hover:bg-paper-100">
              <X className="h-4 w-4" />
            </button>
          </div>
          {children}
          {footer && <div className="mt-6 flex justify-end gap-2">{footer}</div>}
        </div>
      )}
    </dialog>
  );
}

export function EmptyState({ icon, title, text, action }: { icon?: React.ReactNode; title: string; text: string; action?: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-paper-200 px-6 py-12 text-center">
      {icon && <div className="mb-3 text-navy-300">{icon}</div>}
      <p className="font-semibold">{title}</p>
      <p className="mt-1 max-w-[46ch] text-sm text-navy-500">{text}</p>
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="flex items-start gap-3 rounded-2xl border border-danger/20 bg-danger-50 p-4 text-sm text-danger-700">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
      <div className="flex-1">
        <p className="font-semibold">Something went wrong</p>
        <p className="mt-0.5">{message}</p>
      </div>
      {onRetry && (
        <button type="button" onClick={onRetry} className="btn-ghost py-1 text-xs">
          <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" /> Retry
        </button>
      )}
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={clsx("skeleton", className)} aria-hidden="true" />;
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: string; actions?: React.ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">{title}</h1>
        {subtitle && <p className="mt-1 max-w-[70ch] text-sm text-navy-500">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

export function ComingInRound3({ title, text }: { title: string; text: string }) {
  return (
    <div className="rounded-2xl border border-dashed border-purple/30 bg-purple-50/50 p-4">
      <p className="text-[11px] font-bold uppercase tracking-wider text-purple-700">Coming in Round 3</p>
      <p className="mt-1 font-semibold">{title}</p>
      <p className="mt-0.5 text-sm text-navy-500">{text}</p>
    </div>
  );
}
