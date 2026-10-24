import { clsx } from "clsx";

export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" aria-hidden="true" className={clsx("shrink-0", className)}>
      <rect width="32" height="32" rx="8" fill="#1B2A4A" />
      <path d="M6 15.5 26 7l-5.5 18-5-6.2-4.3 3.2.6-5.4L23 9.5 10.4 16.9z" fill="#0F8B7E" />
      <path d="m11.8 15.9 3.7 2.9-4.3 3.2z" fill="#FBF8EF" opacity=".9" />
    </svg>
  );
}

export function Logo({ className }: { className?: string }) {
  return (
    <span className={clsx("inline-flex items-center gap-2 font-bold tracking-tight text-navy", className)}>
      <LogoMark className="h-7 w-7" />
      Preflight
    </span>
  );
}
