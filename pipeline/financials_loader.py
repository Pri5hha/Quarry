"""
Financials Loader
==================
Pulls financial statement data (revenue, EBITDA, debt, free cash flow, capex,
working capital) for a broad universe of mid-cap public companies via yfinance.

Mid-cap companies (roughly $1B-$15B market cap) are the realistic LBO size
range: large enough to matter, small enough that a PE sponsor can actually
finance the deal without needing a club of five other funds.

Output schema is "long" format: one row per (ticker, fiscal_year). This is
deliberate -- the same schema is produced by backtest/backtest_runner.py from
SEC EDGAR data for historical (delisted) LBO targets, so ratio_engine.py can
operate identically on live-universe data and backtest data.

Output: data/raw/financials.csv
"""

import concurrent.futures
import sys
import time
from pathlib import Path

import pandas as pd
import yfinance as yf

REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = REPO_ROOT / "data" / "raw" / "financials.csv"

# Curated universe of mid-cap US public companies, spread across sectors that
# are realistic PE take-private candidates (industrials, consumer, healthcare
# services, specialty software, materials, distribution). Mega-caps, banks,
# and heavily regulated utilities are intentionally excluded -- they are not
# realistic LBO targets.
TICKER_UNIVERSE = [
    # Industrials
    "ACM", "WSO", "CR", "FLS", "ITT", "XPO", "RXO", "JBHT", "CHRW", "ALLE",
    "AOS", "PNR", "GGG", "NDSN", "HUBB", "ROL", "CLH", "MAS", "LII", "EXPD",
    "UNF", "MLI", "EME", "AAON", "WTS",
    # Consumer Discretionary
    "BBWI", "LKQ", "AN", "KMX", "GPC", "WEN", "DRI", "RL", "TPR", "LEVI",
    "HAS", "WHR", "PII", "BBY", "THO", "LAD", "SAH",
    # Consumer Staples
    "CPB", "CAG", "SJM", "HRL", "MKC", "CHD", "CLX", "TAP", "POST", "BGS",
    "USFD", "SFM",
    # Health Care
    "MOH", "DVA", "PDCO", "BAX", "TFX", "HOLX", "RGEN", "ICUI", "OMCL",
    "CHE", "ENSG", "ACHC", "AMED", "AGL", "AVNS",
    # Information Technology
    "JKHY", "FFIV", "TER", "SSNC", "PTC", "GDDY", "WEX", "EPAM", "CIEN",
    "TYL", "ZBRA", "DBX", "BOX", "PCTY", "QLYS", "ACIW", "BR", "CSGS",
    # Materials
    "RPM", "ASH", "CC", "OLN", "SEE", "SON", "AVY", "PKG", "GEF", "SCL",
    "MOS", "CF", "IOSP",
    # Communication Services
    "LAMR", "IPG", "TDS", "SBGI", "SCHL",
    # Financials (non-bank -- asset managers, insurers, brokers)
    "SF", "EVR", "PJT", "MC", "WU", "AXS", "ORI", "JXN", "NAVI",
    # Energy
    "PR", "MTDR", "CHRD", "RRC", "AR", "DINO", "PBF", "CIVI", "SM",
]
TICKER_UNIVERSE = sorted(set(TICKER_UNIVERSE))

MAX_WORKERS = 8
REQUEST_RETRIES = 2


def _extract_annual_series(statement: pd.DataFrame, candidate_rows: list[str]) -> pd.Series | None:
    """Return the first matching row (indexed by period-end Timestamp) from a
    yfinance financial statement dataframe, trying each candidate label."""
    if statement is None or statement.empty:
        return None
    for row_name in candidate_rows:
        if row_name in statement.index:
            series = statement.loc[row_name]
            if isinstance(series, pd.DataFrame):
                series = series.iloc[0]
            return series
    return None


