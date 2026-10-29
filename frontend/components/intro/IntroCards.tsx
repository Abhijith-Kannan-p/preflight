// The intro's cards: small pieces of a real Preflight review of the fictional PayWise launch
// post, drawn as components (no stock imagery). Decorative: the stage marks them aria-hidden.

import { clsx } from "clsx";

const card = "paper-scope rounded-md border border-rule bg-sheet shadow-sheet";

function Dial({ score }: { score: number }) {
  const start = 150;
  const sweep = 240;
  const r = 34;
  const point = (deg: number) => ({ x: 44 + r * Math.cos((deg * Math.PI) / 180), y: 44 + r * Math.sin((deg * Math.PI) / 180) });
  const arc = (to: number) => {
    const a = point(start);
    const b = point(to);
    return `M ${a.x} ${a.y} A ${r} ${r} 0 ${to - start > 180 ? 1 : 0} 1 ${b.x} ${b.y}`;
  };
  const colour = score >= 85 ? "rgb(var(--cleared))" : "rgb(var(--signal))";
  return (
    <div className={clsx(card, "flex w-[150px] flex-col items-center px-3 pb-3 pt-2")}>
      <svg width="88" height="74" viewBox="0 0 88 74">
        <path d={arc(start + sweep)} fill="none" stroke="rgb(var(--rule))" strokeWidth="2" />
        <path d={arc(start + (sweep * score) / 100)} fill="none" stroke={colour} strokeWidth="3" />
        <text x="44" y="52" textAnchor="middle" className="fill-ink font-mono" fontSize="22">
          {score}
        </text>
      </svg>
      <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-graphite">Brand score</span>
    </div>
  );
}

export const INTRO_CARDS: { id: string; node: React.ReactNode; phone?: boolean }[] = [
  {
    id: "draft",
    phone: true,
    node: (
      <div className={clsx(card, "w-[300px] px-5 py-4")}>
        <p className="font-mono text-[10px] uppercase tracking-[0.12em] text-graphite">LinkedIn · draft</p>
        <p className="mt-2 font-serif text-[17px] leading-snug text-ink">
          Say hello to <span className="mark-critical">India&apos;s #1</span> and <span className="mark-critical">100% secure</span> payments app!
        </p>
      </div>
    ),
  },
  {
    id: "note",
    phone: true,
    node: (
      <div className={clsx(card, "w-[260px] border-l-[3px] border-l-signal px-4 py-3")}>
        <p className="flex items-center gap-2 text-xs font-semibold text-signal-700">
          <span className="inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-signal-700 px-1 text-[10px] text-sheet">2</span>
          Critical <span className="rounded-sm border border-rule px-1 font-mono text-[10px] font-medium text-ink">CLM-04 · p14</span>
        </p>
        <p className="mt-1.5 text-[13px] leading-snug text-graphite">An absolute security claim. Describe the protection instead.</p>
        <p className="mt-1.5 text-[13px]">
          <span className="text-graphite line-through">100% secure</span> → <span className="font-medium text-ink">bank-grade encrypted</span>
        </p>
      </div>
    ),
  },
  {
    id: "fact",
    node: (
      <div className={clsx(card, "w-[250px] px-4 py-3")}>
        <p className="font-mono text-[10px] uppercase tracking-[0.12em] text-cleared-700">Approved fact · current</p>
        <p className="mt-1 font-mono text-sm font-medium text-ink">F-087</p>
        <p className="mt-1 font-serif text-[15px] leading-snug text-ink">PayWise settles merchant payments in under 10 seconds.</p>
      </div>
    ),
  },
  {
    id: "banner",
    phone: true,
    node: (
      <div className={clsx(card, "w-[280px] p-2")}>
        <div className="relative overflow-hidden rounded-sm">
          {/* eslint-disable-next-line @next/next/no-img-element -- a small local, lazily loaded decoration */}
          <img src="/intro/festive-banner.webp" alt="" width={480} height={252} loading="lazy" decoding="async" className="block h-auto w-full" />
          <span className="absolute border-2 border-amber" style={{ left: "70%", top: "45%", width: "29%", height: "54%" }} />
          <span className="absolute rounded-sm bg-sheet px-1 font-mono text-[9px] font-medium text-ink" style={{ left: "70%", top: "34%" }}>
            VIS-01
          </span>
        </div>
        <p className="mt-1.5 px-1 font-mono text-[10px] text-graphite">#E1105F covers 15% · ΔE00 38 from the palette</p>
      </div>
    ),
  },
  { id: "score-24", phone: true, node: <Dial score={24} /> },
  {
    id: "ledger",
    node: (
      <div className={clsx(card, "w-[290px] px-4 py-3")}>
        <p className="flex items-center gap-2">
          <span className="rounded-sm border border-amber px-1.5 font-mono text-[10px] font-medium uppercase text-amber-700">Outdated</span>
          <span className="font-mono text-[10px] text-graphite">Claim Ledger</span>
        </p>
        <p className="mt-1.5 font-serif text-[14px] leading-snug text-ink">“settles in under 5 seconds”</p>
        <p className="mt-1 text-[12px] text-graphite">F-086 was superseded by F-087 on 2 Sep</p>
      </div>
    ),
  },
  {
    id: "palette",
    node: (
      <div className={clsx(card, "w-[230px] px-3 py-3")}>
        <p className="font-mono text-[10px] uppercase tracking-[0.12em] text-graphite">Brand palette</p>
        <div className="mt-2 flex gap-1">
          {["#13294B", "#12A594", "#4FB3E8", "#F5A623", "#2E3440", "#F4F7FA"].map((hex) => (
            <span key={hex} className="h-7 flex-1 rounded-sm border border-ink/10" style={{ background: hex }} />
          ))}
        </div>
      </div>
    ),
  },
  { id: "score-97", phone: true, node: <Dial score={97} /> },
  {
    id: "stamp",
    phone: true,
    node: (
      <div className="paper-scope -rotate-[8deg] rounded-sm border-[3px] border-double border-cleared bg-sheet px-4 py-2 text-center font-mono uppercase text-cleared-700 shadow-sheet">
        <p className="text-[15px] font-medium tracking-[0.18em]">Cleared for publication</p>
        <p className="text-[10px] tracking-[0.12em]">By abhi4 · audit 769f1525</p>
      </div>
    ),
  },
  {
    id: "certificate",
    node: (
      <div className={clsx(card, "flex w-[260px] items-center gap-3 px-3 py-3")}>
        {/* eslint-disable-next-line @next/next/no-img-element -- a small local, lazily loaded decoration */}
        <img src="/intro/certificate-qr.svg" alt="" width={64} height={64} loading="lazy" className="h-16 w-16" />
        <div>
          <p className="font-mono text-[10px] uppercase tracking-[0.12em] text-graphite">Clearance certificate</p>
          <p className="mt-0.5 font-mono text-xs text-ink">sub_3f250b9797ea</p>
          <p className="mt-1 border-l-2 border-cleared pl-1.5 text-[11px] text-cleared-700">Audit chain verified</p>
        </div>
      </div>
    ),
  },
];
