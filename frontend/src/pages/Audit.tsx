import { Fragment, useEffect, useState } from "react";
import { api } from "../api";
import { ts } from "../format";
import type { AuditEvent } from "../types";

export default function Audit() {
  const [rows, setRows] = useState<AuditEvent[]>([]);
  const [verify, setVerify] = useState<{ ok: boolean; checked: number; first_bad_id: number | null } | null>(null);
  const [type, setType] = useState("");
  const [open, setOpen] = useState<number | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api.get<AuditEvent[]>(`/api/audit?limit=500${type ? `&event_type=${type}` : ""}`).then(setRows).catch((e) => setErr(e.message));
  }, [type]);

  const types = ["", "upload.accepted", "upload.rejected", "screen_run.completed", "document.registered", "extraction.completed",
    "extraction.failed", "finding.created", "review.approve", "review.reject", "review.annotate", "review.reopen", "export.approved_csv"];

  return (
    <>
      <div className="kpis">
        <div className="kpi hero">
          <div className={`v ${verify && !verify.ok ? "under" : ""}`}>{verify ? (verify.ok ? "INTACT" : `BROKEN @ #${verify.first_bad_id}`) : "—"}</div>
          <div className="l">Hash chain {verify ? `· ${verify.checked} events checked` : ""}</div>
        </div>
        <div className="kpi"><div className="v">{rows.length}</div><div className="l">Events shown</div></div>
      </div>
      <div className="bar">
        <h1>Audit trail</h1>
        <select className="f" value={type} onChange={(e) => setType(e.target.value)}>
          {types.map((t) => <option key={t} value={t}>{t || "all event types"}</option>)}
        </select>
        <button className="btn" onClick={() => api.get<typeof verify>("/api/audit/verify").then(setVerify).catch((e) => setErr(e.message))}>Verify chain</button>
        <span className="muted">Append-only: the database rejects updates and deletes on audit tables.</span>
      </div>
      {err && <div className="err">{err}</div>}
      <div className="panel">
        <table className="grid">
          <thead><tr><th>#</th><th>Time (UTC)</th><th>User</th><th>Event</th><th>Entity</th><th>Summary</th><th>Hash</th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <Fragment key={r.id}>
                <tr className="click" onClick={() => setOpen(open === r.id ? null : r.id)}>
                  <td className="mono">{r.id}</td><td className="mono nowrap">{ts(r.ts)}</td><td>{r.actor}</td>
                  <td className="mono">{r.event_type}</td><td className="mono">{r.entity_type}:{r.entity_id}</td>
                  <td className="wrap">{summary(r)}</td><td className="hash">{r.hash.slice(0, 10)}…</td>
                </tr>
                {open === r.id && (
                  <tr key={r.id + "-p"}><td /><td colSpan={6}><pre className="mono" style={{ margin: 0, whiteSpace: "pre-wrap" }}>{JSON.stringify(r.payload, null, 2)}</pre><div className="hash">prev {r.prev_hash}<br />hash {r.hash}</div></td></tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

function summary(r: AuditEvent): string {
  const p = r.payload as Record<string, unknown>;
  const keys = ["filename", "cusip", "status", "flag_count", "income_impact_usd", "comment", "rows", "error"];
  return keys.filter((k) => p[k] !== undefined && p[k] !== null).map((k) => `${k}=${String(p[k])}`).join(" · ");
}
