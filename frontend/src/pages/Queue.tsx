import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { RULE_LABEL, ts, usd } from "../format";
import type { FindingSummary } from "../types";
import { AssetChip } from "../components";

type Filter = "open" | "approved" | "rejected" | "all";

export default function Queue() {
  const [rows, setRows] = useState<FindingSummary[] | null>(null);
  const [filter, setFilter] = useState<Filter>("open");
  const [asset, setAsset] = useState<string>("all");
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api.get<FindingSummary[]>("/api/findings").then(setRows).catch((e) => setErr(String(e.message)));
  }, []);

  const stats = useMemo(() => {
    const s = { open: 0, approved: 0, rejected: 0, openUsd: 0, approvedUsd: 0, openRunRate: 0 };
    for (const r of rows ?? []) {
      s[r.status]++;
      if (r.status === "open") {
        s.openUsd += r.income_impact_usd;
        s.openRunRate += r.run_rate_gap_usd;
      }
      if (r.status === "approved") s.approvedUsd += r.income_impact_usd;
    }
    return s;
  }, [rows]);

  const shown = (rows ?? []).filter((r) => (filter === "all" || r.status === filter) && (asset === "all" || r.asset_class === asset));

  return (
    <>
      <div className="kpis">
        <div className="kpi hero">
          <div className={`v ${stats.openUsd > 0 ? "under" : ""}`}>{usd(stats.openUsd)}</div>
          <div className="l">Unbooked income · open findings</div>
        </div>
        <div className="kpi">
          <div className="v">{usd(stats.openRunRate)}</div>
          <div className="l">12m run-rate gap · open</div>
        </div>
        <div className="kpi">
          <div className="v">{stats.open}</div>
          <div className="l">Open</div>
        </div>
        <div className="kpi">
          <div className="v">{stats.approved}</div>
          <div className="l">Approved · {usd(stats.approvedUsd)}</div>
        </div>
        <div className="kpi">
          <div className="v">{stats.rejected}</div>
          <div className="l">Rejected</div>
        </div>
      </div>

      <div className="bar">
        <h1>Review queue</h1>
        <div className="tabs">
          {(["open", "approved", "rejected", "all"] as Filter[]).map((f) => (
            <button key={f} className={filter === f ? "on" : ""} onClick={() => setFilter(f)}>
              {f[0].toUpperCase() + f.slice(1)}
            </button>
          ))}
        </div>
        <div className="tabs">
          {[["all", "All classes"], ["muni", "Municipal"], ["agency_mbs", "Agency MBS"]].map(([k, l]) => (
            <button key={k} className={asset === k ? "on" : ""} onClick={() => setAsset(k)}>{l}</button>
          ))}
        </div>
        <span className="muted">sorted by absolute income impact</span>
        <div className="spacer" />
        <button
          className="btn"
          disabled={!stats.approved}
          onClick={() => api.download("/api/exports/approved.csv", "terms_check_approved.csv").catch((e) => setErr(e.message))}
        >
          Export approved CSV
        </button>
      </div>
      {err && <div className="err">{err}</div>}

      <div className="panel">
        <table className="grid">
          <thead>
            <tr>
              <th className="n">Income impact</th>
              <th className="n">12m run-rate</th>
              <th>Class</th>
              <th>CUSIP</th>
              <th>Description</th>
              <th>Finding</th>
              <th>Screens</th>
              <th>Extraction</th>
              <th>Status</th>
              <th>Created</th>
            </tr>
          </thead>
          <tbody>
            {rows === null && (
              <tr>
                <td colSpan={10} className="muted">Loading…</td>
              </tr>
            )}
            {rows !== null && shown.length === 0 && (
              <tr>
                <td colSpan={10} className="muted">
                  No {filter === "all" ? "" : filter} findings. Flagged CUSIPs become findings once their official
                  statement is analysed (Screen flags tab).
                </td>
              </tr>
            )}
            {shown.map((r) => (
              <tr key={r.id} className="click" onClick={() => (window.location.hash = `#/findings/${r.id}`)}>
                <td className={`n b ${r.income_impact_usd > 0.5 ? "under" : r.income_impact_usd < -0.5 ? "over" : ""}`}>
                  {usd(r.income_impact_usd)}
                </td>
                <td className="n">{usd(r.run_rate_gap_usd)}</td>
                <td><AssetChip c={r.asset_class} /></td>
                <td className="mono">{r.cusip}</td>
                <td>{r.description}</td>
                <td className="wrap">{r.headline}</td>
                <td className="nowrap">
                  {r.rules.map((x) => (
                    <span key={x} className="chip">{RULE_LABEL[x] ?? x}</span>
                  ))}
                </td>
                <td><span className={`badge ${r.extraction_status}`}>{r.extraction_status}</span></td>
                <td><span className={`badge ${r.status}`}>{r.status}</span></td>
                <td className="mono muted nowrap">{ts(r.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
