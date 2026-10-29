"use client";

// A murmuration that spells a word. Thousands of starlings fold through the sky, converge into
// the word, hold it, then scatter again; the pointer (or a finger) is a hawk the flock flees.
// One canvas, one path per frame and O(n) work per bird (each bird steers towards its place
// in a shared, slowly folding flock shape, so there is no neighbour search). The loop starts
// after hydration, pauses while the canvas is off-screen or the tab is hidden, and with
// reduced motion the formed word is drawn once, still.

import { useEffect, useRef } from "react";

export type MurmurationPreset = "dusk" | "paper";

type Palette = {
  /** Sky gradient stops, top to bottom. */
  sky: [number, string][];
  /** The warm glow the word forms in front of. */
  glow: string;
  bird: string;
  reed: string;
};

export const PRESETS: Record<MurmurationPreset, Palette> = {
  dusk: {
    sky: [
      [0, "#2B211D"],
      [0.28, "#5C3628"],
      [0.5, "#B5683F"],
      [0.62, "#D99560"],
      [0.72, "#7A4A31"],
      [0.86, "#2B211D"],
      [1, "#1C1816"],
    ],
    glow: "rgba(255, 196, 128, 0.32)",
    bird: "#1C1816",
    reed: "#1C1816",
  },
  paper: {
    sky: [
      [0, "#F7F4EC"],
      [0.45, "#F3ECDD"],
      [0.62, "#EFE3CC"],
      [0.8, "#F5F0E5"],
      [1, "#F7F4EC"],
    ],
    glow: "rgba(217, 160, 96, 0.16)",
    bird: "#1B2A4A",
    reed: "rgba(27, 42, 74, 0.55)",
  },
};

/** Phase lengths in seconds: fold → converge → hold → scatter, then round again. */
const FOLD = 7;
const CONVERGE = 2.6;
const HOLD = 4.4;
const SCATTER = 1.4;
const CYCLE = FOLD + CONVERGE + HOLD + SCATTER;
/** The first word forms after this much folding, not a full fold. */
const FIRST_FOLD = 2.2;
const REFERENCE_AREA = 1440 * 900;

type Flock = {
  n: number;
  x: Float32Array;
  y: Float32Array;
  vx: Float32Array;
  vy: Float32Array;
  /** Place in the word. */
  tx: Float32Array;
  ty: Float32Array;
  /** Place in the folding flock shape (a unit disc). */
  ox: Float32Array;
  oy: Float32Array;
  phase: Float32Array;
  size: Float32Array;
};

type Reed = { x: number; h: number; lean: number; phase: number; head: boolean };

function makeFlock(n: number, w: number, h: number): Flock {
  const f: Flock = {
    n,
    x: new Float32Array(n),
    y: new Float32Array(n),
    vx: new Float32Array(n),
    vy: new Float32Array(n),
    tx: new Float32Array(n),
    ty: new Float32Array(n),
    ox: new Float32Array(n),
    oy: new Float32Array(n),
    phase: new Float32Array(n),
    size: new Float32Array(n),
  };
  for (let i = 0; i < n; i++) {
    const r = Math.sqrt(Math.random());
    const a = Math.random() * Math.PI * 2;
    f.ox[i] = r * Math.cos(a);
    f.oy[i] = r * Math.sin(a);
    f.x[i] = w * (0.5 + f.ox[i] * 0.3);
    f.y[i] = h * (0.38 + f.oy[i] * 0.14);
    f.phase[i] = Math.random() * Math.PI * 2;
    f.size[i] = 1.5 + Math.random() * 1.1;
  }
  return f;
}

