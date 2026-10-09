"""Print each completed result in a week with its archived pre-game probability."""

import csv
import sys
from pathlib import Path

DATA = Path(__file__).resolve().parents[4] / "data"


def main(week: str) -> None:
    with (DATA / "archive" / f"forecasts_pre_week{week}.csv").open(encoding="utf-8") as handle:
        forecasts = {row["game_id"]: row for row in csv.DictReader(handle)}
    with (DATA / "schedule.csv").open(encoding="utf-8") as handle:
        games = [
            row
            for row in csv.DictReader(handle)
            if row["week"] == week and row["completed"] == "True"
        ]
    for game in games:
        forecast = forecasts[game["game_id"]]
        away, home = int(game["away_score"]), int(game["home_score"])
        if away > home:
            outcome, probability = "away win", forecast["away_win_pct"]
        elif home > away:
            outcome, probability = "home win", forecast["home_win_pct"]
        else:
            outcome, probability = "draw", forecast["draw_pct"]
        print(
            f'{game["away_team"]} {away}-{home} {game["home_team"]}: '
            f"{outcome} had {probability}% pre-game"
        )


if __name__ == "__main__":
    main(sys.argv[1])
