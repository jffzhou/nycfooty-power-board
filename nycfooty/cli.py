import argparse
from pathlib import Path

from nycfooty.client import fetch_league_data
from nycfooty.constants import DEFAULT_SIMULATIONS, PROJECT_ROOT
from nycfooty.export import write_outputs


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Refresh NYC Footy league results and forecasts",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT,
        help="Directory for dashboard.html and data CSVs",
    )
    parser.add_argument(
        "--simulations",
        type=int,
        default=DEFAULT_SIMULATIONS,
        help="Number of seeded final-standings simulations",
    )
    args = parser.parse_args()
    games, standings = fetch_league_data()
    outputs = write_outputs(
        games,
        standings,
        args.output_dir,
        simulations=args.simulations,
    )
    completed = sum(game.completed for game in games)
    print(f"Fetched {len(games)} games ({completed} completed) and {len(standings)} teams")
    for label, path in outputs.items():
        print(f"{label:10} {path}")