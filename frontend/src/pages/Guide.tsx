import { useEffect, useState } from "react";
import { api } from "../api";
import { RULE_LABEL, usd } from "../format";
import type { FindingSummary, ScreenRunT } from "../types";

const SCREENS: { rule: string; title: string; plain: string; strength: string }[] = [
  { rule: "cash_reconciliation", title: "Cash vs booked income",
    plain: "Interest cash actually arrived, but the books recorded little or no income for the same months. Cash is a fact, so this is the strongest signal. It also shows the rate the cash implies.",
    strength: "Highest" },
  { rule: "null_vs_zero", title: "Blank became zero",
    plain: "One data source left a field (usually the coupon) blank, and another shows it as 0%. A blank means \"unknown\"; somewhere downstream it was turned into zero.",
    strength: "High" },
  { rule: "frequency_contradiction", title: "Pays interest but has no coupon",
    plain: "The record says the security pays interest (e.g. monthly) yet the coupon is 0 or blank. Both cannot be true.",
    strength: "High" },
  { rule: "rate_vs_disclosure", title: "Coupon vs published rate (MBS)",
    plain: "The coupon in the books differs from the rate in the pool's monthly disclosure file (e.g. a mistyped rate or a missed rate reset).",
    strength: "High" },
  { rule: "factor_mismatch", title: "Stale pool factor (MBS)",
    plain: "The books use a different share of principal outstanding than the pool disclosure. Income is then accrued on the wrong balance.",
    strength: "Medium" },
  { rule: "vendor_disagreement", title: "Sources disagree",
    plain: "The fund's records and the vendor feeds don't match on a term (coupon, accrual type, payment delay, price convention...).",
    strength: "Medium" },
  { rule: "yield_coupon_impossibility", title: "Yield doesn't fit the coupon (muni)",
    plain: "At this price, the stated coupon could not produce the reported yield. The coupon or the price convention is probably wrong.",
    strength: "Medium" },
  { rule: "zero_coupon_sanity", title: "Zero coupon priced near par (muni)",
    plain: "A true zero-coupon bond with years to go trades well below 100. One priced at or above par is likely carrying accrued interest in its price.",
    strength: "Medium" },
  { rule: "price_drift", title: "\"Clean\" price climbs like accrued interest (muni)",
    plain: "The price rises steadily month after month, faster than the stated terms explain - the pattern of interest building up inside the price.",
    strength: "Medium" },
  { rule: "peer_outlier", title: "Yield unlike its peers (muni)",
    plain: "The yield is far from similar bonds (same sector, rating, maturity). Could be a data error - or a genuine credit story.",
    strength: "Lower - review" },
];

const GLOSSARY: [string, string][] = [
  ["Book of record", "The fund accounting system's version of each security's terms. Vendor files are compared against it."],
  ["BLANK vs 0", "Blank = the source didn't say. 0 = the source said zero. The app never treats one as the other; BLANK is shown in an orange box."],
  ["Unbooked income", "Interest the security has earned that the books have not recorded as income. Positive = income understated."],
  ["Clean / dirty price", "Clean excludes accrued interest; dirty (full) includes it. Labelling a dirty price \"clean\" hides accrued interest inside the price."],
  ["Accrued interest", "Interest earned since the last payment but not yet received."],
  ["Deferred interest / CAB", "Muni bonds that pay no interest until maturity; it builds up (accretes) instead. The fund must still book it as income as it accrues."],
  ["Agency MBS pool", "A bundle of mortgages; investors get monthly interest plus principal as homeowners pay down or prepay."],
  ["Factor", "Share of the original principal still outstanding (0.85 = 85%). Interest is earned on original face x factor."],
  ["WAC-based coupon", "An MBS rate that changes monthly: the average rate on the underlying mortgages minus fees. Often a non-round number like 4.773%."],
  ["Payment delay", "Days between the start of an accrual month and when its interest is paid (e.g. 45 days = 15th of the next month)."],
  ["Citation (p. 6 / file:row)", "Where in the offering document or disclosure file a term came from. Click a page link to see the quoted text highlighted."],
  ["Severity x confidence", "Severity = how big the anomaly is. Confidence = how often that kind of signal is a real data defect. Lists are ordered by both."],
];

