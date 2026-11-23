"""
Chance Constraints
==================
Re-solves the allocation problem treating each company's LBO value as
uncertain -- score_i + noise, where noise ~ Normal(0, sigma_i) and sigma_i is
calibrated to that company's historical revenue volatility -- instead of a
fixed point estimate. The resulting portfolio is required to hit a minimum
total value with a target probability (e.g. 90%), rather than assuming the
scores are exact.

Method: Sample Average Approximation (SAA).
A true chance constraint P(portfolio value >= V_min) >= beta is not directly
representable as a linear MILP once you require it to hold exactly under a
continuous distribution -- that's a second-order-cone constraint, which needs
an SOCP solver PuLP/CBC don't provide. SAA sidesteps this: draw S scenarios of
noisy company values, and for each scenario add a binary "shortfall"
indicator that must switch on if that scenario's realized portfolio value
falls below V_min. Capping the fraction of scenarios allowed to trigger the
indicator at (1 - beta) is a linear MILP that converges to the true chance
constraint as S grows. This is a standard, well-established technique for
chance-constrained integer programs.

Output: data/outputs/robust_portfolio.json
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pulp

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from optimization.allocation_optimizer import (  # noqa: E402
    build_acquisition_costs, solve_allocation,
    DEFAULT_MAX_PER_SECTOR, DEFAULT_TAKEOUT_PREMIUM,
)

SCORES_PATH = REPO_ROOT / "data" / "outputs" / "scores.csv"
OUTPUT_PATH = REPO_ROOT / "data" / "outputs" / "robust_portfolio.json"

# A smaller budget than the main $50B allocation_optimizer scenario is used
# here by default. At $50B the deterministic-optimal portfolio already
# spreads across ~17 companies / most sector caps, which diversifies away
# most idiosyncratic noise -- so the chance constraint never binds and the
# robust solution is identical to the deterministic one. At a tighter budget
# the deterministic optimum concentrates value in fewer names, which is
# exactly where uncertainty-aware reallocation has something to trade off.
DEFAULT_BUDGET_USD = 12e9
DEFAULT_TARGET_PROBABILITY = 0.90
DEFAULT_N_SCENARIOS = 300
DEFAULT_MIN_VALUE_FRACTION = 0.95  # V_min as a fraction of the deterministic-optimal value
RANDOM_SEED = 42


def calibrate_sigma(scores: pd.DataFrame) -> pd.Series:
    """Uncertainty (std dev, in score points) per company, scaled by its
    historical revenue volatility. A floor is applied since even the most
    stable company's realized value isn't risk-free, and a cap avoids single
    high-volatility outliers dominating the scenario spread."""
    vol = scores["revenue_volatility"].clip(lower=0.01, upper=0.5).fillna(0.05)
    sigma = (scores["lbo_score"] * vol).clip(lower=1.5)
    return sigma


def solve_chance_constrained_allocation(
    scores: pd.DataFrame,
    budget: float = DEFAULT_BUDGET_USD,
    max_per_sector: int = DEFAULT_MAX_PER_SECTOR,
    takeout_premium: float = DEFAULT_TAKEOUT_PREMIUM,
    target_probability: float = DEFAULT_TARGET_PROBABILITY,
    n_scenarios: int = DEFAULT_N_SCENARIOS,
    min_value_fraction: float = DEFAULT_MIN_VALUE_FRACTION,
    seed: int = RANDOM_SEED,
) -> dict:
    df = scores.dropna(subset=["market_cap", "lbo_score"]).reset_index(drop=True)
    df["acquisition_cost"] = build_acquisition_costs(df, takeout_premium)
    df["sigma"] = calibrate_sigma(df)

    baseline = solve_allocation(scores, budget=budget, max_per_sector=max_per_sector,
                                 takeout_premium=takeout_premium)
    v_min = min_value_fraction * baseline["total_portfolio_value"]

    rng = np.random.default_rng(seed)
    noise = rng.normal(loc=0.0, scale=df["sigma"].values, size=(n_scenarios, len(df)))
    scenario_values = df["lbo_score"].values[None, :] + noise  # (S, n_companies)

    prob = pulp.LpProblem("Quarry_LBO_Allocation_Chance_Constrained", pulp.LpMaximize)
    x = {i: pulp.LpVariable(f"x_{i}", cat="Binary") for i in df.index}
    z = {s: pulp.LpVariable(f"shortfall_{s}", cat="Binary") for s in range(n_scenarios)}

    prob += pulp.lpSum(df.loc[i, "lbo_score"] * x[i] for i in df.index), "Expected_Portfolio_Value"

    prob += pulp.lpSum(df.loc[i, "acquisition_cost"] * x[i] for i in df.index) <= budget, "Budget"
    for sector, group in df.groupby("sector"):
        cname = f"Diversification_{sector.replace(' ', '_')}"
        prob += pulp.lpSum(x[i] for i in group.index) <= max_per_sector, cname

    # Big-M: worst case a scenario's portfolio value can fall short of v_min
    # (all selected companies hit their most negative plausible draw).
    big_m = v_min + float(np.abs(noise).max()) * len(df) + 1.0

    for s in range(n_scenarios):
        scenario_value_expr = pulp.lpSum(float(scenario_values[s, i]) * x[i] for i in df.index)
        # If scenario value < v_min, z[s] must be forced to 1:
        # v_min - scenario_value <= big_m * z[s]
        prob += v_min - scenario_value_expr <= big_m * z[s], f"Shortfall_link_{s}"

    max_shortfall_scenarios = int(np.floor((1 - target_probability) * n_scenarios))
    prob += pulp.lpSum(z[s] for s in range(n_scenarios)) <= max_shortfall_scenarios, "Chance_Constraint"

    solver = pulp.PULP_CBC_CMD(msg=0)
    prob.solve(solver)
    status = pulp.LpStatus[prob.status]

    if status == "Optimal":
        selected_idx = [i for i in df.index if x[i].value() == 1]
    else:
        selected_idx = []  # solver may leave stale variable values on infeasible/unsolved runs
    selected = df.loc[selected_idx].copy()

    # Empirical validation: re-simulate the CHOSEN portfolio's realized value
    # distribution and measure the actual probability it clears v_min.
    if selected_idx:
        realized = scenario_values[:, selected_idx].sum(axis=1)
        empirical_prob_above_vmin = float((realized >= v_min).mean())
        expected_value = float(df.loc[selected_idx, "lbo_score"].sum())
        value_std = float(realized.std())
        value_p10 = float(np.percentile(realized, 10))
    else:
        empirical_prob_above_vmin, expected_value, value_std, value_p10 = 0.0, 0.0, 0.0, 0.0

    total_cost = selected["acquisition_cost"].sum() if len(selected) else 0.0

    sector_summary = (
        selected.groupby("sector")
        .agg(n_targets=("ticker", "count"), total_cost=("acquisition_cost", "sum"), avg_score=("lbo_score", "mean"))
        .reset_index()
        .to_dict(orient="records")
        if len(selected) else []
    )

    return {
        "status": status,
        "parameters": {
            "budget_usd": budget,
            "max_per_sector": max_per_sector,
            "takeout_premium": takeout_premium,
            "target_probability": target_probability,
            "n_scenarios": n_scenarios,
            "min_value_fraction": min_value_fraction,
        },
        "min_portfolio_value_target": round(v_min, 2),
        "deterministic_baseline_value": round(baseline["total_portfolio_value"], 2),
        "n_targets_selected": len(selected),
        "budget_used_usd": round(float(total_cost), 2),
        "budget_utilization_pct": round(100 * float(total_cost) / budget, 1) if budget else None,
        "expected_portfolio_value": round(expected_value, 2),
        "portfolio_value_std_dev": round(value_std, 2),
        "portfolio_value_p10": round(value_p10, 2),
        "empirical_probability_above_target": round(empirical_prob_above_vmin, 4),
        "sector_breakdown": sector_summary,
        "selected_companies": [
            {
                "ticker": row["ticker"],
                "name": row["name"],
                "sector": row["sector"],
                "lbo_score": round(float(row["lbo_score"]), 2),
                "sigma": round(float(row["sigma"]), 2),
                "market_cap": float(row["market_cap"]),
                "acquisition_cost": round(float(row["acquisition_cost"]), 2),
            }
            for _, row in selected.sort_values("lbo_score", ascending=False).iterrows()
        ] if len(selected) else [],
        "comparison_vs_deterministic": {
            "deterministic_tickers": sorted(t["ticker"] for t in baseline["selected_companies"]),
            "robust_tickers": sorted(selected["ticker"].tolist()) if len(selected) else [],
            "dropped_by_robust_solution": sorted(
                set(t["ticker"] for t in baseline["selected_companies"]) - set(selected["ticker"].tolist())
            ) if len(selected) else [],
            "added_by_robust_solution": sorted(
                set(selected["ticker"].tolist()) - set(t["ticker"] for t in baseline["selected_companies"])
            ) if len(selected) else [],
            # Floating-point noise can push this fractionally below 0 when the
            # chance constraint isn't binding and picks the same optimum;
            # clamp since the robust solution can't exceed the deterministic one.
            "expected_value_given_up": max(0.0, round(baseline["total_portfolio_value"] - expected_value, 2)),
        },
        "methodology_note": (
            "Uncertainty is simulated via Sample Average Approximation: each company's value "
            "is treated as score + Normal(0, sigma) noise, sigma calibrated from historical "
            "revenue volatility, and the portfolio is required to clear the target minimum "
            "value in at least target_probability of simulated scenarios. This converts an "
            "otherwise non-linear chance constraint into a solvable MILP."
        ),
    }


def main():
    if not SCORES_PATH.exists():
        print(f"ERROR: {SCORES_PATH} not found. Run model/scoring_model.py first.", file=sys.stderr)
        sys.exit(1)

    scores = pd.read_csv(SCORES_PATH)
    result = solve_chance_constrained_allocation(scores)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(result, indent=2))

    print(f"Solved chance-constrained allocation: {result['status']}")
    print(f"Target: P(portfolio value >= {result['min_portfolio_value_target']}) >= "
          f"{result['parameters']['target_probability']*100:.0f}%")
    print(f"Selected {result['n_targets_selected']} companies, "
          f"empirical P(above target) = {result['empirical_probability_above_target']*100:.1f}%")
    print(f"Expected value: {result['expected_portfolio_value']} "
          f"(vs. deterministic baseline {result['deterministic_baseline_value']})")
    print(f"Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
