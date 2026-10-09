from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, replace
from statistics import fmean

from nycfooty.client import fetch_league_data
from nycfooty.constants import DEFAULT_SIMULATIONS
from nycfooty.forecast import estimate_draw_rate, forecast_final_standings, forecast_match
from nycfooty.models import Game
from nycfooty.ratings import calculate_ratings


@dataclass(frozen=True)
class ValidationLeague:
    league_id: str
    name: str
    url: str


@dataclass(frozen=True)
class MatchValidation:
    game_id: str
    week: int
    away_team: str
    home_team: str
    away_score: int
    home_score: int
    away_win_probability: float
    draw_probability: float
    home_win_probability: float
    baseline_away_probability: float
    baseline_draw_probability: float
    baseline_home_probability: float
    expected_margin: float

    @property
    def outcome_index(self) -> int:
        if self.away_score > self.home_score:
            return 0
        if self.away_score == self.home_score:
            return 1
        return 2

    @property
    def probabilities(self) -> tuple[float, float, float]:
        return (
            self.away_win_probability,
            self.draw_probability,
            self.home_win_probability,
        )

    @property
    def baseline_probabilities(self) -> tuple[float, float, float]:
        return (
            self.baseline_away_probability,
            self.baseline_draw_probability,
            self.baseline_home_probability,
        )


@dataclass(frozen=True)
class LeagueValidation:
    league: ValidationLeague
    team_count: int
    training_matches: int
    training_games_min: int
    training_games_max: int
    holdout_matches: int
    excluded_holdout_forfeits: int
    match_predictions: tuple[MatchValidation, ...]
    log_loss: float
    baseline_log_loss: float
    brier_score: float
    baseline_brier_score: float
    outcome_accuracy: float
    margin_mae: float
    baseline_margin_mae: float
    strength_rank_correlation: float
    current_table_rank_correlation: float
    projected_rank_correlation: float
    projected_rank_mae: float
    champion_correct: bool
    actual_champion_probability: float
    top_four_overlap: int
    actual_order: tuple[str, ...]
    projected_order: tuple[str, ...]


ARCHIVE_ELIGIBLE_LEAGUES = (
    ValidationLeague("4688994", "2025 Fall · Harlem Riverbank · Wednesdays", "https://nycfooty.leagueapps.com/leagues/4688994/standings"),
    ValidationLeague("4887195", "2026 Spring · Brooklyn Heights · Saturdays", "https://nycfooty.leagueapps.com/leagues/4887195/standings"),
    ValidationLeague("4887792", "2026 Spring · Chinatown · Sundays", "https://nycfooty.leagueapps.com/leagues/4887792/standings"),
    ValidationLeague("4978774", "2026 Summer · Lower East Side · Mondays", "https://nycfooty.leagueapps.com/leagues/4978774/standings"),
    ValidationLeague("4981886", "2026 Summer · Downtown Brooklyn · Saturdays", "https://nycfooty.leagueapps.com/leagues/4981886/standings"),
    ValidationLeague("4981937", "2026 Summer · Chinatown · Sundays", "https://nycfooty.leagueapps.com/leagues/4981937/standings"),
    ValidationLeague("4987937", "2026 Summer · Williamsburg · Thursdays", "https://nycfooty.leagueapps.com/leagues/4987937/standings"),
    ValidationLeague("4783265", "2026 Winter · Chinatown · Sundays", "https://nycfooty.leagueapps.com/leagues/4783265/standings"),
    ValidationLeague("4789879", "2026 Winter · Williamsburg · Saturdays", "https://nycfooty.leagueapps.com/leagues/4789879/standings"),
    ValidationLeague("4980765", "2026 Summer · Upper East Side · Tuesdays", "https://nycfooty.leagueapps.com/leagues/4980765/standings"),
    ValidationLeague("5029631", "2026 Summer · Two Bridges · Tuesdays", "https://nycfooty.leagueapps.com/leagues/5029631/standings"),
    ValidationLeague("4783983", "2026 Winter · West Village · Sundays", "https://nycfooty.leagueapps.com/leagues/4783983/standings"),
)

