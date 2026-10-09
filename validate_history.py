import csv
from pathlib import Path
from statistics import fmean

from nycfooty.constants import DEFAULT_SIMULATIONS, PROJECT_ROOT
from nycfooty.validation import VALIDATION_SAMPLE, evaluate_league, pooled_match_metrics


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    reports = [
        evaluate_league(league, simulations=DEFAULT_SIMULATIONS)
        for league in VALIDATION_SAMPLE
    ]
    pooled = pooled_match_metrics(reports)
    data_dir = PROJECT_ROOT / "data"
    summary_rows = [
        {
            "league_id": report.league.league_id,
            "league": report.league.name,
            "teams": report.team_count,
            "training_matches": report.training_matches,
            "training_games_min": report.training_games_min,
            "training_games_max": report.training_games_max,
            "scored_holdout_matches": report.holdout_matches,
            "excluded_holdout_forfeits": report.excluded_holdout_forfeits,
            "log_loss": round(report.log_loss, 4),
            "baseline_log_loss": round(report.baseline_log_loss, 4),
            "brier_score": round(report.brier_score, 4),
            "baseline_brier_score": round(report.baseline_brier_score, 4),
            "outcome_accuracy_pct": round(report.outcome_accuracy * 100.0, 2),
            "margin_mae": round(report.margin_mae, 3),
            "baseline_margin_mae": round(report.baseline_margin_mae, 3),
            "strength_rank_correlation": round(report.strength_rank_correlation, 3),
            "week3_table_rank_correlation": round(report.current_table_rank_correlation, 3),
            "projected_rank_correlation": round(report.projected_rank_correlation, 3),
            "projected_rank_mae": round(report.projected_rank_mae, 3),
            "champion_correct": report.champion_correct,
            "actual_champion_probability_pct": round(report.actual_champion_probability * 100.0, 2),
            "top_four_overlap": report.top_four_overlap,
        }
        for report in reports
    ]
    match_rows = [
        {
            "league_id": report.league.league_id,
            "game_id": prediction.game_id,
            "week": prediction.week,
            "away_team": prediction.away_team,
            "home_team": prediction.home_team,
            "away_score": prediction.away_score,
            "home_score": prediction.home_score,
            "away_win_probability": round(prediction.away_win_probability, 6),
            "draw_probability": round(prediction.draw_probability, 6),
            "home_win_probability": round(prediction.home_win_probability, 6),
            "expected_margin": round(prediction.expected_margin, 4),
        }
        for report in reports
        for prediction in report.match_predictions
    ]
    summary_path = data_dir / "historical_validation_by_league.csv"
    matches_path = data_dir / "historical_validation_matches.csv"
    report_path = PROJECT_ROOT / "historical_validation.md"
    _write_csv(summary_path, summary_rows)
    _write_csv(matches_path, match_rows)

    report_lines = [
        "# Historical three-game validation",
        "",
        "Evaluates the production parameters in `nycfooty/constants.py`. They were tuned on these same six leagues on 2026-10-09 (`hyperparameter_backtest.md`), so these results are in-sample.",
        "",
        "## Selection and cutoff",
        "",
        "The completed archive contained 17 exact P4/P5 outdoor listings. After requiring 7v7, a posted schedule, eight completed regular-season games per team, and a post-cutoff holdout, 12 leagues remained. Six were sampled with `random.Random(5086028)`.",
        "",
        "For every team, only results that were within both teams' first three chronological regular-season games entered training. This yields 2-3 training games per team, comparable to the current league. Playoffs and all later scores were hidden. Administrative forfeits were excluded from match scoring.",
        "",
        "The neutral baseline uses the same training-snapshot draw prior but assigns equal probability to either team. Lower log loss, Brier score, and margin MAE are better.",
        "",
        "## Pooled holdout results",
        "",
        f"- Scored matches: **{int(pooled['matches'])}**; excluded future forfeits: **{int(pooled['excluded_forfeits'])}**",
        f"- Log loss: **{pooled['log_loss']:.3f}** vs baseline **{pooled['baseline_log_loss']:.3f}**",
        f"- Multiclass Brier: **{pooled['brier_score']:.3f}** vs baseline **{pooled['baseline_brier_score']:.3f}**",
        f"- Most-likely-outcome accuracy: **{pooled['outcome_accuracy']:.1%}**",
        f"- Average favorite probability: **{pooled['average_confidence']:.1%}**; confidence minus accuracy: **{pooled['confidence_gap']:+.1%}**",
        f"- Goal-margin MAE: **{pooled['margin_mae']:.2f}** vs zero-margin baseline **{pooled['baseline_margin_mae']:.2f}**",
        "",
        "## By league",
        "",
        "| League | Train/team | Holdout | Log loss (base) | Accuracy | Margin MAE (base) | Strength ρ | Projection ρ | Champion | Top 4 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|:---:|:---:|",
    ]
    for report in reports:
        report_lines.append(
            f"| [{report.league.name}]({report.league.url}) | "
            f"{report.training_games_min}-{report.training_games_max} | "
            f"{report.holdout_matches} | {report.log_loss:.3f} ({report.baseline_log_loss:.3f}) | "
            f"{report.outcome_accuracy:.1%} | {report.margin_mae:.2f} ({report.baseline_margin_mae:.2f}) | "
            f"{report.strength_rank_correlation:+.2f} | {report.projected_rank_correlation:+.2f} | "
            f"{'yes' if report.champion_correct else 'no'} | {report.top_four_overlap}/4 |"
        )
    report_lines.extend(
        [
            "",
            "## Final-table summary",
            "",
            f"- Mean strength-rank Spearman ρ: **{fmean(report.strength_rank_correlation for report in reports):.3f}**",
            f"- Mean Week-3 table Spearman ρ: **{fmean(report.current_table_rank_correlation for report in reports):.3f}**",
            f"- Mean projected-table Spearman ρ: **{fmean(report.projected_rank_correlation for report in reports):.3f}**",
            f"- Projected champion correct: **{sum(report.champion_correct for report in reports)}/{len(reports)}**",
            f"- Projected top-four overlap: **{sum(report.top_four_overlap for report in reports)}/{4 * len(reports)}**",
            "",
            "## Interpretation",
            "",
            "The model has real early-season signal: pooled proper scores and margin error beat neutral baselines. The evidence is not uniformly strong: log loss lost to baseline in three of six leagues, and average confidence exceeded favorite accuracy by roughly ten percentage points.",
            "",
            "For final ordering, the simulation did not improve on the raw Week-3 table in this sample: mean projected-table rank correlation was lower. Its 5/6 champion hit rate is encouraging, but the six-league sample is too small for a strong claim.",
            "",
            "This is an external check of the frozen model, not parameter selection. These results must not be used to tune the same model and then quoted as out-of-sample evidence.",
            "",
        ]
    )
    report_path.write_text("\n".join(report_lines), encoding="utf-8")
    print(report_path)
    print(summary_path)
    print(matches_path)


if __name__ == "__main__":
    main()