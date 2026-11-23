"""
Historical LBO Targets
=======================
Curated list of real public companies taken private by PE sponsors (or
PE-led consortia) in roughly the last 5 years. This is the positive-label
set used by the backtest: for each of these, backtest_runner.py pulls
financials from BEFORE the deal was announced (via SEC EDGAR, since these
tickers are delisted and no longer served by yfinance) and checks where the
scoring model would have ranked them ahead of time.

CIKs were resolved against SEC EDGAR's company search
(https://www.sec.gov/cgi-bin/browse-edgar) and cross-checked against
https://data.sec.gov/submissions/CIK##########.json.

Deal dates are the publicly announced signing date of the take-private deal.

Output: data/raw/historical_targets.csv
"""

import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = REPO_ROOT / "data" / "raw" / "historical_targets.csv"

HISTORICAL_LBO_TARGETS = [
    {"ticker": "CDK", "name": "CDK Global, Inc.", "cik": "0001609702",
     "deal_announce_date": "2022-06-13", "acquirer": "Brookfield Business Partners",
     "sector": "Technology", "deal_value_usd_bn": 8.3},
    {"ticker": "ZEN", "name": "Zendesk, Inc.", "cik": "0001463172",
     "deal_announce_date": "2022-06-24", "acquirer": "Hellman & Friedman / Permira",
     "sector": "Technology", "deal_value_usd_bn": 10.2},
    {"ticker": "PLAN", "name": "Anaplan, Inc.", "cik": "0001540755",
     "deal_announce_date": "2022-03-21", "acquirer": "Thoma Bravo",
     "sector": "Technology", "deal_value_usd_bn": 10.7},
    {"ticker": "CTXS", "name": "Citrix Systems, Inc.", "cik": "0000877890",
     "deal_announce_date": "2022-01-31", "acquirer": "Vista Equity Partners / Evergreen Coast Capital",
     "sector": "Technology", "deal_value_usd_bn": 16.5},
    {"ticker": "SAIL", "name": "SailPoint Technologies Holdings, Inc.", "cik": "0001627857",
     "deal_announce_date": "2022-04-11", "acquirer": "Thoma Bravo",
     "sector": "Technology", "deal_value_usd_bn": 6.9},
    {"ticker": "CVET", "name": "Covetrus, Inc.", "cik": "0001752836",
     "deal_announce_date": "2022-08-01", "acquirer": "CD&R / TPG",
     "sector": "Healthcare", "deal_value_usd_bn": 4.0},
    {"ticker": "TEN", "name": "Tenneco Inc.", "cik": "0001024725",
     "deal_announce_date": "2022-02-22", "acquirer": "Apollo Global Management",
     "sector": "Industrials", "deal_value_usd_bn": 7.1},
    {"ticker": "CNR", "name": "Cornerstone Building Brands, Inc.", "cik": "0000883902",
     "deal_announce_date": "2022-03-07", "acquirer": "Clayton, Dubilier & Rice",
     "sector": "Industrials", "deal_value_usd_bn": 5.8},
    {"ticker": "MANT", "name": "ManTech International Corporation", "cik": "0000892537",
     "deal_announce_date": "2022-05-02", "acquirer": "Carlyle Group",
     "sector": "Technology", "deal_value_usd_bn": 4.2},
    {"ticker": "CVT", "name": "Cvent Holding Corp.", "cik": "0001827075",
     "deal_announce_date": "2023-06-15", "acquirer": "Blackstone",
     "sector": "Technology", "deal_value_usd_bn": 4.6},
    {"ticker": "UNVR", "name": "Univar Solutions Inc.", "cik": "0001494319",
     "deal_announce_date": "2023-03-12", "acquirer": "Apollo Global Management",
     "sector": "Basic Materials", "deal_value_usd_bn": 8.1},
    {"ticker": "SYNH", "name": "Syneos Health, Inc.", "cik": "0001610950",
     "deal_announce_date": "2023-05-10", "acquirer": "Elliott / Patient Square / Veritas / Cinven",
     "sector": "Healthcare", "deal_value_usd_bn": 7.1},
    {"ticker": "FOCS", "name": "Focus Financial Partners Inc.", "cik": "0001651052",
     "deal_announce_date": "2023-05-23", "acquirer": "Clayton, Dubilier & Rice",
     "sector": "Financial Services", "deal_value_usd_bn": 7.0},
    {"ticker": "SUMO", "name": "Sumo Logic, Inc.", "cik": "0001643269",
     "deal_announce_date": "2023-12-11", "acquirer": "Francisco Partners",
     "sector": "Technology", "deal_value_usd_bn": 1.7},
    {"ticker": "EVBG", "name": "Everbridge, Inc.", "cik": "0001437352",
     "deal_announce_date": "2024-02-19", "acquirer": "Thoma Bravo",
     "sector": "Technology", "deal_value_usd_bn": 1.8},
    {"ticker": "SQSP", "name": "Squarespace, Inc.", "cik": "0001496963",
     "deal_announce_date": "2024-05-13", "acquirer": "Permira",
     "sector": "Technology", "deal_value_usd_bn": 6.9},
    {"ticker": "MODN", "name": "Model N, Inc.", "cik": "0001118417",
     "deal_announce_date": "2024-05-06", "acquirer": "Vista Equity Partners",
     "sector": "Technology", "deal_value_usd_bn": 1.25},
    {"ticker": "RCM", "name": "R1 RCM Inc.", "cik": "0001910851",
     "deal_announce_date": "2024-05-14", "acquirer": "TowerBrook Capital / Clayton, Dubilier & Rice",
     "sector": "Healthcare", "deal_value_usd_bn": 8.9},
    {"ticker": "INST", "name": "Instructure Holdings, Inc.", "cik": "0001841804",
     "deal_announce_date": "2024-02-05", "acquirer": "KKR",
     "sector": "Technology", "deal_value_usd_bn": 4.8},
    {"ticker": "PRFT", "name": "Perficient, Inc.", "cik": "0001085869",
     "deal_announce_date": "2024-12-18", "acquirer": "EQT",
     "sector": "Technology", "deal_value_usd_bn": 3.0},
    {"ticker": "ENV", "name": "Envestnet, Inc.", "cik": "0001337619",
     "deal_announce_date": "2024-08-29", "acquirer": "Bain Capital",
     "sector": "Financial Services", "deal_value_usd_bn": 4.5},
    {"ticker": "SMAR", "name": "Smartsheet Inc.", "cik": "0001366561",
     "deal_announce_date": "2024-09-23", "acquirer": "Blackstone / Vista Equity Partners",
     "sector": "Technology", "deal_value_usd_bn": 8.4},
]


def load_historical_targets() -> pd.DataFrame:
    df = pd.DataFrame(HISTORICAL_LBO_TARGETS)
    df["deal_announce_date"] = pd.to_datetime(df["deal_announce_date"])
    return df.sort_values("deal_announce_date").reset_index(drop=True)


def main():
    df = load_historical_targets()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_PATH, index=False)
    print(f"Wrote {len(df)} historical LBO targets ({df['deal_announce_date'].dt.year.min()}-"
          f"{df['deal_announce_date'].dt.year.max()}) -> {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
