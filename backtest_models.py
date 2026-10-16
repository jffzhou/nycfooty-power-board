"""Compare model families by walk-forward log loss; writes model_comparison.md and data/model_comparison.csv."""

import csv
from collections.abc import Sequence
from datetime import date
from itertools import product

from nycfooty.backtest import (
    TEST_LEAGUES,
    TUNING_LEAGUES,
    BacktestPrediction,
    WalkForwardBacktest,
    evaluate_grid,
    paired_log_loss_difference,
    summarize,
)
from nycfooty.client import fetch_league_data
from nycfooty.constants import LEAGUE_ID, PROJECT_ROOT
from nycfooty.strength_models import (
    MODEL_CHOICES,
    DixonColesParameters,
    ModelParameters,
    StrengthParameters,
    describe_parameters,
)
from nycfooty.validation import ValidationLeague

RESULTS_MARGIN_GRID = tuple(
    ModelParameters(ridge=ridge, margin_cap=cap, sigma_scale=sigma_scale, result_weight=weight)
    for ridge, cap, sigma_scale, weight in product(
        (0.02, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0),
        (2, 3, 4, 5),
        (1.0, 1.2, 1.4, 1.7),
        (0.0, 0.25, 0.5, 0.75, 0.9, 1.0),
    )
)
DIXON_COLES_GRID = tuple(
    DixonColesParameters(ridge=ridge, rho=rho, half_life_days=half_life, goal_cap=cap)
    for ridge, rho, half_life, cap in product(
        (1.0, 2.0, 4.0, 8.0, 16.0),
        (0.15, 0.1, 0.05, 0.0, -0.05, -0.1, -0.15),
        (None, 14.0, 28.0, 56.0),
        (None, 4, 6),
    )
)
KNOBS = {
    "results": ("ridge", "margin_cap", "sigma_scale", "result_weight"),
    "dixon-coles": ("ridge", "rho", "half_life_days", "goal_cap"),
}


def _fetch(leagues: Sequence[ValidationLeague]) -> dict[str, list]:
    return {league.league_id: fetch_league_data(league.league_id)[0] for league in leagues}


def _log_loss(predictions: Sequence[BacktestPrediction]) -> float:
    return summarize(predictions)["log_loss"]


def _value(value: object) -> str:
    return "none" if value is None else f"{value:g}"


