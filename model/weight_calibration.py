"""
Weight Calibration (optional)
==============================
Instead of the hand-set weights in scoring_model.py, learn data-driven
weights from a logistic regression trained on the historical backtest set:
positive label = real company that was actually taken private by a PE
sponsor; negative label = everything else in the live mid-cap universe.

The regression is fit on the same sector-normalized z-scored features the
hand-set model uses, so the two weight schemes are directly comparable.
Coefficients are converted to a weight vector (absolute value, normalized to
sum to 1) so they can be dropped straight into score_companies().

Caveat (documented, not hidden): with only ~22 positive examples, this is a
small, tech-heavy sample and the comparison below is evaluated in-sample
(same data used to fit and to score) -- so it is illustrative of the general
approach, not a rigorous out-of-sample validation. Read the comparison as
"how differently would a data-driven weighting scheme have screened these
deals," not as proof the calibrated weights generalize.

Output: data/outputs/weight_calibration.json
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from pipeline.ratio_engine import compute_ratios  # noqa: E402
from pipeline.preprocessor import normalize, SCREENING_RATIOS  # noqa: E402
from model.scoring_model import score_companies, DEFAULT_WEIGHTS  # noqa: E402
from backtest.historical_lbo_targets import load_historical_targets  # noqa: E402
from backtest.backtest_runner import (  # noqa: E402
    fetch_company_facts, extract_pre_deal_financials, TOP_PERCENTILE_THRESHOLD,
)

LIVE_RATIOS_PATH = REPO_ROOT / "data" / "processed" / "ratios.csv"
OUTPUT_PATH = REPO_ROOT / "data" / "outputs" / "weight_calibration.json"

FEATURES = list(SCREENING_RATIOS.keys())


def _build_labeled_dataset() -> tuple[pd.DataFrame, pd.Series]:
    """Pools the live universe with historical targets (same as
    backtest_runner) and returns (normalized_metrics, label)."""
    live_ratios = pd.read_csv(LIVE_RATIOS_PATH)
    targets = load_historical_targets()

    all_backtest_financials = []
    for _, row in targets.iterrows():
        facts = fetch_company_facts(row["cik"])
        if facts is None:
            continue
        fin_rows = extract_pre_deal_financials(
            facts, row["ticker"], row["name"], row["sector"], row["deal_announce_date"],
        )
        all_backtest_financials.extend(fin_rows)

    backtest_ratios = compute_ratios(pd.DataFrame(all_backtest_financials))
    pooled_ratios = pd.concat([live_ratios, backtest_ratios], ignore_index=True, sort=False)
    pooled_metrics = normalize(pooled_ratios)

    label = pooled_metrics["ticker"].isin(set(backtest_ratios["ticker"])).astype(int)
    return pooled_metrics, label


def calibrate_weights(metrics: pd.DataFrame, label: pd.Series) -> dict:
    X = metrics[[f"{f}_z" for f in FEATURES]].values
    y = label.values

    clf = LogisticRegression(class_weight="balanced", max_iter=2000)
    clf.fit(X, y)

    coefs = clf.coef_[0]
    signed = dict(zip(FEATURES, coefs.round(4)))

    abs_coefs = np.abs(coefs)
    norm_weights = abs_coefs / abs_coefs.sum()
    calibrated_weights = {f: round(float(w), 4) for f, w in zip(FEATURES, norm_weights)}

    train_auc = roc_auc_score(y, clf.predict_proba(X)[:, 1])

    return {
        "calibrated_weights": calibrated_weights,
        "signed_coefficients": signed,
        "train_auc": round(float(train_auc), 3),
        "n_positive": int(y.sum()),
        "n_negative": int((y == 0).sum()),
    }


def compare_backtest_performance(metrics: pd.DataFrame, label: pd.Series,
                                  calibrated_weights: dict) -> dict:
    backtest_tickers = set(metrics.loc[label == 1, "ticker"])

    def eval_weights(weights: dict) -> dict:
        scored = score_companies(metrics, weights=weights)
        target_rows = scored[scored["ticker"].isin(backtest_tickers)]
        pct = target_rows["percentile"]
        return {
            "hit_rate_top20_pct": round(100 * (pct >= TOP_PERCENTILE_THRESHOLD).mean(), 1),
            "median_percentile": round(float(pct.median()), 1),
            "mean_percentile": round(float(pct.mean()), 1),
        }

    return {
        "hand_set_weights": {"weights": DEFAULT_WEIGHTS, **eval_weights(DEFAULT_WEIGHTS)},
        "calibrated_weights": {"weights": calibrated_weights, **eval_weights(calibrated_weights)},
    }


def main():
    if not LIVE_RATIOS_PATH.exists():
        print(f"ERROR: {LIVE_RATIOS_PATH} not found. Run the live pipeline first.", file=sys.stderr)
        sys.exit(1)

    print("Building labeled dataset (live universe + historical LBO targets)...")
    metrics, label = _build_labeled_dataset()
    print(f"  {len(metrics)} companies, {label.sum()} positive (real LBO targets)")

    print("Fitting logistic regression to calibrate weights...")
    calibration = calibrate_weights(metrics, label)

    print("Comparing hand-set vs calibrated weights on backtest hit-rate...")
    comparison = compare_backtest_performance(metrics, label, calibration["calibrated_weights"])

    result = {**calibration, "backtest_comparison": comparison,
              "caveat": ("Evaluated in-sample on a small (~22 positive), tech-heavy sample. "
                         "Treat as illustrative of the calibration approach, not a validated "
                         "generalization claim.")}

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(result, indent=2))

    print(f"\nWrote {OUTPUT_PATH}")
    print(f"Train AUC: {calibration['train_auc']}")
    print("\nHand-set weights backtest:", comparison["hand_set_weights"]["hit_rate_top20_pct"], "% top-20 hit rate")
    print("Calibrated weights backtest:", comparison["calibrated_weights"]["hit_rate_top20_pct"], "% top-20 hit rate")
    print("\nCalibrated weights:")
    for f, w in calibration["calibrated_weights"].items():
        print(f"  {f}: {w}")


if __name__ == "__main__":
    main()
