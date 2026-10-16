"""Walk-forward backtest and hyperparameter search for the strength models."""

import math
import random
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date
from itertools import product
from statistics import fmean

from nycfooty.forecast import estimate_draw_rate
from nycfooty.models import Game
from nycfooty.strength_models import (
    DixonColesParameters,
    FittedModel,
    MarginFit,
    ModelParameters,
    StrengthParameters,
    fit_model,
    margin_sigma,
)
from nycfooty.validation import ARCHIVE_ELIGIBLE_LEAGUES, VALIDATION_SAMPLE

TUNING_LEAGUES = VALIDATION_SAMPLE
TEST_LEAGUES = tuple(
    league for league in ARCHIVE_ELIGIBLE_LEAGUES if league not in VALIDATION_SAMPLE
)


PRE_TUNING_PARAMETERS = ModelParameters(
    ridge=2.0,
    margin_cap=None,
    draw_prior_rate=0.22,
    sigma_scale=1.0,
)


SEARCH_GRID = tuple(
    ModelParameters(
        ridge=ridge,
        margin_cap=margin_cap,
        draw_prior_rate=draw_prior_rate,
        sigma_scale=sigma_scale,
    )
    for ridge, margin_cap, draw_prior_rate, sigma_scale in product(
        (0.5, 1.0, 2.0, 4.0, 8.0, 16.0),
        (1, 2, 3, 4, 5, None),
        (0.12, 0.17, 0.22, 0.27),
        (0.8, 1.0, 1.2, 1.4, 1.7, 2.0),
    )
)


@dataclass(frozen=True)
class BacktestPrediction:
    game_id: str
    played_on: date
    away_team: str
    home_team: str
    away_score: int
    home_score: int
    probabilities: tuple[float, float, float]
    baseline: tuple[float, float, float]

    @property
    def outcome_index(self) -> int:
        if self.away_score > self.home_score:
            return 0
        if self.away_score == self.home_score:
            return 1
        return 2

    @property
    def log_loss(self) -> float:
        return -math.log(max(self.probabilities[self.outcome_index], 1e-15))

    @property
    def baseline_log_loss(self) -> float:
        return -math.log(self.baseline[self.outcome_index])


class WalkForwardBacktest:
    """Predicts each completed regular-season game from results on strictly earlier dates."""

    def __init__(self, games: Iterable[Game]) -> None:
        all_games = list(games)
        self._teams = sorted(
            {team for game in all_games for team in (game.away_team, game.home_team)}
        )
        regular = sorted(
            (
                game
                for game in all_games
                if game.completed and game.game_type.lower() == "regular season"
            ),
            key=lambda game: (game.played_at, game.game_id),
        )
        days = sorted({game.played_at.date() for game in regular})
        self._snapshots = [
            (
                [game for game in regular if game.played_at.date() < day],
                [
                    game
                    for game in regular
                    if game.played_at.date() == day and not game.is_forfeit
                ],
            )
            for day in days[1:]
        ]
        self._fits: dict[tuple, FittedModel] = {}

    def _fit(self, index: int, parameters: StrengthParameters) -> FittedModel:
        training, _ = self._snapshots[index]
        if isinstance(parameters, DixonColesParameters):
            key = (index, "goals", parameters.ridge, parameters.half_life_days, parameters.goal_cap)
        elif parameters.result_weight == 0.0:
            key = (index, "margin", parameters.ridge, parameters.margin_cap)
        else:
            key = (index, parameters)
        if key not in self._fits:
            self._fits[key] = fit_model(parameters, training, self._teams, with_errors=False)
        fitted = self._fits[key]
        # Rho and the draw-implied sigma change predictions without changing fitted strengths.
        if isinstance(parameters, DixonColesParameters):
            return replace(fitted, rho=parameters.rho)
        draw_rate = estimate_draw_rate(
            training,
            prior_rate=parameters.draw_prior_rate,
            prior_games=parameters.draw_prior_games,
        )
        assert isinstance(fitted, MarginFit)
        return replace(fitted, sigma=margin_sigma(draw_rate) * parameters.sigma_scale)

    def predictions(self, parameters: StrengthParameters) -> list[BacktestPrediction]:
        predictions = []
        for index, (training, targets) in enumerate(self._snapshots):
            fitted = self._fit(index, parameters)
            neutral_draw = estimate_draw_rate(training)
            baseline = ((1.0 - neutral_draw) / 2.0, neutral_draw, (1.0 - neutral_draw) / 2.0)
            for game in targets:
                predictions.append(
                    BacktestPrediction(
                        game_id=game.game_id,
                        played_on=game.played_at.date(),
                        away_team=game.away_team,
                        home_team=game.home_team,
                        away_score=int(game.away_score),
                        home_score=int(game.home_score),
                        probabilities=fitted.probabilities(game.away_team, game.home_team),
                        baseline=baseline,
                    )
                )
        return predictions


def walk_forward_predictions(
    games: Iterable[Game],
    parameters: StrengthParameters = ModelParameters(),
) -> list[BacktestPrediction]:
    return WalkForwardBacktest(games).predictions(parameters)


def evaluate_grid(
    league_games: Mapping[str, Sequence[Game]],
    grid: Iterable[StrengthParameters] = SEARCH_GRID,
) -> dict[StrengthParameters, list[BacktestPrediction]]:
    backtests = [WalkForwardBacktest(games) for games in league_games.values()]
    return {
        parameters: [
            prediction
            for backtest in backtests
            for prediction in backtest.predictions(parameters)
        ]
        for parameters in grid
    }


def summarize(predictions: Sequence[BacktestPrediction]) -> dict[str, float]:
    accuracy = fmean(
        max(range(3), key=prediction.probabilities.__getitem__) == prediction.outcome_index
        for prediction in predictions
    )
    confidence = fmean(max(prediction.probabilities) for prediction in predictions)
    return {
        "matches": float(len(predictions)),
        "log_loss": fmean(prediction.log_loss for prediction in predictions),
        "baseline_log_loss": fmean(prediction.baseline_log_loss for prediction in predictions),
        "brier": fmean(
            sum(
                (probability - (index == prediction.outcome_index)) ** 2
                for index, probability in enumerate(prediction.probabilities)
            )
            for prediction in predictions
        ),
        "accuracy": accuracy,
        "confidence": confidence,
        "confidence_gap": confidence - accuracy,
    }


def paired_log_loss_difference(
    candidate: Sequence[BacktestPrediction],
    reference: Sequence[BacktestPrediction],
    *,
    resamples: int = 5000,
    seed: int = 5086028,
) -> tuple[float, float, float]:
    """Mean candidate-minus-reference log loss with a 95% match-bootstrap interval."""
    differences = [
        first.log_loss - second.log_loss
        for first, second in zip(candidate, reference, strict=True)
    ]
    generator = random.Random(seed)
    means = sorted(
        fmean(generator.choices(differences, k=len(differences)))
        for _ in range(resamples)
    )
    return (
        fmean(differences),
        means[int(0.025 * resamples)],
        means[int(0.975 * resamples) - 1],
    )
