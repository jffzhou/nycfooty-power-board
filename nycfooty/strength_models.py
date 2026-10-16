"""Team-strength models behind every forecast.

Two families share one interface (strengths in goals per game versus an average team,
match probabilities, knockout odds, and score sampling for season simulations):

- `ModelParameters`: goal-margin least squares. `result_weight` > 0 blends in the
  win/draw/loss likelihood of the same forecast distribution ("results + margin").
- `DixonColesParameters`: Poisson attack/defence goals model with the Dixon-Coles
  low-score correction and optional time decay.
"""

import math
import random
from bisect import bisect_left
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field

from nycfooty.constants import (
    DRAW_PRIOR_GAMES,
    DRAW_PRIOR_RATE,
    FORECAST_SIGMA_SCALE,
    GOAL_MARGIN_OBSERVATION_SIGMA,
    MARGIN_CAP,
    MARGIN_RIDGE,
)
from nycfooty.models import Game
from nycfooty.ratings import _fit_margin_strengths, _solve_linear_system, relative_standard_errors

SQRT_TWO = math.sqrt(2.0)
DIXON_COLES_MAX_GOALS = 20
DIXON_COLES_PRIOR_GOALS = 2.0
DIXON_COLES_MU_PRECISION = 0.01


@dataclass(frozen=True)
class ModelParameters:
    ridge: float = MARGIN_RIDGE
    margin_cap: int | None = MARGIN_CAP
    draw_prior_rate: float = DRAW_PRIOR_RATE
    draw_prior_games: float = DRAW_PRIOR_GAMES
    sigma_scale: float = FORECAST_SIGMA_SCALE
    result_weight: float = 0.0


@dataclass(frozen=True)
class DixonColesParameters:
    """Defaults were selected 2026-10-16 by backtest_models.py on the tuning leagues."""

    ridge: float = 2.0
    rho: float = 0.15
    half_life_days: float | None = 28.0
    goal_cap: int | None = 4


StrengthParameters = ModelParameters | DixonColesParameters


def estimate_draw_rate(
    games: Iterable[Game],
    *,
    prior_rate: float = DRAW_PRIOR_RATE,
    prior_games: float = DRAW_PRIOR_GAMES,
) -> float:
    completed = [game for game in games if game.completed and not game.is_forfeit]
    draws = sum(game.away_score == game.home_score for game in completed)
    return (draws + prior_games * prior_rate) / (len(completed) + prior_games)


def margin_sigma(draw_rate: float) -> float:
    """Normal margin noise under which two equal teams draw (|margin| < 0.5) at `draw_rate`."""
    target_draw_rate = min(0.35, max(0.03, draw_rate))
    lower_sigma, upper_sigma = 0.1, 20.0
    for _ in range(60):
        sigma = (lower_sigma + upper_sigma) / 2.0
        equal_team_draw_rate = math.erf(0.5 / (sigma * SQRT_TWO))
        if equal_team_draw_rate > target_draw_rate:
            lower_sigma = sigma
        else:
            upper_sigma = sigma
    return (lower_sigma + upper_sigma) / 2.0


def normal_outcome_probabilities(expected_margin: float, sigma: float) -> tuple[float, float, float]:
    def margin_cdf(value: float) -> float:
        return 0.5 * (1.0 + math.erf((value - expected_margin) / (sigma * SQRT_TWO)))

    second_win = margin_cdf(-0.5)
    draw = margin_cdf(0.5) - second_win
    return 1.0 - margin_cdf(0.5), draw, second_win


def sample_poisson(random_generator: random.Random, rate: float) -> int:
    threshold = math.exp(-rate)
    product = 1.0
    count = 0
    while product > threshold:
        count += 1
        product *= random_generator.random()
    return count - 1


def _rated_games(games: Iterable[Game]) -> list[Game]:
    return [
        game
        for game in games
        if game.completed and not game.is_forfeit and game.game_type.lower() == "regular season"
    ]


ScoreSampler = Callable[[random.Random], tuple[int, int]]


