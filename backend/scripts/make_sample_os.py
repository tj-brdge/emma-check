#!/usr/bin/env python3
"""Build synthetic official statements (fictional issuers) for planted defects D01 and D12.

These PDFs exist to exercise the extraction pipeline: realistic structure (cover, maturity
schedule with CUSIPs, description of the bonds, redemption, filler sections, accreted value
table) with the operative terms stated once, on specific pages, in ordinary OS language.
"""
from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table

from termscheck.plugins.muni.bondmath import accretion_schedule
from termscheck.plugins.muni.synthetic import SEED, generate

ss = getSampleStyleSheet()
H = ParagraphStyle("h", parent=ss["Heading2"], fontName="Times-Bold", fontSize=12, spaceAfter=6)
B = ParagraphStyle("b", parent=ss["BodyText"], fontName="Times-Roman", fontSize=10, leading=13,
                   spaceAfter=6, alignment=4)
C = ParagraphStyle("c", parent=B, alignment=1)

FILLER = (
    "The information set forth herein has been obtained from the District and other sources "
    "believed to be reliable, but is not guaranteed as to accuracy or completeness. The "
    "information and expressions of opinion herein are subject to change without notice, and "
    "neither the delivery of this Official Statement nor any sale made hereunder shall create "
    "any implication that there has been no change in the affairs of the issuer since the date "
    "hereof. Prospective investors should read this Official Statement in its entirety. "
)


def filler(title: str, n: int = 6):
    return [Paragraph(title, H)] + [Paragraph(FILLER, B) for _ in range(n)] + [PageBreak()]


