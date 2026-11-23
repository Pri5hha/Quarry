"""
Explainability (SHAP)
======================
Explains an individual company's LBO attractiveness score using SHAP
(SHapley Additive exPlanations), so the score is defensible -- which
specific screening ratios pushed it up or down relative to the average
company -- rather than a black box.

The default hand-set weighted-sum scoring model (model/scoring_model.py) is
exactly linear in the five sector-percentile ratios: score = sum(weight_i *
pct_i). For a linear model, Shapley values have a closed form --
SHAP_i = weight_i * (x_i - E[x_i]) against a background population -- which
shap.LinearExplainer computes directly and exactly (verified: base_value +
sum(shap values) == the actual score, to float precision).

Two usage modes:
- explain_live_company(ticker): explains a company's current score, reading
  its already-normalized ratios straight from company_metrics.csv.
- explain_timeline_point(ticker, date): explains a historical LBO target's
  score AT one point on its backtest replay timeline (score_history.py),
  reading the stored percentile breakdown from score_timeline.json -- no
  lookahead, no re-computation, just decomposing the score that was already
  computed for that point in time. This is what powers the "why did the
  score move" panel next to the replay timeline in the dashboard.
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import shap

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from model.scoring_model import DEFAULT_WEIGHTS  # noqa: E402

FEATURES = list(DEFAULT_WEIGHTS.keys())

COMPANY_METRICS_PATH = REPO_ROOT / "data" / "processed" / "company_metrics.csv"
TIMELINE_PATH = REPO_ROOT / "data" / "outputs" / "score_timeline.json"

FEATURE_LABELS = {
    "ebitda_margin": "EBITDA Margin",
    "leverage_headroom": "Leverage Headroom",
    "fcf_conversion": "FCF Conversion",
    "ebitda_growth_stability": "EBITDA Stability",
    "revenue_volatility": "Revenue Predictability",
}


def _linear_shap(coef: np.ndarray, background: np.ndarray, row: np.ndarray) -> tuple[np.ndarray, float]:
    masker = shap.maskers.Independent(background)
    explainer = shap.LinearExplainer((coef, 0.0), masker)
    shap_values = explainer.shap_values(row.reshape(1, -1))[0]
    return shap_values, float(explainer.expected_value)


def _explain_pct_row(pct_values: dict[str, float], background_df: pd.DataFrame) -> dict:
    coef = np.array([DEFAULT_WEIGHTS[f] for f in FEATURES])
    background = background_df[[f"{f}_pct" for f in FEATURES]].fillna(50.0).values
    row = np.array([pct_values[f] if pct_values[f] is not None else 50.0 for f in FEATURES])

    shap_values, base_value = _linear_shap(coef, background, row)

    contributions = [
        {
            "ratio": f,
            "label": FEATURE_LABELS[f],
            "value_pct": round(float(pct_values[f]), 1) if pct_values[f] is not None else None,
            "weight": DEFAULT_WEIGHTS[f],
            "shap_value": round(float(sv), 3),
        }
        for f, sv in zip(FEATURES, shap_values)
    ]
    contributions.sort(key=lambda c: abs(c["shap_value"]), reverse=True)

    return {
        "base_value": round(base_value, 2),
        "predicted_score": round(base_value + float(shap_values.sum()), 2),
        "contributions": contributions,
    }


def explain_live_company(ticker: str) -> dict | None:
    """SHAP breakdown of a live-universe company's current score."""
    if not COMPANY_METRICS_PATH.exists():
        return None
    metrics = pd.read_csv(COMPANY_METRICS_PATH)
    row = metrics[metrics["ticker"].str.upper() == ticker.upper()]
    if row.empty:
        return None
    row = row.iloc[0]

    pct_values = {f: row[f"{f}_pct"] for f in FEATURES}
    explanation = _explain_pct_row(pct_values, metrics)
    explanation.update({
        "ticker": row["ticker"], "name": row["name"], "sector": row["sector"], "as_of": "current",
    })
    return explanation


def explain_timeline_point(ticker: str, date: str) -> dict | None:
    """SHAP breakdown of a historical LBO target's score at one point on its
    backtest replay timeline (see backtest/score_history.py)."""
    if not TIMELINE_PATH.exists() or not COMPANY_METRICS_PATH.exists():
        return None
    timelines = json.loads(TIMELINE_PATH.read_text())
    entry = timelines.get(ticker.upper())
    if not entry:
        return None
    point = next((p for p in entry["points"] if p["date"] == date), None)
    if point is None:
        return None

    background = pd.read_csv(COMPANY_METRICS_PATH)
    explanation = _explain_pct_row(point["ratios_pct"], background)
    explanation.update({
        "ticker": entry["ticker"], "name": entry["name"], "sector": entry["sector"],
        "as_of": date, "months_before_deal": point["months_before_deal"],
        "actual_score": point["score"],
    })
    return explanation


def main():
    """Smoke-test explainability against a handful of live companies."""
    if not COMPANY_METRICS_PATH.exists():
        print(f"ERROR: {COMPANY_METRICS_PATH} not found. Run the live pipeline first.", file=sys.stderr)
        sys.exit(1)

    metrics = pd.read_csv(COMPANY_METRICS_PATH)
    sample = metrics.sort_values("ticker").head(3)["ticker"].tolist()
    for ticker in sample:
        result = explain_live_company(ticker)
        print(f"\n{ticker}: predicted_score={result['predicted_score']} (base={result['base_value']})")
        for c in result["contributions"]:
            sign = "+" if c["shap_value"] >= 0 else ""
            print(f"  {c['label']:24s} {sign}{c['shap_value']:6.2f}  (value_pct={c['value_pct']})")


if __name__ == "__main__":
    main()
