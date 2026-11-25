import { useEffect, useState } from "react";
import { api, ApiError } from "../api";
import { ts } from "../format";
import type { Batch, ScreenRunT } from "../types";

const KINDS: { kind: Batch["kind"]; label: string; hint: string }[] = [
  { kind: "holdings", label: "Holdings + primary vendor terms", hint: "CUSIP, description, par, price, convention, coupon, accrual type, maturity, issue date, rating, sector, state" },
  { kind: "vendor_secondary", label: "Second vendor file (optional)", hint: "Same columns without par; used for vendor-disagreement screen" },
  { kind: "price_history", label: "Price history (optional)", hint: "cusip, price_date, price, price_convention" },
  { kind: "ledger", label: "Cash / income ledger (optional)", hint: "cusip, entry_date, cash, type (interest|principal)[, portfolio, booked_income]" },
];

interface RowErr { row: number; column: string | null; message: string }

export default function Data() {
  const [batches, setBatches] = useState<Batch[]>([]);
  const [runs, setRuns] = useState<ScreenRunT[]>([]);
  const [errors, setErrors] = useState<{ kind: string; msg: string; rows: RowErr[] } | null>(null);
  const [ok, setOk] = useState<string | null>(null);
  const [form, setForm] = useState({ as_of: "2026-11-30", holdings: "", history: "", ledger: "", z: "3.0" });
  const [vendorIds, setVendorIds] = useState<number[]>([]);
  const [running, setRunning] = useState(false);

  const load = () => {
    api.get<Batch[]>("/api/batches").then((b) => {
      setBatches(b);
      const first = (k: string) => String(b.find((x) => x.kind === k)?.id ?? "");
      setForm((f) => ({ ...f, holdings: f.holdings || first("holdings"), history: f.history || first("price_history"), ledger: f.ledger || first("ledger") }));
      setVendorIds((v) => (v.length ? v : b.filter((x) => x.kind === "vendor_secondary").map((x) => x.id)));
    });
    api.get<ScreenRunT[]>("/api/screen-runs").then(setRuns);
  };
  useEffect(load, []);

  const upload = async (kind: string, file: File, vendor: string) => {
    setErrors(null);
    setOk(null);
    const fd = new FormData();
    fd.append("file", file);
    if (vendor) fd.append("vendor", vendor);
    try {
      const r = await api.post<{ batch: Batch; records: number; prices: number }>(`/api/uploads/${kind}`, fd);
      setOk(`${file.name}: batch #${r.batch.id}, ${r.batch.row_count} rows accepted.`);
      if (kind === "vendor_secondary") setVendorIds((v) => [...v, r.batch.id]);
      else setForm((f) => ({ ...f, [kind === "holdings" ? "holdings" : kind === "ledger" ? "ledger" : "history"]: String(r.batch.id) }));
      load();
    } catch (e) {
      const d = (e as ApiError).detail as { message?: string; errors?: RowErr[] } | string;
      setErrors({ kind, msg: typeof d === "string" ? d : d?.message ?? "rejected", rows: typeof d === "string" ? [] : d?.errors ?? [] });
    }
  };

  const uploadDisclosure = async (file: File) => {
    setErrors(null);
    setOk(null);
    const fd = new FormData();
    fd.append("file", file);
    fd.append("cusip", "MULTIPLE");
    fd.append("doc_kind", "pool_disclosure");
    fd.append("asset_class", "agency_mbs");
    try {
      const d = await api.post<{ id: number }>("/api/documents", fd);
      setOk(`${file.name}: pool disclosure registered as document #${d.id}. Screen runs use the latest disclosure per CUSIP.`);
    } catch (e) {
      setErrors({ kind: "pool disclosure", msg: (e as Error).message, rows: [] });
    }
  };

  const runScreens = async () => {
    setRunning(true);
    try {
      const r = await api.post<ScreenRunT>("/api/screen-runs", {
        as_of: form.as_of,
        holdings_batch_id: Number(form.holdings),
        vendor_batch_ids: vendorIds,
        history_batch_id: form.history ? Number(form.history) : null,
        ledger_batch_id: form.ledger ? Number(form.ledger) : null,
        config: { peer_z_threshold: Number(form.z) },
      });
      window.location.hash = `#/flags/${r.id}`;
    } catch (e) {
      setErrors({ kind: "screen run", msg: (e as Error).message, rows: [] });
    } finally {
      setRunning(false);
    }
  };

  const opts = (k: string) => batches.filter((b) => b.kind === k).map((b) => (
    <option key={b.id} value={b.id}>#{b.id} {b.filename} ({b.row_count})</option>
  ));

  return (
    <>
      <div className="bar"><h1>Data &amp; screen runs</h1></div>
      {ok && <div className="note" style={{ color: "var(--ok)", borderColor: "#9bd1ad", background: "#eefaf2" }}>{ok}</div>}
      {errors && (
        <div className="err">
          <b>{errors.kind}: {errors.msg}</b>
          {errors.rows.length > 0 && (
            <table className="grid" style={{ marginTop: 6, background: "#fff" }}>
              <thead><tr><th className="n">Row</th><th>Column</th><th>Problem</th></tr></thead>
              <tbody>{errors.rows.slice(0, 50).map((r, i) => <tr key={i}><td className="n">{r.row}</td><td className="mono">{r.column}</td><td>{r.message}</td></tr>)}</tbody>
            </table>
          )}
        </div>
      )}
      <div className="cols">
        <div className="panel">
          <h2>Upload CSV</h2>
          <table className="grid">
            <tbody>
              {KINDS.map((k) => (
                <UploadRow key={k.kind} {...k} onFile={(f, v) => upload(k.kind, f, v)} />
              ))}
            </tbody>
          </table>
          <div className="body muted">Coupons and yields in percent. Blank cells are kept as blank (never read as zero); a file with any invalid row is rejected whole. Optional columns: asset_class (muni | agency_mbs), product_type, factor, factor_date, payment_delay_days, rate_type.</div>
          <div className="body" style={{ borderTop: "1px solid var(--line)" }}>
            <span className="b">Pool disclosure file (agency MBS)</span> <span className="muted">monthly factor / net coupon per CUSIP; CSV or pipe-delimited</span>{" "}
            <label className="btn">Choose file<input type="file" hidden onChange={(e) => { if (e.target.files?.[0]) uploadDisclosure(e.target.files[0]); e.target.value = ""; }} /></label>
          </div>
        </div>
        <div className="panel">
          <h2>Run screens</h2>
          <div className="body" style={{ display: "grid", gridTemplateColumns: "140px 1fr", gap: 6, alignItems: "center" }}>
            <span>As-of date</span><input className="f" type="date" value={form.as_of} onChange={(e) => setForm({ ...form, as_of: e.target.value })} />
            <span>Holdings batch</span><select className="f" value={form.holdings} onChange={(e) => setForm({ ...form, holdings: e.target.value })}><option value="">—</option>{opts("holdings")}</select>
            <span>Vendor files</span>
            <div>
              {batches.filter((b) => b.kind === "vendor_secondary").map((b) => (
                <label key={b.id} style={{ display: "block" }}>
                  <input type="checkbox" checked={vendorIds.includes(b.id)}
                    onChange={(e) => setVendorIds(e.target.checked ? [...vendorIds, b.id] : vendorIds.filter((x) => x !== b.id))} />{" "}
                  #{b.id} {b.vendor} · {b.filename}
                </label>
              ))}
              {!batches.some((b) => b.kind === "vendor_secondary") && <span className="muted">none uploaded</span>}
            </div>
            <span>Price history</span><select className="f" value={form.history} onChange={(e) => setForm({ ...form, history: e.target.value })}><option value="">none</option>{opts("price_history")}</select>
            <span>Cash ledger</span><select className="f" value={form.ledger} onChange={(e) => setForm({ ...form, ledger: e.target.value })}><option value="">none</option>{opts("ledger")}</select>
            <span>Peer z-score</span><input className="f" type="number" step="0.5" value={form.z} onChange={(e) => setForm({ ...form, z: e.target.value })} />
            <span />
            <button className="btn primary" disabled={!form.holdings || running} onClick={runScreens}>{running ? "Running…" : "Run screens"}</button>
          </div>
        </div>
      </div>
      <div className="cols">
        <div className="panel">
          <h2>Upload batches</h2>
          <table className="grid">
            <thead><tr><th>#</th><th>Kind</th><th>File</th><th className="n">Rows</th><th>By</th><th>At</th><th>SHA-256</th></tr></thead>
            <tbody>{batches.map((b) => (
              <tr key={b.id}><td className="mono">{b.id}</td><td>{b.kind}{b.vendor ? ` · ${b.vendor}` : ""}</td><td>{b.filename}</td><td className="n">{b.row_count}</td><td>{b.uploaded_by}</td><td className="mono nowrap">{ts(b.uploaded_at)}</td><td className="hash">{b.sha256.slice(0, 12)}…</td></tr>
            ))}</tbody>
          </table>
        </div>
        <div className="panel">
          <h2>Screen runs</h2>
          <table className="grid">
            <thead><tr><th>#</th><th>As of</th><th className="n">Flags</th><th>By</th><th>Finished</th></tr></thead>
            <tbody>{runs.map((r) => (
              <tr key={r.id} className="click" onClick={() => (window.location.hash = `#/flags/${r.id}`)}><td className="mono">{r.id}</td><td className="mono">{r.as_of}</td><td className="n">{r.flag_count}</td><td>{r.started_by}</td><td className="mono nowrap">{ts(r.finished_at)}</td></tr>
            ))}</tbody>
          </table>
        </div>
      </div>
    </>
  );
}

function UploadRow({ kind, label, hint, onFile }: { kind: string; label: string; hint: string; onFile: (f: File, vendor: string) => void }) {
  const [vendor, setVendor] = useState(kind === "holdings" ? "VendorA" : kind === "vendor_secondary" ? "VendorB" : "");
  return (
    <tr>
      <td><div className="b">{label}</div><div className="muted">{hint}</div></td>
      <td className="nowrap">
        {kind !== "price_history" && <input className="f" style={{ width: 90, marginRight: 6 }} value={vendor} onChange={(e) => setVendor(e.target.value)} title="vendor name" />}
        <label className="btn">Choose CSV<input type="file" accept=".csv,text/csv" hidden onChange={(e) => { if (e.target.files?.[0]) onFile(e.target.files[0], vendor); e.target.value = ""; }} /></label>
      </td>
    </tr>
  );
}
