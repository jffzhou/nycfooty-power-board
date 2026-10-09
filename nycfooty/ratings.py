from collections.abc import Iterable

import math

from nycfooty.constants import (
    ELO_POINTS_PER_GOAL,
    GOAL_MARGIN_OBSERVATION_SIGMA,
    INITIAL_ELO,
    MARGIN_CAP,
    MARGIN_RIDGE,
)
from nycfooty.models import Game, RatingSnapshot, TeamRating


def power_rating(elo: float) -> float:
    return round(
        min(10.0, max(1.0, 5.0 + (elo - INITIAL_ELO) / ELO_POINTS_PER_GOAL)),
        1,
    )


def power_rating_interval(
    rating: TeamRating,
    *,
    z_score: float = 1.2815515655446004,
) -> tuple[float, float]:
    center = 5.0 + rating.expected_margin_vs_average
    radius = z_score * rating.strength_standard_error
    return max(1.0, center - radius), min(10.0, center + radius)


def _solve_linear_system(matrix: list[list[float]], vector: list[float]) -> list[float]:
    size = len(vector)
    augmented = [row[:] + [value] for row, value in zip(matrix, vector, strict=True)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(augmented[row][column]))
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        divisor = augmented[column][column]
        for item in range(column, size + 1):
            augmented[column][item] /= divisor
        for row in range(size):
            if row == column:
                continue
            factor = augmented[row][column]
            for item in range(column, size + 1):
                augmented[row][item] -= factor * augmented[column][item]
    return [augmented[row][-1] for row in range(size)]


def _fit_margin_strengths(
    games: list[Game],
    teams: list[str],
    *,
    ridge: float = MARGIN_RIDGE,
    margin_cap: int | None = MARGIN_CAP,
) -> tuple[dict[str, float], dict[str, float]]:
    team_index = {team: index for index, team in enumerate(teams)}
    normal_matrix = [[0.0] * len(teams) for _ in teams]
    target = [0.0] * len(teams)
    for index in range(len(teams)):
        normal_matrix[index][index] = ridge

    for game in games:
        away = team_index[game.away_team]
        home = team_index[game.home_team]
        margin = int(game.away_score) - int(game.home_score)
        if margin_cap is not None:
            margin = max(-margin_cap, min(margin_cap, margin))
        normal_matrix[away][away] += 1.0
        normal_matrix[home][home] += 1.0
        normal_matrix[away][home] -= 1.0
        normal_matrix[home][away] -= 1.0
        target[away] += margin
        target[home] -= margin

    strengths = _solve_linear_system(normal_matrix, target)
    standard_errors = []
    for index in range(len(teams)):
        unit_vector = [0.0] * len(teams)
        unit_vector[index] = 1.0
        inverse_column = _solve_linear_system(normal_matrix, unit_vector)
        standard_errors.append(
            GOAL_MARGIN_OBSERVATION_SIGMA * math.sqrt(max(0.0, inverse_column[index]))
        )
    return (
        dict(zip(teams, strengths, strict=True)),
        dict(zip(teams, standard_errors, strict=True)),
    )


def calculate_ratings(
    games: Iterable[Game],
) -> tuple[dict[str, TeamRating], list[RatingSnapshot]]:
    ordered_games = sorted(games, key=lambda game: game.played_at)
    team_names = sorted(
        {
            team
            for game in ordered_games
            for team in (game.away_team, game.home_team)
        }
    )
    ratings = {team: TeamRating() for team in team_names}
    history: list[RatingSnapshot] = []
    rated_games: list[Game] = []

    for game in ordered_games:
        if not game.completed or game.game_type.lower() != "regular season":
            continue
        away = ratings[game.away_team]
        home = ratings[game.home_team]
        away_score = int(game.away_score)
        home_score = int(game.home_score)

        if away_score > home_score:
            away.wins += 1
            home.losses += 1
        elif away_score < home_score:
            away.losses += 1
            home.wins += 1
        else:
            away.ties += 1
            home.ties += 1

        away.games += 1
        home.games += 1
        away.goals_for += away_score
        away.goals_against += home_score
        home.goals_for += home_score
        home.goals_against += away_score
        if not game.is_forfeit:
            rated_games.append(game)
            away.rated_games += 1
            home.rated_games += 1

        strengths, standard_errors = _fit_margin_strengths(rated_games, team_names)
        for team, strength in strengths.items():
            ratings[team].expected_margin_vs_average = strength
            ratings[team].elo = INITIAL_ELO + ELO_POINTS_PER_GOAL * strength
            ratings[team].strength_standard_error = standard_errors[team]
        history.append(
            RatingSnapshot(
                week=game.week,
                played_at=game.played_at,
                ratings={team: rating.elo for team, rating in ratings.items()},
            )
        )
    return ratings, history