# Quarry

Quarry is a tool that looks at public companies and scores how good a fit
each one would be for a leveraged buyout (a private equity firm buying the
company, mostly using borrowed money). It then checks that score against 22
real buyouts that actually happened, and finally works out the best group of
companies to buy under a fixed budget.

It's one pipeline, start to finish: pull company data → compute financial
ratios → turn ratios into a single score → test the score against real deals
→ pick the best companies to buy under a budget → check how sensitive that
choice is → stress-test it against uncertainty → show all of it in a
dashboard.

## What it actually does

1. **Scores about 120 mid-size public companies** on 5 things a private
   equity buyer cares about: how profitable the company is, how steady that
   profit has been, how much more debt it could safely take on, how much of
   its profit turns into real cash, and how predictable its revenue is. Each
   company ends up with one **score from 0 to 100** — higher means a more
   attractive buyout target. Companies are only compared against others in
   their own industry, since a software company and a grocery chain don't
   have comparable profit margins.

2. **Checks if the score actually works.** It takes 22 real companies that
   were bought out by private equity firms between 2022 and 2024, scores
   them using only the financial information that existed *before* their
   deal was publicly announced (so it's not cheating by looking at
   information from after the fact), and checks where each one ranked.

3. **Picks which companies to buy.** Given a fixed amount of money to spend
   and a rule that you can't put too much of it into one industry, it
   mathematically works out the exact group of companies that gets you the
   most total value without breaking either rule.

4. **Shows what the budget and the diversification rule are actually
   costing or earning you** — e.g. "one more million dollars of budget buys
   you this much extra value" and "spreading across industries costs you
   this much value, in exchange for not being overexposed to one sector."

5. **Stress-tests the choice.** Instead of assuming every score is exactly
   right, it treats each company's true value as somewhat uncertain (based
   on how volatile that company's revenue has historically been) and checks
   whether the chosen group of companies still hits its target value even
   when things don't go exactly as scored.

