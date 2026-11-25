# Terms Check

Finds municipal bonds whose vendor reference data misstates how they pay interest, reads the
bond's official statement to establish the true terms, computes the correct accounting
treatment, and puts a cited, dollar-quantified finding in front of a reviewer.

The motivating pattern: a vendor sends a coupon of zero and labels its price "clean" for a
bond that actually accrues interest and pays it all at maturity. The accrued interest is
embedded in the price, fund accounting books no income, the value lands in unrealized
appreciation, and tax-exempt interest looks like capital gain. Nothing errors out.

Nothing is written back to any accounting system. Approved findings export to CSV.

## Run it

```bash
docker compose up --build
```

Open http://localhost:8080 and enter a reviewer name (top right). Extraction calls the
Anthropic API: set `ANTHROPIC_API_KEY` in your shell first. To demo without a key, replay
the recorded extractions for the two sample official statements:

```bash
TERMSCHECK_LLM_MODE=recorded docker compose up --build
```

Load the synthetic dataset and analyse the sample official statements through the API:

```bash
pip install httpx && python backend/scripts/demo_seed.py --api http://localhost:8080
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
cd backend && pytest                 # 117 tests; DB tests use TERMSCHECK_TEST_DATABASE_URL
pytest -m live                       # real extraction against the sample OS (needs ANTHROPIC_API_KEY)
cd ../frontend && npm run typecheck
```

## Workflow

1. **Data & runs**: upload holdings + primary vendor terms (CSV), optionally a second vendor
   file and price history; run the screens for an as-of date.
2. **Screen flags**: every flagged CUSIP with its rules and severities. Upload the official
   statement PDF for a CUSIP; terms are extracted, cited, verified, and a finding is built.
3. **Review queue**: findings sorted by income impact. The detail view shows vendor data
   beside document terms with page citations (click to see the highlighted excerpt on the
   page), the correct clean/dirty split, per-position impact, the accretion schedule and the
   screen flags. Approve, reject (comment required) or annotate.
4. **Export** approved findings to CSV (one row per position) for the operations team.
5. **Audit trail**: every step, who did it and when; verify the hash chain.

## Module layout

```
backend/termscheck/
  bondmath/      PURE. Day counts (MSRB 30/360, ACT/*), schedules, CAB / deferred-interest /
                 convertible-CAB accretion (G-33 linear interpolation), accrued interest,
                 cash flows, price<->yield, treatment (correct split, unbooked income).
  screens/       PURE. Five deterministic screens + runner; no LLM. Typed inputs/outputs.
  ingest/        CSV parsing/validation (whole-file rejection with row-level errors) + writers.
  extraction/    DocumentSource interface (upload; EMMA stub), page text + prefilter, prompt,
                 structured-output LLM client, deterministic citation verification, mapping to
                 bond-math terms. No database access.
  findings/      PURE. Finding narrative (templates over computed numbers, no LLM) and the
                 vendor-vs-document comparison.
  review/        PURE. Review state machine, CSV export format.
  audit/         Hash-chained append-only event log and chain verification.
  services/      The only layer that combines the modules above with persistence and audit.
  api/           FastAPI routers (thin).
  tools.py       JSON-in/JSON-out facades over extraction and bond math, ready to register
                 as MCP tools: extract_official_statement_terms, compute_bond_treatment.
  synthetic.py   Seeded synthetic dataset with planted defects.
frontend/        React + TypeScript (Vite), no UI kit.
data/            synthetic CSVs + planted_defects.json, sample official statements (fictional
                 issuers), recorded extraction responses for offline demo/tests.
```

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
| `audit_event` | hash-chained log of every step | write-once |

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
- Price history: `cusip, price_date, price[, price_convention]`.

A file with any invalid row (including a bad CUSIP check digit or duplicate position) is
rejected whole; the rejection is still audited.

## How the pieces decide

**Screens** (all thresholds in `screens/config.py`, stored with each run):

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

**Treatment**: the full (dirty) value of the position does not depend on labels: vendor price
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

`synthetic.py` generates 200 holdings (seeded) with a shared market rate factor and 12 planted
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
- EMMA retrieval is an interface only (`extraction/sources/emma.py`).
