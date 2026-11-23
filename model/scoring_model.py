"""
Scoring Model
=============
Computes a weighted composite "LBO Attractiveness Score" (0-100) per company
from the sector-normalized percentile ranks produced by preprocessor.py.

Default weights are hand-set based on standard PE screening criteria:
- FCF conversion and leverage headroom matter most (debt service capacity
  and how much leverage a sponsor can actually put on the deal)
- EBITDA margin and growth stability matter almost as much (durability of
  the cash-flow base being levered)
- Revenue volatility (inverted) is a smaller but real predictability signal

Weights are fully configurable -- pass a dict to `score_companies`, or let
weight_calibration.py learn them from the historical backtest set instead.

Output: data/outputs/scores.csv
"""

import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
INPUT_PATH = REPO_ROOT / "data" / "processed" / "company_metrics.csv"
OUTPUT_PATH = REPO_ROOT / "data" / "outputs" / "scores.csv"

# Default hand-set weights (must sum to 1.0). Keys map to the "_pct" columns
# produced by preprocessor.py (sector percentile rank, 0-100, higher=better).
DEFAULT_WEIGHTS = {
    "fcf_conversion": 0.28,
    "leverage_headroom": 0.26,
    "ebitda_margin": 0.20,
    "ebitda_growth_stability": 0.16,
    "revenue_volatility": 0.10,
}

SCORE_COMPONENTS = list(DEFAULT_WEIGHTS.keys())


def score_companies(metrics: pd.DataFrame, weights: dict[str, float] | None = None) -> pd.DataFrame:
    weights = weights or DEFAULT_WEIGHTS
    total_weight = sum(weights.values())
    if abs(total_weight - 1.0) > 1e-6:
        weights = {k: v / total_weight for k, v in weights.items()}

    df = metrics.copy()

    score = pd.Series(0.0, index=df.index)
    for component, weight in weights.items():
        pct_col = f"{component}_pct"
        if pct_col not in df.columns:
            raise ValueError(f"Missing normalized column '{pct_col}' -- run preprocessor.py first")
        score += weight * df[pct_col]

    df["lbo_score"] = score.round(2)
    df["rank"] = df["lbo_score"].rank(ascending=False, method="min").astype(int)
    df["percentile"] = (df["lbo_score"].rank(pct=True) * 100).round(1)

    df = df.sort_values("lbo_score", ascending=False).reset_index(drop=True)

    for component in weights:
        df[f"{component}_weight"] = weights[component]

    return df


def main():
    if not INPUT_PATH.exists():
        print(f"ERROR: {INPUT_PATH} not found. Run pipeline/preprocessor.py first.", file=sys.stderr)
        sys.exit(1)

    metrics = pd.read_csv(INPUT_PATH)
    scores = score_companies(metrics)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    scores.to_csv(OUTPUT_PATH, index=False)

    print(f"Scored {len(scores)} companies -> {OUTPUT_PATH}")
    print("\nTop 10 LBO targets:")
    print(scores[["rank", "ticker", "name", "sector", "lbo_score"]].head(10).to_string(index=False))


if __name__ == "__main__":
    main()
