from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from nycfooty.constants import INITIAL_ELO, KNOWN_FORFEIT_GAME_IDS


@dataclass(frozen=True)
class Game:
    game_id: str
    week: int
    played_at: datetime
    game_type: str
    away_team: str
    away_team_id: str
    home_team: str
    home_team_id: str
    away_score: int | None
    home_score: int | None
    location: str = ""
    status: str = ""
    note: str = ""

    @property
    def completed(self) -> bool:
        return self.away_score is not None and self.home_score is not None

    @property
    def is_forfeit(self) -> bool:
        return self.game_id in KNOWN_FORFEIT_GAME_IDS or "forfeit" in self.note.lower()


@dataclass
class TeamRating:
    elo: float = INITIAL_ELO
    games: int = 0
    rated_games: int = 0
    wins: int = 0
    losses: int = 0
    ties: int = 0
    goals_for: int = 0
    goals_against: int = 0
    expected_margin_vs_average: float = 0.0
    strength_standard_error: float = 0.0

    @property
    def goal_difference(self) -> int:
        return self.goals_for - self.goals_against


@dataclass(frozen=True)
class RatingSnapshot:
    week: int
    played_at: datetime
    ratings: dict[str, float]


@dataclass(frozen=True)
class ResultEdge:
    source: str
    target: str
    away_team: str
    home_team: str
    away_score: int
    home_score: int
    game_id: str
    week: int
    is_forfeit: bool
    is_tie: bool


@dataclass(frozen=True)
class ResultGraphAnalysis:
    results: tuple[ResultEdge, ...]
    components: tuple[tuple[str, ...], ...]
    component_edges: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...]
    topological_layers: tuple[tuple[tuple[str, ...], ...], ...]
    cyclic_components: tuple[tuple[str, ...], ...]


@dataclass(frozen=True)
class DominanceFlow:
    transfer_rate: float
    retained_credit: dict[tuple[str, ...], float]
    edge_credit: dict[str, float]


@dataclass(frozen=True)
class StandingForecast:
    projected_rank: int
    team: str
    current_points: int
    expected_points: float
    expected_wins: float
    expected_losses: float
    expected_ties: float
    average_finish: float
    first_probability: float
    top_four_probability: float