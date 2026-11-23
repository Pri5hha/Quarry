"""
Quarry FastAPI Backend
=======================
Serves the outputs of the data pipeline / scoring model / backtest /
optimization stages to the React dashboard.

Endpoints:
  GET /rankings                    Full scored + ranked company list
  GET /backtest                    Backtest hit-rate results
  GET /backtest/timeline/{company} Quarterly score replay timeline for one historical target
  GET /optimal-portfolio           MILP-selected acquisition set
  GET /sensitivity                 Shadow price / duality report
  GET /robust-portfolio            Chance-constrained portfolio
  GET /explain/{company}           SHAP breakdown of a live company's current score
  GET /explain/{company}/{date}    SHAP breakdown at one point on its replay timeline
  GET /key-findings                Auto-generated summary banner content
  GET /health                      Liveness + data-freshness check
"""

import json
import math
import sys
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from model.explainability import explain_live_company, explain_timeline_point  # noqa: E402

SCORES_PATH = REPO_ROOT / "data" / "outputs" / "scores.csv"
BACKTEST_PATH = REPO_ROOT / "data" / "outputs" / "backtest_results.json"
OPTIMAL_PORTFOLIO_PATH = REPO_ROOT / "data" / "outputs" / "optimal_portfolio.json"
SENSITIVITY_PATH = REPO_ROOT / "data" / "outputs" / "sensitivity_report.json"
ROBUST_PORTFOLIO_PATH = REPO_ROOT / "data" / "outputs" / "robust_portfolio.json"
WEIGHT_CALIBRATION_PATH = REPO_ROOT / "data" / "outputs" / "weight_calibration.json"
SCORE_TIMELINE_PATH = REPO_ROOT / "data" / "outputs" / "score_timeline.json"

app = FastAPI(title="Quarry API", description="LBO/PE target screening and capital allocation engine")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _read_json(path: Path) -> dict:
    if not path.exists():
        raise HTTPException(status_code=503, detail=f"{path.name} not found -- run the pipeline first (python run.py)")
    return json.loads(path.read_text())


def _clean_records(df: pd.DataFrame) -> list[dict]:
    """Replace NaN/inf with None so the JSON encoder doesn't choke."""
    df = df.replace([float("inf"), float("-inf")], None)
    records = df.to_dict(orient="records")
    for r in records:
        for k, v in r.items():
            if isinstance(v, float) and math.isnan(v):
                r[k] = None
    return records


@app.get("/health")
def health():
    files = {
        "scores": SCORES_PATH.exists(),
        "backtest": BACKTEST_PATH.exists(),
        "optimal_portfolio": OPTIMAL_PORTFOLIO_PATH.exists(),
        "sensitivity": SENSITIVITY_PATH.exists(),
        "robust_portfolio": ROBUST_PORTFOLIO_PATH.exists(),
        "score_timeline": SCORE_TIMELINE_PATH.exists(),
    }
    return {"status": "ok" if all(files.values()) else "partial", "data_available": files}


@app.get("/rankings")
def rankings():
    if not SCORES_PATH.exists():
        raise HTTPException(status_code=503, detail="scores.csv not found -- run the pipeline first (python run.py)")
    df = pd.read_csv(SCORES_PATH)
    return {
        "n_companies": len(df),
        "n_sectors": int(df["sector"].nunique()),
        "companies": _clean_records(df),
    }


@app.get("/backtest")
def backtest():
    return _read_json(BACKTEST_PATH)


@app.get("/backtest/timeline/{company}")
def backtest_timeline(company: str):
    """Quarterly score replay timeline for one historical LBO target -- how
    its score evolved in the 3 years leading up to its real deal date."""
    timelines = _read_json(SCORE_TIMELINE_PATH)
    entry = timelines.get(company.upper())
    if entry is None:
        raise HTTPException(status_code=404, detail=f"No score timeline for '{company}'")
    return entry


@app.get("/optimal-portfolio")
def optimal_portfolio():
    return _read_json(OPTIMAL_PORTFOLIO_PATH)


