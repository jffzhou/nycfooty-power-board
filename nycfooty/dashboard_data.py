import math
from datetime import datetime

from nycfooty.constants import INITIAL_ELO, PROFILE_URL, TEAM_COLORS
from nycfooty.flow import calculate_dominance_flow
from nycfooty.forecast import estimate_draw_rate, forecast_match, unplayed_pairings
from nycfooty.graph import analyze_result_graph
from nycfooty.models import Game, StandingForecast
from nycfooty.ratings import calculate_ratings, power_rating, power_rating_interval


def _date_label(value: datetime, *, include_time: bool = False) -> str:
    label = value.strftime("%a, %b %d").replace(" 0", " ")
    if include_time:
        label += value.strftime(" at %I:%M %p").replace(" 0", " ")
    return label


def _projection_rows(season_forecast: list[StandingForecast]) -> list[dict[str, object]]:
    return [
        {
            "rank": item.projected_rank,
            "team": item.team,
            "currentPoints": item.current_points,
            "expectedRemainingPoints": item.expected_points - item.current_points,
            "expectedPoints": item.expected_points,
            "expectedWins": item.expected_wins,
            "expectedLosses": item.expected_losses,
            "expectedTies": item.expected_ties,
            "averageFinish": item.average_finish,
            "firstProbability": item.first_probability,
            "topFourProbability": item.top_four_probability,
        }
        for item in season_forecast
    ]


def _projection_history(
    history: list[tuple[int, list[StandingForecast]]] | None,
    fixed_strength_history: list[tuple[int, list[StandingForecast]]] | None,
    teams: list[str],
    colors: dict[str, str],
) -> dict[str, object]:
    snapshots = [{item.team: item for item in snapshot} for _, snapshot in history or []]
    fixed_snapshots = [
        {item.team: item for item in snapshot}
        for _, snapshot in fixed_strength_history or []
    ]

    def percentages(by_week: list[dict[str, StandingForecast]], team: str, field: str) -> list[float]:
        return [round(100.0 * getattr(by_team[team], field), 1) for by_team in by_week]

    return {
        "labels": ["Start" if week == 0 else f"W{week}" for week, _ in history or []],
        "series": [
            {
                "team": team,
                "color": colors[team],
                "first": percentages(snapshots, team, "first_probability"),
                "topFour": percentages(snapshots, team, "top_four_probability"),
                "firstFixed": percentages(fixed_snapshots, team, "first_probability"),
                "topFourFixed": percentages(fixed_snapshots, team, "top_four_probability"),
            }
            for team in teams
        ],
    }