/** Points inside the word's letters, one per bird, inside the slot box. */
function samplePoints(word: string, weight: number, family: string, n: number, box: { x: number; y: number; w: number; h: number }): Float32Array {
  const out = new Float32Array(n * 2);
  const canvas = document.createElement("canvas");
  const w = Math.max(1, Math.round(box.w));
  const h = Math.max(1, Math.round(box.h));
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  if (!ctx) return out;
  ctx.font = `${weight} 100px ${family}`;
  const spaced = ctx as CanvasRenderingContext2D & { letterSpacing?: string };
  if ("letterSpacing" in spaced) spaced.letterSpacing = "4px";
  const m = ctx.measureText(word);
  const capHeight = (m.actualBoundingBoxAscent + m.actualBoundingBoxDescent) || 72;
  const size = Math.min((w * 0.94 * 100) / m.width, (h * 0.86 * 100) / capHeight);
  ctx.font = `${weight} ${size}px ${family}`;
  if ("letterSpacing" in spaced) spaced.letterSpacing = `${size * 0.04}px`;
  ctx.textAlign = "center";
  ctx.textBaseline = "alphabetic";
  const fitted = ctx.measureText(word);
  const baseline = h / 2 + (fitted.actualBoundingBoxAscent - fitted.actualBoundingBoxDescent) / 2;
  ctx.fillStyle = "#000";
  ctx.fillText(word, w / 2, baseline);
  const data = ctx.getImageData(0, 0, w, h).data;

  let filled = 0;
  for (let i = 3; i < data.length; i += 4) if (data[i] > 128) filled++;
  if (!filled) return out;
  // A grid fine enough to give about one point per bird, jittered inside each cell.
  const step = Math.max(1, Math.sqrt(filled / n));
  const pts: number[] = [];
  for (let y = step / 2; y < h; y += step) {
    for (let x = step / 2; x < w; x += step) {
      const px = Math.min(w - 1, Math.round(x + (Math.random() - 0.5) * step * 0.6));
      const py = Math.min(h - 1, Math.round(y + (Math.random() - 0.5) * step * 0.6));
      if (data[(py * w + px) * 4 + 3] > 128) pts.push(px, py);
    }
  }
  const count = pts.length / 2;
  // Shuffle, then hand out (repeating with a small offset if there are more birds than points).
  for (let i = count - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [pts[i * 2], pts[j * 2]] = [pts[j * 2], pts[i * 2]];
    [pts[i * 2 + 1], pts[j * 2 + 1]] = [pts[j * 2 + 1], pts[i * 2 + 1]];
  }
  for (let i = 0; i < n; i++) {
    const k = i % count;
    const again = i >= count;
    out[i * 2] = box.x + pts[k * 2] + (again ? (Math.random() - 0.5) * step : 0);
    out[i * 2 + 1] = box.y + pts[k * 2 + 1] + (again ? (Math.random() - 0.5) * step : 0);
  }
  return out;
}

function makeReeds(w: number, h: number): Reed[] {
  // Clusters at both edges, so the middle stays clear for the word and the text.
  const reeds: Reed[] = [];
  const perSide = Math.round(Math.min(34, Math.max(12, w / 42)));
  for (const side of [0, 1]) {
    for (let i = 0; i < perSide; i++) {
      const t = Math.pow(Math.random(), 1.6);
      const x = side === 0 ? t * w * 0.24 : w - t * w * 0.24;
      reeds.push({ x, h: h * (0.12 + Math.random() * 0.3) * (1 - t * 0.55), lean: (Math.random() - 0.5) * 0.25 + (side === 0 ? 0.05 : -0.05), phase: Math.random() * Math.PI * 2, head: Math.random() < 0.45 });
    }
  }
  return reeds;
}

function paintSky(ctx: CanvasRenderingContext2D, w: number, h: number, palette: Palette, glowY: number) {
  const sky = ctx.createLinearGradient(0, 0, 0, h);
  for (const [stop, colour] of palette.sky) sky.addColorStop(stop, colour);
  ctx.fillStyle = sky;
  ctx.fillRect(0, 0, w, h);
  const glow = ctx.createRadialGradient(w / 2, glowY, 0, w / 2, glowY, Math.max(w, h) * 0.55);
  glow.addColorStop(0, palette.glow);
  glow.addColorStop(1, "rgba(0,0,0,0)");
  ctx.fillStyle = glow;
  ctx.fillRect(0, 0, w, h);
}

function paintReeds(ctx: CanvasRenderingContext2D, reeds: Reed[], h: number, t: number, colour: string) {
  ctx.strokeStyle = colour;
  ctx.fillStyle = colour;
  ctx.lineCap = "round";
  for (const r of reeds) {
    const sway = Math.sin(t * 0.9 + r.phase) * 0.05 + r.lean;
    const tipX = r.x + sway * r.h;
    const tipY = h - r.h;
    ctx.lineWidth = 1.4;
    ctx.beginPath();
    ctx.moveTo(r.x, h);
    ctx.quadraticCurveTo(r.x + sway * r.h * 0.3, h - r.h * 0.55, tipX, tipY);
    ctx.stroke();
    if (r.head) {
      ctx.beginPath();
      ctx.ellipse(tipX, tipY + 7, 2.2, 7, sway, 0, Math.PI * 2);
      ctx.fill();
    }
  }
}

