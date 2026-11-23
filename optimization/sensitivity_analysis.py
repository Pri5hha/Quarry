"""
Sensitivity Analysis
=====================
Extracts shadow prices / dual values for the budget and diversification
constraints from the allocation problem.

MILPs don't have well-defined dual values once variables are integer, so the
standard approach is used here: solve the LP relaxation (binary variables
relaxed to [0,1]) of the identical problem and read off the dual value on
each constraint from the simplex solution. This is an approximation of the
true MILP shadow prices, but a standard and interpretable one -- documented
as such in the output.

Two complementary views are reported:
1. Shadow prices from the LP relaxation:
   - Budget dual: marginal increase in portfolio value per additional
     dollar of budget (reported per $1M for readability).
   - Diversification duals: marginal increase in portfolio value per
     additional slot allowed in each sector's cap (for sectors where the
     cap actually binds).
2. A direct MILP-vs-MILP comparison: total value with diversification
   constraints vs. total value if they were removed entirely -- "the cost
   of diversification" in absolute forgone value, which doesn't rely on the
   LP-relaxation approximation.

Output: data/outputs/sensitivity_report.json
"""

import json
import sys
from pathlib import Path

import pandas as pd
import pulp

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from optimization.allocation_optimizer import (  # noqa: E402
    build_acquisition_costs, solve_allocation, DEFAULT_BUDGET_USD,
    DEFAULT_MAX_PER_SECTOR, DEFAULT_TAKEOUT_PREMIUM,
)

SCORES_PATH = REPO_ROOT / "data" / "outputs" / "scores.csv"
OUTPUT_PATH = REPO_ROOT / "data" / "outputs" / "sensitivity_report.json"


def solve_lp_relaxation(
    scores: pd.DataFrame,
    budget: float = DEFAULT_BUDGET_USD,
    max_per_sector: int = DEFAULT_MAX_PER_SECTOR,
    takeout_premium: float = DEFAULT_TAKEOUT_PREMIUM,
) -> dict:
    df = scores.dropna(subset=["market_cap", "lbo_score"]).reset_index(drop=True)
    df["acquisition_cost"] = build_acquisition_costs(df, takeout_premium)

    prob = pulp.LpProblem("Quarry_LBO_Allocation_LP_Relaxation", pulp.LpMaximize)
    x = {i: pulp.LpVariable(f"x_{i}", lowBound=0, upBound=1, cat="Continuous") for i in df.index}

    value = {i: df.loc[i, "lbo_score"] for i in df.index}
    prob += pulp.lpSum(value[i] * x[i] for i in df.index), "Total_Portfolio_Value"

    prob += pulp.lpSum(df.loc[i, "acquisition_cost"] * x[i] for i in df.index) <= budget, "Budget"

    sector_constraint_names = {}
    for sector, group in df.groupby("sector"):
        cname = f"Diversification_{sector.replace(' ', '_')}"
        prob += pulp.lpSum(x[i] for i in group.index) <= max_per_sector, cname
        sector_constraint_names[cname] = sector

    solver = pulp.PULP_CBC_CMD(msg=0)
    prob.solve(solver)

    budget_dual = prob.constraints["Budget"].pi
    budget_slack = prob.constraints["Budget"].slack

    sector_duals = []
    for cname, sector in sector_constraint_names.items():
        constraint = prob.constraints[cname]
        n_in_sector = (df["sector"] == sector).sum()
        sector_duals.append({
            "sector": sector,
            "cap": max_per_sector,
            "n_candidates_in_sector": int(n_in_sector),
            "binding": abs(constraint.slack) < 1e-6,
            "shadow_price": round(constraint.pi, 4) if constraint.pi is not None else None,
            "slack": round(constraint.slack, 4) if constraint.slack is not None else None,
        })
    sector_duals.sort(key=lambda d: (-d["binding"], -(d["shadow_price"] or 0)))

    return {
        "lp_objective_value": round(pulp.value(prob.objective), 2),
        "budget_shadow_price_per_dollar": round(budget_dual, 8) if budget_dual is not None else None,
        "budget_shadow_price_per_1m": round(budget_dual * 1e6, 4) if budget_dual is not None else None,
        "budget_binding": abs(budget_slack) < 1e-6 if budget_slack is not None else None,
        "sector_diversification_duals": sector_duals,
    }


