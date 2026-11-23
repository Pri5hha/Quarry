"""
Backtest Runner
===============
For each historical LBO target (real companies actually taken private by PE
firms), pulls financials from BEFORE the deal was announced -- via SEC EDGAR's
XBRL company-facts API, since these companies are delisted and no longer
served by yfinance -- and runs them through the same ratio engine and scoring
model used for the live universe.

Methodology:
1. Pull up to 5 fiscal years of pre-deal financials per target from SEC EDGAR.
2. Compute the same screening ratios as the live universe (ratio_engine.py).
3. Pool each target's raw ratios into the live universe's ratio table and
   re-run the same sector-relative normalization (preprocessor.py) and the
   same scoring model (scoring_model.py) -- so each historical target is
   scored on a level playing field against real, currently-scored companies,
   using sector peer groups.
4. Report where each real target ranked/percentiled *before* its deal was
   ever announced, and the headline hit-rate: what fraction of real targets
   scored in the top 20% of the universe ahead of time.

Caveat (documented, not hidden): the comparison universe is today's live
mid-cap universe, not the actual universe as of each historical deal date.
This is a practical simplification -- see README for discussion.

Output: data/outputs/backtest_results.json
"""

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from scipy.stats import mannwhitneyu

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from pipeline.ratio_engine import compute_ratios  # noqa: E402
from pipeline.preprocessor import normalize  # noqa: E402
from model.scoring_model import score_companies, DEFAULT_WEIGHTS  # noqa: E402
from backtest.historical_lbo_targets import load_historical_targets  # noqa: E402

TARGETS_PATH = REPO_ROOT / "data" / "raw" / "historical_targets.csv"
LIVE_RATIOS_PATH = REPO_ROOT / "data" / "processed" / "ratios.csv"
OUTPUT_PATH = REPO_ROOT / "data" / "outputs" / "backtest_results.json"
CACHE_DIR = REPO_ROOT / "data" / "raw" / "sec_cache"

SEC_HEADERS = {"User-Agent": "Quarry LBO Screener research@quarry-project.local"}
TOP_PERCENTILE_THRESHOLD = 80.0  # "top 20%" cutoff
MAX_HISTORY_YEARS = 5

DURATION_TAGS = {
    "revenue": ["Revenues", "SalesRevenueNet", "RevenueFromContractWithCustomerExcludingAssessedTax",
                "RevenueFromContractWithCustomerIncludingAssessedTax"],
    "operating_income": ["OperatingIncomeLoss"],
    "da": ["DepreciationDepletionAndAmortization", "DepreciationAmortizationAndAccretionNet",
           "DepreciationAndAmortization"],
    "ocf": ["NetCashProvidedByUsedInOperatingActivities",
            "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"],
    "capex": ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsForCapitalImprovements",
              "PaymentsToAcquireProductiveAssets"],
}
INSTANT_TAGS = {
    "ltd_noncurrent": ["LongTermDebtNoncurrent"],
    "ltd_current": ["LongTermDebtCurrent", "DebtCurrent"],
    "total_debt_single": ["LongTermDebt"],
    "current_assets": ["AssetsCurrent"],
    "current_liabilities": ["LiabilitiesCurrent"],
    "cash": ["CashAndCashEquivalentsAtCarryingValue"],
}


def fetch_company_facts(cik: str) -> dict | None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE_DIR / f"CIK{cik}.json"
    if cache_path.exists():
        return json.loads(cache_path.read_text())

    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
    for attempt in range(3):
        try:
            resp = requests.get(url, headers=SEC_HEADERS, timeout=20)
            if resp.status_code == 200:
                data = resp.json()
                cache_path.write_text(json.dumps(data))
                time.sleep(0.15)  # be polite to SEC's rate limit (10 req/s)
                return data
            time.sleep(0.5)
        except requests.RequestException:
            time.sleep(0.5)
    return None


