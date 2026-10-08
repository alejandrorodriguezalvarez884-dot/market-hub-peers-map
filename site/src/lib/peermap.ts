// The peer map: every company a dot, close to the companies whose business description reads
// like its own, and coloured by how its price has moved. Drawn on a canvas (well over a thousand
// dots, panned and zoomed), at the screen's real pixels. Choosing a company rings it and its
// neighbours; the page lists them beside it.
import { add, h } from "./dom";
import { signedPct } from "./format";
import { tidyName } from "./site";
import type { PeerOverview } from "./types";

const PAGE = "#0b0c0d";
const DOT = "#8c8b86";
const INK = "#f2f0ea";
const PLACE = "#c9c7c1";
// A move's colour: the portal's green and red, stronger the bigger the move against `cap` (the
// move that gets the full colour), and grey around zero. A company without prices stays dim.
const UP = [53, 201, 143], DOWN = [255, 107, 87], FLAT = [118, 118, 114];
const NO_DATA = "#4a4a47";
export function moveColor(v: number | null | undefined, cap: number): string {
  if (v == null) return NO_DATA;
  // The root lifts small moves off the grey, so that the side of a quiet day still shows.
  const t = Math.min(1, Math.abs(v) / cap) ** 0.6, to = v >= 0 ? UP : DOWN;
  return `rgb(${FLAT.map((c, k) => Math.round(c + (to[k] - c) * t)).join(" ")})`;
}
export type Colouring = { values: (number | null)[]; cap: number; label: string };
const PAD = 28;
const SANS = '"IBM Plex Sans", system-ui, sans-serif';
const MONO = '"IBM Plex Mono", ui-monospace, monospace';

type View = { cx: number; cy: number; k: number }; // centre in map units, and pixels per map unit
type Box = [number, number, number, number];

