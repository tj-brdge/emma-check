# Terms Check

Finds fixed-income securities whose reference data misstates how they pay interest, reads the
offering document to establish the true terms, computes the correct accounting treatment, and
puts a cited, dollar-quantified finding in front of a reviewer. Asset classes are plugins; v1
ships **municipal bonds** and **agency MBS** (pass-throughs, WAC-based and ARM pools).

Two motivating patterns:
- **Muni:** a vendor sends a zero coupon and a "clean" price for a bond that accrues interest
  and pays it at maturity. The accrual sits in the price, no income is booked, and tax-exempt
  interest shows up as unrealized appreciation.
- **Agency MBS:** a monthly-pay pool with a collateral-based (WAC) net coupon arrives with the
  coupon **blank** in one vendor feed; downstream the blank became **0%**, so fund accounting
  books no income while interest cash arrives every month. Nothing errors out.

Nothing is written back to any accounting system. Approved findings export to CSV.

## Run it

```bash
docker compose up --build
```

Open http://localhost:18080 and enter a reviewer name (top right). Host ports are 18080 (UI) and
18000 (API) to avoid clashing with other local services; change them in `docker-compose.yml`. Extraction calls the
Anthropic API: set `ANTHROPIC_API_KEY` in your shell first. To demo without a key, replay
the recorded extractions for the two sample official statements:

```bash
TERMSCHECK_LLM_MODE=recorded docker compose up --build
```

Load the synthetic muni + agency MBS universe (book of record, three vendor files, price
history, cash ledger, pool disclosure) and analyse the sample offering documents through the API:

```bash
python3 backend/scripts/demo_seed.py      # standard library only, no installs
```

Configuration (environment, prefix `TERMSCHECK_`): `EXTRACTION_MODEL` (default
`claude-sonnet-5-5`), `LLM_MODE` (`anthropic` | `recorded`), `EXTRACTION_MAX_PAGES` (page
budget after prefiltering, default 60), `EXTRACTION_SERVER_FALLBACK` (server-side refusal
fallback, default on), `DATABASE_URL`, `MIGRATION_DATABASE_URL`, `STORAGE_DIR`.

### Local development

```bash
cd backend && uv venv --python 3.12 && uv pip install -e '.[dev]'
alembic upgrade head            # TERMSCHECK_DATABASE_URL -> a local PostgreSQL 16
uvicorn termscheck.api.app:app --reload
cd ../frontend && npm install && npm run dev   # http://localhost:5173, proxies /api
```

### Tests

```bash
cd backend && pytest                 # 205 tests; DB tests use TERMSCHECK_TEST_DATABASE_URL
pytest -m live                       # real extraction against the sample OS (needs ANTHROPIC_API_KEY)
cd ../frontend && npm run typecheck
```

## Workflow

1. **Data & runs**: upload the book of record (CSV), any number of vendor files, optional price
   history, cash ledger and pool disclosure; run the screens for an as-of date.
2. **Screen flags**: every flagged CUSIP with its asset class, rules and severities (ordered by
   severity x confidence). Upload the offering document (muni official statement, MBS offering
   circular supplement); terms are extracted, cited, verified, and a finding is built.
3. **Review queue**: findings sorted by income impact. The detail view shows vendor data
   beside document terms with page citations (click to see the highlighted excerpt on the
   page), the correct clean/dirty split, per-position impact, the accretion schedule and the
   screen flags. Approve, reject (comment required) or annotate.
4. **Export** approved findings to CSV (one row per position) for the operations team.
5. **Audit trail**: every step, who did it and when; verify the hash chain.

## Module layout

