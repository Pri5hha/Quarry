"""
Allocation Optimizer
=====================
Given a fixed acquisition budget and a diversification constraint (max N
targets per sector), selects the subset of scored companies that maximizes
total LBO attractiveness value, using a binary-knapsack-style MILP solved
with PuLP (CBC backend).

Acquisition cost per company is modeled as current market cap plus a
takeout premium (PE sponsors virtually always pay a premium to the
undisturbed public price -- typically 25-35% in recent take-privates).

Objective (configurable): maximize sum(score_i * x_i) -- i.e. build the
highest-quality portfolio of targets the budget can buy. A size-weighted
variant (maximize sum(score_i * market_cap_i * x_i), rewarding scale as
well as quality) is available via `objective_mode="size_weighted"`.

Output: data/outputs/optimal_portfolio.json
"""

import json
import sys
from pathlib import Path

import pandas as pd
import pulp

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

SCORES_PATH = REPO_ROOT / "data" / "outputs" / "scores.csv"
OUTPUT_PATH = REPO_ROOT / "data" / "outputs" / "optimal_portfolio.json"

DEFAULT_BUDGET_USD = 50e9
DEFAULT_TAKEOUT_PREMIUM = 0.30
DEFAULT_MAX_PER_SECTOR = 3


def build_acquisition_costs(scores: pd.DataFrame, takeout_premium: float = DEFAULT_TAKEOUT_PREMIUM) -> pd.Series:
    return scores["market_cap"] * (1 + takeout_premium)


def solve_allocation(
    scores: pd.DataFrame,
    budget: float = DEFAULT_BUDGET_USD,
    max_per_sector: int = DEFAULT_MAX_PER_SECTOR,
    takeout_premium: float = DEFAULT_TAKEOUT_PREMIUM,
    objective_mode: str = "score_sum",
) -> dict:
    df = scores.dropna(subset=["market_cap", "lbo_score"]).reset_index(drop=True)
    df["acquisition_cost"] = build_acquisition_costs(df, takeout_premium)

    prob = pulp.LpProblem("Quarry_LBO_Allocation", pulp.LpMaximize)
    x = {i: pulp.LpVariable(f"x_{i}", cat="Binary") for i in df.index}

    if objective_mode == "size_weighted":
        value = {i: df.loc[i, "lbo_score"] * df.loc[i, "market_cap"] / 1e9 for i in df.index}
    else:
        value = {i: df.loc[i, "lbo_score"] for i in df.index}

    prob += pulp.lpSum(value[i] * x[i] for i in df.index), "Total_Portfolio_Value"

    budget_constraint = pulp.lpSum(df.loc[i, "acquisition_cost"] * x[i] for i in df.index) <= budget
    prob += budget_constraint, "Budget"

    sector_constraints = {}
    for sector, group in df.groupby("sector"):
        cname = f"Diversification_{sector.replace(' ', '_')}"
        constraint = pulp.lpSum(x[i] for i in group.index) <= max_per_sector
        prob += constraint, cname
        sector_constraints[sector] = cname

    solver = pulp.PULP_CBC_CMD(msg=0)
    prob.solve(solver)

    status = pulp.LpStatus[prob.status]
    selected_idx = [i for i in df.index if x[i].value() == 1]
    selected = df.loc[selected_idx].copy()

    total_cost = selected["acquisition_cost"].sum()
    total_value = selected["lbo_score"].sum() if objective_mode == "score_sum" else pulp.value(prob.objective)

    sector_summary = (
        selected.groupby("sector")
        .agg(n_targets=("ticker", "count"), total_cost=("acquisition_cost", "sum"),
             avg_score=("lbo_score", "mean"))
        .reset_index()
        .to_dict(orient="records")
    )

    result = {
        "status": status,
        "objective_mode": objective_mode,
        "parameters": {
            "budget_usd": budget,
            "max_per_sector": max_per_sector,
            "takeout_premium": takeout_premium,
        },
        "n_targets_selected": len(selected),
        "budget_used_usd": round(float(total_cost), 2),
        "budget_utilization_pct": round(100 * float(total_cost) / budget, 1),
        "total_portfolio_value": round(float(total_value), 2),
        "avg_score_selected": round(float(selected["lbo_score"].mean()), 2) if len(selected) else None,
        "sector_breakdown": sector_summary,
        "selected_companies": [
            {
                "ticker": row["ticker"],
                "name": row["name"],
                "sector": row["sector"],
                "lbo_score": round(float(row["lbo_score"]), 2),
                "rank": int(row["rank"]),
                "market_cap": float(row["market_cap"]),
                "acquisition_cost": round(float(row["acquisition_cost"]), 2),
            }
            for _, row in selected.sort_values("lbo_score", ascending=False).iterrows()
        ],
    }
    return result


def main():
    if not SCORES_PATH.exists():
        print(f"ERROR: {SCORES_PATH} not found. Run model/scoring_model.py first.", file=sys.stderr)
        sys.exit(1)

    scores = pd.read_csv(SCORES_PATH)
    result = solve_allocation(scores)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(result, indent=2))

    print(f"Solved allocation: {result['status']}")
    print(f"Selected {result['n_targets_selected']} companies, "
          f"${result['budget_used_usd']/1e9:.2f}B of ${DEFAULT_BUDGET_USD/1e9:.0f}B budget "
          f"({result['budget_utilization_pct']}% utilized)")
    print(f"Total portfolio value (sum of scores): {result['total_portfolio_value']}")
    print(f"Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
