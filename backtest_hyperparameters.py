import csv
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from statistics import fmean

from nycfooty.backtest import (
    PRE_TUNING_PARAMETERS,
    SEARCH_GRID,
    TEST_LEAGUES,
    TUNING_LEAGUES,
    BacktestPrediction,
    ModelParameters,
    WalkForwardBacktest,
    evaluate_grid,
    paired_log_loss_difference,
    summarize,
)
from nycfooty.client import fetch_league_data
from nycfooty.constants import PROJECT_ROOT
from nycfooty.validation import ValidationLeague

KNOBS = ("ridge", "margin_cap", "draw_prior_rate", "sigma_scale")


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _label(parameters: ModelParameters) -> str:
    cap = "none" if parameters.margin_cap is None else str(parameters.margin_cap)
    return (
        f"ridge {parameters.ridge:g}, cap {cap}, draw prior {parameters.draw_prior_rate:.0%}, "
        f"sigma x{parameters.sigma_scale:g}"
    )


def _fetch(leagues: Sequence[ValidationLeague]) -> dict[str, list]:
    return {league.league_id: fetch_league_data(league.league_id)[0] for league in leagues}


def _metrics_row(predictions: Sequence[BacktestPrediction]) -> str:
    summary = summarize(predictions)
    return (
        f"{summary['log_loss']:.4f} | {summary['brier']:.4f} | {summary['accuracy']:.1%} | "
        f"{summary['confidence']:.1%} | {summary['confidence_gap']:+.1%}"
    )