def build_d01(path: Path, cusip: str, other_cusips: list[str]):
    """Deferred interest bonds, 11% compounded semiannually, paid at maturity 2034."""
    from termscheck.plugins.muni.bondmath import InterestTerms, InterestType
    t = InterestTerms(InterestType.DEFERRED_INTEREST, 0.11, date(2019, 7, 1), date(2034, 7, 1))
    s = []
    s += [Paragraph("NEW ISSUE - BOOK-ENTRY ONLY &nbsp;&nbsp;&nbsp; NOT RATED", C), Spacer(1, 12),
          Paragraph("$48,215,000<br/>CORAL BEND COMMUNITY DEVELOPMENT DISTRICT<br/>(Seagrape County, Florida)"
                    "<br/>SPECIAL ASSESSMENT REVENUE BONDS, SERIES 2019", C), Spacer(1, 12),
          Paragraph("consisting of<br/>$35,715,000 Current Interest Bonds<br/>$12,500,000 Deferred Interest Bonds", C),
          Spacer(1, 12),
          Paragraph("Dated: Date of Delivery &nbsp;&nbsp;&nbsp;&nbsp; Due: As shown on the inside cover", C),
          Paragraph("The Series 2019 Bonds are being issued by Coral Bend Community Development District "
                    "(the \"District\") to finance a portion of the cost of public infrastructure within "
                    "the District. The Series 2019 Bonds are payable solely from Special Assessments levied "
                    "on assessable lands within the District. The Series 2019 Bonds involve a significant "
                    "degree of risk and are not suitable for all investors. See \"RISK FACTORS\" herein.", B),
          Paragraph("This cover page contains information for quick reference only. It is not a summary of "
                    "this issue. Investors must read the entire Official Statement to obtain information "
                    "essential to the making of an informed investment decision.", B),
          Paragraph("Official Statement dated June 18, 2019", C), PageBreak()]
    rows = [["Maturity (July 1)", "Principal", "Interest Rate", "Price", "CUSIP"]]
    for i, (y, amt, rate) in enumerate([(2024, "2,145,000", "4.250%"), (2026, "3,380,000", "4.625%"),
                                         (2029, "6,190,000", "5.000%"), (2039, "24,000,000", "5.375%")]):
        rows.append([str(y), "$" + amt, rate, "100.000", other_cusips[i]])
    s += [Paragraph("MATURITY SCHEDULE", H), Paragraph("CURRENT INTEREST BONDS", C),
          Table(rows, hAlign="CENTER"), Spacer(1, 18), Paragraph("DEFERRED INTEREST BONDS", C),
          Table([["Maturity", "Principal", "Interest Rate", "Price", "CUSIP"],
                 ["July 1, 2034", "$12,500,000", "11.000%", "100.000", cusip]], hAlign="CENTER"),
          Spacer(1, 12),
          Paragraph("CUSIP numbers are provided for convenience of reference only. Neither the District "
                    "nor the Underwriter takes any responsibility for the accuracy of such numbers.", B),
          PageBreak()]
    s += filler("TABLE OF CONTENTS", 3)
    s += filler("INTRODUCTION", 7)
    s += [Paragraph("DESCRIPTION OF THE SERIES 2019 BONDS", H),
          Paragraph("General. The Series 2019 Bonds will be dated their date of delivery, which is "
                    "expected to be July 1, 2019 (the \"Dated Date\"). The Series 2019 Bonds will be issued "
                    "in fully registered form in denominations of $5,000 or any integral multiple thereof.", B),
          Paragraph("Current Interest Bonds. Interest on the Current Interest Bonds is payable "
                    "semiannually on each January 1 and July 1, commencing January 1, 2020, at the rates "
                    "set forth on the inside cover hereof. Interest on the Current Interest Bonds shall be "
                    "computed on the basis of a 360-day year consisting of twelve 30-day months.", B),
          Paragraph(FILLER, B), PageBreak()]
    s += [Paragraph("Deferred Interest Bonds. The Deferred Interest Bonds will bear interest at the rate of "
                    "11.000% per annum from the Dated Date. Interest on the Deferred Interest Bonds will not "
                    "be paid currently but will accrue and be compounded semiannually on each January 1 "
                    "and July 1, commencing January 1, 2020 (each, a \"Compounding Date\"), and will be "
                    "payable, together with the principal thereof, only at maturity or upon prior "
                    "redemption. Holders of the Deferred Interest Bonds will receive no payments of "
                    "interest prior to maturity or redemption.", B),
          Paragraph("Interest on the Deferred Interest Bonds shall be computed on the basis of a 360-day "
                    "year consisting of twelve 30-day months. The \"Accreted Value\" of a Deferred Interest "
                    "Bond means, as of any date of computation, the principal amount thereof plus interest "
                    "accrued and compounded to the most recent Compounding Date, plus interest accrued "
                    "from such Compounding Date to the date of computation, determined on the basis of "
                    "straight-line interpolation. A table of Accreted Values per $5,000 principal amount "
                    "is set forth in APPENDIX E hereto.", B), Paragraph(FILLER, B), PageBreak()]
    s += [Paragraph("REDEMPTION PROVISIONS", H),
          Paragraph("Optional Redemption. The Current Interest Bonds maturing on or after July 1, 2029 are "
                    "subject to optional redemption prior to maturity, at the option of the District, in "
                    "whole or in part on any date on or after July 1, 2029, at a redemption price equal to "
                    "the principal amount thereof plus accrued interest to the redemption date.", B),
          Paragraph("The Deferred Interest Bonds are subject to optional redemption prior to maturity in "
                    "whole or in part on any date on or after July 1, 2029, at a redemption price equal to "
                    "the Accreted Value thereof as of the redemption date, without premium.", B),
          Paragraph("Extraordinary Mandatory Redemption. The Series 2019 Bonds are subject to "
                    "extraordinary mandatory redemption in whole or in part on any Interest Payment Date "
                    "from prepayments of Special Assessments, at a redemption price equal to 100% of the "
                    "principal amount (or Accreted Value, in the case of the Deferred Interest Bonds) "
                    "thereof plus accrued interest to the redemption date.", B), PageBreak()]
    s += filler("SECURITY FOR AND SOURCE OF PAYMENT OF THE SERIES 2019 BONDS", 7)
    s += filler("RISK FACTORS", 7)
    s += filler("TAX MATTERS", 6)
    rows = [["Date", "Accreted Value per $5,000"]]
    for p in accretion_schedule(t)[::2] + [accretion_schedule(t)[-1]]:
        rows.append([p.date.strftime("%B %-d, %Y"), f"${p.value * 50:,.2f}"])
    s += [Paragraph("APPENDIX E - TABLE OF ACCRETED VALUES (DEFERRED INTEREST BONDS)", H),
          Table(rows, hAlign="CENTER")]
    SimpleDocTemplate(str(path), pagesize=letter, leftMargin=inch, rightMargin=inch,
                      title="Coral Bend CDD Series 2019 Official Statement").build(s)


