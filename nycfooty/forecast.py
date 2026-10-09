import math
import random
from bisect import bisect_left, bisect_right
from collections.abc import Iterable
from dataclasses import replace
from datetime import timedelta
from itertools import combinations, product

from nycfooty.constants import (
    DEFAULT_SIMULATIONS,
    DRAW_PRIOR_GAMES,
    DRAW_PRIOR_RATE,
    ELO_POINTS_PER_GOAL,
    FORECAST_SIGMA_SCALE,
    LEAGUE_ID,
)
from nycfooty.models import Game, StandingForecast
from nycfooty.ratings import calculate_ratings


def estimate_draw_rate(
    games: Iterable[Game],
    *,
    prior_rate: float = DRAW_PRIOR_RATE,
    prior_games: float = DRAW_PRIOR_GAMES,
) -> float:
    completed = [game for game in games if game.completed and not game.is_forfeit]
    draws = sum(game.away_score == game.home_score for game in completed)
    return (draws + prior_games * prior_rate) / (len(completed) + prior_games)


def _regular_season(games: Iterable[Game]) -> list[Game]:
    return [game for game in games if game.game_type.lower() == "regular season"]


def unplayed_pairings(games: Iterable[Game]) -> list[tuple[str, str]]:
    regular = _regular_season(games)
    teams = sorted({team for game in regular for team in (game.away_team, game.home_team)})
    scheduled = {frozenset((game.away_team, game.home_team)) for game in regular}
    return [
        (first, second)
        for first, second in combinations(teams, 2)
        if frozenset((first, second)) not in scheduled
    ]


def complete_round_robin(games: Iterable[Game]) -> list[Game]:
    """Append one unplayed hypothetical fixture for every pairing the schedule omits."""
    all_games = list(games)
    regular = _regular_season(all_games)
    if not regular:
        return all_games
    team_ids = {
        team: team_id
        for game in regular
        for team, team_id in (
            (game.away_team, game.away_team_id),
            (game.home_team, game.home_team_id),
        )
    }
    last_game = max(regular, key=lambda game: game.played_at)
    hypothetical = [
        replace(
            last_game,
            game_id=f"round-robin-{index}",
            week=last_game.week + 1,
            played_at=last_game.played_at + timedelta(days=7),
            away_team=away,
            away_team_id=team_ids[away],
            home_team=home,
            home_team_id=team_ids[home],
            away_score=None,
            home_score=None,
            status="Hypothetical round-robin fixture",
            note="",
        )
        for index, (away, home) in enumerate(unplayed_pairings(regular), start=1)
    ]
    return [*all_games, *hypothetical]


def _margin_sigma(draw_rate: float) -> float:
    target_draw_rate = min(0.35, max(0.03, draw_rate))
    lower_sigma, upper_sigma = 0.1, 20.0
    for _ in range(60):
        sigma = (lower_sigma + upper_sigma) / 2.0
        equal_team_draw_rate = math.erf(0.5 / (sigma * math.sqrt(2.0)))
        if equal_team_draw_rate > target_draw_rate:
            lower_sigma = sigma
        else:
            upper_sigma = sigma
    return (lower_sigma + upper_sigma) / 2.0


def forecast_match(
    first_elo: float,
    second_elo: float,
    *,
    draw_rate: float,
    sigma_scale: float = FORECAST_SIGMA_SCALE,
) -> tuple[float, float, float]:
    sigma = _margin_sigma(draw_rate) * sigma_scale
    expected_margin = (first_elo - second_elo) / ELO_POINTS_PER_GOAL

    def margin_cdf(value: float) -> float:
        standardized = (value - expected_margin) / (sigma * math.sqrt(2.0))
        return 0.5 * (1.0 + math.erf(standardized))

    second_win = margin_cdf(-0.5)
    draw_probability = margin_cdf(0.5) - second_win
    first_win = 1.0 - margin_cdf(0.5)
    return first_win, draw_probability, second_win


def _sample_poisson(random_generator: random.Random, rate: float) -> int:
    threshold = math.exp(-rate)
    product = 1.0
    count = 0
    while product > threshold:
        count += 1
        product *= random_generator.random()
    return count - 1


def simulation_sigma(games: Iterable[Game]) -> float:
    return _margin_sigma(estimate_draw_rate(games)) * FORECAST_SIGMA_SCALE