def _extract_tag_values(facts: dict, tags: list[str], instant: bool) -> dict[str, float]:
    """Return {period_end_date: value}, merging across all candidate tags
    (companies often switch primary XBRL tags over time -- e.g. the ASC 606
    revenue recognition transition around 2018 -- so no single tag covers a
    company's full history). Later tags in `tags` take precedence on overlap;
    within a tag, the latest-filed value wins (restatements overwrite
    originals)."""
    gaap = facts.get("facts", {}).get("us-gaap", {})
    result: dict[str, float] = {}
    for tag in tags:
        entries = gaap.get(tag, {}).get("units", {}).get("USD", [])
        if not entries:
            continue
        entries = sorted(entries, key=lambda e: e.get("filed", ""))
        for e in entries:
            if e.get("form") not in ("10-K", "10-K/A"):
                continue
            end = e.get("end")
            if not end:
                continue
            if instant:
                result[end] = e["val"]
            else:
                start = e.get("start")
                if not start:
                    continue
                duration_days = (pd.Timestamp(end) - pd.Timestamp(start)).days
                if 350 <= duration_days <= 380:
                    result[end] = e["val"]
    return result


def extract_pre_deal_financials(facts: dict, ticker: str, name: str, sector: str,
                                 deal_date: pd.Timestamp, max_years: int = MAX_HISTORY_YEARS) -> list[dict]:
    revenue = _extract_tag_values(facts, DURATION_TAGS["revenue"], instant=False)
    op_income = _extract_tag_values(facts, DURATION_TAGS["operating_income"], instant=False)
    da = _extract_tag_values(facts, DURATION_TAGS["da"], instant=False)
    ocf = _extract_tag_values(facts, DURATION_TAGS["ocf"], instant=False)
    capex = _extract_tag_values(facts, DURATION_TAGS["capex"], instant=False)

    ltd_noncurrent = _extract_tag_values(facts, INSTANT_TAGS["ltd_noncurrent"], instant=True)
    ltd_current = _extract_tag_values(facts, INSTANT_TAGS["ltd_current"], instant=True)
    total_debt_single = _extract_tag_values(facts, INSTANT_TAGS["total_debt_single"], instant=True)
    current_assets = _extract_tag_values(facts, INSTANT_TAGS["current_assets"], instant=True)
    current_liabilities = _extract_tag_values(facts, INSTANT_TAGS["current_liabilities"], instant=True)
    cash = _extract_tag_values(facts, INSTANT_TAGS["cash"], instant=True)

    # Fiscal year-end dates strictly before the deal was announced
    eligible_ends = sorted(
        [d for d in revenue if pd.Timestamp(d) < deal_date],
        reverse=True,
    )[:max_years]

    rows = []
    for end in eligible_ends:
        rev = revenue.get(end)
        if rev is None:
            continue
        oi = op_income.get(end)
        d_a = da.get(end)
        ebitda = (oi + d_a) if oi is not None and d_a is not None else None

        ocf_val = ocf.get(end)
        capex_val = capex.get(end)
        fcf = (ocf_val - capex_val) if ocf_val is not None and capex_val is not None else None

        if end in ltd_noncurrent or end in ltd_current:
            debt = (ltd_noncurrent.get(end, 0) or 0) + (ltd_current.get(end, 0) or 0)
        else:
            debt = total_debt_single.get(end)

        ca, cl = current_assets.get(end), current_liabilities.get(end)
        wc = (ca - cl) if ca is not None and cl is not None else None

        rows.append({
            "ticker": ticker,
            "name": name,
            "sector": sector,
            "industry": sector,
            "market_cap": np.nan,
            "fiscal_year": pd.Timestamp(end).year,
            "period_end": end,
            "revenue": rev,
            "ebitda": ebitda,
            "total_debt": debt,
            "free_cash_flow": fcf,
            "capex": -capex_val if capex_val is not None else None,  # match yfinance sign convention (negative = outflow)
            "working_capital": wc,
            "cash": cash.get(end),
        })
    return rows


