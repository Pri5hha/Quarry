"""
Score History (Backtest Replay Timeline)
==========================================
For each historical LBO target, recomputes its Quarry score at quarterly
points going back 3 years before the deal was announced -- using only
financial data that would have been available AT that point (no lookahead:
every quarterly/annual XBRL fact used for a given point has an end-date on
or before that point's date).

This turns the backtest from a single before/after snapshot into a replay:
does the score actually climb as the company approaches its real buyout, or
does it only look attractive in hindsight?

Method:
1. Reuse the SEC EDGAR company-facts cache already populated by
   backtest_runner.py (offline, no new network calls).
2. Derive DISCRETE quarterly figures for revenue, operating income, D&A, OCF
   and capex from the raw XBRL duration facts. SEC filers report these two
   different ways -- some tag genuinely discrete ~3-month periods directly,
   others tag year-to-date cumulative periods (Q1, 6-mo, 9-mo, FY) that all
   share the same period *start* date. Grouping facts by shared start date
   and differencing consecutive end-dates recovers true discrete quarters
   either way (a lone discrete period is just a "group of one" and passes
   through unchanged).
3. At each as-of date, build a trailing-twelve-month (TTM) aggregate from
   the 4 most recent discrete quarters ending on or before that date (skip
   the point if fewer than 4 are available yet), and look up the most
   recent balance-sheet instant (debt) at or before that date.
4. Feed that TTM snapshot into ratio_engine.compute_ratios() as if it were
   the company's "latest fiscal year," alongside its real completed annual
   fiscal years before that date (for the growth-stability / volatility
   history) -- so this reuses the exact same ratio math as the live
   pipeline and the point-in-time backtest.
5. Pool the resulting single-row ratios into the live universe and re-run
   the same normalization + scoring pipeline as backtest_runner.py, so each
   timeline point is scored on the same footing as everything else.

Same caveat as backtest_runner.py: the comparison universe is today's live
mid-cap universe, not the exact universe as of each historical date.

Output: data/outputs/score_timeline.json
  { TICKER: { ticker, name, sector, acquirer, deal_announce_date,
              points: [ {date, months_before_deal, score, rank,
                         rank_percentile, universe_size, ratios_pct,
                         raw_ratios}, ... ] } }
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from pipeline.ratio_engine import compute_ratios  # noqa: E402
from pipeline.preprocessor import normalize  # noqa: E402
from model.scoring_model import score_companies, DEFAULT_WEIGHTS  # noqa: E402
from backtest.historical_lbo_targets import load_historical_targets  # noqa: E402
from backtest.backtest_runner import fetch_company_facts, DURATION_TAGS, INSTANT_TAGS  # noqa: E402

LIVE_RATIOS_PATH = REPO_ROOT / "data" / "processed" / "ratios.csv"
OUTPUT_PATH = REPO_ROOT / "data" / "outputs" / "score_timeline.json"

FEATURES = list(DEFAULT_WEIGHTS.keys())
QUARTER_OFFSETS_MONTHS = [3 * k for k in range(1, 13)]  # 3, 6, ..., 36 months before the deal


def _period_map(facts: dict, tags: list[str]) -> dict[tuple[str, str], float]:
    """{(start, end): value}, across 10-Q and 10-K filings, latest-filed wins."""
    gaap = facts.get("facts", {}).get("us-gaap", {})
    out: dict[tuple[str, str], float] = {}
    for tag in tags:
        entries = gaap.get(tag, {}).get("units", {}).get("USD", [])
        for e in sorted(entries, key=lambda e: e.get("filed", "")):
            if e.get("form") not in ("10-Q", "10-K", "10-K/A", "10-Q/A"):
                continue
            start, end = e.get("start"), e.get("end")
            if not start or not end:
                continue
            out[(start, end)] = e["val"]
    return out


def _discrete_quarterly(period_map: dict[tuple[str, str], float]) -> dict[str, float]:
    """Group facts sharing a start date (same fiscal year) and difference
    consecutive end-dates to recover discrete quarterly figures, whether the
    filer reported discrete periods or YTD-cumulative ones."""
    by_start: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for (start, end), val in period_map.items():
        by_start[start].append((end, val))

    discrete: dict[str, float] = {}
    for periods in by_start.values():
        periods.sort(key=lambda x: x[0])
        prev_val = 0.0
        for end, val in periods:
            discrete[end] = val - prev_val
            prev_val = val
    return discrete


def _annual_series(period_map: dict[tuple[str, str], float]) -> dict[str, float]:
    """{end: value} for full fiscal-year (350-380 day) periods only."""
    out = {}
    for (start, end), val in period_map.items():
        duration = (pd.Timestamp(end) - pd.Timestamp(start)).days
        if 350 <= duration <= 380:
            out[end] = val
    return out


def _instant_map(facts: dict, tags: list[str]) -> dict[str, float]:
    gaap = facts.get("facts", {}).get("us-gaap", {})
    out: dict[str, float] = {}
    for tag in tags:
        entries = gaap.get(tag, {}).get("units", {}).get("USD", [])
        for e in sorted(entries, key=lambda e: e.get("filed", "")):
            if e.get("form") not in ("10-Q", "10-K", "10-K/A", "10-Q/A"):
                continue
            end = e.get("end")
            if end:
                out[end] = e["val"]
    return out


def _ttm_at(discrete_series: dict[str, float], as_of: pd.Timestamp) -> float | None:
    """Sum of the 4 most recent discrete quarters ending on/before as_of.
    None if fewer than 4 are available -- never looks past as_of."""
    ends = sorted((e for e in discrete_series if pd.Timestamp(e) <= as_of), reverse=True)[:4]
    if len(ends) < 4:
        return None
    return sum(discrete_series[e] for e in ends)


def _instant_at(instant_series: dict[str, float], as_of: pd.Timestamp) -> float | None:
    ends = sorted((e for e in instant_series if pd.Timestamp(e) <= as_of), reverse=True)
    return instant_series[ends[0]] if ends else None


def _score_point(point_ratios: pd.DataFrame, live_ratios: pd.DataFrame) -> dict | None:
    pooled = pd.concat([live_ratios, point_ratios], ignore_index=True, sort=False)
    pooled_metrics = normalize(pooled)
    pooled_scores = score_companies(pooled_metrics, weights=DEFAULT_WEIGHTS)

    ticker = point_ratios.iloc[0]["ticker"]
    row = pooled_scores[pooled_scores["ticker"] == ticker]
    if row.empty:
        return None
    row = row.iloc[0]
    return {
        "score": float(row["lbo_score"]),
        "rank": int(row["rank"]),
        "rank_percentile": float(row["percentile"]),
        "universe_size": int(len(pooled_scores)),
        "ratios_pct": {f: round(float(row[f"{f}_pct"]), 2) for f in FEATURES},
    }


def build_company_timeline(facts: dict, ticker: str, name: str, sector: str,
                            deal_date: pd.Timestamp, live_ratios: pd.DataFrame) -> list[dict]:
    revenue_periods = _period_map(facts, DURATION_TAGS["revenue"])
    oi_periods = _period_map(facts, DURATION_TAGS["operating_income"])
    da_periods = _period_map(facts, DURATION_TAGS["da"])
    ocf_periods = _period_map(facts, DURATION_TAGS["ocf"])
    capex_periods = _period_map(facts, DURATION_TAGS["capex"])

    revenue_q = _discrete_quarterly(revenue_periods)
    oi_q = _discrete_quarterly(oi_periods)
    da_q = _discrete_quarterly(da_periods)
    ocf_q = _discrete_quarterly(ocf_periods)
    capex_q = _discrete_quarterly(capex_periods)

    revenue_annual = _annual_series(revenue_periods)
    oi_annual = _annual_series(oi_periods)
    da_annual = _annual_series(da_periods)
    ebitda_annual = {end: oi_annual[end] + da_annual[end] for end in oi_annual if end in da_annual}

    ltd_noncurrent = _instant_map(facts, INSTANT_TAGS["ltd_noncurrent"])
    ltd_current = _instant_map(facts, INSTANT_TAGS["ltd_current"])
    total_debt_single = _instant_map(facts, INSTANT_TAGS["total_debt_single"])

    def debt_at(as_of: pd.Timestamp) -> float | None:
        nc = _instant_at(ltd_noncurrent, as_of)
        c = _instant_at(ltd_current, as_of)
        if nc is not None or c is not None:
            return (nc or 0) + (c or 0)
        return _instant_at(total_debt_single, as_of)

    points = []
    for months_back in reversed(QUARTER_OFFSETS_MONTHS):  # oldest first
        as_of = deal_date - pd.DateOffset(months=months_back)

        ttm_revenue = _ttm_at(revenue_q, as_of)
        ttm_oi = _ttm_at(oi_q, as_of)
        ttm_da = _ttm_at(da_q, as_of)
        if ttm_revenue is None or ttm_oi is None or ttm_da is None:
            continue  # not enough quarterly history yet as of this point

        ttm_ebitda = ttm_oi + ttm_da
        ttm_ocf = _ttm_at(ocf_q, as_of)
        ttm_capex = _ttm_at(capex_q, as_of)
        ttm_fcf = (ttm_ocf - ttm_capex) if ttm_ocf is not None and ttm_capex is not None else None
        debt = debt_at(as_of)

        rows = [
            {
                "ticker": ticker, "name": name, "sector": sector, "industry": sector,
                "market_cap": np.nan, "fiscal_year": pd.Timestamp(end).toordinal(),
                "period_end": end, "revenue": rev, "ebitda": ebitda_annual[end],
                "total_debt": np.nan, "free_cash_flow": np.nan, "capex": np.nan,
                "working_capital": np.nan, "cash": np.nan,
            }
            for end, rev in revenue_annual.items()
            if pd.Timestamp(end) < as_of and end in ebitda_annual
        ]
        rows.append({
            "ticker": ticker, "name": name, "sector": sector, "industry": sector,
            "market_cap": np.nan, "fiscal_year": as_of.toordinal(),
            "period_end": as_of.date().isoformat(), "revenue": ttm_revenue, "ebitda": ttm_ebitda,
            "total_debt": debt, "free_cash_flow": ttm_fcf, "capex": np.nan,
            "working_capital": np.nan, "cash": np.nan,
        })

        point_ratios = compute_ratios(pd.DataFrame(rows))
        if point_ratios.empty:
            continue

        scored = _score_point(point_ratios, live_ratios)
        if scored is None:
            continue

        raw = point_ratios.iloc[0]
        points.append({
            "date": as_of.date().isoformat(),
            "months_before_deal": months_back,
            "score": scored["score"],
            "rank": scored["rank"],
            "rank_percentile": scored["rank_percentile"],
            "universe_size": scored["universe_size"],
            "ratios_pct": scored["ratios_pct"],
            "raw_ratios": {
                "ebitda_margin": None if pd.isna(raw["ebitda_margin"]) else round(float(raw["ebitda_margin"]), 4),
                "leverage_headroom": None if pd.isna(raw["leverage_headroom"]) else round(float(raw["leverage_headroom"]), 2),
                "fcf_conversion": None if pd.isna(raw["fcf_conversion"]) else round(float(raw["fcf_conversion"]), 4),
                "ebitda_growth_stability": None if pd.isna(raw["ebitda_growth_stability"]) else round(float(raw["ebitda_growth_stability"]), 4),
                "revenue_volatility": None if pd.isna(raw["revenue_volatility"]) else round(float(raw["revenue_volatility"]), 4),
            },
        })

    return points


def build_all_timelines() -> dict:
    if not LIVE_RATIOS_PATH.exists():
        print(f"ERROR: {LIVE_RATIOS_PATH} not found. Run the live pipeline first.", file=sys.stderr)
        sys.exit(1)

    targets = load_historical_targets()
    live_ratios = pd.read_csv(LIVE_RATIOS_PATH)

    timelines = {}
    print(f"Building score replay timelines for {len(targets)} historical LBO targets...")
    for _, row in targets.iterrows():
        facts = fetch_company_facts(row["cik"])
        if facts is None:
            print(f"  [warn] {row['ticker']}: SEC EDGAR fetch failed, skipping")
            continue

        points = build_company_timeline(
            facts, row["ticker"], row["name"], row["sector"], row["deal_announce_date"], live_ratios,
        )
        if not points:
            print(f"  [warn] {row['ticker']}: no usable quarterly history, skipping")
            continue

        timelines[row["ticker"]] = {
            "ticker": row["ticker"],
            "name": row["name"],
            "sector": row["sector"],
            "acquirer": row["acquirer"],
            "deal_announce_date": row["deal_announce_date"].date().isoformat(),
            "points": points,
        }
        print(f"  {row['ticker']}: {len(points)} timeline points "
              f"({points[0]['date']} -> {points[-1]['date']}, deal {row['deal_announce_date'].date()})")

    return timelines


def main():
    timelines = build_all_timelines()
    if not timelines:
        print("ERROR: no score timelines could be built.", file=sys.stderr)
        sys.exit(1)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(timelines, indent=2))
    print(f"\nWrote score timelines for {len(timelines)} companies -> {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