```
backend/termscheck/
  core/          Shared types: SecurityRecord (nullable terms + per-field state: value / blank /
                 absent, raw cell text, source row), LedgerEntry, PeriodObservation, CashPeriod,
                 Flag (severity x confidence), day counts, identifiers, display helpers,
                 generic FindingDraft, and the AssetClassPlugin protocol + registry.
  screens/       Shared deterministic screens (run on every security) + plugin-aware runner:
                 cash_reconciliation, null_vs_zero, frequency_contradiction, vendor_disagreement.
  plugins/
    muni/        bondmath (CAB / deferred / convertible CAB accretion, G-33), yield_coupon,
                 price_drift, peer_outlier, zero_coupon screens, official-statement extraction
                 spec, EMMA source stub, findings, synthetic munis.
    agency_mbs/  bondmath (factor, current face, delay, monthly accrual, paydowns, variable
                 rates), treatment, factor_mismatch and rate_vs_disclosure screens, offering
                 circular supplement extraction spec, pool disclosure parser, findings,
                 synthetic MBS.
  extraction/    Shared pipeline: DocumentSource interface + upload store, page text and
                 prefilter, LLM client (structured output, schema from the plugin), citation
                 verification, ExtractionSpec. No database access.
  ingest/        CSV parsing/validation (blanks recorded, never coerced) + writers.
  review/, audit/, services/, api/   as before; services is the only layer that touches
                 persistence, and it reaches plugins only through the registry.
  tools.py       JSON-in/JSON-out facades for MCP: extract_official_statement_terms,
                 compute_bond_treatment (muni), compute_mbs_treatment.
frontend/        React + TypeScript (Vite), no UI kit.
data/            synthetic CSVs + planted_defects.json, sample offering documents (fictional
                 issuers), recorded extraction responses for offline demo/tests.
```

**Adding an asset class** means adding `plugins/<name>/` with a class that has `key`, `label`,
`term_fields`, `math_version`, `primary_document_kind`, `screens`, `extraction` (an
`ExtractionSpec`: schema, prompt, field mapping), `terms_to_json` / `terms_from_json`,
`build_finding` and, for cash reconciliation, `cash_period`; then importing it in
`plugins/__init__.py`. `tests/test_architecture.py` fails if a shared layer imports a plugin or
plugins import each other.

## Data model (PostgreSQL, Alembic migrations 0001-0005)

| Table | Purpose | Mutability |
|---|---|---|
| `upload_batch` | every accepted file: kind, vendor, filename, sha256, rows, user | write-once |
| `holding` | position: portfolio, CUSIP, par, acquisition date | write-once |
| `vendor_terms` | one vendor's reference data per CUSIP per batch | write-once |
| `price_history` | optional price series | write-once |
| `screen_run` | as-of, input batches, full config, user, timings | write-once |
| `screen_flag` | rule, severity, message, inputs, computed values | write-once |
| `document`, `document_page` | official statement (content-addressed) and its page text | write-once |
| `extraction` | model requested/served, prompt version, cited fields, citation checks, mapped terms, problems | write-once |
| `finding` | per-CUSIP impact, headline, narrative, comparison | only `status` may change |
| `computation` | per-position bond-math inputs/outputs + bondmath version | write-once |
| `review_action` | approve / reject / annotate / reopen, comment, user | write-once |
| `ledger_entry` | cash receipts: CUSIP, portfolio, date, cash, interest/principal, optional booked income | write-once |
| `disclosure_observation` | monthly factor / net coupon per CUSIP from a pool disclosure, with file:row locator | write-once |
| `audit_event` | hash-chained log of every step | write-once |

`vendor_terms` term columns are nullable; `field_states` records whether each was a value, a
blank cell or an absent column, and `raw` keeps the cell text. Migrations 0006-0008 add asset
class, the MBS columns, multi-vendor and ledger references on screen runs, flag confidence and
the two new tables.

Write-once is enforced twice: triggers reject UPDATE/DELETE/TRUNCATE (and any finding change
other than `status`), and the API connects as `termscheck_app`, which has only SELECT and
INSERT plus UPDATE on `finding.status`. Migrations run as the owner role.

## CSV formats

Coupons and yields in **percent**, prices per 100 par, dates `YYYY-MM-DD` or `MM/DD/YYYY`,
headers case-insensitive with common aliases (`market_price`, `vendor_coupon`, ...).

- Holdings (required): `cusip, description, par, price, price_convention (clean|dirty),
  coupon, accrual_type, maturity_date, issue_date, rating, sector, state`.
  Optional: `portfolio, vendor_yield, payment_frequency, day_count, acquisition_date`.