def wilson_confidence_interval(successes: int, n: int, z: float = 1.96) -> dict:
    """Wilson score interval for a binomial proportion (default 95% CI, z=1.96).
    More accurate than a normal approximation at small n -- which matters here,
    since n=22 makes a bare hit-rate percentage misleadingly precise-looking on
    its own."""
    if n == 0:
        return {"lower_pct": 0.0, "upper_pct": 0.0, "confidence": 0.95}
    p_hat = successes / n
    denom = 1 + z**2 / n
    center = p_hat + z**2 / (2 * n)
    margin = z * np.sqrt((p_hat * (1 - p_hat) + z**2 / (4 * n)) / n)
    lower = max(0.0, (center - margin) / denom)
    upper = min(1.0, (center + margin) / denom)
    return {"lower_pct": round(100 * lower, 1), "upper_pct": round(100 * upper, 1), "confidence": 0.95}


def sector_gap_significance(per_target: list[dict], focus_sector: str = "Technology") -> dict:
    """Mann-Whitney U test comparing the focus sector's backtest percentiles
    against all other sectors pooled -- turns the observed gap (e.g. Technology
    scoring lower than Healthcare/Basic Materials) into a statistically testable
    claim instead of just two numbers that happen to look different."""
    focus = [t["percentile"] for t in per_target if t["sector"] == focus_sector]
    other = [t["percentile"] for t in per_target if t["sector"] != focus_sector]
    if len(focus) < 2 or len(other) < 2:
        return {
            "test": "Mann-Whitney U", "applicable": False,
            "reason": f"insufficient sample size (n_{focus_sector.lower()}={len(focus)}, n_other={len(other)})",
        }
    stat, p_value = mannwhitneyu(focus, other, alternative="two-sided")
    return {
        "test": "Mann-Whitney U", "applicable": True,
        "group_a": focus_sector, "n_a": len(focus),
        "group_b": "all other sectors", "n_b": len(other),
        "u_statistic": float(stat),
        "p_value": round(float(p_value), 4),
        "significant_at_0.05": bool(p_value < 0.05),
    }