def main() -> None:
    current = PRE_TUNING_PARAMETERS
    tuning_games = _fetch(TUNING_LEAGUES)
    tuning = evaluate_grid(tuning_games, SEARCH_GRID)
    ranked = sorted(tuning, key=lambda parameters: summarize(tuning[parameters])["log_loss"])
    selected = ranked[0]

    test_games = _fetch(TEST_LEAGUES)
    test = evaluate_grid(test_games, (current, selected))
    difference, low, high = paired_log_loss_difference(test[selected], test[current])
    tuning_difference = paired_log_loss_difference(tuning[selected], tuning[current])
    by_league = []
    for league in TEST_LEAGUES:
        backtest = WalkForwardBacktest(test_games[league.league_id])
        league_current = summarize(backtest.predictions(current))
        league_selected = summarize(backtest.predictions(selected))
        by_league.append((league, league_current, league_selected))

    data_dir = PROJECT_ROOT / "data"
    grid_rows = []
    for rank, parameters in enumerate(ranked, start=1):
        summary = summarize(tuning[parameters])
        grid_rows.append(
            {
                "tuning_rank": rank,
                "ridge": parameters.ridge,
                "margin_cap": "" if parameters.margin_cap is None else parameters.margin_cap,
                "draw_prior_rate": parameters.draw_prior_rate,
                "sigma_scale": parameters.sigma_scale,
                "is_pre_tuning": parameters == current,
                "is_production": parameters == ModelParameters(),
                **{key: round(value, 5) for key, value in summary.items()},
            }
        )
    _write_csv(data_dir / "backtest_grid.csv", grid_rows)
    _write_csv(
        data_dir / "backtest_test_by_league.csv",
        [
            {
                "league_id": league.league_id,
                "league": league.name,
                "matches": int(league_current["matches"]),
                "current_log_loss": round(league_current["log_loss"], 4),
                "selected_log_loss": round(league_selected["log_loss"], 4),
                "baseline_log_loss": round(league_current["baseline_log_loss"], 4),
            }
            for league, league_current, league_selected in by_league
        ],
    )

    current_rank = ranked.index(current) + 1
    tuning_current = summarize(tuning[current])
    tuning_selected = summarize(tuning[selected])
    lines = [
        "# Hyperparameter backtest",
        "",
        f"Generated {date.today().isoformat()} by `uv run python backtest_hyperparameters.py`. First run and adoption: 2026-10-09.",
        "",
        "## Protocol",
        "",
        "- Walk-forward: every completed, non-forfeit regular-season game is predicted from results on strictly earlier dates in the same league. The first match date of each league is skipped.",
        f"- Tuning set: the {len(TUNING_LEAGUES)} leagues sampled for `historical_validation.md`. Test set: the other {len(TEST_LEAGUES)} eligible leagues, first scored on 2026-10-09; later runs re-score them in-sample.",
        f"- Grid: {len(SEARCH_GRID)} configurations over ridge pseudo-games, goal-margin cap, draw prior rate (20 pseudo-games), and a sigma multiplier on the draw-implied margin noise.",
        "- Selection rule, fixed before the test set was fetched: lowest pooled tuning log loss. Only the pre-tuning and selected configurations were scored on the test set.",
        f"- \"Pre-tuning\" means the production parameters before 2026-10-09. The selected configuration {'is' if selected == ModelParameters() else 'is NOT'} the production default in `nycfooty/constants.py`.",
        "",
        "## Tuning set",
        "",
        f"- Predictions: **{int(tuning_current['matches'])}**; neutral baseline log loss **{tuning_current['baseline_log_loss']:.4f}**",
        f"- Pre-tuning ({_label(current)}): log loss **{tuning_current['log_loss']:.4f}**, rank {current_rank} of {len(ranked)}",
        f"- Selected ({_label(selected)}): log loss **{tuning_selected['log_loss']:.4f}**",
        f"- Selected minus pre-tuning: {tuning_difference[0]:+.4f} (95% CI {tuning_difference[1]:+.4f} to {tuning_difference[2]:+.4f}); optimistic because the same games chose it",
        "",
        "Best tuning log loss for each knob value, minimizing over the other knobs:",
        "",
    ]
    for knob in KNOBS:
        values = sorted({getattr(parameters, knob) for parameters in SEARCH_GRID}, key=lambda value: (value is None, value))
        cells = []
        for value in values:
            best = min(
                summarize(tuning[parameters])["log_loss"]
                for parameters in SEARCH_GRID
                if getattr(parameters, knob) == value
            )
            cells.append(f"{'none' if value is None else f'{value:g}'}: {best:.4f}")
        lines.append(f"- `{knob}`: " + "; ".join(cells))
    lines.extend(
        [
            "",
            "Top 10 tuning configurations:",
            "",
            "| Rank | Ridge | Cap | Draw prior | Sigma x | Log loss |",
            "|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for rank, parameters in enumerate(ranked[:10], start=1):
        cap = "none" if parameters.margin_cap is None else parameters.margin_cap
        lines.append(
            f"| {rank} | {parameters.ridge:g} | {cap} | {parameters.draw_prior_rate:.0%} | "
            f"{parameters.sigma_scale:g} | {summarize(tuning[parameters])['log_loss']:.4f} |"
        )
    test_current = summarize(test[current])
    lines.extend(
        [
            "",
            "## Untouched test set",
            "",
            f"Predictions: **{int(test_current['matches'])}**",
            "",
            "| Model | Log loss | Brier | Accuracy | Avg favorite prob | Confidence gap |",
            "|---|---:|---:|---:|---:|---:|",
            f"| Neutral baseline | {test_current['baseline_log_loss']:.4f} | | | | |",
            f"| Pre-tuning | {_metrics_row(test[current])} |",
            f"| Selected | {_metrics_row(test[selected])} |",
            "",
            f"Selected minus pre-tuning log loss: **{difference:+.4f}** (95% match-bootstrap CI {low:+.4f} to {high:+.4f}).",
            "",
            "| League | Games | Pre-tuning | Selected | Baseline |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for league, league_current, league_selected in by_league:
        lines.append(
            f"| [{league.name}]({league.url}) | {int(league_current['matches'])} | "
            f"{league_current['log_loss']:.4f} | {league_selected['log_loss']:.4f} | "
            f"{league_current['baseline_log_loss']:.4f} |"
        )
    improved = sum(selected_row["log_loss"] < current_row["log_loss"] for _, current_row, selected_row in by_league)
    lines.extend(
        [
            "",
            f"Selected beat pre-tuning in {improved} of {len(by_league)} test leagues.",
            "",
            "The test set has now been used. Any further tuning that looks at these results makes them in-sample.",
            "",
        ]
    )
    report_path = PROJECT_ROOT / "hyperparameter_backtest.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"mean tuning log loss across grid: {fmean(row['log_loss'] for row in grid_rows):.4f}")


if __name__ == "__main__":
    main()