def main() -> None:
    tuning_games = _fetch(TUNING_LEAGUES)
    test_games = _fetch(TEST_LEAGUES)
    season_games = fetch_league_data(LEAGUE_ID)[0]
    production = MODEL_CHOICES["margin"].parameters

    grids = {"results": RESULTS_MARGIN_GRID, "dixon-coles": DIXON_COLES_GRID}
    tuning = {family: evaluate_grid(tuning_games, grid) for family, grid in grids.items()}
    tuning["margin"] = evaluate_grid(tuning_games, (production,))
    selected: dict[str, StrengthParameters] = {"margin": production}
    for family, scores in tuning.items():
        if family != "margin":
            selected[family] = min(scores, key=lambda parameters: _log_loss(scores[parameters]))

    test = evaluate_grid(test_games, tuple(selected.values()))
    season_backtest = WalkForwardBacktest(season_games)
    season = {family: season_backtest.predictions(parameters) for family, parameters in selected.items()}
    order = ("margin", "results", "dixon-coles")

    rows = []
    for family in order:
        parameters = selected[family]
        tuning_summary = summarize(tuning[family][parameters])
        test_summary = summarize(test[parameters])
        season_summary = summarize(season[family])
        difference = (
            paired_log_loss_difference(test[parameters], test[production])
            if family != "margin"
            else (0.0, 0.0, 0.0)
        )
        rows.append(
            {
                "model": family,
                "label": MODEL_CHOICES[family].label,
                "parameters": describe_parameters(parameters),
                "in_production_registry": MODEL_CHOICES[family].parameters == parameters,
                "tuning_matches": int(tuning_summary["matches"]),
                "tuning_log_loss": round(tuning_summary["log_loss"], 4),
                "test_matches": int(test_summary["matches"]),
                "test_log_loss": round(test_summary["log_loss"], 4),
                "test_brier": round(test_summary["brier"], 4),
                "test_accuracy": round(test_summary["accuracy"], 4),
                "test_minus_margin": round(difference[0], 4),
                "test_minus_margin_low": round(difference[1], 4),
                "test_minus_margin_high": round(difference[2], 4),
                "season_matches": int(season_summary["matches"]),
                "season_log_loss": round(season_summary["log_loss"], 4),
            }
        )
    baseline = {
        "tuning": summarize(tuning["margin"][production])["baseline_log_loss"],
        "test": summarize(test[production])["baseline_log_loss"],
        "season": summarize(season["margin"])["baseline_log_loss"],
    }
    rows.append(
        {
            "model": "coin-flip",
            "label": "Coin flip (draw rate only)",
            "parameters": "",
            "in_production_registry": False,
            "tuning_matches": rows[0]["tuning_matches"],
            "tuning_log_loss": round(baseline["tuning"], 4),
            "test_matches": rows[0]["test_matches"],
            "test_log_loss": round(baseline["test"], 4),
            "test_brier": "",
            "test_accuracy": "",
            "test_minus_margin": "",
            "test_minus_margin_low": "",
            "test_minus_margin_high": "",
            "season_matches": rows[0]["season_matches"],
            "season_log_loss": round(baseline["season"], 4),
        }
    )
    with (PROJECT_ROOT / "data" / "model_comparison.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    lines = [
        "# Model comparison",
        "",
        f"Generated {date.today().isoformat()} by `uv run python backtest_models.py`. First run: 2026-10-16.",
        "",
        "## Protocol",
        "",
        "- Walk-forward: every completed, non-forfeit regular-season game is predicted from results on strictly earlier dates in the same league.",
        f"- Each challenger family is tuned on the {len(TUNING_LEAGUES)} tuning leagues only (lowest pooled log loss), then scored once on the {len(TEST_LEAGUES)} test leagues and on this season.",
        "- The goal-margin model is the production configuration chosen on the same tuning leagues on 2026-10-09. Its test-league score was seen then, so the test set is not fully fresh for it.",
        f"- Grids: results + margin {len(RESULTS_MARGIN_GRID)} configurations (result weight 0 is the plain margin model); Dixon-Coles {len(DIXON_COLES_GRID)} configurations.",
        "- The first run (2026-10-16) selected edge values (results + margin ridge 0.25; Dixon-Coles rho 0 and half-life 28 days) and scored them on the test leagues. The grids were widened twice past the edges and reselected on the tuning leagues only, so the test leagues have been seen before this selection.",
        "- This season is small and still in progress; treat it as a sanity check, not evidence.",
        "",
        "## Results",
        "",
        "| Model | Selected parameters | Tuning log loss | Test log loss | Test minus margin (95% CI) | Test accuracy | This season |",
        "|---|---|---:|---:|---|---:|---:|",
    ]
    for row in rows:
        ci = (
            f"{row['test_minus_margin']:+.4f} ({row['test_minus_margin_low']:+.4f} to {row['test_minus_margin_high']:+.4f})"
            if row["model"] not in ("margin", "coin-flip")
            else ""
        )
        accuracy = f"{row['test_accuracy']:.1%}" if row["test_accuracy"] != "" else ""
        lines.append(
            f"| {row['label']} | {row['parameters']} | {row['tuning_log_loss']:.4f} | {row['test_log_loss']:.4f} | "
            f"{ci} | {accuracy} | {row['season_log_loss']:.4f} |"
        )
    lines.extend(
        [
            "",
            f"Matches: tuning {rows[0]['tuning_matches']}, test {rows[0]['test_matches']}, this season {rows[0]['season_matches']}. Lower log loss is better.",
            "",
        ]
    )
    for family in ("results", "dixon-coles"):
        lines.extend([f"Best tuning log loss for each {MODEL_CHOICES[family].label} knob value:", ""])
        for knob in KNOBS[family]:
            values = sorted({getattr(parameters, knob) for parameters in grids[family]}, key=lambda value: (value is None, value))
            cells = [
                f"{_value(value)}: "
                + f"{min(_log_loss(tuning[family][parameters]) for parameters in grids[family] if getattr(parameters, knob) == value):.4f}"
                for value in values
            ]
            lines.append(f"- `{knob}`: " + "; ".join(cells))
        lines.append("")
    lines.extend(
        [
            "## Test leagues",
            "",
            "| League | Games | " + " | ".join(MODEL_CHOICES[family].label for family in order) + " | Coin flip |",
            "|---|---:|" + "---:|" * (len(order) + 1),
        ]
    )
    for league in TEST_LEAGUES:
        backtest = WalkForwardBacktest(test_games[league.league_id])
        scores = [summarize(backtest.predictions(selected[family])) for family in order]
        lines.append(
            f"| [{league.name}]({league.url}) | {int(scores[0]['matches'])} | "
            + " | ".join(f"{score['log_loss']:.4f}" for score in scores)
            + f" | {scores[0]['baseline_log_loss']:.4f} |"
        )
    registry_matches = all(row["in_production_registry"] for row in rows if row["model"] != "coin-flip")
    lines.extend(
        [
            "",
            f"The dashboard's model registry (`MODEL_CHOICES` in `nycfooty/strength_models.py`) {'matches' if registry_matches else 'does NOT match'} the selected parameters.",
            "",
        ]
    )
    report = "\n".join(lines)
    (PROJECT_ROOT / "model_comparison.md").write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
