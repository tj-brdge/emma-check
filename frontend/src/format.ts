export const usd = (x: number | null | undefined, signed = false) => {
  if (x === null || x === undefined) return "—";
  const s = Math.abs(x).toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
  if (Math.abs(x) < 0.5) return "$0";
  return x < 0 ? `(${s})` : signed ? `+${s}` : s;
};
export const num = (x: number | null | undefined, d = 4) =>
  x === null || x === undefined ? "—" : x.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
export const pct = (x: number | null | undefined, d = 2) => (x === null || x === undefined ? "—" : `${(x * 100).toFixed(d)}%`);
export const par = (x: number) => (x >= 1e6 ? `${(x / 1e6).toFixed(2)}MM` : `${(x / 1e3).toFixed(0)}M`);
export const ts = (s: string | null | undefined) => (s ? s.replace("T", " ").slice(0, 19) : "—");
export const ASSET_LABEL: Record<string, string> = { muni: "MUNI", agency_mbs: "MBS" };
export const RULE_LABEL: Record<string, string> = {
  cash_reconciliation: "CASH",
  null_vs_zero: "NULL≠0",
  frequency_contradiction: "FREQ",
  factor_mismatch: "FACTOR",
  rate_vs_disclosure: "RATE/DISC",
  yield_coupon_impossibility: "YLD/CPN",
  price_drift: "DRIFT",
  peer_outlier: "PEER",
  vendor_disagreement: "VENDOR",
  zero_coupon_sanity: "ZERO",
};