@dataclass(frozen=True)
class MarginFit:
    strengths: dict[str, float]
    standard_errors: dict[str, float]
    sigma: float

    kind = "margin"

    def expected_margin(self, first: str, second: str) -> float:
        return self.strengths[first] - self.strengths[second]

    def probabilities(self, first: str, second: str) -> tuple[float, float, float]:
        return normal_outcome_probabilities(self.expected_margin(first, second), self.sigma)

    def knockout(self, first: str, second: str) -> float:
        win, draw, _ = self.probabilities(first, second)
        return win + 0.5 * draw

    def sampler(self, first: str, second: str, losing_score_rate: float) -> ScoreSampler:
        mean = self.expected_margin(first, second)
        sigma = self.sigma

        def sample(random_generator: random.Random) -> tuple[int, int]:
            sampled = random_generator.gauss(mean, sigma)
            base = sample_poisson(random_generator, losing_score_rate)
            if sampled > 0.5:
                return base + max(1, round(sampled)), base
            if sampled < -0.5:
                return base, base + max(1, round(-sampled))
            return base, base

        return sample

    def simulator_fixture(self, first: str, second: str) -> dict[str, float]:
        return {"expectedMargin": self.expected_margin(first, second)}


def _normal_cdf(value: float) -> float:
    return 0.5 * math.erfc(-value / SQRT_TWO)


def _normal_pdf(value: float) -> float:
    return math.exp(-0.5 * value * value) / math.sqrt(2.0 * math.pi)


def _result_terms(delta: float, outcome: int, sigma: float) -> tuple[float, float, float]:
    """Negative log-probability of a win (1), draw (0) or loss (-1) and its first two derivatives in delta."""
    if outcome:
        z = (outcome * delta - 0.5) / sigma
        cdf = _normal_cdf(z)
        if cdf < 1e-300:
            mills = -z
            negative_log = 0.5 * z * z + math.log(-z) + 0.5 * math.log(2.0 * math.pi)
        else:
            mills = _normal_pdf(z) / cdf
            negative_log = -math.log(cdf)
        return negative_log, -outcome * mills / sigma, mills * (z + mills) / (sigma * sigma)
    upper = (0.5 - delta) / sigma
    lower = (-0.5 - delta) / sigma
    if lower > 0.0:
        probability = 0.5 * (math.erfc(lower / SQRT_TWO) - math.erfc(upper / SQRT_TWO))
    else:
        probability = 0.5 * (math.erfc(-upper / SQRT_TWO) - math.erfc(-lower / SQRT_TWO))
    probability = max(probability, 1e-300)
    upper_density, lower_density = _normal_pdf(upper), _normal_pdf(lower)
    slope = -(upper_density - lower_density) / sigma / probability
    curvature = (-upper * upper_density + lower * lower_density) / (sigma * sigma) / probability
    return -math.log(probability), -slope, slope * slope - curvature


def _newton(
    evaluate: Callable[[list[float], bool], tuple[float, list[float], list[list[float]]]],
    start: list[float],
    *,
    iterations: int = 100,
    tolerance: float = 1e-10,
) -> tuple[list[float], list[list[float]]]:
    """Minimize a convex objective by damped Newton steps; returns the optimum and its Hessian."""
    theta = start[:]
    value, gradient, hessian = evaluate(theta, True)
    for _ in range(iterations):
        step = _solve_linear_system(hessian, gradient)
        scale = 1.0
        while True:
            candidate = [current - scale * change for current, change in zip(theta, step, strict=True)]
            candidate_value, _, _ = evaluate(candidate, False)
            if candidate_value <= value + 1e-12 or scale < 1e-6:
                break
            scale /= 2.0
        theta = candidate
        value, gradient, hessian = evaluate(theta, True)
        if max(abs(scale * change) for change in step) < tolerance:
            break
    return theta, hessian