def diversification_cost_comparison(
    scores: pd.DataFrame,
    budget: float = DEFAULT_BUDGET_USD,
    max_per_sector: int = DEFAULT_MAX_PER_SECTOR,
    takeout_premium: float = DEFAULT_TAKEOUT_PREMIUM,
) -> dict:
    with_diversification = solve_allocation(
        scores, budget=budget, max_per_sector=max_per_sector, takeout_premium=takeout_premium,
    )
    n_companies = scores["ticker"].nunique()
    without_diversification = solve_allocation(
        scores, budget=budget, max_per_sector=n_companies, takeout_premium=takeout_premium,
    )

    forgone_value = without_diversification["total_portfolio_value"] - with_diversification["total_portfolio_value"]
    forgone_pct = (
        100 * forgone_value / without_diversification["total_portfolio_value"]
        if without_diversification["total_portfolio_value"] else None
    )

    return {
        "with_diversification": {
            "max_per_sector": max_per_sector,
            "total_value": with_diversification["total_portfolio_value"],
            "n_selected": with_diversification["n_targets_selected"],
        },
        "without_diversification": {
            "max_per_sector": n_companies,
            "total_value": without_diversification["total_portfolio_value"],
            "n_selected": without_diversification["n_targets_selected"],
        },
        "forgone_value_from_diversification": round(forgone_value, 2),
        "forgone_value_pct": round(forgone_pct, 2) if forgone_pct is not None else None,
    }


def run_sensitivity_analysis(
    scores: pd.DataFrame,
    budget: float = DEFAULT_BUDGET_USD,
    max_per_sector: int = DEFAULT_MAX_PER_SECTOR,
    takeout_premium: float = DEFAULT_TAKEOUT_PREMIUM,
) -> dict:
    lp = solve_lp_relaxation(scores, budget, max_per_sector, takeout_premium)
    div_cost = diversification_cost_comparison(scores, budget, max_per_sector, takeout_premium)

    binding_sectors = [d for d in lp["sector_diversification_duals"] if d["binding"]]

    headline = []
    if lp["budget_shadow_price_per_1m"]:
        headline.append(
            f"An additional $1M of budget would increase total portfolio value by "
            f"~{lp['budget_shadow_price_per_1m']:.3f} score-points (LP-relaxation shadow price)."
        )
    if div_cost["forgone_value_from_diversification"] > 0:
        headline.append(
            f"The max-{max_per_sector}-per-sector diversification constraint costs "
            f"{div_cost['forgone_value_from_diversification']:.1f} points of total portfolio value "
            f"({div_cost['forgone_value_pct']:.1f}%) versus the unconstrained-by-sector optimum."
        )
    if binding_sectors:
        top_binding = binding_sectors[0]
        headline.append(
            f"The {top_binding['sector']} sector cap is binding "
            f"({top_binding['n_candidates_in_sector']} eligible candidates vs. cap of {max_per_sector})."
        )

    return {
        "parameters": {"budget_usd": budget, "max_per_sector": max_per_sector, "takeout_premium": takeout_premium},
        "lp_relaxation_shadow_prices": lp,
        "diversification_cost": div_cost,
        "headline_findings": headline,
        "methodology_note": (
            "Shadow prices are read from the LP relaxation of the MILP (binary selection "
            "variables relaxed to [0,1]); this is a standard approximation since integer "
            "programs don't have exact dual values. The diversification cost figure instead "
            "compares two fully-solved MILPs (with vs. without the sector cap) and so is exact, "
            "not an approximation."
        ),
    }


def main():
    if not SCORES_PATH.exists():
        print(f"ERROR: {SCORES_PATH} not found. Run model/scoring_model.py first.", file=sys.stderr)
        sys.exit(1)

    scores = pd.read_csv(SCORES_PATH)
    report = run_sensitivity_analysis(scores)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(report, indent=2))

    print(f"Wrote {OUTPUT_PATH}\n")
    for line in report["headline_findings"]:
        print(f"- {line}")


if __name__ == "__main__":
    main()