def fetch_company(ticker: str) -> list[dict]:
    """Fetch up to 5 fiscal years of financials for a single ticker.
    Returns a list of row-dicts (one per fiscal year), or [] on failure."""
    rows: list[dict] = []
    last_err = None
    for attempt in range(REQUEST_RETRIES + 1):
        try:
            t = yf.Ticker(ticker)
            info = t.info
            if not info or info.get("quoteType") is None:
                return []

            name = info.get("shortName") or info.get("longName") or ticker
            sector = info.get("sector") or "Unknown"
            industry = info.get("industry") or "Unknown"
            market_cap = info.get("marketCap")

            income = t.financials
            cashflow = t.cashflow
            balance = t.balance_sheet

            revenue_s = _extract_annual_series(income, ["Total Revenue", "Operating Revenue"])
            ebitda_s = _extract_annual_series(income, ["EBITDA", "Normalized EBITDA"])
            capex_s = _extract_annual_series(cashflow, ["Capital Expenditure", "Capital Expenditure Reported"])
            fcf_s = _extract_annual_series(cashflow, ["Free Cash Flow"])
            ocf_s = _extract_annual_series(cashflow, ["Operating Cash Flow", "Cash Flow From Continuing Operating Activities"])
            debt_s = _extract_annual_series(balance, ["Total Debt"])
            wc_s = _extract_annual_series(balance, ["Working Capital"])
            cash_s = _extract_annual_series(balance, ["Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments"])
            curr_assets_s = _extract_annual_series(balance, ["Current Assets"])
            curr_liab_s = _extract_annual_series(balance, ["Current Liabilities"])

            if revenue_s is None:
                return []

            for period_end in revenue_s.index:
                fiscal_year = period_end.year
                revenue = revenue_s.get(period_end)
                if pd.isna(revenue):
                    continue

                ebitda = ebitda_s.get(period_end) if ebitda_s is not None else None
                capex = capex_s.get(period_end) if capex_s is not None else None
                fcf = fcf_s.get(period_end) if fcf_s is not None else None
                ocf = ocf_s.get(period_end) if ocf_s is not None else None
                debt = debt_s.get(period_end) if debt_s is not None else None
                wc = wc_s.get(period_end) if wc_s is not None else None
                cash = cash_s.get(period_end) if cash_s is not None else None

                if (fcf is None or pd.isna(fcf)) and ocf is not None and capex is not None:
                    if not pd.isna(ocf) and not pd.isna(capex):
                        fcf = ocf + capex  # capex already negative in yfinance cashflow

                if wc is None or pd.isna(wc):
                    ca = curr_assets_s.get(period_end) if curr_assets_s is not None else None
                    cl = curr_liab_s.get(period_end) if curr_liab_s is not None else None
                    if ca is not None and cl is not None and not pd.isna(ca) and not pd.isna(cl):
                        wc = ca - cl

                rows.append({
                    "ticker": ticker,
                    "name": name,
                    "sector": sector,
                    "industry": industry,
                    "market_cap": market_cap,
                    "fiscal_year": fiscal_year,
                    "period_end": period_end.date().isoformat(),
                    "revenue": revenue,
                    "ebitda": ebitda if ebitda is None or pd.isna(ebitda) else ebitda,
                    "total_debt": debt,
                    "free_cash_flow": fcf,
                    "capex": capex,
                    "working_capital": wc,
                    "cash": cash,
                })
            return rows
        except Exception as e:  # noqa: BLE001 -- best-effort scraping across a large universe
            last_err = e
            time.sleep(0.5 * (attempt + 1))
    print(f"  [warn] {ticker}: failed after retries ({last_err})", file=sys.stderr)
    return []


def load_financials(tickers: list[str] | None = None, max_workers: int = MAX_WORKERS) -> pd.DataFrame:
    tickers = tickers or TICKER_UNIVERSE
    print(f"Pulling financials for {len(tickers)} companies via yfinance...")

    all_rows: list[dict] = []
    succeeded, failed = [], []

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
        future_to_ticker = {pool.submit(fetch_company, tk): tk for tk in tickers}
        for i, future in enumerate(concurrent.futures.as_completed(future_to_ticker), 1):
            ticker = future_to_ticker[future]
            rows = future.result()
            if rows:
                all_rows.extend(rows)
                succeeded.append(ticker)
            else:
                failed.append(ticker)
            if i % 10 == 0 or i == len(tickers):
                print(f"  ...{i}/{len(tickers)} processed ({len(succeeded)} ok, {len(failed)} failed)")

    df = pd.DataFrame(all_rows)
    print(f"Done. {len(succeeded)} companies loaded, {len(failed)} failed.")
    if failed:
        print(f"  Failed tickers: {', '.join(failed)}")
    return df


def main():
    df = load_financials()
    if df.empty:
        print("ERROR: no financials data was loaded. Check network access / yfinance status.", file=sys.stderr)
        sys.exit(1)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_PATH, index=False)
    print(f"Wrote {len(df)} rows ({df['ticker'].nunique()} companies) to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
