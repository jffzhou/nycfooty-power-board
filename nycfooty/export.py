import csv
import json
import os
import shutil
import subprocess
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from pathlib import Path

from nycfooty.constants import DEFAULT_SIMULATIONS, DIST_ROOT, ELO_POINTS_PER_GOAL, INITIAL_ELO, PROJECT_ROOT, WEB_ROOT
from nycfooty.dashboard_data import POWER_RANGE_Z, build_dashboard_bundle, build_dashboard_data
from nycfooty.flow import calculate_dominance_flow
from nycfooty.forecast import complete_round_robin, forecast_history
from nycfooty.graph import analyze_result_graph
from nycfooty.models import Game, StandingForecast
from nycfooty.ratings import calculate_ratings, power_rating
from nycfooty.strength_models import DEFAULT_MODEL, MODEL_CHOICES, fit_model


def _write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _projected_rows(season_forecast: list[StandingForecast]) -> list[dict[str, object]]:
    return [
        {
            "projected_rank": item.projected_rank,
            "team": item.team,
            "current_points": item.current_points,
            "expected_remaining_points": round(
                item.expected_points - item.current_points,
                2,
            ),
            "expected_points": round(item.expected_points, 2),
            "expected_wins": round(item.expected_wins, 2),
            "expected_losses": round(item.expected_losses, 2),
            "expected_ties": round(item.expected_ties, 2),
            "average_finish": round(item.average_finish, 2),
            "first_pct": round(item.first_probability * 100.0, 2),
            "top_four_pct": round(item.top_four_probability * 100.0, 2),
            "final_pct": round(item.final_probability * 100.0, 2),
            "champion_pct": round(item.champion_probability * 100.0, 2),
        }
        for item in season_forecast
    ]


def _projection_history_rows(
    history: list[tuple[int, list[StandingForecast]]],
    fixed_strength_history: list[tuple[int, list[StandingForecast]]],
) -> list[dict[str, object]]:
    fixed_by_week = {
        week: {item.team: item for item in snapshot}
        for week, snapshot in fixed_strength_history
    }
    return [
        {
            "week": week,
            "team": item.team,
            "first_pct": round(item.first_probability * 100.0, 2),
            "top_four_pct": round(item.top_four_probability * 100.0, 2),
            "first_pct_hindsight": round(
                fixed_by_week[week][item.team].first_probability * 100.0,
                2,
            ),
            "top_four_pct_hindsight": round(
                fixed_by_week[week][item.team].top_four_probability * 100.0,
                2,
            ),
        }
        for week, snapshot in history
        for item in snapshot
    ]


def _build_dashboard(destination: Path) -> None:
    local_node_bin = PROJECT_ROOT / ".node" / "bin"
    npm = local_node_bin / "npm"
    if not npm.exists():
        system_npm = shutil.which("npm")
        if system_npm is None:
            raise RuntimeError("Node/npm is required to build dashboard.html")
        npm = Path(system_npm)

    environment = os.environ.copy()
    environment["PATH"] = f"{local_node_bin}:{environment.get('PATH', '')}"
    subprocess.run(
        [str(npm), "run", "build"],
        cwd=PROJECT_ROOT,
        env=environment,
        check=True,
    )
    shutil.copy2(DIST_ROOT / "index.html", destination)


