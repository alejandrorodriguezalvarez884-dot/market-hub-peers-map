// Tiny DOM helpers. Everything that comes from the API or the address bar goes in as text, never
// as markup.
export function h<K extends keyof HTMLElementTagNameMap>(tag: K, cls = "", text?: string): HTMLElementTagNameMap[K] {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

export function add<T extends Element>(parent: T, ...children: (Node | string | null | undefined | false)[]): T {
  for (const c of children) if (c) parent.append(c);
  return parent;
}

export function svg<K extends keyof SVGElementTagNameMap>(tag: K, attrs: Record<string, string | number> = {}): SVGElementTagNameMap[K] {
  const e = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, String(v));
  return e;
}

// A titled section, the building block of every page: a rule, a title, the content. No box.
export function card(title: string, subtitle?: string, cls = ""): { el: HTMLElement; body: HTMLElement } {
  const el = h("section", `sec ${cls}`);
  const head = add(h("header", "mb-4"), h("h3", "sec-title", title));
  if (subtitle) head.append(h("p", "mt-1 max-w-3xl text-[13px] text-muted", subtitle));
  const body = h("div");
  add(el, head, body);
  return { el, body };
}

// A small figure: label above, value below.
export function stat(label: string, value: string, note?: string, tone: "up" | "down" | "" = ""): HTMLElement {
  const color = tone === "up" ? "text-up" : tone === "down" ? "text-down" : "text-ink-strong";
  return add(
    h("div", "min-w-0"),
    h("div", "text-[13px] text-muted", label),
    h("div", `num mt-1 text-xl ${color}`, value),
    note ? h("div", "mt-0.5 text-[12.5px] text-muted", note) : null,
  );
}

export const toneOf = (v: number | null | undefined): "up" | "down" | "" =>
  typeof v === "number" ? (v > 0 ? "up" : v < 0 ? "down" : "") : "";

// The same company in the three parts of Market Hub: its price page on the portal, its numbers
// here and its latest results release in the Earnings Radar.
export function companyTabs(links: { label: string; href: string; current?: boolean }[]): HTMLElement {
  const nav = h("nav", "tabs");
  nav.setAttribute("aria-label", "This company in Market Hub");
  for (const l of links) {
    const a = h("a", "tab-btn", l.label);
    a.href = l.href;
    if (l.current) a.setAttribute("aria-selected", "true"), a.setAttribute("aria-current", "page");
    nav.append(a);
  }
  return nav;
}
