# abs-pool-monitor

A small end-to-end **medallion pipeline** (bronze → silver → gold) built in Databricks
that monitors the performance of a European consumer-loan pool from a monthly
**servicer tape**, in the style of asset-backed loan surveillance.

> **Learning project**, built in ~4 days to get hands-on with Databricks, Delta Lake
> and an AI-assisted workflow. Framed around European asset-backed credit. Synthetic
> data — no real loans.

## Why this shape

A loan servicer sends a lender a monthly loan-level file ("tape"). The lender has to
turn that messy file into a clear answer: *is this pool healthy, or are arrears
rising?* This pipeline does exactly that, in miniature:

- **Bronze** — land the raw servicer tape exactly as it arrives, untouched.
- **Silver** — clean and type it: parse European dates, standardise arrears labels,
  dedupe, handle nulls.
- **Gold** — a monthly pool-health report: delinquency buckets (30/60/90+ DPD),
  prepayment, weighted-average coupon and balance, by vintage.

## Features

- Daily scheduled Databricks Workflow with a data-quality gate.
- A covenant-style **alert**: flag when 90+ DPD breaches a threshold.
- A **vintage delinquency curve** (% delinquent vs. months-on-book).
- An **AI-assisted mapping** step: Claude reads the headers of an *unknown*
  counterparty tape and proposes a mapping to the standard schema, for a human to
  approve before ingest.

## Layout

```
abs-pool-monitor/
├── src/
│   └── generate_loan_tape.py   # makes the synthetic servicer tape
├── notebooks/                  # Databricks notebooks (added day by day)
├── data/                       # generated tape (git-ignored, not committed)
└── README.md
```

## Data

`src/generate_loan_tape.py` generates a synthetic European loan tape (~63k monthly
rows across 3,000 loans, EUR balances, DE/FR/ES/IT/NL, day-bucket arrears). The file
is intentionally a little messy so the silver layer has real work to do.

```
python src/generate_loan_tape.py   # writes data/loan_tape.csv
```

## How I used AI tooling in this build

_(to be filled in — pragmatic wins, and where I didn't trust it)_
