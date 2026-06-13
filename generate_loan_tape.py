"""
generate_loan_tape.py
----------------------
Generates a synthetic European consumer-loan SERVICER TAPE for the
abs-pool-monitor project.

A "servicer tape" is the monthly loan-level file a loan servicer sends to a
lender (like NorthWall) so the lender can monitor pool performance. This script
fakes one: a panel of loans observed every month from origination up to an
"as-of" date, with balances amortising down and some loans rolling into arrears
or paying off early.

Deliberately includes a little MESS (European date format, inconsistent status
labels, duplicates, nulls, a few bad balances) so the silver layer has real
cleaning work to do.

Run:  python generate_loan_tape.py
Out:  data/loan_tape.csv
"""

import numpy as np
import pandas as pd
from datetime import date
from dateutil.relativedelta import relativedelta
import os

rng = np.random.default_rng(42)  # reproducible

# ---- knobs -------------------------------------------------------------
N_LOANS      = 3000
AS_OF        = date(2025, 12, 31)        # latest reporting month
ORIG_START   = date(2023, 1, 1)          # earliest origination
ORIG_END     = date(2024, 12, 1)         # latest origination
COUNTRIES    = ["DE", "FR", "ES", "IT", "NL"]
COUNTRY_W    = [0.32, 0.24, 0.18, 0.14, 0.12]
PRODUCTS     = ["Auto", "Personal", "SME"]
PRODUCT_W    = [0.45, 0.40, 0.15]
TERMS        = [24, 36, 48, 60]

# arrears states: 0=Current 1=1-30 2=31-60 3=61-90 4=90+ (sticky default)
STATUS_LABEL = {0: "Current", 1: "1-30 DPD", 2: "31-60 DPD",
                3: "61-90 DPD", 4: "90+ DPD"}

def month_floor(d):
    return date(d.year, d.month, 1)

def months_between(a, b):
    return (b.year - a.year) * 12 + (b.month - a.month)

# ---- build the loan book ----------------------------------------------
orig_span = months_between(ORIG_START, ORIG_END)
rows = []

for i in range(1, N_LOANS + 1):
    loan_id   = f"NW-{i:06d}"
    country   = rng.choice(COUNTRIES, p=COUNTRY_W)
    product   = rng.choice(PRODUCTS, p=PRODUCT_W)
    term      = int(rng.choice(TERMS))
    orig      = month_floor(ORIG_START + relativedelta(months=int(rng.integers(0, orig_span + 1))))
    orig_bal  = float(np.round(rng.lognormal(mean=9.4, sigma=0.5), 2))   # ~ EUR 5k-40k
    orig_bal  = min(max(orig_bal, 2000), 60000)
    rate      = float(np.round(rng.uniform(4.0, 13.5), 2))

    # per-loan latent monthly default hazard (~0.3%-1.5%/mo) + prepayment appetite
    risk      = rng.beta(2, 6) * 0.04               # mean ~1%/month into arrears
    # later vintages run slightly hotter (recent stress) -> separates the curves
    vintage_bump = months_between(ORIG_START, orig) / max(orig_span, 1) * 0.004
    prepay_p  = rng.uniform(0.004, 0.018)

    state = 0
    months_in_90 = 0
    last_month = min(orig + relativedelta(months=term), AS_OF)
    n_months = months_between(orig, month_floor(last_month))

    for m in range(0, n_months + 1):
        report = month_floor(orig + relativedelta(months=m))
        if report > AS_OF:
            break

        # straight-line amortisation of the balance
        cur_bal = round(orig_bal * max(0.0, 1 - m / term), 2)

        # early payoff (prepayment): emit a final paid-off row and stop
        if m > 0 and state < 2 and rng.random() < prepay_p:
            rows.append([loan_id, report, orig, country, product, orig_bal,
                         0.0, rate, term, "Paid Off", m])
            break

        # arrears state machine
        if state == 0:
            if rng.random() < risk + vintage_bump:
                state = 1
        else:
            r = rng.random()
            if r < 0.40:                               # cure
                state = max(0, state - 1)
            elif r < 0.40 + 0.30 + (risk + vintage_bump) * 5:  # worsen / roll forward
                state = min(4, state + 1)
            # else: hold

        # charge-off: after ~6 months stuck in 90+, the loan exits the pool
        if state == 4:
            months_in_90 += 1
            if months_in_90 >= 6:
                rows.append([loan_id, report, orig, country, product, orig_bal,
                             cur_bal, rate, term, "Charged Off", m])
                break
        else:
            months_in_90 = 0

        rows.append([loan_id, report, orig, country, product, orig_bal,
                     cur_bal, rate, term, STATUS_LABEL[state], m])

cols = ["loan_id", "reporting_date", "origination_date", "country", "product",
        "original_balance_eur", "current_balance_eur", "interest_rate_pct",
        "term_months", "arrears_status", "months_on_book"]
df = pd.DataFrame(rows, columns=cols)

# ---- format + inject realistic MESS (work for the silver layer) --------
# European date format on origination (DD/MM/YYYY); ISO on reporting date
df["reporting_date"]   = pd.to_datetime(df["reporting_date"]).dt.strftime("%Y-%m-%d")
df["origination_date"] = pd.to_datetime(df["origination_date"]).dt.strftime("%d/%m/%Y")

# inconsistent casing on ~8% of status labels
mask = rng.random(len(df)) < 0.08
df.loc[mask, "arrears_status"] = df.loc[mask, "arrears_status"].str.upper()

# ~0.5% null current balance (missing from servicer file)
mask = rng.random(len(df)) < 0.005
df.loc[mask, "current_balance_eur"] = np.nan

# a few negative balances (data-entry errors -> data quality gate fodder)
mask = rng.random(len(df)) < 0.002
df.loc[mask, "current_balance_eur"] = -df.loc[mask, "current_balance_eur"].abs()

# ~0.5% duplicate rows (servicer re-sent lines)
dupes = df.sample(frac=0.005, random_state=1)
df = pd.concat([df, dupes], ignore_index=True)

# shuffle so dupes/mess aren't clustered
df = df.sample(frac=1, random_state=7).reset_index(drop=True)

os.makedirs("data", exist_ok=True)
out = "data/loan_tape.csv"
df.to_csv(out, index=False)

print(f"Wrote {out}")
print(f"Rows: {len(df):,}  |  Loans: {df['loan_id'].nunique():,}")
print(f"Reporting range: {df['reporting_date'].min()} -> {df['reporting_date'].max()}")
print("\nArrears status counts:")
print(df["arrears_status"].value_counts())
print("\nSample:")
print(df.head(6).to_string(index=False))
