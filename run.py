"""
Quarry -- run everything end to end.

Usage:
    python run.py                  # full pipeline + start API server (blocks)
    python run.py --skip-fetch     # reuse existing data/raw/financials.csv (skip the slow yfinance pull)
    python run.py --no-serve       # run the pipeline only, don't start the API server
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))

# Force line-buffered stdout so progress is visible in real time even when
# output is piped/redirected (not just when attached to an interactive TTY).
sys.stdout.reconfigure(line_buffering=True)

API_HOST = "127.0.0.1"
API_PORT = 8000
API_BASE = f"http://{API_HOST}:{API_PORT}"
ENDPOINTS = ["/health", "/rankings", "/backtest", "/optimal-portfolio", "/sensitivity",
             "/robust-portfolio", "/weight-calibration", "/key-findings"]


def step(title: str):
    print(f"\n{'=' * 70}\n  {title}\n{'=' * 70}")


def run_pipeline(skip_fetch: bool):
    financials_path = REPO_ROOT / "data" / "raw" / "financials.csv"

    step("STEP 1a -- Financials Loader")
    if skip_fetch and financials_path.exists():
        print(f"--skip-fetch set and {financials_path} exists, reusing it.")
    else:
        from pipeline.financials_loader import main as loader_main
        loader_main()

    step("STEP 1b -- Ratio Engine")
    from pipeline.ratio_engine import main as ratio_main
    ratio_main()

    step("STEP 1c -- Preprocessor")
    from pipeline.preprocessor import main as preprocessor_main
    preprocessor_main()

    step("STEP 2a -- Scoring Model")
    from model.scoring_model import main as scoring_main
    scoring_main()

    step("STEP 3a -- Historical LBO Targets")
    from backtest.historical_lbo_targets import main as targets_main
    targets_main()

    step("STEP 3b -- Backtest Runner")
    from backtest.backtest_runner import main as backtest_main
    backtest_main()

    step("STEP 3c -- Score History (Backtest Replay Timeline)")
    try:
        from backtest.score_history import main as score_history_main
        score_history_main()
    except Exception as e:  # noqa: BLE001 -- feeds an optional dashboard panel, don't fail the whole run
        print(f"[warn] score history failed, continuing without it: {e}")

    step("STEP 2b -- Weight Calibration (optional)")
    try:
        from model.weight_calibration import main as calibration_main
        calibration_main()
    except Exception as e:  # noqa: BLE001 -- optional step, don't fail the whole run
        print(f"[warn] weight calibration failed, continuing without it: {e}")

    step("STEP 4a -- Allocation Optimizer")
    from optimization.allocation_optimizer import main as allocation_main
    allocation_main()

    step("STEP 4b -- Sensitivity Analysis")
    from optimization.sensitivity_analysis import main as sensitivity_main
    sensitivity_main()

    step("STEP 4c -- Chance Constraints")
    from optimization.chance_constraints import main as chance_main
    chance_main()


def start_api_server() -> subprocess.Popen:
    step("STEP 5 -- Starting FastAPI backend")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "dashboard.api:app", "--host", API_HOST, "--port", str(API_PORT)],
        cwd=str(REPO_ROOT),
    )
    for attempt in range(30):
        try:
            r = requests.get(f"{API_BASE}/health", timeout=1)
            if r.status_code == 200:
                print(f"API server is up at {API_BASE}")
                return proc
        except requests.RequestException:
            pass
        time.sleep(1)
    print("[warn] API server did not become healthy within 30s")
    return proc


def _sample_timeline_endpoints() -> list[str]:
    """Exercise the company-specific replay/explain endpoints: a historical
    (delisted) target for the timeline + timeline-date explain endpoints,
    and a live-universe ticker for the current-score explain endpoint --
    these are two different company sets, so a single sample ticker can't
    cover both (a delisted target was never in the live universe, and
    /explain/{ticker} 404s for it by design)."""
    import json

    endpoints = []

    timeline_path = REPO_ROOT / "data" / "outputs" / "score_timeline.json"
    if timeline_path.exists():
        timelines = json.loads(timeline_path.read_text())
        if timelines:
            ticker = next(iter(timelines))
            sample_date = timelines[ticker]["points"][-1]["date"]
            endpoints += [f"/backtest/timeline/{ticker}", f"/explain/{ticker}/{sample_date}"]

    scores_path = REPO_ROOT / "data" / "outputs" / "scores.csv"
    if scores_path.exists():
        import pandas as pd
        live_ticker = pd.read_csv(scores_path)["ticker"].iloc[0]
        endpoints.append(f"/explain/{live_ticker}")

    return endpoints


def confirm_endpoints():
    step("STEP 6 -- Confirming all endpoints return data")
    all_ok = True
    for ep in ENDPOINTS + _sample_timeline_endpoints():
        try:
            r = requests.get(f"{API_BASE}{ep}", timeout=5)
            ok = r.status_code == 200
            all_ok &= ok
            print(f"  {'OK ' if ok else 'FAIL'}  GET {ep}  -> {r.status_code}")
        except requests.RequestException as e:
            all_ok = False
            print(f"  FAIL  GET {ep}  -> {e}")
    return all_ok


def print_summary():
    step("SUMMARY -- Key Findings")
    try:
        r = requests.get(f"{API_BASE}/key-findings", timeout=5)
        findings = r.json().get("findings", [])
        for f in findings:
            print(f"\n[{f['label']}] {f['value']}")
            print(f"  {f['detail']}")
    except Exception as e:  # noqa: BLE001
        print(f"Could not fetch key findings from API: {e}")
    print()


def main():
    parser = argparse.ArgumentParser(description="Run the full Quarry pipeline end to end.")
    parser.add_argument("--skip-fetch", action="store_true", help="Reuse existing data/raw/financials.csv")
    parser.add_argument("--no-serve", action="store_true", help="Run the pipeline only, skip starting the API server")
    args = parser.parse_args()

    start_time = time.time()
    run_pipeline(skip_fetch=args.skip_fetch)
    print(f"\nPipeline complete in {time.time() - start_time:.1f}s")

    if args.no_serve:
        print_summary_from_files()
        return

    proc = start_api_server()
    try:
        endpoints_ok = confirm_endpoints()
        print_summary()
        if not endpoints_ok:
            print("Some endpoints failed -- check the API server log above.")
        print(f"\nDashboard API running at {API_BASE} (docs at {API_BASE}/docs). Press Ctrl+C to stop.")
        print(f"To run the React dashboard: cd dashboard/frontend && npm install && npm run dev")
        proc.wait()
    except KeyboardInterrupt:
        print("\nStopping API server...")
        proc.terminate()


def print_summary_from_files():
    import json
    step("SUMMARY -- Key Findings (from files, API not started)")
    bt_path = REPO_ROOT / "data" / "outputs" / "backtest_results.json"
    op_path = REPO_ROOT / "data" / "outputs" / "optimal_portfolio.json"
    if bt_path.exists():
        bt = json.loads(bt_path.read_text())
        print(f"\n{bt['summary']['headline_finding']}")
    if op_path.exists():
        op = json.loads(op_path.read_text())
        print(f"Optimal portfolio: {op['n_targets_selected']} targets, "
              f"${op['budget_used_usd']/1e9:.2f}B deployed ({op['budget_utilization_pct']}% of budget)")


if __name__ == "__main__":
    main()