def _knockout_probability(expected_margin: float, sigma: float) -> float:
    """Win probability with a drawn knockout game settled 50/50."""

    def margin_cdf(value: float) -> float:
        return 0.5 * (1.0 + math.erf((value - expected_margin) / (sigma * math.sqrt(2.0))))

    return 1.0 - 0.5 * margin_cdf(0.5) - 0.5 * margin_cdf(-0.5)


def playoff_status(
    games: Iterable[Game],
    *,
    spots: int,
    exact_limit: int = 10,
) -> dict[str, dict[str, object]]:
    """Points-only clinch/elimination; ties count against the team because tiebreakers are unknown.

    Exact over every win/draw/loss outcome when at most `exact_limit` games remain,
    otherwise a conservative bound that ignores rivals having to play each other.
    """
    all_games = list(games)
    ratings, _ = calculate_ratings(all_games)
    teams = sorted(ratings)
    count = len(teams)
    index = {team: position for position, team in enumerate(teams)}
    base = [3 * ratings[team].wins + ratings[team].ties for team in teams]
    remaining = [
        (index[game.away_team], index[game.home_team])
        for game in _regular_season(all_games)
        if not game.completed
    ]
    games_left = [0] * count
    for away, home in remaining:
        games_left[away] += 1
        games_left[home] += 1
    max_points = [base[team] + 3 * games_left[team] for team in range(count)]
    exact = len(remaining) <= exact_limit
    if exact:
        clinched = [True] * count
        eliminated = [True] * count
        for outcome in product((0, 1, 2), repeat=len(remaining)):
            points = base.copy()
            for (away, home), result in zip(remaining, outcome, strict=True):
                if result == 0:
                    points[away] += 3
                elif result == 2:
                    points[home] += 3
                else:
                    points[away] += 1
                    points[home] += 1
            ascending = sorted(points)
            for team in range(count):
                at_least = count - bisect_left(ascending, points[team]) - 1
                ahead = count - bisect_right(ascending, points[team])
                clinched[team] = clinched[team] and at_least < spots
                eliminated[team] = eliminated[team] and ahead >= spots
            if not any(clinched) and not any(eliminated):
                break
    else:
        clinched = [
            sum(max_points[other] >= base[team] for other in range(count) if other != team) < spots
            for team in range(count)
        ]
        eliminated = [
            sum(base[other] > max_points[team] for other in range(count) if other != team) >= spots
            for team in range(count)
        ]
    return {
        team: {
            "clinched": clinched[position],
            "eliminated": eliminated[position],
            "maxPoints": max_points[position],
            "exact": exact,
        }
        for position, team in enumerate(teams)
    }


def average_losing_score(games: Iterable[Game]) -> float:
    completed = [game for game in games if game.completed and not game.is_forfeit]
    return (
        sum(min(int(game.away_score), int(game.home_score)) for game in completed)
        / max(1, len(completed))
    )


