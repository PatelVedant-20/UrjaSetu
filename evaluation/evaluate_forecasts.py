"""UrjaSetu Phase 3 Forecast Evaluation CLI Runner.

Evaluates forecast accuracy against synthetic ground truth across 7
representative development cases.
Can be executed directly from terminal:
    python evaluation/evaluate_forecasts.py --all
    python evaluation/evaluate_forecasts.py --scenario normal_solar_day
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Ensure backend and repo root are on sys.path
_REPO_ROOT = Path(__file__).resolve().parent.parent
_BACKEND_DIR = _REPO_ROOT / "backend"
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tests.fixtures.forecast.evaluator import ForecastEvaluator  # noqa: E402
from tests.fixtures.forecast.loader import list_available_forecast_scenarios  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="UrjaSetu Phase 3 Forecast Accuracy Evaluation CLI"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--all",
        action="store_true",
        help="Evaluate all 7 available forecast scenarios",
    )
    group.add_argument(
        "--scenario",
        type=str,
        help="Evaluate a specific forecast scenario (e.g., normal_solar_day)",
    )
    group.add_argument(
        "--list",
        action="store_true",
        help="List all available forecast scenarios",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results in structured JSON format",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.1,
        help="Minimum actual value (kW) for computing safe MAPE (default: 0.1 kW)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    evaluator = ForecastEvaluator(zero_threshold=args.threshold)

    if args.list:
        scenarios = list_available_forecast_scenarios()
        if args.json:
            print(json.dumps({"available_scenarios": scenarios}, indent=2))
        else:
            print("Available forecast scenarios:")
            for sc in scenarios:
                print(f"  - {sc}")
        return

    if args.all:
        reports = evaluator.evaluate_all()
        if args.json:
            output = [r.to_dict() for r in reports]
            print(json.dumps(output, indent=2))
        else:
            print(
                "\n========================================================================================="
            )
            print("URJASETU PHASE 3 FORECAST ACCURACY BENCHMARK REPORT")
            print(
                "=========================================================================================\n"
            )
            print(evaluator.format_summary_table(reports))
            print("\n* MAE/RMSE/Bias in kW. Safe MAPE excludes night/near-zero hours (< 0.1 kW).")
            print(
                "* nMAE is normalized against asset rated capacity "
                "(5.0 kW for solar, CERC standard).\n"
            )
        return

    if args.scenario:
        try:
            report = evaluator.evaluate_scenario(args.scenario)
        except FileNotFoundError as err:
            print(f"Error: {err}", file=sys.stderr)
            sys.exit(1)

        if args.json:
            print(json.dumps(report.to_dict(), indent=2))
        else:
            m = report.metrics
            print(f"\nScenario: {report.title} ({report.scenario_id})")
            print(f"Type: {report.forecast_type.upper()} | Site ID: {report.site_id}")
            print("-" * 60)
            print(f"Evaluated Intervals: {m.evaluated_intervals} / {m.sample_count}")
            print(f"Mean Absolute Error (MAE):    {m.mae_kw:.4f} kW")
            print(f"Root Mean Sq Error (RMSE):    {m.rmse_kw:.4f} kW")
            print(f"Mean Bias Error (MBE):        {m.mean_bias_kw:+.4f} kW")
            mape_disp = f"{m.safe_mape_percent:.2f}%" if m.safe_mape_percent is not None else "N/A"
            print(f"Safe Masked MAPE:             {mape_disp}")
            print(f"Symmetric MAPE (sMAPE):       {m.smape_percent:.2f}%")
            if m.nmae_percent is not None:
                print(f"Normalized MAE (nMAE):        {m.nmae_percent:.2f}% (relative to capacity)")
            print("-" * 60)


if __name__ == "__main__":
    main()