def _fit_results_margin(
    games: list[Game],
    teams: list[str],
    parameters: ModelParameters,
    result_sigma: float,
    *,
    with_errors: bool,
) -> tuple[dict[str, float], dict[str, float]]:
    """Minimize (1-w)/2 sum (m - d)^2 - w*s^2 sum log P(result | d) + ridge/2 sum strength^2.

    m is the capped goal margin, d the strength difference, s the margin observation sigma,
    and P the forecast model's win/draw/loss probability. w = 0 is the plain margin model.
    """
    start, _ = _fit_margin_strengths(games, teams, ridge=parameters.ridge, margin_cap=parameters.margin_cap)
    index = {team: position for position, team in enumerate(teams)}
    weight = parameters.result_weight
    result_scale = weight * GOAL_MARGIN_OBSERVATION_SIGMA**2
    cap = parameters.margin_cap
    observations = []
    for game in games:
        margin = int(game.away_score) - int(game.home_score)
        outcome = (margin > 0) - (margin < 0)
        if cap is not None:
            margin = max(-cap, min(cap, margin))
        observations.append((index[game.away_team], index[game.home_team], margin, outcome))

    def evaluate(strengths: list[float], derivatives: bool):
        value = 0.5 * parameters.ridge * sum(strength * strength for strength in strengths)
        gradient = [parameters.ridge * strength for strength in strengths] if derivatives else []
        hessian = []
        if derivatives:
            hessian = [[0.0] * len(teams) for _ in teams]
            for position in range(len(teams)):
                hessian[position][position] = parameters.ridge
        for away, home, margin, outcome in observations:
            delta = strengths[away] - strengths[home]
            negative_log, slope, curvature = _result_terms(delta, outcome, result_sigma)
            residual = margin - delta
            value += 0.5 * (1.0 - weight) * residual * residual + result_scale * negative_log
            if derivatives:
                first = -(1.0 - weight) * residual + result_scale * slope
                second = (1.0 - weight) + result_scale * curvature
                gradient[away] += first
                gradient[home] -= first
                hessian[away][away] += second
                hessian[home][home] += second
                hessian[away][home] -= second
                hessian[home][away] -= second
        return value, gradient, hessian

    strengths, hessian = _newton(evaluate, [start[team] for team in teams])
    standard_errors = (
        relative_standard_errors(hessian, teams, GOAL_MARGIN_OBSERVATION_SIGMA) if with_errors else {}
    )
    return dict(zip(teams, strengths, strict=True)), standard_errors


def _fit_margin_family(
    parameters: ModelParameters,
    games: list[Game],
    teams: list[str],
    *,
    with_errors: bool,
) -> MarginFit:
    rated = _rated_games(games)
    draw_rate = estimate_draw_rate(
        games,
        prior_rate=parameters.draw_prior_rate,
        prior_games=parameters.draw_prior_games,
    )
    sigma = margin_sigma(draw_rate) * parameters.sigma_scale
    if parameters.result_weight == 0.0:
        strengths, standard_errors = _fit_margin_strengths(
            rated,
            teams,
            ridge=parameters.ridge,
            margin_cap=parameters.margin_cap,
        )
    else:
        strengths, standard_errors = _fit_results_margin(
            rated,
            teams,
            parameters,
            sigma,
            with_errors=with_errors,
        )
    return MarginFit(strengths=strengths, standard_errors=standard_errors, sigma=sigma)


def dixon_coles_tau(first_goals: int, second_goals: int, first_rate: float, second_rate: float, rho: float) -> float:
    if first_goals == 0 and second_goals == 0:
        return 1.0 - first_rate * second_rate * rho
    if first_goals == 0 and second_goals == 1:
        return 1.0 + first_rate * rho
    if first_goals == 1 and second_goals == 0:
        return 1.0 + second_rate * rho
    if first_goals == 1 and second_goals == 1:
        return 1.0 - rho
    return 1.0


def dixon_coles_score_table(
    first_rate: float,
    second_rate: float,
    rho: float,
    max_goals: int = DIXON_COLES_MAX_GOALS,
) -> list[tuple[int, int, float]]:
    def pmf(rate: float) -> list[float]:
        values = [math.exp(-rate)]
        for goals in range(1, max_goals + 1):
            values.append(values[-1] * rate / goals)
        return values

    first, second = pmf(first_rate), pmf(second_rate)
    table = [
        (
            first_goals,
            second_goals,
            first[first_goals]
            * second[second_goals]
            * max(0.0, dixon_coles_tau(first_goals, second_goals, first_rate, second_rate, rho)),
        )
        for first_goals in range(max_goals + 1)
        for second_goals in range(max_goals + 1)
    ]
    total = sum(probability for _, _, probability in table)
    return [(first_goals, second_goals, probability / total) for first_goals, second_goals, probability in table]