@app.get("/sensitivity")
def sensitivity():
    return _read_json(SENSITIVITY_PATH)


@app.get("/robust-portfolio")
def robust_portfolio():
    return _read_json(ROBUST_PORTFOLIO_PATH)


@app.get("/weight-calibration")
def weight_calibration():
    return _read_json(WEIGHT_CALIBRATION_PATH)


@app.get("/explain/{company}")
def explain(company: str):
    """SHAP breakdown of a live-universe company's current score: which
    screening ratios pushed it up or down relative to the average company."""
    result = explain_live_company(company)
    if result is None:
        raise HTTPException(status_code=404, detail=f"No live company found for '{company}'")
    return result


@app.get("/explain/{company}/{date}")
def explain_at_date(company: str, date: str):
    """SHAP breakdown of a historical LBO target's score at one point on its
    backtest replay timeline (date must match one of that company's
    /backtest/timeline/{company} point dates, e.g. '2022-08-14')."""
    result = explain_timeline_point(company, date)
    if result is None:
        raise HTTPException(status_code=404, detail=f"No timeline point for '{company}' at '{date}'")
    return result


@app.get("/key-findings")
def key_findings():
    findings = []

    if BACKTEST_PATH.exists():
        bt = json.loads(BACKTEST_PATH.read_text())
        ci = bt["summary"].get("hit_rate_top20_pct_ci_95")
        findings.append({
            "label": "Backtest hit rate",
            "value": f"{bt['summary']['hit_rate_top20_pct']}%"
                     + (f" (95% CI {ci['lower_pct']}-{ci['upper_pct']}%)" if ci else ""),
            "detail": bt["summary"]["headline_finding"],
        })
        gap = bt["summary"].get("sector_gap_significance", {})
        if gap.get("applicable"):
            findings.append({
                "label": "Sector gap significance",
                "value": f"p = {gap['p_value']}",
                "detail": f"{gap['group_a']} (n={gap['n_a']}) vs {gap['group_b']} (n={gap['n_b']}): "
                          f"Mann-Whitney U test, {'statistically significant' if gap['significant_at_0.05'] else 'not statistically significant'} "
                          f"at the 0.05 level.",
            })
        top_sector = next(iter(bt["summary"]["sector_breakdown"].items()), None)
        if top_sector:
            sector_name, sector_stats = top_sector
            findings.append({
                "label": "Strongest sector signal",
                "value": sector_name,
                "detail": f"Real {sector_name} take-privates had a median percentile of "
                          f"{sector_stats['median_percentile']} ahead of their deals.",
            })

    if OPTIMAL_PORTFOLIO_PATH.exists():
        op = json.loads(OPTIMAL_PORTFOLIO_PATH.read_text())
        findings.append({
            "label": "Optimal portfolio",
            "value": f"{op['n_targets_selected']} targets",
            "detail": f"${op['budget_used_usd']/1e9:.2f}B of ${op['parameters']['budget_usd']/1e9:.0f}B budget "
                      f"deployed ({op['budget_utilization_pct']}% utilized).",
        })

    if SENSITIVITY_PATH.exists():
        sens = json.loads(SENSITIVITY_PATH.read_text())
        if sens.get("headline_findings"):
            findings.append({
                "label": "Sensitivity",
                "value": "Shadow prices",
                "detail": sens["headline_findings"][0],
            })

    if ROBUST_PORTFOLIO_PATH.exists():
        rp = json.loads(ROBUST_PORTFOLIO_PATH.read_text())
        given_up = rp.get("comparison_vs_deterministic", {}).get("expected_value_given_up")
        findings.append({
            "label": "Robust allocation",
            "value": f"{rp['parameters']['target_probability']*100:.0f}% confidence",
            "detail": f"Uncertainty-aware reallocation gives up {given_up} points of expected value "
                      f"to hit a {rp['parameters']['target_probability']*100:.0f}% probability of "
                      f"clearing the target portfolio value." if given_up is not None else "",
        })

    return {"findings": findings}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("dashboard.api:app", host="0.0.0.0", port=8000, reload=False)