- Second vendor: same columns, `par` optional.
- Optional MBS / multi-asset columns on holdings and vendor files: `asset_class`
  (`muni` | `agency_mbs`), `product_type` (pass_through, arm, po, io), `factor`, `factor_date`,
  `payment_delay_days`, `rate_type` (fixed, wac, arm). For MBS, `par` is **original face**.
- Price history: `cusip, price_date, price[, price_convention]`.
- Cash / income ledger: `cusip, entry_date, cash, type (interest|principal)[, portfolio,
  booked_income]`. When `booked_income` is supplied it is used; otherwise booked income is
  derived from the book-of-record terms.
- Pool disclosure (data document, uploaded on the Data page): `cusip, factor_month, factor[,
  net_coupon, wac]`, comma or pipe delimited; column names are mapped through
  `plugins/agency_mbs/disclosure.py:DEFAULT_MAPPING`, so a real layout needs a mapping entry,
  not code.

**Blank is never zero.** Empty cells and null tokens (`NA`, `N/A`, `--`, `null`, ...) are stored
as NULL with state `blank` and the raw text; a column missing from a file is `absent`. Zero is
only ever a value someone sent. A static test fails the build on `x or 0`-style coercion.

A file with any invalid row (including a bad CUSIP check digit or duplicate position) is
rejected whole; the rejection is still audited.

## How the pieces decide

**Shared screens** (every asset class; thresholds in `screens/config.py`):

- *Cash reconciliation* (confidence 0.95, the highest): each interest receipt is mapped by the
  plugin to the accrual period it pays (MBS: payment date minus the stated delay; muni: coupon
  period) and the face outstanding then. Booked income for those periods comes from the ledger
  or the book terms - a BLANK book coupon books nothing, said explicitly. Flags no income
  booked, or booked income >10% below cash with the cash-implied rate >25 bp from the book;
  over-accrual is flagged separately. For variable rates only the current rate regime (since the
  latest month-to-month jump, e.g. an ARM reset) is reconciled against today's book.
- *Null vs zero* (0.9): a term blank in one source and 0 in another. Blank coupon or factor on
  its own is reported at low severity. Only fields that apply to the asset class are checked.
- *Frequency contradiction* (0.85): payment frequency > 0 with a zero or blank coupon; low
  severity when the record is explicitly labelled non-paying (zero / CAB / deferred / PO).
- *Vendor disagreement* (0.8): any term that differs across the book and every vendor file.

Flags are ordered by severity x confidence.

**Agency MBS screens:** *factor mismatch* (book factor vs the disclosed factor for the month) and
*rate vs disclosure* (book coupon vs the disclosed net coupon).

**Muni screens:**

- *Yield/coupon impossibility*: solve the yield implied by the price **under the vendor's own
  terms**; flag if it is below a plausible floor or more than 150 bp from the vendor's
  reported yield.
- *Price drift*: convert each "clean" price to its vendor-terms implied yield, remove the
  maturity band's median yield move (market factor), regress on time; a steady fall in
  implied yield means the price grows faster than the vendor's terms explain (embedded
  accrual). Requires R² ≥ 0.90, unexplained growth ≥ 2.5%/yr and ≥ 30 bp/yr.
- *Peer outlier*: robust additive peer model (median polish over maturity band, rating
  bucket and sector); robust z of the residual (MAD floored at 15 bp), default |z| > 3.
- *Vendor disagreement*: coupon, accrual type, payment frequency, price convention, day
  count, maturity, and price beyond 2 points.
- *Zero-coupon sanity*: zero coupon priced ≥ 95 with ≥ 3 years to maturity.

**Extraction**: page-tagged text (whole document up to the page budget, otherwise cover pages,
pages naming the CUSIP and pages ranked by interest-terms keywords) goes to the model with a
JSON schema in which every field carries `page` and a verbatim `excerpt`. Vendor data is
never sent (no anchoring). Each excerpt is then checked deterministically against the cited
page (normalised exact match, fuzzy ≥ 0.90, or found on a different page); unverified
citations, values not visible in their excerpt, or missing required terms mark the extraction
`needs_review`. The API's native citations feature cannot be combined with structured output,
which is why citations are part of the schema and verified locally.

