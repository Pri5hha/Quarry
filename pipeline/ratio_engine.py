"""
Ratio Engine
============
Computes the screening ratios PE firms actually use when evaluating LBO
candidates, from the long-format financials table produced by
financials_loader.py (or, for backtest targets, backtest_runner.py's SEC
EDGAR pull -- same schema, same function).

Ratios computed (one row per company, using its most recent fiscal year as
the "as of" point, and up to 5 years of history for stability measures):

- ebitda_margin              EBITDA / Revenue (most recent year)
- ebitda_growth_stability    1 / (1 + std dev of YoY EBITDA growth) over
                              available history -- higher = more stable
- leverage_headroom          how much more debt the company could take on
                              before hitting a ~6.0x Debt/EBITDA ceiling
                              (a rough proxy for typical LBO leverage limits)
- fcf_conversion             Free Cash Flow / EBITDA (most recent year)
- revenue_volatility         std dev of YoY revenue growth over available
                              history (lower = more predictable, better LBO
                              candidate)

Output: data/processed/ratios.csv
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
INPUT_PATH = REPO_ROOT / "data" / "raw" / "financials.csv"
OUTPUT_PATH = REPO_ROOT / "data" / "processed" / "ratios.csv"

MAX_LEVERAGE_MULTIPLE = 6.0  # rough ceiling on Debt/EBITDA a PE sponsor would underwrite to


def _yoy_growth(series: pd.Series) -> pd.Series:
    return series.sort_index().pct_change().dropna()


def compute_ratios(financials: pd.DataFrame) -> pd.DataFrame:
    financials = financials.copy()
    financials["fiscal_year"] = financials["fiscal_year"].astype(int)

    records = []
    for ticker, g in financials.groupby("ticker"):
        g = g.sort_values("fiscal_year")
        latest = g.iloc[-1]

        revenue = latest["revenue"]
        ebitda = latest["ebitda"]
        debt = latest["total_debt"]
        fcf = latest["free_cash_flow"]

        ebitda_margin = ebitda / revenue if pd.notna(ebitda) and pd.notna(revenue) and revenue != 0 else np.nan
        # Only meaningful when EBITDA is positive -- negative/negative would
        # otherwise look like a healthy conversion ratio.
        fcf_conversion = fcf / ebitda if pd.notna(fcf) and pd.notna(ebitda) and ebitda > 0 else np.nan

        # Debt/EBITDA headroom: positive = room to lever up further,
        # negative = already over the assumed underwriting ceiling.
        if pd.notna(debt) and pd.notna(ebitda) and ebitda > 0:
            current_leverage = debt / ebitda
            leverage_headroom = MAX_LEVERAGE_MULTIPLE - current_leverage
        else:
            current_leverage = np.nan
            leverage_headroom = np.nan

        ebitda_series = g.set_index("fiscal_year")["ebitda"].dropna()
        revenue_series = g.set_index("fiscal_year")["revenue"].dropna()

        ebitda_growth = _yoy_growth(ebitda_series)
        revenue_growth = _yoy_growth(revenue_series)

        ebitda_growth_std = ebitda_growth.std() if len(ebitda_growth) >= 2 else np.nan
        revenue_volatility = revenue_growth.std() if len(revenue_growth) >= 2 else np.nan

        ebitda_growth_stability = (
            1.0 / (1.0 + abs(ebitda_growth_std)) if pd.notna(ebitda_growth_std) else np.nan
        )
        ebitda_cagr = (
            (ebitda_series.iloc[-1] / ebitda_series.iloc[0]) ** (1 / max(len(ebitda_series) - 1, 1)) - 1
            if len(ebitda_series) >= 2 and ebitda_series.iloc[0] > 0 and ebitda_series.iloc[-1] > 0
            else np.nan
        )

        records.append({
            "ticker": ticker,
            "name": latest["name"],
            "sector": latest["sector"],
            "industry": latest["industry"],
            "market_cap": latest["market_cap"],
            "fiscal_year": int(latest["fiscal_year"]),
            "n_years_history": g["fiscal_year"].nunique(),
            "revenue": revenue,
            "ebitda": ebitda,
            "total_debt": debt,
            "free_cash_flow": fcf,
            "ebitda_margin": ebitda_margin,
            "current_leverage": current_leverage,
            "leverage_headroom": leverage_headroom,
            "fcf_conversion": fcf_conversion,
            "ebitda_growth_stability": ebitda_growth_stability,
            "ebitda_cagr": ebitda_cagr,
            "revenue_volatility": revenue_volatility,
        })

    return pd.DataFrame.from_records(records)


def main():
    if not INPUT_PATH.exists():
        print(f"ERROR: {INPUT_PATH} not found. Run pipeline/financials_loader.py first.", file=sys.stderr)
        sys.exit(1)

    financials = pd.read_csv(INPUT_PATH)
    ratios = compute_ratios(financials)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    ratios.to_csv(OUTPUT_PATH, index=False)
    print(f"Computed ratios for {len(ratios)} companies -> {OUTPUT_PATH}")

    coverage = ratios[[
        "ebitda_margin", "leverage_headroom", "fcf_conversion",
        "ebitda_growth_stability", "revenue_volatility",
    ]].notna().mean() * 100
    print("Field coverage (% of companies with a valid value):")
    print(coverage.round(1).to_string())


if __name__ == "__main__":
    main()