def build_d12(path: Path, cusip: str, other_cusips: list[str]):
    """Convertible capital appreciation bonds: 5.5% accreting to 12/1/2031, then current pay."""
    s = []
    s += [Paragraph("NEW ISSUE - BOOK-ENTRY ONLY &nbsp;&nbsp;&nbsp; S&amp;P: \"A\"", C), Spacer(1, 12),
          Paragraph("$61,040,000<br/>NORTHGATE UNIVERSITY FACILITIES AUTHORITY<br/>REVENUE BONDS, SERIES 2021B", C),
          Spacer(1, 12),
          Paragraph("$41,040,000 Current Interest Bonds &nbsp;&nbsp; $20,000,000 Convertible Capital Appreciation Bonds", C),
          Paragraph("Dated: Date of Delivery (December 1, 2021)", C),
          Paragraph("This cover page contains information for quick reference only. Investors must read the "
                    "entire Official Statement to obtain information essential to the making of an "
                    "informed investment decision.", B), PageBreak()]
    rows = [["Maturity (December 1)", "Principal", "Rate", "Yield", "CUSIP"],
            ["2031", "$9,500,000", "4.000%", "2.100%", other_cusips[0]],
            ["2036", "$31,540,000", "4.000%", "2.450%", other_cusips[1]]]
    s += [Paragraph("MATURITY SCHEDULE", H), Table(rows, hAlign="CENTER"), Spacer(1, 12),
          Paragraph("CONVERTIBLE CAPITAL APPRECIATION BONDS", C),
          Table([["Maturity", "Initial Principal Amount", "Conversion Date", "Accretion Rate", "CUSIP"],
                 ["December 1, 2045", "$15,624,000", "December 1, 2031", "5.500%", cusip]],
                hAlign="CENTER"), PageBreak()]
    s += filler("INTRODUCTION", 7)
    s += [Paragraph("THE SERIES 2021B BONDS", H),
          Paragraph("Convertible Capital Appreciation Bonds. The Convertible Capital Appreciation Bonds "
                    "will be dated the date of delivery thereof, December 1, 2021, and will accrete in value "
                    "from such date at the accretion rate of 5.500% per annum, compounded semiannually on "
                    "each June 1 and December 1, commencing June 1, 2022, to December 1, 2031 (the "
                    "\"Conversion Date\"). No interest will be payable on the Convertible Capital "
                    "Appreciation Bonds prior to the Conversion Date.", B),
          Paragraph("On the Conversion Date the Accreted Value of each Convertible Capital Appreciation "
                    "Bond will equal its stated principal amount at maturity, and from and after the "
                    "Conversion Date interest will accrue on such principal amount at the rate of 5.500% "
                    "per annum, payable semiannually on each June 1 and December 1, commencing June 1, "
                    "2032. Accreted Value and interest will be computed on the basis of a 360-day year "
                    "comprised of twelve 30-day months.", B), Paragraph(FILLER, B), PageBreak()]
    s += [Paragraph("REDEMPTION", H),
          Paragraph("The Convertible Capital Appreciation Bonds are subject to optional redemption on any "
                    "date on or after December 1, 2031, at a redemption price equal to the principal "
                    "amount thereof plus accrued interest, without premium.", B), PageBreak()]
    s += filler("THE UNIVERSITY", 7)
    s += filler("TAX MATTERS", 5)
    SimpleDocTemplate(str(path), pagesize=letter, leftMargin=inch, rightMargin=inch,
                      title="Northgate University Facilities Authority Series 2021B").build(s)