@dataclass(frozen=True)
class DixonColesFit:
    mu: float
    attack: dict[str, float]
    defense: dict[str, float]
    rho: float
    standard_errors: dict[str, float]
    strengths: dict[str, float] = field(init=False)

    kind = "goals"

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "strengths",
            {
                team: math.exp(self.mu + self.attack[team]) - math.exp(self.mu - self.defense[team])
                for team in self.attack
            },
        )

    def rates(self, first: str, second: str) -> tuple[float, float]:
        return (
            math.exp(self.mu + self.attack[first] - self.defense[second]),
            math.exp(self.mu + self.attack[second] - self.defense[first]),
        )

    def expected_margin(self, first: str, second: str) -> float:
        first_rate, second_rate = self.rates(first, second)
        return first_rate - second_rate

    def score_table(self, first: str, second: str) -> list[tuple[int, int, float]]:
        return dixon_coles_score_table(*self.rates(first, second), self.rho)

    def probabilities(self, first: str, second: str) -> tuple[float, float, float]:
        win = draw = loss = 0.0
        for first_goals, second_goals, probability in self.score_table(first, second):
            if first_goals > second_goals:
                win += probability
            elif first_goals == second_goals:
                draw += probability
            else:
                loss += probability
        return win, draw, loss

    def knockout(self, first: str, second: str) -> float:
        win, draw, _ = self.probabilities(first, second)
        return win + 0.5 * draw

    def sampler(self, first: str, second: str, losing_score_rate: float) -> ScoreSampler:
        table = self.score_table(first, second)
        cumulative = []
        running = 0.0
        for _, _, probability in table:
            running += probability
            cumulative.append(running)
        last = len(table) - 1

        def sample(random_generator: random.Random) -> tuple[int, int]:
            first_goals, second_goals, _ = table[min(last, bisect_left(cumulative, random_generator.random()))]
            return first_goals, second_goals

        return sample

    def simulator_fixture(self, first: str, second: str) -> dict[str, float]:
        first_rate, second_rate = self.rates(first, second)
        return {
            "expectedMargin": first_rate - second_rate,
            "awayRate": first_rate,
            "homeRate": second_rate,
        }


def _fit_dixon_coles(
    parameters: DixonColesParameters,
    games: list[Game],
    teams: list[str],
    *,
    with_errors: bool,
) -> DixonColesFit:
    rated = _rated_games(games)
    count = len(teams)
    index = {team: position for position, team in enumerate(teams)}
    latest = max((game.played_at.date() for game in rated), default=None)
    rows = []
    for game in rated:
        weight = (
            1.0
            if parameters.half_life_days is None
            else 0.5 ** ((latest - game.played_at.date()).days / parameters.half_life_days)
        )
        away_goals, home_goals = int(game.away_score), int(game.home_score)
        if parameters.goal_cap is not None:
            away_goals = min(parameters.goal_cap, away_goals)
            home_goals = min(parameters.goal_cap, home_goals)
        rows.append((index[game.away_team], index[game.home_team], away_goals, home_goals, weight))
    prior_mu = math.log(DIXON_COLES_PRIOR_GOALS)
    exposure = sum(2.0 * weight for *_, weight in rows)
    goals = sum(weight * (away + home) for _, _, away, home, weight in rows)
    start_mu = math.log(max(goals, 0.5) / exposure) if exposure else prior_mu
    size = 2 * count + 1

    def evaluate(theta: list[float], derivatives: bool):
        mu = theta[0]
        value = 0.5 * DIXON_COLES_MU_PRECISION * (mu - prior_mu) ** 2
        value += 0.5 * parameters.ridge * sum(parameter * parameter for parameter in theta[1:])
        gradient: list[float] = []
        hessian: list[list[float]] = []
        if derivatives:
            gradient = [DIXON_COLES_MU_PRECISION * (mu - prior_mu)] + [parameters.ridge * parameter for parameter in theta[1:]]
            hessian = [[0.0] * size for _ in range(size)]
            hessian[0][0] = DIXON_COLES_MU_PRECISION
            for position in range(1, size):
                hessian[position][position] = parameters.ridge
        for away, home, away_goals, home_goals, weight in rows:
            for scorer, conceder, scored in ((away, home, away_goals), (home, away, home_goals)):
                linear = min(50.0, mu + theta[1 + scorer] - theta[1 + count + conceder])
                rate = math.exp(linear)
                value += weight * (rate - scored * linear)
                if derivatives:
                    residual = weight * (rate - scored)
                    curvature = weight * rate
                    positions = (0, 1 + scorer, 1 + count + conceder)
                    signs = (1.0, 1.0, -1.0)
                    for row, row_sign in zip(positions, signs, strict=True):
                        gradient[row] += row_sign * residual
                        for column, column_sign in zip(positions, signs, strict=True):
                            hessian[row][column] += row_sign * column_sign * curvature
        return value, gradient, hessian

    theta, hessian = _newton(evaluate, [start_mu] + [0.0] * (2 * count))
    mu = theta[0]
    attack = {team: theta[1 + position] for position, team in enumerate(teams)}
    defense = {team: theta[1 + count + position] for position, team in enumerate(teams)}
    standard_errors = {}
    if with_errors:
        gradients = []
        for position in range(count):
            scored = math.exp(mu + theta[1 + position])
            conceded = math.exp(mu - theta[1 + count + position])
            gradient = [0.0] * size
            gradient[0] = scored - conceded
            gradient[1 + position] = scored
            gradient[1 + count + position] = conceded
            gradients.append(gradient)
        average = [sum(column) / count for column in zip(*gradients, strict=True)]
        for position, team in enumerate(teams):
            direction = [own - mean for own, mean in zip(gradients[position], average, strict=True)]
            solved = _solve_linear_system(hessian, direction)
            variance = sum(left * right for left, right in zip(direction, solved, strict=True))
            standard_errors[team] = math.sqrt(max(0.0, variance))
    return DixonColesFit(
        mu=mu,
        attack=attack,
        defense=defense,
        rho=parameters.rho,
        standard_errors=standard_errors,
    )