def run_backtest() -> dict:
    if not LIVE_RATIOS_PATH.exists():
        print(f"ERROR: {LIVE_RATIOS_PATH} not found. Run the live pipeline first.", file=sys.stderr)
        sys.exit(1)

    targets = load_historical_targets()
    live_ratios = pd.read_csv(LIVE_RATIOS_PATH)

    all_backtest_financials = []
    per_company_data_quality = {}

    print(f"Pulling pre-deal SEC EDGAR financials for {len(targets)} historical LBO targets...")
    for _, row in targets.iterrows():
        facts = fetch_company_facts(row["cik"])
        if facts is None:
            print(f"  [warn] {row['ticker']}: SEC EDGAR fetch failed, skipping")
            per_company_data_quality[row["ticker"]] = "fetch_failed"
            continue

        fin_rows = extract_pre_deal_financials(
            facts, row["ticker"], row["name"], row["sector"], row["deal_announce_date"],
        )
        if not fin_rows:
            print(f"  [warn] {row['ticker']}: no usable pre-deal financials found, skipping")
            per_company_data_quality[row["ticker"]] = "no_data"
            continue

        all_backtest_financials.extend(fin_rows)
        per_company_data_quality[row["ticker"]] = f"{len(fin_rows)}_years"
        print(f"  {row['ticker']}: {len(fin_rows)} pre-deal fiscal years "
              f"(latest {fin_rows[0]['fiscal_year']}, deal announced {row['deal_announce_date'].date()})")

    if not all_backtest_financials:
        print("ERROR: no historical target financials could be extracted.", file=sys.stderr)
        sys.exit(1)

    backtest_financials_df = pd.DataFrame(all_backtest_financials)
    backtest_ratios = compute_ratios(backtest_financials_df)

    # Pool with the live universe so normalization + scoring happens against
    # real sector peer groups, then run the identical scoring pipeline.
    pooled_ratios = pd.concat([live_ratios, backtest_ratios], ignore_index=True, sort=False)
    pooled_metrics = normalize(pooled_ratios)
    pooled_scores = score_companies(pooled_metrics, weights=DEFAULT_WEIGHTS)

    backtest_tickers = set(backtest_ratios["ticker"])
    results_rows = pooled_scores[pooled_scores["ticker"].isin(backtest_tickers)].copy()

    target_meta = targets.set_index("ticker")
    per_target = []
    for _, r in results_rows.iterrows():
        meta = target_meta.loc[r["ticker"]]
        per_target.append({
            "ticker": r["ticker"],
            "name": r["name"],
            "sector": r["sector"],
            "acquirer": meta["acquirer"],
            "deal_announce_date": meta["deal_announce_date"].date().isoformat(),
            "deal_value_usd_bn": meta["deal_value_usd_bn"],
            "pre_deal_fiscal_year": int(r["fiscal_year"]),
            "lbo_score": float(r["lbo_score"]),
            "rank": int(r["rank"]),
            "percentile": float(r["percentile"]),
            "in_top_20_pct": bool(r["percentile"] >= TOP_PERCENTILE_THRESHOLD),
            "universe_size_at_scoring": int(len(pooled_scores)),
        })

    per_target.sort(key=lambda x: x["percentile"], reverse=True)

    n_scored = len(per_target)
    n_top20 = sum(1 for t in per_target if t["in_top_20_pct"])
    hit_rate_top20 = round(100 * n_top20 / n_scored, 1) if n_scored else 0.0
    median_percentile = round(float(np.median([t["percentile"] for t in per_target])), 1) if n_scored else None
    mean_percentile = round(float(np.mean([t["percentile"] for t in per_target])), 1) if n_scored else None

    by_sector: dict[str, list[float]] = {}
    for t in per_target:
        by_sector.setdefault(t["sector"], []).append(t["percentile"])
    sector_breakdown = {
        sector: {
            "n_targets": len(pcts),
            "median_percentile": round(float(np.median(pcts)), 1),
            "hit_rate_top20_pct": round(100 * sum(1 for p in pcts if p >= TOP_PERCENTILE_THRESHOLD) / len(pcts), 1),
        }
        for sector, pcts in sorted(by_sector.items(), key=lambda kv: -np.median(kv[1]))
    }

    hit_rate_ci = wilson_confidence_interval(n_top20, n_scored)
    gap_significance = sector_gap_significance(per_target, focus_sector="Technology")

    summary = {
        "n_historical_targets_curated": len(targets),
        "n_targets_scored": n_scored,
        "n_targets_skipped": len(targets) - n_scored,
        "hit_rate_top20_pct": hit_rate_top20,
        "hit_rate_top20_pct_ci_95": hit_rate_ci,
        "median_percentile": median_percentile,
        "mean_percentile": mean_percentile,
        "top_percentile_threshold": TOP_PERCENTILE_THRESHOLD,
        "headline_finding": (
            f"{hit_rate_top20}% of real LBO targets scored in the top "
            f"{100 - TOP_PERCENTILE_THRESHOLD:.0f}% of all companies before their deal was announced "
            f"(n={n_scored} targets, {2022}-{2024}; 95% CI "
            f"{hit_rate_ci['lower_pct']}-{hit_rate_ci['upper_pct']}%, Wilson score interval)."
        ),
        "sector_breakdown": sector_breakdown,
        "sector_gap_significance": gap_significance,
        "methodology_note": (
            "Historical target financials are pulled from SEC EDGAR XBRL filings dated "
            "before each deal's announcement date. Scores are computed by pooling each "
            "target's pre-deal ratios into the current live mid-cap universe and re-running "
            "the same sector-relative normalization and scoring model, so comparisons use "
            "consistent sector peer groups. The comparison universe itself reflects today's "
            "live company set rather than the exact universe as of each historical deal date."
        ),
        "scoring_weights": DEFAULT_WEIGHTS,
    }

    return {
        "summary": summary,
        "targets": per_target,
        "data_quality": per_company_data_quality,
    }


def main():
    results = run_backtest()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(results, indent=2))
    print(f"\nWrote backtest results -> {OUTPUT_PATH}")
    print(f"\n{results['summary']['headline_finding']}")
    print(f"Median percentile of real targets: {results['summary']['median_percentile']}")
    gap = results["summary"]["sector_gap_significance"]
    if gap.get("applicable"):
        print(f"Sector gap significance ({gap['group_a']} vs {gap['group_b']}): "
              f"p={gap['p_value']} (Mann-Whitney U, significant={gap['significant_at_0.05']})")


if __name__ == "__main__":
    main()
