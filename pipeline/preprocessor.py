"""
Preprocessor
============
Takes the raw screening ratios from ratio_engine.py, handles missing data,
and normalizes each ratio to a per-sector percentile rank and z-score so
companies in structurally different sectors (e.g. software vs. energy) are
compared fairly against their peers rather than the whole universe.

Steps:
1. Orient every ratio so that "higher is better" (revenue_volatility is
   inverted -- lower volatility is the attractive trait).
2. Impute missing values with the sector median (falling back to the
   global median if a sector has fewer than 3 non-null observations).
3. Compute both a per-sector z-score and a per-sector percentile rank
   (0-100) for each oriented ratio.

Output: data/processed/company_metrics.csv
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
INPUT_PATH = REPO_ROOT / "data" / "processed" / "ratios.csv"
OUTPUT_PATH = REPO_ROOT / "data" / "processed" / "company_metrics.csv"

# Ratio -> whether higher is better ("attractive" direction for LBO screening)
SCREENING_RATIOS = {
    "ebitda_margin": True,
    "ebitda_growth_stability": True,
    "leverage_headroom": True,
    "fcf_conversion": True,
    "revenue_volatility": False,  # lower volatility is more attractive
}

MIN_SECTOR_SIZE_FOR_MEDIAN = 3


def _impute_missing(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    df = df.copy()
    global_medians = df[columns].median()
    for col in columns:
        sector_counts = df.groupby("sector")[col].transform("count")
        sector_medians = df.groupby("sector")[col].transform("median")
        use_sector_median = sector_counts >= MIN_SECTOR_SIZE_FOR_MEDIAN
        fill_values = sector_medians.where(use_sector_median, global_medians[col])
        df[col] = df[col].fillna(fill_values).fillna(global_medians[col])
    return df


def _sector_zscore(series: pd.Series, sector: pd.Series) -> pd.Series:
    grouped = series.groupby(sector)
    mean = grouped.transform("mean")
    std = grouped.transform("std").replace(0, np.nan)
    z = (series - mean) / std
    return z.fillna(0.0)


def _sector_percentile(series: pd.Series, sector: pd.Series) -> pd.Series:
    return series.groupby(sector).rank(pct=True) * 100.0


def normalize(ratios: pd.DataFrame) -> pd.DataFrame:
    df = ratios.copy()
    raw_cols = list(SCREENING_RATIOS.keys())

    df = _impute_missing(df, raw_cols)

    # Orient so higher = more attractive
    oriented_cols = []
    for col, higher_is_better in SCREENING_RATIOS.items():
        oriented_col = f"{col}_oriented"
        df[oriented_col] = df[col] if higher_is_better else -df[col]
        oriented_cols.append(oriented_col)

    for col in oriented_cols:
        base = col.replace("_oriented", "")
        df[f"{base}_z"] = _sector_zscore(df[col], df["sector"])
        df[f"{base}_pct"] = _sector_percentile(df[col], df["sector"])

    df = df.drop(columns=oriented_cols)
    return df


def main():
    if not INPUT_PATH.exists():
        print(f"ERROR: {INPUT_PATH} not found. Run pipeline/ratio_engine.py first.", file=sys.stderr)
        sys.exit(1)

    ratios = pd.read_csv(INPUT_PATH)
    metrics = normalize(ratios)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    metrics.to_csv(OUTPUT_PATH, index=False)
    print(f"Normalized {len(metrics)} companies across {metrics['sector'].nunique()} sectors -> {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
