from pathlib import Path


LEAGUE_ID = "5086028"
BASE_URL = "https://nycfooty.leagueapps.com"
PROFILE_URL = (
    f"{BASE_URL}/leagues/soccer-(outdoor)/{LEAGUE_ID}-2026-fall--thursdays--"
    "two-bridges-tanahey-playground--7v7-coed--p4p5"
)
SCHEDULE_PAGE_URL = f"{BASE_URL}/leagues/{LEAGUE_ID}/schedule"
SCHEDULE_DATA_URL = f"{BASE_URL}/ajax/loadSchedule"
STANDINGS_URL = f"{BASE_URL}/leagues/{LEAGUE_ID}/standings"

INITIAL_ELO = 1500.0
ELO_POINTS_PER_GOAL = 100.0
# Tuned 2026-10-09 by backtest_hyperparameters.py; see README "Model history".
MARGIN_RIDGE = 0.5
MARGIN_CAP = 4
GOAL_MARGIN_OBSERVATION_SIGMA = 2.0
DRAW_PRIOR_RATE = 0.17
DRAW_PRIOR_GAMES = 20.0
FORECAST_SIGMA_SCALE = 1.2
DEFAULT_SIMULATIONS = 25_000
KNOWN_FORFEIT_GAME_IDS = frozenset({"13852824"})

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WEB_ROOT = PROJECT_ROOT / "web"
DIST_ROOT = PROJECT_ROOT / "dist"

TEAM_COLORS = (
    "#087f5b",
    "#d1495b",
    "#276fbf",
    "#e09f3e",
    "#725ac1",
    "#0081a7",
    "#c8553d",
    "#59656f",
    "#c13584",
    "#6a994e",
)