# random.Random(5086028).sample(ARCHIVE_ELIGIBLE_LEAGUES, 6), frozen for auditability.
VALIDATION_SAMPLE = (
    ARCHIVE_ELIGIBLE_LEAGUES[3],
    ARCHIVE_ELIGIBLE_LEAGUES[0],
    ARCHIVE_ELIGIBLE_LEAGUES[2],
    ARCHIVE_ELIGIBLE_LEAGUES[1],
    ARCHIVE_ELIGIBLE_LEAGUES[7],
    ARCHIVE_ELIGIBLE_LEAGUES[10],
)


def split_first_team_games(
    games: list[Game],
    *,
    games_per_team: int = 3,
) -> tuple[list[Game], list[Game]]:
    regular_games = sorted(
        (
            game
            for game in games
            if game.completed and game.game_type.lower() == "regular season"
        ),
        key=lambda game: (game.played_at, game.game_id),
    )
    appearances: Counter[str] = Counter()
    training: list[Game] = []
    holdout: list[Game] = []
    for game in regular_games:
        if (
            appearances[game.away_team] < games_per_team
            and appearances[game.home_team] < games_per_team
        ):
            training.append(game)
        else:
            holdout.append(game)
        appearances[game.away_team] += 1
        appearances[game.home_team] += 1
    return training, holdout


def _log_loss(predictions: list[MatchValidation], *, baseline: bool = False) -> float:
    return fmean(
        -math.log(
            max(
                (
                    prediction.baseline_probabilities
                    if baseline
                    else prediction.probabilities
                )[prediction.outcome_index],
                1e-15,
            )
        )
        for prediction in predictions
    )


def _brier_score(predictions: list[MatchValidation], *, baseline: bool = False) -> float:
    return fmean(
        sum(
            (probability - (index == prediction.outcome_index)) ** 2
            for index, probability in enumerate(
                prediction.baseline_probabilities if baseline else prediction.probabilities
            )
        )
        for prediction in predictions
    )


def _spearman(first: list[str], second: list[str]) -> float:
    if set(first) != set(second):
        raise ValueError("ranked team sets do not match")
    first_rank = {team: rank for rank, team in enumerate(first, start=1)}
    second_rank = {team: rank for rank, team in enumerate(second, start=1)}
    count = len(first)
    squared_difference = sum(
        (first_rank[team] - second_rank[team]) ** 2
        for team in first
    )
    return 1.0 - 6.0 * squared_difference / (count * (count**2 - 1))