FittedModel = MarginFit | DixonColesFit


@dataclass(frozen=True)
class ModelChoice:
    label: str
    summary: str
    details: str
    parameters: StrengthParameters


MODEL_CHOICES = {
    "margin": ModelChoice(
        "Goal margin",
        "Rates teams by goal margin, adjusted for opponent strength.",
        "Ratings are fitted so that rating differences reproduce observed goal margins, each capped at "
        "4 goals. Results enter only through the margin, so a draw is a margin of zero. This is the "
        "default model because neither alternative forecast past leagues measurably better.",
        ModelParameters(),
    ),
    # Challenger settings selected 2026-10-16 by backtest_models.py on the tuning leagues.
    "results": ModelChoice(
        "Results + margin",
        "Rates teams by win, draw and loss results and, with less weight, by goal margin, adjusted "
        "for opponent strength.",
        "The fit weights the likelihood of each observed result at 0.75 and the goal margin, capped "
        "at 2, at 0.25. A 1-0 win therefore counts nearly as much as a 5-0 win, and a single "
        "lopsided result has limited influence. On past leagues its forecasts were as accurate as "
        "the goal-margin model's.",
        ModelParameters(ridge=0.02, margin_cap=2, sigma_scale=1.4, result_weight=0.75),
    ),
    "dixon-coles": ModelChoice(
        "Dixon-Coles goals",
        "Estimates separate attack and defence ratings from goals scored and conceded, weighting "
        "recent matches more heavily.",
        "A team's expected goals in a match depend on its attack rating and the opponent's defence "
        "rating. Goals are modelled as Poisson counts with the Dixon-Coles adjustment for low "
        "scores. A match loses half its weight every 28 days, and goals above four per team in a "
        "match are not counted. The model is widely used for professional football but was the "
        "least accurate of the three on past leagues.",
        DixonColesParameters(),
    ),
}
DEFAULT_MODEL = "margin"


def describe_parameters(parameters: StrengthParameters) -> str:
    def value(item: object) -> str:
        return "none" if item is None else f"{item:g}"

    if isinstance(parameters, DixonColesParameters):
        return (
            f"ridge {value(parameters.ridge)}, rho {value(parameters.rho)}, "
            f"half-life {value(parameters.half_life_days)} days, goal cap {value(parameters.goal_cap)}"
        )
    return (
        f"ridge {value(parameters.ridge)}, cap {value(parameters.margin_cap)}, "
        f"draw prior {parameters.draw_prior_rate:.0%}, sigma x{value(parameters.sigma_scale)}, "
        f"result weight {value(parameters.result_weight)}"
    )


def fit_model(
    parameters: StrengthParameters,
    games: Sequence[Game],
    teams: Sequence[str] | None = None,
    *,
    with_errors: bool = True,
) -> FittedModel:
    """Fit on completed, non-forfeit regular-season games; `teams` defaults to every team in `games`."""
    all_games = list(games)
    team_list = sorted(
        teams
        if teams is not None
        else {team for game in all_games for team in (game.away_team, game.home_team)}
    )
    if isinstance(parameters, DixonColesParameters):
        return _fit_dixon_coles(parameters, all_games, team_list, with_errors=with_errors)
    return _fit_margin_family(parameters, all_games, team_list, with_errors=with_errors)
