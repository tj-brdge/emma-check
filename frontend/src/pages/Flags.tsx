import { Fragment, useEffect, useState } from "react";
import { api } from "../api";
import { RULE_LABEL, par, pct, usd } from "../format";
import type { FlaggedCusip, ScreenRunT } from "../types";
import { AssetChip, Val } from "../components";

interface PipelineResult {
  extraction: { id: number; status: string; problems: string[] | null; error: string | null };
  finding: { id: number } | null;
  error: string | null;
}

export default function Flags({ runId }: { runId?: number }) {
  const [runs, setRuns] = useState<ScreenRunT[]>([]);
  const [run, setRun] = useState<number | undefined>(runId);
  const [data, setData] = useState<{ run: { id: number; as_of: string; flag_count: number }; cusips: FlaggedCusip[] } | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState<{ cusip: string; text: string; bad: boolean } | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api.get<ScreenRunT[]>("/api/screen-runs").then((r) => {
      setRuns(r);
      if (run === undefined && r.length) setRun(r[0].id);
    }).catch((e) => setErr(e.message));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const load = (id: number) => api.get<typeof data>(`/api/screen-runs/${id}/cusips`).then(setData).catch((e) => setErr(e.message));
  useEffect(() => {
    if (run !== undefined) load(run);
  }, [run]);

  const analyse = async (c: FlaggedCusip, file: File) => {
    if (run === undefined) return;
    setBusy(c.cusip);
    setMsg(null);
    const fd = new FormData();
    fd.append("file", file);
    try {
      const r = await api.post<PipelineResult>(`/api/screen-runs/${run}/cusips/${c.cusip}/official-statement`, fd);
      if (r.finding) window.location.hash = `#/findings/${r.finding.id}`;
      else setMsg({ cusip: c.cusip, text: `Extraction ${r.extraction.status}: ${r.error ?? (r.extraction.problems ?? []).join("; ")}`, bad: true });
      await load(run);
    } catch (e) {
      setMsg({ cusip: c.cusip, text: (e as Error).message, bad: true });
    } finally {
      setBusy(null);
    }
  };

  const total = data?.cusips.reduce((a, c) => a + c.par, 0) ?? 0;
  return (
    <>
      <div className="kpis">
        <div className="kpi hero"><div className="v">{data?.cusips.length ?? "—"}</div><div className="l">Flagged CUSIPs · {par(total)} par</div></div>
        <div className="kpi"><div className="v">{data?.run.flag_count ?? "—"}</div><div className="l">Flags</div></div>
        <div className="kpi"><div className="v">{data?.cusips.filter((c) => c.finding_id).length ?? "—"}</div><div className="l">With findings</div></div>
        <div className="kpi"><div className="v">{data?.cusips.filter((c) => !c.document_id).length ?? "—"}</div><div className="l">Awaiting official statement</div></div>
      </div>
      <div className="bar">
        <h1>Screen flags</h1>
        <select className="f" value={run ?? ""} onChange={(e) => setRun(Number(e.target.value))}>
          {runs.map((r) => <option key={r.id} value={r.id}>Run #{r.id} · as of {r.as_of} · {r.flag_count} flags · {r.started_by}</option>)}
        </select>
        <span className="muted">Upload the offering document (muni official statement, MBS offering circular supplement) for a flagged CUSIP to extract terms and build its finding.</span>
      </div>
      {err && <div className="err">{err}</div>}
      {!runs.length && <div className="note">No screen runs yet. Upload holdings and run the screens on the Data &amp; runs tab.</div>}
      <div className="panel">
        <table className="grid">
          <thead>
            <tr>
              <th className="n">Sev</th><th>Class</th><th>CUSIP</th><th>Description</th><th className="n">Par</th><th className="n">Price</th>
              <th>Conv</th><th className="n">Cpn</th><th>Accrual</th><th className="n">Vnd yld</th><th>Rating</th><th>Screens</th>
              <th>Official statement / finding</th>
            </tr>
          </thead>
          <tbody>
            {data?.cusips.map((c) => (
              <Fragment key={c.cusip}>
                <tr className="click" onClick={() => setOpen(open === c.cusip ? null : c.cusip)}>
                  <td className="n b">{c.max_severity}</td>
                  <td><AssetChip c={c.asset_class} /></td>
                  <td className="mono">{c.cusip}</td>
                  <td>{c.description}</td>
                  <td className="n">{par(c.par)}</td>
                  <td className="n">{c.price.toFixed(3)}</td>
                  <td>{c.price_convention ?? <span className="blank">BLANK</span>}</td>
                  <td className="n">{c.coupon === null ? <span className="blank">BLANK</span> : (c.coupon * 100).toFixed(3)}</td>
                  <td>{c.accrual_type ?? <span className="blank">BLANK</span>}</td>
                  <td className="n">{pct(c.vendor_yield)}</td>
                  <td><Val v={c.rating} /></td>
                  <td className="nowrap">
                    {c.flags.map((f) => <span key={f.rule} className={`chip ${f.severity >= 70 ? "sev-hi" : ""}`} title={f.message}>{RULE_LABEL[f.rule] ?? f.rule} {f.severity}</span>)}
                  </td>
                  <td className="nowrap" onClick={(e) => e.stopPropagation()}>
                    {c.finding_id ? (
                      <a href={`#/findings/${c.finding_id}`}>
                        Finding #{c.finding_id} · <b>{usd(c.income_impact_usd)}</b> · {c.finding_status}
                      </a>
                    ) : busy === c.cusip ? (
                      <span className="muted">Extracting terms…</span>
                    ) : (
                      <label className="btn">
                        {c.extraction_status === "failed" ? "Retry: upload document" : c.asset_class === "agency_mbs" ? "Upload OC supplement (PDF)" : "Upload OS (PDF)"}
                        <input type="file" accept="application/pdf" hidden onChange={(e) => e.target.files?.[0] && analyse(c, e.target.files[0])} />
                      </label>
                    )}
                  </td>
                </tr>
                {msg?.cusip === c.cusip && (
                  <tr key={c.cusip + "-msg"}><td colSpan={13}><div className={msg.bad ? "err" : "note"}>{msg.text}</div></td></tr>
                )}
                {open === c.cusip && (
                  <tr key={c.cusip + "-d"}>
                    <td />
                    <td colSpan={12}>
                      {c.flags.map((f) => (
                        <div key={f.rule} style={{ marginBottom: 3 }}>
                          <span className="chip">{RULE_LABEL[f.rule] ?? f.rule} {f.severity}</span> {f.message}
                        </div>
                      ))}
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