def build_mbs_supplement(path: Path, h, label: str):
    """Offering circular supplement for one synthetic agency pass-through pool (fictional issuer)."""
    from termscheck.plugins.agency_mbs.bondmath import payment_date
    t = h.terms
    cusip = h.position.cusip
    pool = "P" + cusip[1:7]
    first_pay = payment_date(t.issue_date, t.payment_delay_days)
    orig = f"${h.position.par * 3:,.0f}"
    s = [Paragraph("OFFERING CIRCULAR SUPPLEMENT", C),
         Paragraph("MERIDIAN MORTGAGE SECURITIES TRUST<br/>(a fictional issuer used for software testing)", C),
         Spacer(1, 10),
         Paragraph(f"{label} Mortgage Pass-Through Certificates<br/>Pool {pool}", C), Spacer(1, 10),
         Table([["Pool Number", "CUSIP", "Original Principal Balance", "Issue Date", "Maturity Date"],
                [pool, cusip, orig, t.issue_date.strftime("%B %-d, %Y"), t.maturity_date.strftime("%B %-d, %Y")]],
               hAlign="CENTER"), Spacer(1, 10),
         Paragraph("This Supplement should be read together with the Offering Circular for the Trust's "
                   "Mortgage Pass-Through Certificates. Capitalized terms not defined here have the meanings given "
                   "in the Offering Circular.", B), PageBreak()]
    s += filler("SUMMARY OF TERMS", 5)
    s += [Paragraph("DESCRIPTION OF THE CERTIFICATES", H)]
    if t.rate_type.value == "wac":
        fee = h.meta["fee"] * 100
        s += [Paragraph(f"Pass-Through Rate. The Pass-Through Rate on the Certificates will change monthly. For each "
                        f"Accrual Period the Pass-Through Rate will equal the weighted average of the Mortgage Rates on "
                        f"the Mortgage Loans in the Pool as of the first day of that Accrual Period, less {fee:.2f}% "
                        f"(the sum of the servicing fee and the guarantee fee). The initial Pass-Through Rate is "
                        f"{h.meta['initial_rate'] * 100:.3f}% per annum. The Pass-Through Rate for each subsequent "
                        "Accrual Period will be published monthly in the Pool disclosure file.", B)]
    else:
        s += [Paragraph(f"Pass-Through Rate. The Certificates will bear interest at a fixed Pass-Through Rate of "
                        f"{t.net_coupon * 100:.3f}% per annum.", B)]
    s += [Paragraph(FILLER, B), PageBreak(),
          Paragraph("PAYMENTS", H),
          Paragraph("Accrual Period and Calculation. Interest on the Certificates accrues during each calendar month "
                    "(each, an \"Accrual Period\") on the principal balance outstanding at the beginning of that month "
                    "and is calculated on the basis of a 360-day year consisting of twelve 30-day months.", B),
          Paragraph(f"Payment Dates and Delay. Payments of principal and interest are made monthly. Each payment of "
                    f"interest for an Accrual Period is made {t.payment_delay_days} days after the first day of that "
                    f"Accrual Period (a {t.payment_delay_days}-day payment delay), or on the next Business Day. The first "
                    f"Payment Date will be {first_pay.strftime('%B %-d, %Y')}.", B),
          Paragraph("Principal. Principal will be passed through monthly as received on the Mortgage Loans, "
                    "including scheduled payments and prepayments. The outstanding principal balance of the "
                    "Certificates is expressed as a Pool Factor published monthly.", B), PageBreak()]
    s += filler("RISK FACTORS", 7)
    s += filler("CERTAIN FEDERAL INCOME TAX CONSEQUENCES", 5)
    SimpleDocTemplate(str(path), pagesize=letter, leftMargin=inch, rightMargin=inch,
                      title=f"Meridian Mortgage Securities Trust Pool {pool} (fictional)").build(s)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--out", default=str(Path(__file__).resolve().parents[2] / "data" / "sample_os"))
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    ds = generate(a.seed)
    from termscheck.plugins.muni.synthetic import _Gen
    g = _Gen(a.seed + 1)
    d = {x.defect_id[:3]: x for x in ds.defects}
    build_d01(out / f"OS_{d['D01'].cusip}.pdf", d["D01"].cusip, [g.cusip() for _ in range(4)])
    build_d12(out / f"OS_{d['D12'].cusip}.pdf", d["D12"].cusip, [g.cusip() for _ in range(2)])
    from termscheck.plugins.agency_mbs import synthetic as mbs
    m = mbs.generate()
    md = {x.defect_id[:3]: x for x in m.defects}
    for key, label in (("M01", "Adjustable-Rate (WAC)"), ("M02", "Fixed-Rate")):
        h = next(x for x in m.holdings if x.position.cusip == md[key].cusip)
        build_mbs_supplement(out / f"SUPP_{h.position.cusip}.pdf", h, label)
    print("wrote", sorted(p.name for p in out.glob("*.pdf")))


if __name__ == "__main__":
    main()
