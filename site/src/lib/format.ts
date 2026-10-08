// Number formatting. Every formatter takes null and returns an em dash for it.
export type N = number | null | undefined;
const DASH = "—";
const ok = (v: N): v is number => typeof v === "number" && Number.isFinite(v);

export function money(v: N, digits = 1): string {
  if (!ok(v)) return DASH;
  const a = Math.abs(v);
  const sign = v < 0 ? "−" : "";
  if (a >= 1e12) return `${sign}$${(a / 1e12).toFixed(digits + 1)}T`;
  if (a >= 1e9) return `${sign}$${(a / 1e9).toFixed(digits)}B`;
  if (a >= 1e6) return `${sign}$${(a / 1e6).toFixed(digits)}M`;
  if (a >= 1e3) return `${sign}$${(a / 1e3).toFixed(digits)}K`;
  return `${sign}$${a.toFixed(2)}`;
}

export function price(v: N): string {
  return ok(v) ? `$${v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : DASH;
}

export function pct(v: N, digits = 1, signed = false): string {
  if (!ok(v)) return DASH;
  const s = (v * 100).toFixed(digits);
  return `${signed && v > 0 ? "+" : ""}${s.replace("-", "−")}%`;
}

export const signedPct = (v: N, digits = 1) => pct(v, digits, true);

export function mult(v: N, digits = 1): string {
  return ok(v) ? `${v.toFixed(digits)}×` : DASH;
}

export function num(v: N, digits = 2): string {
  return ok(v) ? v.toLocaleString("en-US", { maximumFractionDigits: digits }) : DASH;
}

export function count(v: N): string {
  return ok(v) ? Math.round(v).toLocaleString("en-US") : DASH;
}

export function shortDate(iso: string | null | undefined): string {
  if (!iso) return DASH;
  const d = new Date(`${iso.slice(0, 10)}T00:00:00Z`);
  return d.toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric", timeZone: "UTC" });
}

// The formatter for each kind of figure, so tables and charts agree.
export type Kind = "money" | "pct" | "spct" | "mult" | "num" | "price" | "count";
export function fmt(kind: Kind, v: N): string {
  switch (kind) {
    case "money":
      return money(v);
    case "pct":
      return pct(v);
    case "spct":
      return signedPct(v);
    case "mult":
      return mult(v);
    case "price":
      return price(v);
    case "count":
      return count(v);
    default:
      return num(v);
  }
}
