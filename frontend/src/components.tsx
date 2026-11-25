import type { ReactNode } from "react";

/** Render a value, keeping BLANK visually distinct from zero everywhere. */
export function Val({ v }: { v: string | number | null | undefined }): ReactNode {
  if (v === "BLANK") return <span className="blank">BLANK</span>;
  if (v === null || v === undefined || v === "not supplied") return <span className="muted">—</span>;
  return <>{v}</>;
}

export function AssetChip({ c }: { c: string }) {
  return <span className={`chip asset-${c}`}>{c === "agency_mbs" ? "MBS" : c === "muni" ? "MUNI" : c}</span>;
}