def forecast_final_standings(
    games: Iterable[Game],
    *,
    simulations: int = DEFAULT_SIMULATIONS,
    seed: int = int(LEAGUE_ID),
    strength_games: Iterable[Game] | None = None,
) -> list[StandingForecast]:
    if simulations <= 0:
        raise ValueError("simulations must be positive")

    all_games = list(games)
    model_games = all_games if strength_games is None else list(strength_games)
    ratings, _ = calculate_ratings(all_games)
    strengths, _ = calculate_ratings(model_games)
    teams = sorted(ratings)
    team_index = {team: index for index, team in enumerate(teams)}
    sigma = simulation_sigma(model_games)
    fixtures = [
        (
            team_index[game.away_team],
            team_index[game.home_team],
            (
                strengths[game.away_team].expected_margin_vs_average
                - strengths[game.home_team].expected_margin_vs_average
            ),
        )
        for game in all_games
        if not game.completed and game.game_type.lower() == "regular season"
    ]
    base_points = [3 * ratings[team].wins + ratings[team].ties for team in teams]
    base_wins = [ratings[team].wins for team in teams]
    base_losses = [ratings[team].losses for team in teams]
    base_ties = [ratings[team].ties for team in teams]
    base_goal_difference = [ratings[team].goal_difference for team in teams]
    base_goals_against = [ratings[team].goals_against for team in teams]
    losing_score_rate = average_losing_score(all_games)
    team_strength = [
        strengths[team].expected_margin_vs_average if team in strengths else 0.0
        for team in teams
    ]
    knockout = [
        [_knockout_probability(first - second, sigma) for second in team_strength]
        for first in team_strength
    ]
    totals = {
        "points": [0.0] * len(teams),
        "wins": [0.0] * len(teams),
        "losses": [0.0] * len(teams),
        "ties": [0.0] * len(teams),
        "finish": [0.0] * len(teams),
        "first": [0] * len(teams),
        "top_four": [0] * len(teams),
        "final": [0.0] * len(teams),
        "champion": [0.0] * len(teams),
    }
    random_generator = random.Random(seed)

    for _ in range(simulations):
        points = base_points.copy()
        wins = base_wins.copy()
        losses = base_losses.copy()
        ties = base_ties.copy()
        goal_difference = base_goal_difference.copy()
        goals_against = base_goals_against.copy()
        for away, home, expected_margin in fixtures:
            sampled_margin = random_generator.gauss(expected_margin, sigma)
            base_score = _sample_poisson(random_generator, losing_score_rate)
            if sampled_margin > 0.5:
                margin = max(1, round(sampled_margin))
                wins[away] += 1
                losses[home] += 1
                points[away] += 3
                goal_difference[away] += margin
                goal_difference[home] -= margin
                goals_against[away] += base_score
                goals_against[home] += base_score + margin
            elif sampled_margin < -0.5:
                margin = max(1, round(-sampled_margin))
                wins[home] += 1
                losses[away] += 1
                points[home] += 3
                goal_difference[home] += margin
                goal_difference[away] -= margin
                goals_against[home] += base_score
                goals_against[away] += base_score + margin
            else:
                ties[away] += 1
                ties[home] += 1
                points[away] += 1
                points[home] += 1
                goals_against[away] += base_score
                goals_against[home] += base_score

        order = list(range(len(teams)))
        random_generator.shuffle(order)
        order.sort(
            key=lambda index: (
                points[index],
                goal_difference[index],
                -goals_against[index],
            ),
            reverse=True,
        )
        for position, index in enumerate(order, start=1):
            totals["points"][index] += points[index]
            totals["wins"][index] += wins[index]
            totals["losses"][index] += losses[index]
            totals["ties"][index] += ties[index]
            totals["finish"][index] += position
            if position == 1:
                totals["first"][index] += 1
            if position <= min(4, len(teams)):
                totals["top_four"][index] += 1
        if len(order) >= 4:
            # Bracket odds are exact given the seeds, so they add no random draws.
            seed_one, seed_two, seed_three, seed_four = order[:4]
            reach_final = {
                seed_one: knockout[seed_one][seed_four],
                seed_four: knockout[seed_four][seed_one],
                seed_two: knockout[seed_two][seed_three],
                seed_three: knockout[seed_three][seed_two],
            }
            for team, probability in reach_final.items():
                totals["final"][team] += probability
            for upper in (seed_one, seed_four):
                for lower in (seed_two, seed_three):
                    meeting = reach_final[upper] * reach_final[lower]
                    totals["champion"][upper] += meeting * knockout[upper][lower]
                    totals["champion"][lower] += meeting * knockout[lower][upper]

    forecasts = [
        StandingForecast(
            projected_rank=0,
            team=team,
            current_points=base_points[index],
            expected_points=totals["points"][index] / simulations,
            expected_wins=totals["wins"][index] / simulations,
            expected_losses=totals["losses"][index] / simulations,
            expected_ties=totals["ties"][index] / simulations,
            average_finish=totals["finish"][index] / simulations,
            first_probability=totals["first"][index] / simulations,
            top_four_probability=totals["top_four"][index] / simulations,
            final_probability=totals["final"][index] / simulations,
            champion_probability=totals["champion"][index] / simulations,
        )
        for index, team in enumerate(teams)
    ]
    forecasts.sort(key=lambda item: (item.average_finish, -item.expected_points, item.team))
    return [replace(item, projected_rank=rank) for rank, item in enumerate(forecasts, start=1)]


def forecast_history(
    games: Iterable[Game],
    *,
    simulations: int = DEFAULT_SIMULATIONS,
    seed: int = int(LEAGUE_ID),
    fixed_strengths: bool = False,
) -> list[tuple[int, list[StandingForecast]]]:
    all_games = list(games)
    strength_games = all_games if fixed_strengths else None
    completed_weeks = sorted({game.week for game in all_games if game.completed})
    history = []
    for week in [0, *completed_weeks]:
        known_games = [
            game if game.week <= week else replace(game, away_score=None, home_score=None)
            for game in all_games
        ]
        history.append(
            (
                week,
                forecast_final_standings(
                    known_games,
                    simulations=simulations,
                    seed=seed,
                    strength_games=strength_games,
                ),
            )
        )
    return history