def build_dashboard_data(
    games: list[Game],
    standings: list[dict[str, str]],
    season_forecast: list[StandingForecast],
    *,
    generated_at: datetime,
    simulations: int,
    projection_history: list[tuple[int, list[StandingForecast]]] | None = None,
    fixed_strength_history: list[tuple[int, list[StandingForecast]]] | None = None,
    round_robin_history: list[tuple[int, list[StandingForecast]]] | None = None,
    round_robin_fixed_history: list[tuple[int, list[StandingForecast]]] | None = None,
) -> dict[str, object]:
    ratings, history = calculate_ratings(games)
    graph = analyze_result_graph(games)
    dominance_flow = calculate_dominance_flow(graph)
    completed = sorted(
        (game for game in games if game.completed),
        key=lambda game: game.played_at,
    )
    upcoming = sorted(
        (game for game in games if not game.completed),
        key=lambda game: game.played_at,
    )
    draw_rate = estimate_draw_rate(games)
    ranked_teams = sorted(ratings, key=lambda team: ratings[team].elo, reverse=True)
    colors = {
        team: TEAM_COLORS[index % len(TEAM_COLORS)]
        for index, team in enumerate(ranked_teams)
    }

    snapshots = {0: {team: INITIAL_ELO for team in ranked_teams}}
    for snapshot in history:
        snapshots[snapshot.week] = snapshot.ratings
    weeks = sorted(snapshots)
    round_robin_forecast = round_robin_history[-1][1] if round_robin_history else []
    series_teams = [item.team for item in season_forecast] or ranked_teams
    pairings = unplayed_pairings(games)
    regular_season = [
        game for game in games if game.game_type.lower() == "regular season"
    ]
    scheduled_opponents = {
        team: {
            game.home_team if game.away_team == team else game.away_team
            for game in regular_season
            if team in (game.away_team, game.home_team)
        }
        for team in ranked_teams
    }
    schedule_forecast_by_team = {item.team: item for item in season_forecast}
    round_robin_by_team = {item.team: item for item in round_robin_forecast}
    rank_by_team = {team: rank for rank, team in enumerate(ranked_teams, start=1)}
    unplayed_by_team = {
        team: sorted(
            (second if first == team else first)
            for first, second in pairings
            if team in (first, second)
        )
        for team in ranked_teams
    }
    schedule_gaps = []
    for team in ranked_teams:
        opponents = unplayed_by_team[team]
        scheduled = schedule_forecast_by_team.get(team)
        round_robin = round_robin_by_team.get(team)
        schedule_gaps.append(
            {
                "team": team,
                "color": colors[team],
                "power": power_rating(ratings[team].elo),
                "scheduledOpponentCount": len(scheduled_opponents[team]),
                "possibleOpponentCount": len(ranked_teams) - 1,
                "unplayedOpponents": [
                    {
                        "team": opponent,
                        "rank": rank_by_team[opponent],
                        "power": power_rating(ratings[opponent].elo),
                    }
                    for opponent in opponents
                ],
                "scheduleTopFour": scheduled.top_four_probability if scheduled else None,
                "roundRobinTopFour": round_robin.top_four_probability if round_robin else None,
                "scheduleFirst": scheduled.first_probability if scheduled else None,
                "roundRobinFirst": round_robin.first_probability if round_robin else None,
            }
        )

    def opponent_fields(opponent: str) -> dict[str, object]:
        return {
            "opponent": opponent,
            "opponentRank": rank_by_team[opponent],
            "opponentPower": power_rating(ratings[opponent].elo),
        }

    def forecast_fields(team: str, opponent: str) -> dict[str, float]:
        win, draw, loss = forecast_match(
            ratings[team].elo,
            ratings[opponent].elo,
            draw_rate=draw_rate,
        )
        return {"win": win, "draw": draw, "loss": loss}

    team_schedules = {}
    for team in ranked_teams:
        entries = []
        for game in sorted(regular_season, key=lambda item: item.played_at):
            if team not in (game.away_team, game.home_team):
                continue
            is_away = game.away_team == team
            opponent = game.home_team if is_away else game.away_team
            entry = {
                "kind": "result" if game.completed else "upcoming",
                "week": game.week,
                "dateLabel": _date_label(game.played_at, include_time=not game.completed),
                "side": "Away" if is_away else "Home",
                **opponent_fields(opponent),
            }
            if game.completed:
                team_score = int(game.away_score if is_away else game.home_score)
                opponent_score = int(game.home_score if is_away else game.away_score)
                entry |= {
                    "teamScore": team_score,
                    "opponentScore": opponent_score,
                    "outcome": (
                        "W" if team_score > opponent_score
                        else "L" if team_score < opponent_score
                        else "D"
                    ),
                    "forfeit": game.is_forfeit,
                }
            else:
                entry |= forecast_fields(team, opponent)
            entries.append(entry)
        entries.extend(
            {
                "kind": "ghost",
                "week": None,
                "dateLabel": "Not on the schedule",
                "side": None,
                **opponent_fields(opponent),
                **forecast_fields(team, opponent),
            }
            for opponent in unplayed_by_team[team]
        )
        team_schedules[team] = entries

    component_ids = {
        component: f"component-{index}"
        for index, component in enumerate(graph.components)
    }
    component_by_team = {
        team: component
        for component in graph.components
        for team in component
    }
    team_node_ids = {
        team: f"team-{index}"
        for index, team in enumerate(sorted(ratings))
    }
    cyclic_teams = {
        team
        for component in graph.cyclic_components
        for team in component
    }
    flow_available = not graph.cyclic_components
    total_flow_credit = sum(dominance_flow.retained_credit.values())
    flow_ranking = (
        sorted(
            ratings,
            key=lambda team: dominance_flow.retained_credit[component_by_team[team]],
            reverse=True,
        )
        if flow_available
        else []
    )
    flow_rank_by_team = {
        team: rank
        for rank, team in enumerate(flow_ranking, start=1)
    }
    graph_nodes = []
    for team in sorted(ratings):
        rating = ratings[team]
        team_power = power_rating(rating.elo)
        component = component_by_team[team]
        retained_credit = (
            dominance_flow.retained_credit[component]
            if flow_available
            else 0.0
        )
        flow_share = retained_credit / total_flow_credit if flow_available else 0.0
        graph_nodes.append(
            {
                "id": team_node_ids[team],
                "label": team,
                "resultLabel": f"{team}\nPower {team_power:.1f}",
                "flowLabel": f"{team}\n{flow_share:.1%} flow",
                "teams": [team],
                "cyclic": team in cyclic_teams,
                "componentId": component_ids[component],
                "color": colors[team],
                "power": team_power,
                "resultWidth": 112 + 8 * team_power,
                "resultHeight": 54 + 2 * team_power,
                "flowCredit": retained_credit,
                "flowShare": flow_share,
                "flowRank": flow_rank_by_team.get(team),
                "flowWidth": 112 + 320 * flow_share,
                "flowHeight": 54 + 90 * flow_share,
            }
        )

    maximum_flow_credit = max(dominance_flow.edge_credit.values(), default=1.0)
    graph_edges = []
    for index, result in enumerate(graph.results):
        winner_score = (
            result.away_score if result.source == result.away_team else result.home_score
        )
        loser_score = (
            result.home_score if result.source == result.away_team else result.away_score
        )
        suffix = " F" if result.is_forfeit else " T" if result.is_tie else ""
        score_margin = abs(result.away_score - result.home_score)
        flow_credit = dominance_flow.edge_credit.get(result.game_id, 0.0)
        graph_edges.append(
            {
                "id": f"result-{index}",
                "source": team_node_ids[result.source],
                "target": team_node_ids[result.target],
                "label": f"W{result.week} {winner_score}-{loser_score}{suffix}",
                "resultLabel": f"W{result.week} {winner_score}-{loser_score}{suffix}",
                "flowLabel": f"{flow_credit:.2f}" if flow_credit else "0",
                "title": (
                    f"Week {result.week}: {result.away_team} {result.away_score}-"
                    f"{result.home_score} {result.home_team}"
                    + (" (administrative forfeit)" if result.is_forfeit else "")
                ),
                "forfeit": result.is_forfeit,
                "tie": result.is_tie,
                "competitive": not result.is_forfeit and not result.is_tie,
                "scoreMargin": score_margin,
                "resultWidth": (
                    1.5
                    if result.is_forfeit or result.is_tie
                    else 1.5 + 2.2 * math.log1p(score_margin)
                ),
                "flowCredit": flow_credit,
                "flowWidth": (
                    1.0 + 7.0 * flow_credit / maximum_flow_credit
                    if flow_credit
                    else 1.0
                ),
            }
        )

    team_rows = []
    for rank, team in enumerate(ranked_teams, start=1):
        rating = ratings[team]
        power_low, power_high = power_rating_interval(rating)
        team_rows.append(
            {
                "rank": rank,
                "name": team,
                "color": colors[team],
                "power": power_rating(rating.elo),
                "powerLow": power_low,
                "powerHigh": power_high,
                "elo": round(rating.elo, 1),
                "games": rating.games,
                "ratedGames": rating.rated_games,
                "wins": rating.wins,
                "losses": rating.losses,
                "ties": rating.ties,
                "goalsFor": rating.goals_for,
                "goalsAgainst": rating.goals_against,
                "goalDifference": rating.goal_difference,
                "expectedMarginVsAverage": round(
                    rating.expected_margin_vs_average,
                    3,
                ),
                "currentPoints": 3 * rating.wins + rating.ties,
            }
        )

    fixtures = []
    for game in upcoming:
        away_win, draw, home_win = forecast_match(
            ratings[game.away_team].elo,
            ratings[game.home_team].elo,
            draw_rate=draw_rate,
        )
        fixtures.append(
            {
                "gameId": game.game_id,
                "week": game.week,
                "playedAt": game.played_at.isoformat(),
                "dateLabel": _date_label(game.played_at, include_time=True),
                "awayTeam": game.away_team,
                "homeTeam": game.home_team,
                "awayWin": away_win,
                "draw": draw,
                "homeWin": home_win,
            }
        )

    results = [
        {
            "gameId": game.game_id,
            "week": game.week,
            "dateLabel": _date_label(game.played_at),
            "awayTeam": game.away_team,
            "awayScore": game.away_score,
            "homeTeam": game.home_team,
            "homeScore": game.home_score,
            "forfeit": game.is_forfeit,
        }
        for game in reversed(completed)
    ]

    matchup_probabilities = {
        first: {
            second: forecast_match(
                ratings[first].elo,
                ratings[second].elo,
                draw_rate=draw_rate,
            )
            for second in ranked_teams
            if second != first
        }
        for first in ranked_teams
    }
    last_result = completed[-1].played_at if completed else generated_at
    return {
        "metadata": {
            "generatedAt": generated_at.strftime("%Y-%m-%d %H:%M %Z"),
            "resultsThrough": _date_label(last_result),
            "completedCount": len(completed),
            "upcomingCount": len(upcoming),
            "goalCount": sum(
                int(game.away_score) + int(game.home_score)
                for game in completed
            ),
            "drawRate": draw_rate,
            "simulations": simulations,
            "sourceUrl": PROFILE_URL,
            "nextWeek": upcoming[0].week if upcoming else None,
        },
        "teams": team_rows,
        "ratingHistory": {
            "labels": ["Start" if week == 0 else f"W{week}" for week in weeks],
            "series": [
                {
                    "team": team,
                    "color": colors[team],
                    "values": [round(snapshots[week][team], 1) for week in weeks],
                }
                for team in ranked_teams
            ],
        },
        "projectionScenarios": {
            "schedule": {
                "label": "Actual schedule",
                "note": (
                    f"Simulates the {len(regular_season)} scheduled regular-season "
                    f"fixtures; {len(pairings)} pairings never meet."
                ),
                "projections": _projection_rows(season_forecast),
                "history": _projection_history(
                    projection_history,
                    fixed_strength_history,
                    series_teams,
                    colors,
                ),
            },
            "roundRobin": {
                "label": "Full round robin",
                "note": (
                    f"Adds {len(pairings)} hypothetical fixtures so every team meets "
                    f"all {len(ranked_teams) - 1} opponents once."
                ),
                "projections": _projection_rows(round_robin_forecast),
                "history": _projection_history(
                    round_robin_history,
                    round_robin_fixed_history,
                    series_teams,
                    colors,
                ),
            },
        },
        "scheduleGaps": schedule_gaps,
        "teamSchedules": team_schedules,
        "graph": {
            "nodes": graph_nodes,
            "edges": graph_edges,
            "components": [
                {
                    "id": component_ids[component],
                    "teams": list(component),
                    "cyclic": len(component) > 1,
                }
                for component in graph.components
            ],
            "flow": {
                "available": flow_available,
                "unavailableReason": (
                    "Dominance flow is not identifiable inside a competitive cycle."
                    if not flow_available
                    else None
                ),
                "transferRate": dominance_flow.transfer_rate,
                "totalCredit": total_flow_credit,
                "ranking": [team_node_ids[team] for team in flow_ranking],
            },
            "layers": [
                [component_ids[component] for component in layer]
                for layer in graph.topological_layers
            ],
            "cycles": [list(component) for component in graph.cyclic_components],
        },
        "fixtures": fixtures,
        "results": results,
        "matchups": matchup_probabilities,
        "sourceStandings": standings,
    }