def write_outputs(
    games: list[Game],
    standings: list[dict[str, str]],
    output_dir: Path,
    *,
    simulations: int = DEFAULT_SIMULATIONS,
) -> dict[str, Path]:
    generated_at = datetime.now().astimezone()
    ratings, _ = calculate_ratings(games)
    result_graph = analyze_result_graph(games)
    dominance_flow = calculate_dominance_flow(result_graph)
    round_robin_games = complete_round_robin(games)
    scenarios = {"schedule": games, "roundRobin": round_robin_games}
    jobs = [
        (model, scenario, fixed)
        for model in MODEL_CHOICES
        for scenario in scenarios
        for fixed in (False, True)
    ]
    with ProcessPoolExecutor(max_workers=min(len(jobs), os.cpu_count() or 1)) as pool:
        futures = {
            (model, scenario, fixed): pool.submit(
                forecast_history,
                scenarios[scenario],
                simulations=simulations,
                fixed_strengths=fixed,
                model=MODEL_CHOICES[model].parameters,
            )
            for model, scenario, fixed in jobs
        }
        histories = {key: future.result() for key, future in futures.items()}
    projection_history = histories[(DEFAULT_MODEL, "schedule", False)]
    fixed_strength_history = histories[(DEFAULT_MODEL, "schedule", True)]
    round_robin_history = histories[(DEFAULT_MODEL, "roundRobin", False)]
    round_robin_fixed_history = histories[(DEFAULT_MODEL, "roundRobin", True)]
    season_forecast = projection_history[-1][1]
    fitted = fit_model(MODEL_CHOICES[DEFAULT_MODEL].parameters, games, sorted(ratings))
    strength = fitted.strengths
    ranked_teams = sorted(ratings, key=lambda team: strength[team], reverse=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    data_dir = output_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    schedule_rows = [
        {
            "game_id": game.game_id,
            "week": game.week,
            "played_at": game.played_at.isoformat(),
            "game_type": game.game_type,
            "away_team": game.away_team,
            "away_score": "" if game.away_score is None else game.away_score,
            "home_team": game.home_team,
            "home_score": "" if game.home_score is None else game.home_score,
            "completed": game.completed,
            "forfeit": game.is_forfeit,
            "location": game.location,
            "status": game.status,
            "note": game.note,
        }
        for game in games
    ]
    rating_rows = [
        {
            "rank": rank,
            "team": team,
            "power_rating": power_rating(INITIAL_ELO + ELO_POINTS_PER_GOAL * strength[team]),
            "elo": round(INITIAL_ELO + ELO_POINTS_PER_GOAL * strength[team], 1),
            "games": ratings[team].games,
            "rated_games": ratings[team].rated_games,
            "wins": ratings[team].wins,
            "losses": ratings[team].losses,
            "ties": ratings[team].ties,
            "goals_for": ratings[team].goals_for,
            "goals_against": ratings[team].goals_against,
            "goal_difference": ratings[team].goal_difference,
            "expected_margin_vs_average": round(strength[team], 3),
            "strength_standard_error": round(fitted.standard_errors[team], 3),
            "power_80_low": round(max(1.0, 5.0 + strength[team] - POWER_RANGE_Z * fitted.standard_errors[team]), 2),
            "power_80_high": round(min(10.0, 5.0 + strength[team] + POWER_RANGE_Z * fitted.standard_errors[team]), 2),
        }
        for rank, team in enumerate(ranked_teams, start=1)
    ]
    forecast_rows = []
    for game in games:
        if game.completed:
            continue
        away_win, draw, home_win = fitted.probabilities(game.away_team, game.home_team)
        forecast_rows.append(
            {
                "game_id": game.game_id,
                "week": game.week,
                "played_at": game.played_at.isoformat(),
                "away_team": game.away_team,
                "away_win_pct": round(away_win * 100.0, 1),
                "draw_pct": round(draw * 100.0, 1),
                "home_win_pct": round(home_win * 100.0, 1),
                "home_team": game.home_team,
            }
        )
    projected_rows = _projected_rows(season_forecast)
    projection_history_rows = _projection_history_rows(
        projection_history,
        fixed_strength_history,
    )
    round_robin_projected_rows = _projected_rows(round_robin_history[-1][1])
    round_robin_history_rows = _projection_history_rows(
        round_robin_history,
        round_robin_fixed_history,
    )

    outputs = {
        "dashboard": output_dir / "dashboard.html",
        "schedule": data_dir / "schedule.csv",
        "standings": data_dir / "standings.csv",
        "ratings": data_dir / "ratings.csv",
        "forecasts": data_dir / "forecasts.csv",
        "projection": data_dir / "projected_standings.csv",
        "projection_history": data_dir / "projection_history.csv",
        "round_robin_projection": data_dir / "projected_standings_round_robin.csv",
        "round_robin_history": data_dir / "projection_history_round_robin.csv",
        "flow": data_dir / "dominance_flow.csv",
    }
    _write_csv(outputs["schedule"], schedule_rows, list(schedule_rows[0]))
    _write_csv(outputs["standings"], standings, list(standings[0]))
    _write_csv(outputs["ratings"], rating_rows, list(rating_rows[0]))
    _write_csv(
        outputs["forecasts"],
        forecast_rows,
        [
            "game_id",
            "week",
            "played_at",
            "away_team",
            "away_win_pct",
            "draw_pct",
            "home_win_pct",
            "home_team",
        ],
    )
    _write_csv(outputs["projection"], projected_rows, list(projected_rows[0]))
    _write_csv(
        outputs["projection_history"],
        projection_history_rows,
        list(projection_history_rows[0]),
    )
    _write_csv(
        outputs["round_robin_projection"],
        round_robin_projected_rows,
        list(round_robin_projected_rows[0]),
    )
    _write_csv(
        outputs["round_robin_history"],
        round_robin_history_rows,
        list(round_robin_history_rows[0]),
    )
    total_flow_credit = sum(dominance_flow.retained_credit.values())
    flow_rows = [
        {
            "rank": rank,
            "team_or_cycle": " + ".join(component),
            "retained_credit": round(dominance_flow.retained_credit[component], 4),
            "flow_share_pct": round(
                100.0 * dominance_flow.retained_credit[component] / total_flow_credit,
                2,
            ),
        }
        for rank, component in enumerate(
            sorted(
                result_graph.components,
                key=lambda item: dominance_flow.retained_credit[item],
                reverse=True,
            ),
            start=1,
        )
    ]
    _write_csv(outputs["flow"], flow_rows, list(flow_rows[0]))

    payloads = {
        model: build_dashboard_data(
            games,
            standings,
            histories[(model, "schedule", False)][-1][1],
            generated_at=generated_at,
            simulations=simulations,
            projection_history=histories[(model, "schedule", False)],
            fixed_strength_history=histories[(model, "schedule", True)],
            round_robin_history=histories[(model, "roundRobin", False)],
            round_robin_fixed_history=histories[(model, "roundRobin", True)],
            model=model,
        )
        for model in MODEL_CHOICES
    }
    comparison_path = output_dir / "data" / "model_comparison.csv"
    comparison = (
        list(csv.DictReader(comparison_path.open(encoding="utf-8")))
        if comparison_path.exists()
        else []
    )
    (WEB_ROOT / "generated-data.json").write_text(
        json.dumps(build_dashboard_bundle(payloads, comparison), indent=2, ensure_ascii=True),
        encoding="utf-8",
    )
    _build_dashboard(outputs["dashboard"])
    return outputs