def evaluate_league(
    league: ValidationLeague,
    *,
    simulations: int = DEFAULT_SIMULATIONS,
) -> LeagueValidation:
    games, standings = fetch_league_data(league.league_id)
    training, holdout = split_first_team_games(games)
    ratings, _ = calculate_ratings(training)
    draw_rate = estimate_draw_rate(training)
    baseline = ((1.0 - draw_rate) / 2.0, draw_rate, (1.0 - draw_rate) / 2.0)
    predictions: list[MatchValidation] = []
    excluded_forfeits = 0
    for game in holdout:
        if game.is_forfeit:
            excluded_forfeits += 1
            continue
        probabilities = forecast_match(
            ratings[game.away_team].elo,
            ratings[game.home_team].elo,
            draw_rate=draw_rate,
        )
        predictions.append(
            MatchValidation(
                game_id=game.game_id,
                week=game.week,
                away_team=game.away_team,
                home_team=game.home_team,
                away_score=int(game.away_score),
                home_score=int(game.home_score),
                away_win_probability=probabilities[0],
                draw_probability=probabilities[1],
                home_win_probability=probabilities[2],
                baseline_away_probability=baseline[0],
                baseline_draw_probability=baseline[1],
                baseline_home_probability=baseline[2],
                expected_margin=(
                    ratings[game.away_team].expected_margin_vs_average
                    - ratings[game.home_team].expected_margin_vs_average
                ),
            )
        )

    masked_holdout = [
        replace(game, away_score=None, home_score=None, status="", note="")
        for game in holdout
    ]
    projection = forecast_final_standings(
        training + masked_holdout,
        simulations=simulations,
        seed=int(league.league_id),
    )
    actual_order = [row["Team"] for row in standings]
    projected_order = [row.team for row in projection]
    strength_order = sorted(ratings, key=lambda team: ratings[team].elo, reverse=True)
    current_table_order = sorted(
        ratings,
        key=lambda team: (
            3 * ratings[team].wins + ratings[team].ties,
            ratings[team].goal_difference,
            -ratings[team].goals_against,
        ),
        reverse=True,
    )
    actual_rank = {team: rank for rank, team in enumerate(actual_order, start=1)}
    projected_rank_mae = fmean(
        abs(rank - actual_rank[team])
        for rank, team in enumerate(projected_order, start=1)
    )
    actual_champion = actual_order[0]
    champion_projection = next(row for row in projection if row.team == actual_champion)
    coverage = Counter(
        team
        for game in training
        for team in (game.away_team, game.home_team)
    )
    actual_margins = [prediction.away_score - prediction.home_score for prediction in predictions]
    return LeagueValidation(
        league=league,
        team_count=len(ratings),
        training_matches=len(training),
        training_games_min=min(coverage.values()),
        training_games_max=max(coverage.values()),
        holdout_matches=len(predictions),
        excluded_holdout_forfeits=excluded_forfeits,
        match_predictions=tuple(predictions),
        log_loss=_log_loss(predictions),
        baseline_log_loss=_log_loss(predictions, baseline=True),
        brier_score=_brier_score(predictions),
        baseline_brier_score=_brier_score(predictions, baseline=True),
        outcome_accuracy=fmean(
            max(range(3), key=prediction.probabilities.__getitem__)
            == prediction.outcome_index
            for prediction in predictions
        ),
        margin_mae=fmean(
            abs(actual - prediction.expected_margin)
            for actual, prediction in zip(actual_margins, predictions, strict=True)
        ),
        baseline_margin_mae=fmean(abs(margin) for margin in actual_margins),
        strength_rank_correlation=_spearman(strength_order, actual_order),
        current_table_rank_correlation=_spearman(current_table_order, actual_order),
        projected_rank_correlation=_spearman(projected_order, actual_order),
        projected_rank_mae=projected_rank_mae,
        champion_correct=projected_order[0] == actual_champion,
        actual_champion_probability=champion_projection.first_probability,
        top_four_overlap=len(set(projected_order[:4]) & set(actual_order[:4])),
        actual_order=tuple(actual_order),
        projected_order=tuple(projected_order),
    )


def pooled_match_metrics(reports: list[LeagueValidation]) -> dict[str, float]:
    predictions = [
        prediction
        for report in reports
        for prediction in report.match_predictions
    ]
    actual_margins = [prediction.away_score - prediction.home_score for prediction in predictions]
    outcome_accuracy = fmean(
        max(range(3), key=prediction.probabilities.__getitem__)
        == prediction.outcome_index
        for prediction in predictions
    )
    average_confidence = fmean(max(prediction.probabilities) for prediction in predictions)
    return {
        "matches": float(len(predictions)),
        "excluded_forfeits": float(sum(report.excluded_holdout_forfeits for report in reports)),
        "log_loss": _log_loss(predictions),
        "baseline_log_loss": _log_loss(predictions, baseline=True),
        "brier_score": _brier_score(predictions),
        "baseline_brier_score": _brier_score(predictions, baseline=True),
        "outcome_accuracy": outcome_accuracy,
        "average_confidence": average_confidence,
        "confidence_gap": average_confidence - outcome_accuracy,
        "margin_mae": fmean(
            abs(actual - prediction.expected_margin)
            for actual, prediction in zip(actual_margins, predictions, strict=True)
        ),
        "baseline_margin_mae": fmean(abs(margin) for margin in actual_margins),
    }