export default function Guide() {
  const [findings, setFindings] = useState<FindingSummary[] | null>(null);
  const [runs, setRuns] = useState<ScreenRunT[]>([]);

  useEffect(() => {
    api.get<FindingSummary[]>("/api/findings").then(setFindings).catch(() => setFindings([]));
    api.get<ScreenRunT[]>("/api/screen-runs").then(setRuns).catch(() => setRuns([]));
  }, []);

  const run = runs[0];
  const open = (findings ?? []).filter((f) => f.status === "open");
  const total = open.reduce((a, f) => a + f.income_impact_usd, 0);
  const empty = findings !== null && findings.length === 0 && runs.length === 0;

  return (
    <div className="guide">
      <div className="panel">
        <h2>Start here · what Terms Check tells you</h2>
        <div className="body">
          <p className="lead">
            Terms Check looks for bonds whose reference data misstates <b>how they pay interest</b>. When that happens,
            fund accounting books the wrong income - often none at all - and nothing errors out. The app finds those
            securities, reads the bond's own offering document to get the true terms, and tells you how much income is
            mis-stated, with page references you can check.
          </p>
          <div className="steps">
            <div><span className="num">1</span><b>Load data</b><br />Holdings and vendor files, optional cash ledger and MBS pool disclosures (<a href="#/data">Data &amp; runs</a>).</div>
            <div><span className="num">2</span><b>Screen</b><br />Deterministic checks flag securities whose data doesn't hang together (<a href="#/flags">Screen flags</a>).</div>
            <div><span className="num">3</span><b>Read the document</b><br />Upload the offering document for a flagged security; its terms are extracted with page citations.</div>
            <div><span className="num">4</span><b>Review</b><br />Each finding states the dollar impact; approve, reject or annotate it (<a href="#/queue">Review queue</a>).</div>
            <div><span className="num">5</span><b>Hand off</b><br />Export approved findings to CSV for operations. Nothing is written to accounting systems.</div>
          </div>
        </div>
      </div>

      <div className="panel">
        <h2>Your data right now</h2>
        <div className="body">
          {empty ? (
            <p>Nothing loaded yet. Start the app with demo data: in a terminal, run <code>python3 backend/scripts/demo_seed.py</code>, then refresh this page. Or upload your own files on <a href="#/data">Data &amp; runs</a>.</p>
          ) : (
            <>
              <p>
                {run ? <>The latest screen run (#{run.id}, as of {run.as_of}) raised <b>{run.flag_count} flags</b>. </> : null}
                {findings && findings.length > 0 ? (
                  <>Documents have been analysed for <b>{findings.length} securities</b>; the <b>{open.length} open findings</b> put{" "}
                    <b className="under">{usd(total)}</b> of income at issue. Biggest first:</>
                ) : <>No offering documents analysed yet - upload one for a flagged security on <a href="#/flags">Screen flags</a>.</>}
              </p>
              {findings && findings.length > 0 && (
                <table className="grid">
                  <thead><tr><th className="n">Income impact</th><th>Security</th><th>What it means</th><th /></tr></thead>
                  <tbody>
                    {findings.slice(0, 6).map((f) => (
                      <tr key={f.id}>
                        <td className={`n b ${f.income_impact_usd > 0.5 ? "under" : f.income_impact_usd < -0.5 ? "over" : ""}`}>{usd(f.income_impact_usd)}</td>
                        <td><span className="mono">{f.cusip}</span><br /><span className="muted">{f.description}</span></td>
                        <td className="wrap">{explain(f)}</td>
                        <td><a href={`#/findings/${f.id}`}>Open →</a></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </>
          )}
        </div>
      </div>

      <div className="cols">
        <div className="panel">
          <h2>How to read a finding</h2>
          <div className="body">
            <ol className="read">
              <li><b>The big red number</b> (top left) is the income the books are missing. Positive = income understated; in brackets = overstated.</li>
              <li><b>The headline</b> says why in one line, e.g. "book coupon 0.000% vs WAC-based net coupon 4.820% (confirmed by cash)".</li>
              <li><b>Book &amp; vendors vs offering document</b>: pink rows are where the books disagree with the document. Each document value cites a page (click it to see the quoted text highlighted) or a row in the pool disclosure file.</li>
              <li><b>Cash reconciliation</b> (when a cash ledger was loaded): every interest payment received, what was booked for it, and the rate the cash implies. If cash shows ~4.8% and the books show 0%, the books are wrong.</li>
              <li><b>Finding</b> (right side): the same story in sentences - what the data says, what the document says, the correct accounting, the dollar impact.</li>
              <li><b>Review</b>: approve if the document supports it; reject with a reason if not (e.g. "correct terms - real credit move"); annotate to leave a note. Every action is logged.</li>
            </ol>
          </div>
        </div>
        <div className="panel">
          <h2>The demo findings, in plain English</h2>
          <div className="body">
            <dl className="narr" style={{ margin: 0 }}>
              <dt>Muni: zero coupon labelled "clean", price 221 (≈ $4.8M)</dt>
              <dd>The bond actually earns 11% a year and pays it all at maturity. The vendor shows a 0% coupon, so the fund books no income; the interest sits inside the price and shows up as an unrealised gain instead of tax-exempt income.</dd>
              <dt>MBS: coupon 0% in the books, blank at FactSet (≈ $229K)</dt>
              <dd>A monthly-pay mortgage pool whose rate floats with its loans (~4.8%). A blank coupon became 0% downstream, so a year of interest cash arrived with no income booked. The cash itself proves the rate.</dd>
              <dt>MBS: coupon mistyped 3.5% vs 5.5% (≈ $95K)</dt>
              <dd>The books accrue at the wrong fixed rate; cash and the offering document both show 5.5%.</dd>
              <dt>Muni: convertible CAB carried as a zero ($0 now, ≈ $95K/yr)</dt>
              <dd>No income is misplaced today, but accounting accretes it at ~1.4% instead of 5.5%, so it under-books about $95K a year going forward.</dd>
            </dl>
          </div>
        </div>
      </div>

      <div className="panel">
        <h2>What each flag means</h2>
        <table className="grid">
          <thead><tr><th>Flag</th><th>Plain English</th><th>Signal strength</th></tr></thead>
          <tbody>
            {SCREENS.map((s) => (
              <tr key={s.rule}>
                <td className="nowrap"><span className="chip">{RULE_LABEL[s.rule] ?? s.rule}</span> <b>{s.title}</b></td>
                <td className="wrap">{s.plain}</td>
                <td className="nowrap">{s.strength}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="panel">
        <h2>Glossary</h2>
        <table className="grid">
          <tbody>
            {GLOSSARY.map(([t, d]) => (
              <tr key={t}><td className="nowrap b">{t}</td><td className="wrap">{d}</td></tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function explain(f: FindingSummary): string {
  const h = f.headline;
  if (f.income_impact_usd > 0.5) return `Income is understated: ${h.split(": ").slice(1).join(": ") || h}.`;
  if (f.income_impact_usd < -0.5) return `Income is overstated: ${h.split(": ").slice(1).join(": ") || h}.`;
  if (Math.abs(f.run_rate_gap_usd) > 0.5) return `Nothing misplaced today, but ${usd(Math.abs(f.run_rate_gap_usd))} a year will be ${f.run_rate_gap_usd > 0 ? "under" : "over"}-booked going forward.`;
  return "Terms check out - likely a genuine market move rather than a data defect. Review and reject with a note if so.";
}
