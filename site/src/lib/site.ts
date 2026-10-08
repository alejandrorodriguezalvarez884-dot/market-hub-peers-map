// Site-wide constants and links.
export const SITE_NAME = "Peer Map";
export const REPO_URL = "https://github.com/alejandrorodriguezalvarez884-dot/market-hub-peers-map";
export const AUTHOR_URL = "https://alejandrorodriguez.dev/";

// The tool is a section of Market Hub: a company here links to the same company in the portal,
// in Fundamentals Lab and in the Earnings Radar.
const site = (v: string | undefined, fallback: string) => (v ?? fallback).replace(/\/$/, "");
export const HUB_URL = site(import.meta.env.PUBLIC_HUB_URL, "https://themarkethub.app");
export const FUNDAMENTALS_URL = site(import.meta.env.PUBLIC_FUNDAMENTALS_URL, "https://fundamentals.themarkethub.app");
export const RADAR_URL = site(import.meta.env.PUBLIC_RADAR_URL, "https://radar.themarkethub.app");
export const hubQuoteUrl = (ticker: string) => `${HUB_URL}/quote/?t=${encodeURIComponent(ticker)}`;
export const fundamentalsUrl = (ticker: string) => `${FUNDAMENTALS_URL}/stock/?t=${encodeURIComponent(ticker)}`;
export const compareUrl = (tickers: string[]) => `${FUNDAMENTALS_URL}/compare/?t=${tickers.map(encodeURIComponent).join(",")}`;
export const radarUrl = (ticker: string) => `${RADAR_URL}/analyze/?ticker=${encodeURIComponent(ticker)}`;

// Every internal link goes through here, so the site works under a sub-path too.
export function link(path: string): string {
  const base = import.meta.env.BASE_URL.replace(/\/$/, "");
  return `${base}${path}`;
}

// The API lives on the same origin in production; in development it is another port.
export const API = (import.meta.env.PUBLIC_API_URL ?? "").replace(/\/$/, "");

// A company on the map, by its address: /?t=NVDA&p=1m (the span the dots are coloured by).
export const mapUrl = (ticker?: string | null, period?: string | null) => {
  const q = new URLSearchParams();
  if (ticker) q.set("t", ticker);
  if (period) q.set("p", period);
  const s = q.toString();
  return s ? `${link("/")}?${s}` : link("/");
};

// Company names as the SEC writes them ("APPLE INC") read better in title case.
export function tidyName(name: string): string {
  if (name !== name.toUpperCase()) return name;
  const keep = new Set(["LLC", "PLC", "NV", "SA", "AG", "SE", "LP", "ETF", "REIT", "USA", "II", "III"]);
  return name
    .toLowerCase()
    .split(/(\s+|-|\/)/)
    .map((w) => (keep.has(w.toUpperCase()) ? w.toUpperCase() : w.charAt(0).toUpperCase() + w.slice(1)))
    .join("")
    .replace(/\b(Inc|Corp|Co|Ltd)\b(?!\.)/g, "$1.");
}