function paintBirds(ctx: CanvasRenderingContext2D, f: Flock, t: number, colour: string, flapping: boolean) {
  ctx.strokeStyle = colour;
  ctx.lineWidth = 1.1;
  ctx.lineCap = "round";
  ctx.beginPath();
  for (let i = 0; i < f.n; i++) {
    const x = f.x[i];
    const y = f.y[i];
    const s = f.size[i];
    const speed = Math.hypot(f.vx[i], f.vy[i]);
    // A small chevron pointing along the bird's heading, wings beating while it flies.
    const heading = speed > 4 ? Math.atan2(f.vy[i], f.vx[i]) : -Math.PI / 2;
    const flap = flapping ? Math.sin(t * 16 + f.phase[i]) * 0.55 : 0.2;
    const back = heading + Math.PI;
    const spread = 0.95 + flap;
    ctx.moveTo(x + Math.cos(back - spread) * s, y + Math.sin(back - spread) * s);
    ctx.lineTo(x, y);
    ctx.lineTo(x + Math.cos(back + spread) * s, y + Math.sin(back + spread) * s);
  }
  ctx.stroke();
}

export function MurmurationWordmark({
  word,
  preset,
  slotRef,
  birdCount = 3000,
  reeds = true,
  birdInk,
  fontFamily = "var(--font-newsreader)",
  fontWeight = 800,
  className,
}: {
  word: string;
  preset: MurmurationPreset;
  /** The element the word forms inside; the canvas fills the nearest positioned parent. */
  slotRef: React.RefObject<HTMLElement | null>;
  birdCount?: number;
  reeds?: boolean;
  birdInk?: string;
  /** The letters' typeface; a CSS variable is resolved before drawing. */
  fontFamily?: string;
  fontWeight?: number;
  className?: string;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const paletteRef = useRef<Palette>(PRESETS[preset]);
  const redrawRef = useRef<() => void>(() => {});
  paletteRef.current = { ...PRESETS[preset], ...(birdInk ? { bird: birdInk } : {}) };

  // A preset change repaints at once (a still frame needs it; the loop picks it up anyway).
  useEffect(() => {
    redrawRef.current();
  }, [preset, birdInk]);

  useEffect(() => {
    const canvas = canvasRef.current;
    const host = canvas?.parentElement;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !host || !ctx) return;
    const still = window.matchMedia("(prefers-reduced-motion: reduce)");

    let w = 0;
    let h = 0;
    let flock: Flock | null = null;
    let reedList: Reed[] = [];
    let glowY = 0;
    let wordCentre = { x: 0, y: 0 };
    let frame = 0;
    let visible = true;
    let last = 0;
    let clock = FOLD - FIRST_FOLD; // start part-way into the fold, so the word forms soon
    let scattered = false;
    const hawk = { x: -1e4, y: -1e4, until: 0 };
    let cancelled = false;

    const resolveFamily = () => {
      const variable = fontFamily.match(/^var\((--[\w-]+)\)$/)?.[1];
      return variable ? getComputedStyle(document.body).getPropertyValue(variable).trim() || "Georgia, serif" : fontFamily;
    };

    const layout = () => {
      const rect = host.getBoundingClientRect();
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      w = rect.width;
      h = rect.height;
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      // The flock scales with the sky's area, so phones carry fewer birds.
      const n = Math.round(birdCount * Math.min(1, Math.max(0.28, (w * h) / REFERENCE_AREA)));
      if (!flock || flock.n !== n) flock = makeFlock(n, w, h);
      const slot = slotRef.current?.getBoundingClientRect();
      const box = slot
        ? { x: slot.left - rect.left + slot.width * 0.04, y: slot.top - rect.top, w: slot.width * 0.92, h: slot.height }
        : { x: w * 0.05, y: h * 0.2, w: w * 0.9, h: h * 0.3 };
      const pts = samplePoints(word, fontWeight, resolveFamily(), flock.n, box);
      for (let i = 0; i < flock.n; i++) {
        flock.tx[i] = pts[i * 2];
        flock.ty[i] = pts[i * 2 + 1];
      }
      wordCentre = { x: box.x + box.w / 2, y: box.y + box.h / 2 };
      glowY = wordCentre.y;
      reedList = reeds ? makeReeds(w, h) : [];
    };

    const paint = (t: number, flapping: boolean) => {
      if (!flock) return;
      const palette = paletteRef.current;
      paintSky(ctx, w, h, palette, glowY);
      if (reedList.length) paintReeds(ctx, reedList, h, flapping ? t : 0, palette.reed);
      paintBirds(ctx, flock, t, palette.bird, flapping);
    };

    /** The formed word, still: every bird in its place. */
    const paintWord = () => {
      if (!flock) return;
      for (let i = 0; i < flock.n; i++) {
        flock.x[i] = flock.tx[i];
        flock.y[i] = flock.ty[i];
        flock.vx[i] = 0;
        flock.vy[i] = 0;
      }
      paint(0, false);
    };

    const step = (dt: number, time: number) => {
      const f = flock;
      if (!f) return;
      clock = (clock + dt) % CYCLE;
      const phase = clock < FOLD ? "fold" : clock < FOLD + CONVERGE ? "converge" : clock < FOLD + CONVERGE + HOLD ? "hold" : "scatter";
      if (phase === "scatter" && !scattered) {
        scattered = true;
        for (let i = 0; i < f.n; i++) {
          const dx = f.x[i] - wordCentre.x;
          const dy = f.y[i] - wordCentre.y;
          const d = Math.hypot(dx, dy) || 1;
          const kick = 160 + Math.random() * 260;
          f.vx[i] += (dx / d) * kick + (Math.random() - 0.5) * 120;
          f.vy[i] += (dy / d) * kick * 0.6 - 60 - Math.random() * 80;
        }
      }
      if (phase !== "scatter") scattered = false;

      // The flock shape: a disc stretched, folded by a travelling wave and turned slowly.
      const cx = w * (0.5 + 0.2 * Math.sin(time * 0.13));
      const cy = h * (0.36 + 0.07 * Math.sin(time * 0.21 + 1));
      const rx = w * 0.26 * (1 + 0.25 * Math.sin(time * 0.17));
      const ry = h * 0.11 * (0.7 + 0.45 * Math.sin(time * 0.23 + 2));
      const turn = Math.sin(time * 0.11) * 0.5;
      const cos = Math.cos(turn);
      const sin = Math.sin(turn);
      const into = phase === "converge" ? (clock - FOLD) / CONVERGE : 0;
      const k = phase === "fold" ? 1.1 : phase === "converge" ? 2 + into * into * 26 : phase === "hold" ? 30 : 0.25;
      const damp = phase === "fold" ? 1.4 : phase === "converge" ? 2 + into * 6 : phase === "hold" ? 9 : 0.5;
      const toWord = phase === "converge" || phase === "hold";
      const hawkOn = time < hawk.until;
      const fear = Math.max(90, Math.min(w, h) * 0.14);

      for (let i = 0; i < f.n; i++) {
        let gx: number;
        let gy: number;
        if (toWord) {
          gx = f.tx[i] + (phase === "hold" ? Math.sin(time * 2.2 + f.phase[i]) * 0.7 : 0);
          gy = f.ty[i] + (phase === "hold" ? Math.cos(time * 1.9 + f.phase[i]) * 0.7 : 0);
        } else {
          const u = f.ox[i];
          const v = f.oy[i];
          const px = u * rx * (1 + 0.35 * Math.sin(time * 0.31 + v * 2.4));
          const py = v * ry + ry * 0.7 * Math.sin(u * 3.1 + time * 0.8);
          gx = cx + px * cos - py * sin;
          gy = cy + px * sin + py * cos;
        }
        let ax = (gx - f.x[i]) * k - f.vx[i] * damp;
        let ay = (gy - f.y[i]) * k - f.vy[i] * damp;
        // A little personal wander while folding.
        if (!toWord) {
          ax += Math.sin(time * 1.3 + f.phase[i] * 3) * 40;
          ay += Math.cos(time * 1.1 + f.phase[i] * 2) * 30;
        }
        if (hawkOn) {
          const dx = f.x[i] - hawk.x;
          const dy = f.y[i] - hawk.y;
          const d2 = dx * dx + dy * dy;
          if (d2 < fear * fear) {
            const d = Math.sqrt(d2) || 1;
            const push = (1 - d / fear) * 5200;
            ax += (dx / d) * push;
            ay += (dy / d) * push;
          }
        }
        f.vx[i] += ax * dt;
        f.vy[i] += ay * dt;
        const speed = Math.hypot(f.vx[i], f.vy[i]);
        const max = 520;
        if (speed > max) {
          f.vx[i] *= max / speed;
          f.vy[i] *= max / speed;
        }
        f.x[i] += f.vx[i] * dt;
        f.y[i] += f.vy[i] * dt;
      }
    };

    const tick = (now: number) => {
      if (cancelled) return;
      const time = now / 1000;
      const dt = Math.min(0.05, last ? time - last : 0.016);
      last = time;
      step(dt, time);
      paint(time, true);
      frame = visible && !document.hidden ? requestAnimationFrame(tick) : 0;
    };

    const start = () => {
      if (cancelled || frame || still.matches || !visible || document.hidden) return;
      last = 0;
      frame = requestAnimationFrame(tick);
    };
    const stop = () => {
      if (frame) cancelAnimationFrame(frame);
      frame = 0;
    };

    redrawRef.current = () => {
      if (still.matches) paintWord();
      else if (!frame && flock) paint(last, false);
    };

    // Lay out once the heavy display face has loaded, so the letters are sampled from it.
    const ready = document.fonts?.load ? document.fonts.load(`${fontWeight} 100px ${resolveFamily()}`, word).catch(() => []) : Promise.resolve([]);
    void ready.then(() => {
      if (cancelled) return;
      layout();
      if (still.matches) paintWord();
      else start();
    });

    const resize = new ResizeObserver(() => {
      if (!flock) return;
      layout();
      if (still.matches) paintWord();
    });
    resize.observe(host);
    const seen = new IntersectionObserver(([entry]) => {
      visible = entry.isIntersecting;
      if (visible) start();
      else stop();
      // The 1 px inset: a canvas that only touches the viewport edge counts as off-screen.
    }, { rootMargin: "-1px" });
    seen.observe(canvas);
    const onVisibility = () => (document.hidden ? stop() : start());
    document.addEventListener("visibilitychange", onVisibility);
    const onMotion = () => {
      if (still.matches) {
        stop();
        paintWord();
      } else start();
    };
    still.addEventListener("change", onMotion);

    // The hawk: the pointer, or a finger (without blocking the page's own scrolling).
    const hunt = (clientX: number, clientY: number) => {
      const rect = host.getBoundingClientRect();
      hawk.x = clientX - rect.left;
      hawk.y = clientY - rect.top;
      hawk.until = performance.now() / 1000 + 1.2;
    };
    const onPointer = (e: PointerEvent) => hunt(e.clientX, e.clientY);
    const onTouch = (e: TouchEvent) => {
      const touch = e.touches[0];
      if (touch) hunt(touch.clientX, touch.clientY);
    };
    host.addEventListener("pointermove", onPointer);
    host.addEventListener("pointerdown", onPointer);
    host.addEventListener("touchstart", onTouch, { passive: true });
    host.addEventListener("touchmove", onTouch, { passive: true });

    return () => {
      cancelled = true;
      stop();
      resize.disconnect();
      seen.disconnect();
      document.removeEventListener("visibilitychange", onVisibility);
      still.removeEventListener("change", onMotion);
      host.removeEventListener("pointermove", onPointer);
      host.removeEventListener("pointerdown", onPointer);
      host.removeEventListener("touchstart", onTouch);
      host.removeEventListener("touchmove", onTouch);
    };
  }, [word, birdCount, reeds, fontFamily, fontWeight, slotRef]);

  return (
    <>
      <canvas ref={canvasRef} aria-hidden="true" className={className ?? "pointer-events-none absolute inset-0 h-full w-full"} />
      <span className="sr-only">{word}</span>
    </>
  );
}