**Agency MBS bond math** (`plugins/agency_mbs/bondmath.py`): accrual month = calendar month on
30/360; interest for month M = original face x factor[M] x rate[M] / 12; principal =
original face x (factor[M] - factor[M+1]); both paid on M's payment date, where a stated delay D
lands on 30/360 day D counted from the 1st (45 -> 15th of next month, 55 -> 25th, 75 -> 15th of
M+2; no holiday calendar). WAC/ARM rates come from the monthly disclosure; a missing month
carries the last value forward and is reported. Receivable at the as-of date = unpaid completed
months + current month through the as-of date. The MBS headline impact is cumulative unbooked
interest over the window (acquisition date, else the first ledger receipt, through the as-of
date), shown with receivable, run-rate and the month-by-month cash-vs-expected schedule.

**Muni treatment**: the full (dirty) value of the position does not depend on labels: vendor price
plus whatever accrued interest the vendor's own terms imply. The correct split uses accrued
interest from the document: `correct clean = full value - true accrued`.
Headline impact per position = `(true accrued - accrued booked from vendor terms) x par / 100`,
i.e. income carried as principal / unrealized appreciation (positive = income understated).
Also reported: the forward 12-month income run-rate gap (document accretion vs what accounting
books from vendor terms; for a vendor zero coupon, constant-yield accretion at the
vendor-implied yield) and, when an acquisition date is supplied, unbooked income since
acquisition. CABs use the original-issue accretion schedule. Default day count 30/360; the
document's stated day count wins.

## Synthetic dataset and tests

`plugins/agency_mbs/synthetic.py` generates 50 agency pools (fixed, WAC-based with non-round
monthly net coupons from generated collateral, annually resetting ARMs; 45/50/55-day programs),
two vendor files, 12 months of interest and principal cash with business-day shifts and a
monthly pool disclosure. Planted: **M01** - WAC-based coupon, book 0%, FactSet blank, monthly
interest cash (the 31350AEB0 pattern; no real terms used), M02 mistyped coupon, M03 stale
factor, M04 wrong delay, M05 vendor blank vs zero, M06 missed ARM reset, M07 blank book coupon;
traps that must stay quiet: a principal-only strip and cents-level servicer rounding.
`holdings_combined.csv` is one book of record covering both asset classes.

`plugins/muni/synthetic.py` generates 200 holdings (seeded) with a shared market rate factor and 12 planted
defects covering every screen, including D01: zero vendor coupon, "clean" price, 11% deferred
interest compounded semiannually and paid at maturity (~11% yield). `scripts/make_sample_os.py`
builds official statements for D01 and D12 (a convertible CAB) under fictional issuers.
Nothing about any real CUSIP is hard-coded; terms come only from the document.

Test coverage: bond math against hand-calculated values; every planted defect caught across
seeds with a false-positive ceiling; CSV round-trips; extraction (every field cited and
verified, fabricated / wrong-page / uncited excerpts caught, terms equal ground truth,
SDK-level request shape via a mocked transport); findings; review state machine and export;
audit chain, tamper and deletion detection, database-level immutability.

## Limitations (prototype)

- Identity is an `X-User` header chosen in the UI; there is no authentication.
- Extraction runs synchronously in the request (can take tens of seconds per document).
- Yields use compound discounting throughout (G-33 uses simple interest inside the final
  coupon period) and are to maturity, not to call.
- Treatment uses the original-issue accretion schedule; purchase-yield accretion, market
  discount and premium amortisation for secondary-market purchases are out of scope.
- Official statements are read as text (pypdf); scanned PDFs need OCR first.
- EMMA retrieval is an interface only (`plugins/muni/sources/emma.py`); MBS documents and pool
  disclosures are user uploads.
- Pool disclosure layouts: no real Freddie Mac file was available; real layouts need entries
  in the column mapping. Factor/rate history before the disclosure window is not reconstructed.
- MBS: 30/360 monthly accrual only; no business-day calendar for payment dates; CMO tranches and
  IO/PO math are out of scope (PO/IO are recognised by product type so they are not mis-flagged).
- Cash reconciliation compares against today's book record; for variable-rate securities only
  the current rate regime is reconciled because historical book rates are not known.
