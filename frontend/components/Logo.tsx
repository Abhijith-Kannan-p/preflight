import { clsx } from "clsx";

export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" aria-hidden="true" className={clsx("shrink-0", className)}>
      <rect width="32" height="32" rx="3" fill="#9B1C1C" />
      <path d="M6 15.5 26 7l-5.5 18-5-6.2-4.3 3.2.6-5.4L23 9.5 10.4 16.9z" fill="#F3EADC" />
      <path d="m11.8 15.9 3.7 2.9-4.3 3.2z" fill="#D9C9B4" />
    </svg>
  );
}

export function Logo({ className }: { className?: string }) {
  return (
    <span className={clsx("inline-flex items-center gap-2 font-serif text-[19px] font-medium tracking-tight text-ink", className)}>
      <LogoMark className="h-6 w-6" />
      Preflight
    </span>
  );
}