6. **Shows its work.** For any of the 22 real companies, you can scroll
   through its score over the 3 years leading up to its actual buyout, and
   see exactly which of the 5 factors pushed the score up or down at any
   point — see [Explainable Backtesting](#explainable-backtesting) below.

## Where the data comes from and how it's calculated

- **The ~120 companies being screened** (`pipeline/financials_loader.py`):
  pulled from Yahoo Finance — income statement, cash flow, and balance
  sheet, up to 5 years of history per company. Very large companies, banks,
  and regulated utilities are left out, since they don't get bought out in
  leveraged buyouts the way mid-size companies do.
- **The 22 real buyout deals** (`backtest/historical_lbo_targets.py`): hand
  -picked real public-to-private deals from 2022–2024 (CDK Global, Citrix,
  Anaplan, Zendesk, Tenneco, Univar Solutions, Syneos Health, R1 RCM,
  Smartsheet, and others). Because these companies got delisted after being
  bought, their financials disappear from Yahoo Finance almost immediately
  — so instead, their numbers are pulled straight from the **U.S.
  Securities and Exchange Commission's (SEC) public filings database**
  (`backtest/backtest_runner.py`), using only the filings dated *before*
  each deal was announced. That's what makes this a fair test: it only uses
  information that would have actually been available at the time, not
  hindsight.
- **The 5 scoring factors** (`pipeline/ratio_engine.py`): profit margin
  (EBITDA margin), how stable that profit has been year to year, how much
  more debt the company could take on before hitting a standard lending
  ceiling, how much of profit converts into real cash, and how predictable
  revenue is.
- **Making companies comparable** (`pipeline/preprocessor.py`): every
  factor is flipped so "higher is always better," missing numbers are
  filled in with the typical value for that industry, and every company is
  ranked only against others in its own industry (as a percentile, 0–100).
- **Turning 5 factors into 1 score** (`model/scoring_model.py`): a weighted
  average of the 5 percentile ranks. The weights are set by hand to match
  standard private-equity screening priorities (cash conversion and debt
  capacity matter most); they can be changed.
- **An alternative, machine-learned version of the weights**
  (`model/weight_calibration.py`, optional): instead of hand-set weights,
  this trains a model (logistic regression) on the 22 real deals to learn
  its own weights. With only 22 real examples to learn from, this is more
  of a demonstration than something to trust as a finished model — see the
  caveat printed in its own output.
- **Picking which companies to buy** (`optimization/`): solved with a
  standard optimization solver (PuLP/CBC). Each company is either bought or
  not (no partial purchases). The cost to buy a company is assumed to be its
  market value plus a 30% premium, which matches what buyers have typically
  paid on top of market value in recent real deals.

## Explainable Backtesting

Two features that let you check the backtest's work company by company,
instead of just trusting a single before/after number.

### Backtest Replay Timeline (`backtest/score_history.py`)

For each of the 22 real buyout targets, this recalculates its score at 12
points in time spanning the 3 years before its deal was announced — using
only the financial information that would have actually existed at each of
those points (never anything from after the fact).

Companies report their financial numbers to the SEC in a few different
ways, so the code has to do some reconstruction work to pull out clean,
non-overlapping 3-month periods from the raw filings, then build a rolling
12-month total from the 4 most recent of those periods at each point in
time. That reconstructed number is run through the exact same scoring
process as everything else in the app, so a point on this timeline is
directly comparable to any other score shown anywhere in the dashboard.

**In the dashboard:** the *Replay* tab — pick a company, drag the slider,
and watch its score (and rank) move toward its actual buyout date. R1 RCM
is a good one to try: its score drops sharply after a 2022 acquisition
loaded it up with debt and hurt its cash conversion, then climbs back as it
pays that debt down ahead of its 2024 buyout — a real, verifiable story,
not a smoothed-out hindsight line.

**Via the API:** `GET /backtest/timeline/{ticker}` (e.g.
`/backtest/timeline/RCM`).

Coverage: this works for 18 of the 22 real targets; the other 4 (Tenneco,
Sumo Logic, Instructure, Perficient) don't have enough quarterly filing
history available and are skipped rather than guessed at.

### SHAP Explainability (`model/explainability.py`)

Because the score is just a weighted average of 5 numbers, it's possible to
calculate *exactly* how much each factor contributed to pushing a
company's score above or below average — no estimation or approximation
involved, it's checked to match the real score down to the decimal for
every company.

This turns a single score into something you can actually defend: "this
company's score is high mainly because of strong cash conversion, despite
weaker revenue predictability," for example.

**In the dashboard:** the *Why did the score move?* panel below the Replay
timeline updates live as you move the slider, explaining each rise or fall
in the score factor by factor.

**Via the API:**
- `GET /explain/{ticker}` — breakdown of a company's current score.
- `GET /explain/{ticker}/{date}` — breakdown at one point on its replay
  timeline (`date` must match one returned by `/backtest/timeline/{ticker}`).

## Key findings

**Did the score actually predict real buyouts?** Only **4.5% of the 22
real buyout targets** (that's 1 company) scored in the top 20% of all
companies before their deal was announced. Because 22 is a small number of
deals to test against, this comes with a **95% confidence range of
0.8% to 21.8%** — in plain terms, the true rate could reasonably be
anywhere in that wide range, so don't treat 4.5% as a precise number, just
a rough signal that the score mostly did *not* catch these real deals in
advance.

Splitting that by industry: **non-tech companies scored noticeably higher**
than tech companies (Healthcare's typical ranking was around the 77th
percentile; Technology's was around the 28th percentile, and 14 of the 22
deals were tech companies). This lines up with a real pattern from
2022–2024, where most software buyouts happened because growth had slowed
down and valuations had dropped — not because the company matched the
"steady, cash-generative, low-debt" profile this screening tool looks for.
**However, this industry gap is not statistically reliable** at this
sample size — a standard statistical test for this kind of comparison
(Mann-Whitney U test) gives a result of **p = 0.365**, well above the usual
0.05 cutoff for "this is probably a real pattern and not random chance."
So: a plausible pattern, but not one you can say is confirmed with only 22
deals to test on.

**Picking which companies to buy:** with a $50 billion budget and a rule of
buying at most 3 companies per industry, the tool picks **17 companies**,
spending $49.95 billion of the $50 billion (99.9% of it used), for a
combined portfolio value of 991.8 score-points.

**How much the budget and the rules are worth:** one extra $1 million of
budget would buy about 0.009 more score-points of value at the margin. The
"max 3 per industry" rule costs 5.4 score-points (0.5% of total value) —
basically a small, acceptable price for not over-concentrating in one
industry. The industry that rule restricts the most is Consumer Cyclical,
which has 22 eligible companies but is capped at 3.

**Does the chosen portfolio hold up under uncertainty?** Using a smaller
$12 billion budget and requiring a 90% chance of hitting a safety target,
the originally-chosen companies already clear that bar **94.7% of the time**
across 300 randomized "what if things go worse than expected" simulations
— no changes needed to make it safer. That's a finding worth noting on its
own: when you can only buy whole companies (not fractions of them), the
"safest" choice and the "best" choice sometimes turn out to be the exact
same portfolio, or there's no safe choice at all — there isn't always a
smooth trade-off between safety and performance like there would be with
more flexible investments.

**Did a machine-learning model do better than the hand-set weights?** A
version with weights learned by a machine-learning model separated real
buyout targets from everything else more cleanly in one technical
measure (a score of 0.739 out of 1.0, where 0.5 is random guessing and 1.0
is perfect). But on the actual metric that matters here — catching real
targets in the top 20% — it did **worse**, catching 0% of them versus 4.5%
for the simple hand-set weights. This is a useful, cautionary finding on
its own: a model can look better by one measure while actually being worse
at the specific job you need it to do.

Because the ~120-company data is pulled from live market prices, the exact
scores and rankings shift very slightly (usually less than 1%) each time
the pipeline is re-run on a different day — but the overall patterns above
(the industry gap, which rules matter most, the machine-learning model
underperforming) stay the same even as the decimal points move slightly.

**On trustworthiness of these numbers:** the confidence range and the
statistical test above aren't just written into this document by hand —
they're calculated directly by the code itself
(`backtest/backtest_runner.py`, functions `wilson_confidence_interval` and
`sector_gap_significance`) and saved into
`data/outputs/backtest_results.json` and the dashboard's `/key-findings`
endpoint. Re-running the pipeline recalculates them from scratch.

## Project layout

```
quarry/
├── data/
│   ├── raw/              financials.csv, historical_targets.csv, SEC cache
│   ├── processed/        ratios.csv, company_metrics.csv
│   └── outputs/          scores.csv, backtest_results.json, optimal_portfolio.json,
│                         sensitivity_report.json, robust_portfolio.json, weight_calibration.json,
│                         score_timeline.json
├── pipeline/              financials_loader.py, ratio_engine.py, preprocessor.py
├── model/                 scoring_model.py, weight_calibration.py, explainability.py
├── backtest/              historical_lbo_targets.py, backtest_runner.py, score_history.py
├── optimization/          allocation_optimizer.py, sensitivity_analysis.py, chance_constraints.py
├── dashboard/
│   ├── api.py             FastAPI backend
│   └── frontend/          React + Tailwind + Recharts dashboard
└── run.py                 runs everything end to end
```

## How to run

```bash
pip install -r requirements.txt
python run.py
```

This runs the full pipeline (pull data → compute ratios → score companies →
backtest → optimize) and starts the API server at `http://127.0.0.1:8000`
(open `/docs` there for interactive API docs), printing a summary of the
key findings to the console.

Flags:
- `python run.py --skip-fetch` — reuse the financial data already saved in
  `data/raw/financials.csv` instead of re-downloading it (useful once
  you've already pulled it once; the initial download takes a few minutes
  for ~120 companies).
- `python run.py --no-serve` — run the pipeline only, without starting the
  API server.

To run the dashboard:

```bash
cd dashboard/frontend
npm install
npm run dev
```

Then open `http://localhost:5173` in a browser. The dashboard needs the
backend running first (`python run.py`, in a separate terminal) — it sends
its requests to that backend automatically.

### API endpoints

| Endpoint | Returns |
|---|---|
| `GET /rankings` | Full list of scored, ranked companies |
| `GET /backtest` | Results of testing the score against real buyouts |
| `GET /backtest/timeline/{ticker}` | A real target's score over time, leading up to its buyout |
| `GET /optimal-portfolio` | The best group of companies to buy under budget |
| `GET /sensitivity` | What the budget and the diversification rule are each worth |
| `GET /robust-portfolio` | The budget-constrained portfolio, stress-tested against uncertainty |
| `GET /weight-calibration` | Hand-set weights vs. machine-learned weights, compared |
| `GET /explain/{ticker}` | Breakdown of exactly why a company's current score is what it is |
| `GET /explain/{ticker}/{date}` | Same breakdown, at one point on that company's replay timeline |
| `GET /key-findings` | The summary numbers shown at the top of the dashboard |

## Limitations, honestly

- The 22 real buyout targets are compared against **today's** list of
  ~120 companies, not the list of companies that actually existed on each
  deal's real announcement date. Rebuilding an exact historical snapshot
  for 22 different past dates would be a much bigger undertaking, so this
  is a deliberate simplification.
- The machine-learning version of the weights is tested on the same small
  group of 22 real deals it was trained on (not a separate, unseen group),
  and that group is mostly tech companies. Treat it as a demonstration of
  the approach, not a finished, trustworthy model.
- The "what one more dollar of budget is worth" and "what the
  diversification rule costs" figures are a standard mathematical
  approximation (because the underlying problem only allows whole-company,
  yes/no decisions, which don't have exact pricing the way continuous
  decisions do).
- The 30% premium assumed for buying a company is a flat, typical estimate
  — real deal prices vary by situation, how competitive the bidding was,
  and deal terms.
- The quarter-by-quarter replay timeline is rebuilt from raw SEC filing
  data, which can occasionally be tagged inconsistently by different
  companies; 4 of the 22 real targets simply don't have enough usable
  quarterly history to build a timeline at all.
- The factor-by-factor score breakdown (SHAP) is calculated exactly for
  how the scoring model works, but it's always measured against today's
  ~120-company group as the baseline — not the group that existed on each
  historical date (same simplification as above).
