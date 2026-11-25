import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { RULE_LABEL, num, par, pct, ts, usd } from "../format";
import type { Extraction, FindingDetail, Flag, ReviewActionT } from "../types";
import PageViewer from "./PageViewer";

export default function FindingDetailPage({ id }: { id: number }) {
  const [f, setF] = useState<FindingDetail | null>(null);
  const [ex, setEx] = useState<Extraction | null>(null);
  const [flags, setFlags] = useState<Flag[]>([]);
  const [hist, setHist] = useState<ReviewActionT[]>([]);
  const [comment, setComment] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [view, setView] = useState<{ page: number; excerpt: string | null } | null>(null);
  const [showSched, setShowSched] = useState(false);

  const load = useCallback(async () => {
    try {
      const fd = await api.get<FindingDetail>(`/api/findings/${id}`);
      setF(fd);
      const [e, fl, h] = await Promise.all([
        api.get<Extraction>(`/api/extractions/${fd.extraction_id}`),
        api.get<Flag[]>(`/api/cusips/${fd.cusip}/flags?run_id=${fd.screen_run_id}`),
        api.get<ReviewActionT[]>(`/api/findings/${id}/actions`),
      ]);
      setEx(e);
      setFlags(fl);
      setHist(h);
    } catch (e) {
      setErr((e as Error).message);
    }
  }, [id]);
  useEffect(() => {
    load();
  }, [load]);

  const act = async (action: string) => {
    setErr(null);
    try {
      await api.post(`/api/findings/${id}/actions`, { action, comment: comment || null });
      setComment("");
      await load();
    } catch (e) {
      setErr((e as Error).message);
    }
  };

  if (!f) return <div className="muted">{err ?? "Loading…"}</div>;
  const m = f.narrative.per_100;
  const totalPar = f.positions.reduce((a, p) => a + p.par, 0);
  const cite = (page: number | null, excerpt: string | null, status?: string | null) =>
    page ? (
      <a href="#" onClick={(e) => { e.preventDefault(); setView({ page, excerpt }); }} title={excerpt ?? ""}>
        p.{page}{status && status !== "verified" ? ` (${status})` : ""}
      </a>
    ) : <span className="muted">—</span>;

  return (
    <>
      <div className="bar">
        <a href="#/queue">← Queue</a>
        <span className="mono b">{f.cusip}</span>
        <span>{f.description}</span>
        <span className={`badge ${f.status}`}>{f.status}</span>
        <span className="spacer" />
        <span className="muted">as of {f.as_of} · screen run #{f.screen_run_id} · extraction #{f.extraction_id}</span>
      </div>

      <div className="kpis">
        <div className="kpi hero">
          <div className={`v ${f.income_impact_usd > 0.5 ? "under" : f.income_impact_usd < -0.5 ? "over" : ""}`}>{usd(f.income_impact_usd)}</div>
          <div className="l">{f.income_impact_usd >= 0 ? "Unbooked income (understated)" : "Income overstated"}</div>
        </div>
        <div className="kpi"><div className="v">{usd(f.run_rate_gap_usd)}</div><div className="l">12m run-rate gap</div></div>
        <div className="kpi"><div className="v">{num(m.unbooked_per_100)}</div><div className="l">per 100 par</div></div>
        <div className="kpi"><div className="v">{par(totalPar)}</div><div className="l">par held · {f.positions.length} position(s)</div></div>
        <div className="kpi" style={{ flex: 1 }}><div className="wrap b" style={{ fontSize: 13 }}>{f.headline}</div><div className="l">finding</div></div>
      </div>

      {err && <div className="err">{err}</div>}
      {f.narrative.extraction_status !== "ok" && (
        <div className="note">
          Extraction status <b>{f.narrative.extraction_status}</b>: verify the cited terms before approving.
          <ul style={{ margin: "4px 0 0 16px", padding: 0 }}>{f.narrative.extraction_problems.map((p) => <li key={p}>{p}</li>)}</ul>
        </div>
      )}

      <div className="cols">
        <div>
          <div className="panel">
            <h2>Vendor vs official statement</h2>
            <table className="grid">
              <thead><tr><th>Field</th><th>Vendor</th><th>Document</th><th>Source</th><th>Excerpt</th></tr></thead>
              <tbody>
                {f.comparison.map((r) => (
                  <tr key={r.field} className={r.match ? "" : "mismatch"}>
                    <td className="nowrap b">{r.field}</td>
                    <td className="mono nowrap">{r.vendor}</td>
                    <td className="mono nowrap">{r.document}</td>
                    <td className="nowrap">{cite(r.page, r.excerpt, r.citation_status)}</td>
                    <td className="excerpt wrap">{r.excerpt ? `“${r.excerpt}”` : ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="panel">
            <h2>Correct split of the vendor price (per 100 par)</h2>
            <div className="metrics">
              <div><div className="l">Vendor price (full value)</div><div className="v">{num(m.full_value)}</div></div>
              <div><div className="l">Correct clean</div><div className="v">{num(m.correct_clean)}</div></div>
              <div><div className="l">Accrued interest (document)</div><div className="v under">{num(m.true_accrued)}</div></div>
              <div><div className="l">Accrued booked (vendor)</div><div className="v">{num(m.vendor_accrued)}</div></div>
              <div><div className="l">Accreted value</div><div className="v">{num(m.accreted_value)}</div></div>
              <div><div className="l">Yield · document terms</div><div className="v">{pct(m.yield_document_terms)}</div></div>
              <div><div className="l">Yield · vendor terms</div><div className="v">{pct(m.yield_vendor_terms)}</div></div>
              <div><div className="l">12m income doc / vendor</div><div className="v">{num(m.income_next_12m_document, 2)} / {num(m.income_next_12m_vendor, 2)}</div></div>
            </div>
          </div>

          <div className="panel">
            <h2>Positions</h2>
            <table className="grid">
              <thead><tr><th className="n">Unbooked income</th><th className="n">Par</th><th className="n">12m run-rate</th><th className="n">Since acquisition</th><th>Holding</th><th>Computation</th></tr></thead>
              <tbody>
                {f.positions.map((p) => (
                  <tr key={p.computation_id}>
                    <td className="n b">{usd(p.unbooked_income_usd)}</td>
                    <td className="n">{p.par.toLocaleString()}</td>
                    <td className="n">{usd(p.run_rate_gap_usd)}</td>
                    <td className="n">{usd(p.unbooked_window_usd)}</td>
                    <td className="mono">#{p.holding_id}</td>
                    <td className="mono">#{p.computation_id}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="panel">
            <h2>Screen flags</h2>
            <table className="grid">
              <thead><tr><th className="n">Sev</th><th>Rule</th><th>Detail</th></tr></thead>
              <tbody>
                {flags.map((x, i) => (
                  <tr key={i}><td className="n b">{x.severity}</td><td><span className="chip">{RULE_LABEL[x.rule] ?? x.rule}</span></td><td className="wrap">{x.message}</td></tr>
                ))}
              </tbody>
            </table>
          </div>

          {f.narrative.schedule.length > 0 && (
            <div className="panel">
              <h2>
                Accreted value schedule (per 100)
                <span className="spacer" />
                <button className="btn" onClick={() => setShowSched(!showSched)}>{showSched ? "Hide" : `Show ${f.narrative.schedule.length} dates`}</button>
              </h2>
              {showSched && (
                <table className="grid">
                  <thead><tr><th>Date</th><th className="n">Accreted value</th></tr></thead>
                  <tbody>
                    {f.narrative.schedule.map((p) => (
                      <tr key={p.date} className={p.date === f.as_of ? "mismatch" : ""}><td className="mono">{p.date}</td><td className="n">{num(p.value)}</td></tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          )}
        </div>

        <div>
          <div className="panel">
            <h2>Review</h2>
            <div className="body">
              <textarea className="f" placeholder="Comment (required to reject or annotate)" value={comment} onChange={(e) => setComment(e.target.value)} />
              <div className="bar" style={{ marginTop: 6, marginBottom: 0 }}>
                <button className="btn approve" disabled={f.status !== "open"} onClick={() => act("approve")}>Approve</button>
                <button className="btn reject" disabled={f.status !== "open" || !comment.trim()} onClick={() => act("reject")}>Reject</button>
                <button className="btn" disabled={!comment.trim()} onClick={() => act("annotate")}>Annotate</button>
                <button className="btn" disabled={f.status === "open"} onClick={() => act("reopen")}>Reopen</button>
                <span className="spacer" />
                <span className="muted">Nothing is written to accounting systems.</span>
              </div>
            </div>
            <table className="grid">
              <thead><tr><th>When</th><th>Who</th><th>Action</th><th>Comment</th></tr></thead>
              <tbody>
                {hist.length === 0 && <tr><td colSpan={4} className="muted">No reviewer actions yet.</td></tr>}
                {hist.map((h) => (
                  <tr key={h.id}>
                    <td className="mono nowrap">{ts(h.at)}</td><td>{h.actor}</td>
                    <td className="nowrap">{h.action}{h.from_status !== h.to_status ? ` → ${h.to_status}` : ""}</td>
                    <td className="wrap">{h.comment}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="panel">
            <h2>Finding</h2>
            <dl className="narr body" style={{ margin: 0 }}>
              <dt>What the vendor data says</dt><dd>{f.narrative.vendor_says}</dd>
              <dt>What the official statement says</dt><dd>{f.narrative.document_says}</dd>
              <dt>Correct accounting treatment</dt><dd>{f.narrative.correct_treatment}</dd>
              <dt>Income impact</dt><dd className="b">{f.narrative.impact}</dd>
              {f.narrative.notes.length > 0 && (<><dt>Notes</dt><dd>{f.narrative.notes.join(" ")}</dd></>)}
            </dl>
          </div>

          {ex && (
            <div className="panel">
              <h2>
                Extraction #{ex.id} <span className={`badge ${ex.status}`}>{ex.status}</span>
                <span className="spacer" />
                <a href={`/api/documents/${ex.document_id}/file`} target="_blank" rel="noreferrer">Open PDF</a>
              </h2>
              <div className="body muted">
                model {ex.model_served ?? ex.model_requested} · prompt {ex.prompt_version} · pages sent{" "}
                {ex.page_selection ? `${ex.page_selection.pages.length}/${ex.page_selection.total_pages}` : "—"} · by {ex.created_by} {ts(ex.created_at)}
              </div>
              <table className="grid">
                <thead><tr><th>Field</th><th>Citation check</th><th>Page</th><th className="n">Match</th></tr></thead>
                <tbody>
                  {(ex.citation_checks ?? []).map((c) => {
                    const m2 = /^(\w+)\[(\d+)\]$/.exec(c.field);
                    const terms = (ex.terms ?? {}) as Record<string, unknown>;
                    const t = (m2 ? (terms[m2[1]] as unknown[])[Number(m2[2])] : terms[c.field]) as { excerpt?: string } | undefined;
                    return (
                      <tr key={c.field}>
                        <td className="mono">{c.field}</td>
                        <td>
                          <span className={`badge ${c.status}`}>{c.status}</span>
                          {c.found_on_page ? <span className="muted"> found p.{c.found_on_page}</span> : null}
                          {c.value_in_excerpt === false ? <span className="under"> value not in excerpt</span> : null}
                        </td>
                        <td>{cite(c.page, t?.excerpt ?? null)}</td>
                        <td className="n">{c.status === "absent" ? "" : c.score.toFixed(2)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {view && ex && <PageViewer documentId={ex.document_id} page={view.page} excerpt={view.excerpt} onClose={() => setView(null)} />}
    </>
  );
}