export function peerMap(data: PeerOverview, onPick: (index: number) => void): {
  el: HTMLElement;
  select: (index: number | null) => void;
  colour: (by: Colouring | null) => void;
} {
  const pts = data.companies;
  const el = h("div", "relative h-[420px] select-none overflow-hidden rounded-[3px] border border-line sm:h-[560px] lg:h-[640px]");
  const canvas = h("canvas", "block h-full w-full cursor-grab touch-none");
  canvas.setAttribute("role", "img");
  canvas.setAttribute("aria-label", `Map of ${pts.length} companies, placed by how alike their business descriptions are`);
  const tip = h("div", "chart-tip");
  tip.hidden = true;
  const controls = h("div", "absolute right-2 top-2 flex flex-col gap-1");
  add(el, canvas, tip, controls);
  const ctx = canvas.getContext("2d")!;

  const xs = pts.map((p) => p.x), ys = pts.map((p) => p.y);
  const bounds = { x0: Math.min(...xs), x1: Math.max(...xs), y0: Math.min(...ys), y1: Math.max(...ys) };
  let w = 0, h_ = 0;
  let view: View = { cx: 0.5, cy: 0.5, k: 1 };
  let selected: number | null = null;
  let hover: number | null = null;
  let by: Colouring | null = null;
  let frame = 0;
  const fillOf = (i: number) => (by ? moveColor(by.values[i], by.cap) : DOT);

  const fit = (x0: number, x1: number, y0: number, y1: number, pad: number): View => ({
    cx: (x0 + x1) / 2,
    cy: (y0 + y1) / 2,
    k: Math.min((w - 2 * pad) / Math.max(x1 - x0, 1e-6), (h_ - 2 * pad) / Math.max(y1 - y0, 1e-6)),
  });
  const home = () => fit(bounds.x0, bounds.x1, bounds.y0, bounds.y1, PAD);
  const sx = (x: number) => (x - view.cx) * view.k + w / 2;
  const sy = (y: number) => (y - view.cy) * view.k + h_ / 2;

  function draw() {
    const dpr = window.devicePixelRatio || 1;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h_);
    const peers = selected === null ? [] : pts[selected].peers.map(([j]) => j);
    const lit = new Set(selected === null ? [] : [selected, ...peers]);
    const zoom = view.k / home().k;

    ctx.globalAlpha = selected === null ? (by ? 0.95 : 0.75) : by ? 0.5 : 0.35;
    const r = zoom > 3 ? 3.4 : by ? 2.7 : 2.2;
    const inView: number[] = [];
    pts.forEach((p, i) => {
      const x = sx(p.x), y = sy(p.y);
      if (x < -8 || y < -8 || x > w + 8 || y > h_ + 8) return;
      inView.push(i);
      if (lit.has(i)) return;
      ctx.fillStyle = fillOf(i);
      ctx.beginPath();
      ctx.arc(x, y, r, 0, Math.PI * 2);
      ctx.fill();
    });
    ctx.globalAlpha = 1;

    // Text never lands on text: what is drawn first keeps its place.
    const taken: Box[] = [];
    const text = (label: string, x: number, y: number, font: string, color: string, align: CanvasTextAlign = "left"): boolean => {
      ctx.font = font;
      const width = ctx.measureText(label).width;
      // A centred name near the edge is moved in, not cut.
      if (align === "center") x = Math.min(Math.max(x, width / 2 + 6), w - width / 2 - 6);
      const left = align === "center" ? x - width / 2 : x;
      const box: Box = [left - 3, y - 12, left + width + 3, y + 4];
      if (taken.some((t) => box[0] < t[2] && box[2] > t[0] && box[1] < t[3] && box[3] > t[1])) return false;
      taken.push(box);
      ctx.textAlign = align;
      ctx.lineWidth = 3;
      ctx.strokeStyle = PAGE;
      ctx.strokeText(label, x, y);
      ctx.fillStyle = color;
      ctx.fillText(label, x, y);
      return true;
    };

    if (selected !== null) {
      const s = pts[selected];
      ctx.strokeStyle = INK;
      ctx.globalAlpha = 0.3;
      ctx.lineWidth = 1;
      for (const j of peers) {
        ctx.beginPath();
        ctx.moveTo(sx(s.x), sy(s.y));
        ctx.lineTo(sx(pts[j].x), sy(pts[j].y));
        ctx.stroke();
      }
      ctx.globalAlpha = 1;
      for (const j of peers) dot(j, 4.5, 1.25);
      dot(selected, 6.5, 2.25);
      text(s.ticker, sx(s.x) + 11, sy(s.y) + 4, `600 12.5px ${MONO}`, INK);
      for (const j of peers) text(pts[j].ticker, sx(pts[j].x) + 9, sy(pts[j].y) + 4, `500 11.5px ${MONO}`, INK);
    }
    if (hover !== null && !lit.has(hover)) {
      dot(hover, 4.5, 1.25);
      text(pts[hover].ticker, sx(pts[hover].x) + 9, sy(pts[hover].y) + 4, `500 11.5px ${MONO}`, INK);
    }
    for (const l of data.labels) {
      const x = sx(l.x), y = sy(l.y);
      if (x > 0 && y > 0 && x < w && y < h_) text(l.text, x, y, `500 11.5px ${SANS}`, PLACE, "center");
    }
    // Close enough to tell the dots apart, each one gets its ticker.
    if (inView.length <= 160) for (const i of inView) if (!lit.has(i) && i !== hover) text(pts[i].ticker, sx(pts[i].x) + 6, sy(pts[i].y) + 4, `400 11px ${MONO}`, DOT);
  }

  // A company picked out: its dot in its own colour, bigger, inside a light ring. The ring says
  // which company; the colour still says how it moved.
  function dot(i: number, r: number, ring: number) {
    const x = sx(pts[i].x), y = sy(pts[i].y);
    ctx.beginPath();
    ctx.arc(x, y, r + ring + 1.5, 0, Math.PI * 2);
    ctx.fillStyle = PAGE;
    ctx.fill();
    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.fillStyle = by ? fillOf(i) : INK;
    ctx.fill();
    ctx.beginPath();
    ctx.arc(x, y, r + ring / 2 + 1, 0, Math.PI * 2);
    ctx.lineWidth = ring;
    ctx.strokeStyle = INK;
    ctx.stroke();
  }

  const redraw = () => {
    cancelAnimationFrame(frame);
    frame = requestAnimationFrame(draw);
  };

  // Moves the view in a third of a second, or at once for someone who asked for less motion.
  let moving = 0;
  function go(to: View) {
    cancelAnimationFrame(moving);
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      view = to;
      return redraw();
    }
    const from = view, t0 = performance.now();
    const step = (now: number) => {
      const t = Math.min(1, (now - t0) / 320), e = 1 - (1 - t) ** 3;
      view = { cx: from.cx + (to.cx - from.cx) * e, cy: from.cy + (to.cy - from.cy) * e, k: from.k * (to.k / from.k) ** e };
      draw();
      if (t < 1) moving = requestAnimationFrame(step);
    };
    moving = requestAnimationFrame(step);
  }

  const limits = () => ({ min: home().k * 0.8, max: home().k * 40 });
  function zoomAt(px: number, py: number, factor: number, animate = false) {
    const { min, max } = limits();
    const k = Math.min(max, Math.max(min, view.k * factor));
    const wx = (px - w / 2) / view.k + view.cx, wy = (py - h_ / 2) / view.k + view.cy;
    const to = { cx: wx - (px - w / 2) / k, cy: wy - (py - h_ / 2) / k, k };
    if (animate) go(to);
    else (view = to), redraw();
  }

  function nearest(px: number, py: number): number | null {
    let best: number | null = null, bestD = 12 * 12;
    pts.forEach((p, i) => {
      const d = (sx(p.x) - px) ** 2 + (sy(p.y) - py) ** 2;
      if (d < bestD) (best = i), (bestD = d);
    });
    return best;
  }

  function showTip(i: number | null) {
    if (i === null) return void (tip.hidden = true);
    const p = pts[i];
    tip.replaceChildren(
      add(h("div", "flex items-baseline justify-between gap-3"), h("span", "font-medium text-ink-strong", tidyName(p.name)), h("span", "num text-muted", p.ticker)),
      h("div", "mt-0.5 text-muted", p.industry),
      by ? add(h("div", "mt-1.5 flex items-baseline justify-between gap-3"), h("span", "text-muted", by.label),
        h("span", `num ${by.values[i] == null ? "text-muted" : by.values[i]! > 0 ? "text-up" : by.values[i]! < 0 ? "text-down" : "text-ink-strong"}`, signedPct(by.values[i], 2))) : "",
    );
    tip.hidden = false;
    tip.style.left = `${Math.min(Math.max(sx(p.x), 100), w - 100)}px`;
    tip.style.top = `${sy(p.y) + 22}px`;
  }

  // One finger or the mouse pans; two fingers zoom. A press that does not move chooses a company.
  const fingers = new Map<number, { x: number; y: number }>();
  let moved = false;
  const at = (e: PointerEvent | MouseEvent | WheelEvent) => {
    const box = canvas.getBoundingClientRect();
    return { x: e.clientX - box.left, y: e.clientY - box.top };
  };
  canvas.addEventListener("pointerdown", (e) => {
    canvas.setPointerCapture(e.pointerId);
    fingers.set(e.pointerId, at(e));
    moved = false;
    cancelAnimationFrame(moving);
  });
  canvas.addEventListener("pointermove", (e) => {
    const p = at(e), before = fingers.get(e.pointerId);
    if (!before) {
      const i = nearest(p.x, p.y);
      if (i !== hover) (hover = i), redraw();
      canvas.style.cursor = i === null ? "grab" : "pointer";
      return showTip(i);
    }
    if (fingers.size === 2) {
      const other = [...fingers.entries()].find(([id]) => id !== e.pointerId)![1];
      const was = Math.hypot(before.x - other.x, before.y - other.y), now = Math.hypot(p.x - other.x, p.y - other.y);
      if (was > 0) zoomAt((p.x + other.x) / 2, (p.y + other.y) / 2, now / was);
      moved = true;
    } else {
      if (Math.hypot(p.x - before.x, p.y - before.y) > 3) moved = true;
      if (moved) {
        view = { ...view, cx: view.cx - (p.x - before.x) / view.k, cy: view.cy - (p.y - before.y) / view.k };
        canvas.style.cursor = "grabbing";
        showTip(null);
        redraw();
      } else return;
    }
    fingers.set(e.pointerId, p);
  });
  const release = (e: PointerEvent) => {
    const was = fingers.delete(e.pointerId);
    canvas.style.cursor = "grab";
    if (!was || moved || e.type !== "pointerup") return;
    const p = at(e), i = nearest(p.x, p.y);
    if (i !== null) onPick(i);
  };
  canvas.addEventListener("pointerup", release);
  canvas.addEventListener("pointercancel", release);
  canvas.addEventListener("pointerleave", () => {
    if (hover !== null) (hover = null), redraw();
    showTip(null);
  });
  canvas.addEventListener("dblclick", (e) => {
    const p = at(e);
    zoomAt(p.x, p.y, 2, true);
  });
  // The wheel scrolls the page, as everywhere else; with Ctrl (or a pinch on a trackpad) it zooms.
  canvas.addEventListener("wheel", (e) => {
    if (!e.ctrlKey && !e.metaKey) return;
    e.preventDefault();
    const p = at(e);
    zoomAt(p.x, p.y, Math.exp(-e.deltaY * 0.01));
  }, { passive: false });

  const button = (label: string, name: string, act: () => void) => {
    const b = h("button", "flex h-8 w-8 items-center justify-center rounded-[3px] border border-line-strong bg-page/90 text-ink hover:border-muted hover:text-ink-strong", label);
    b.type = "button";
    b.setAttribute("aria-label", name);
    b.title = name;
    b.addEventListener("click", act);
    controls.append(b);
  };
  button("+", "Zoom in", () => zoomAt(w / 2, h_ / 2, 1.8, true));
  button("−", "Zoom out", () => zoomAt(w / 2, h_ / 2, 1 / 1.8, true));
  button("⤢", "Whole map", () => go(home()));

  // The chosen company and its neighbours, framed together.
  function frameOf(i: number): View {
    const group = [pts[i], ...pts[i].peers.map(([j]) => pts[j])];
    const gx = group.map((p) => p.x), gy = group.map((p) => p.y);
    const to = fit(Math.min(...gx), Math.max(...gx), Math.min(...gy), Math.max(...gy), Math.min(110, w / 5));
    return { ...to, k: Math.min(to.k, home().k * 10) };
  }

  new ResizeObserver(() => {
    const first = !w;
    const dpr = window.devicePixelRatio || 1;
    w = el.clientWidth;
    h_ = el.clientHeight;
    if (!w || !h_) return;
    canvas.width = Math.round(w * dpr);
    canvas.height = Math.round(h_ * dpr);
    if (first) view = selected === null ? home() : frameOf(selected);
    draw();
  }).observe(el);
  // The page's fonts may arrive after the first drawing.
  document.fonts?.ready.then(redraw);

  return {
    el,
    colour(next) {
      by = next;
      redraw();
    },
    select(index) {
      selected = index;
      hover = null;
      showTip(null);
      if (!w) return;
      go(index === null ? home() : frameOf(index));
    },
  };
}
