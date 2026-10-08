// The shapes the API returns (see src/peermap/peers.py and performance.py).
export type PeerBrief = { ticker: string; name: string; industry: string };
export type PeerSource = { form: string; filed: string; url: string };
export type PeerDetail = PeerBrief & PeerSource & { peers: (PeerBrief & { similarity: number })[] };
// A company's peers are [index in companies, similarity].
export type PeerPoint = PeerBrief & PeerSource & { x: number; y: number; peers: [number, number][] };
export type PeerOverview = { built: string | null; labels: { text: string; x: number; y: number }[]; companies: PeerPoint[] };

// Returns per company, one per period, in the order of `periods`. Null where the history is short.
export type PeriodKey = "1d" | "1w" | "1m" | "ytd" | "1y";
export type PerformanceDoc = { as_of: string | null; stale: boolean; periods: PeriodKey[]; returns: Record<string, (number | null)[]> };
