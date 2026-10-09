import math
import unittest
from dataclasses import replace
from datetime import datetime, timedelta

from nycfooty.backtest import ModelParameters, walk_forward_predictions
from nycfooty.dashboard_data import build_dashboard_data
from nycfooty import (
  analyze_result_graph,
  calculate_dominance_flow,
    calculate_ratings,
    complete_round_robin,
    estimate_draw_rate,
  forecast_final_standings,
    forecast_match,
    forecast_history,
    parse_schedule,
    parse_standings,
    playoff_status,
    power_rating,
    split_first_team_games,
    unplayed_pairings,
)


SCHEDULE_HTML = """
<h4 class="schedule-week"><strong>Week 1</strong> Thu, Sep 3 - Thu, Sep 3 2026</h4>
<li id="game-1" class="schedule-game clr completed">
  <span class="date">Thu, Sep 3</span><span class="time">6:45 PM</span>
  <span class="schedule-tag game-type">Regular Season</span>
  <h3 class="event-title">
    <span class="team-score score winner">
      <a href="/leagues/5086028/teams/10">Alpha FC</a>
      <strong class="tag">(A)</strong><strong class="score">4</strong>
    </span>
    at
    <span class="team-score score">
      <a href="/leagues/5086028/teams/20">Beta FC</a>
      <strong class="tag">(H)</strong><strong class="score">1</strong>
    </span>
  </h3>
  <p class="event-details"><strong>Location:</strong> Test Field</p>
  <span class="game-note-full">Beta FC FORFEIT with notice</span>
  <em class="game-meta"><span class="game-type tag">Played (regular time)</span></em>
</li>
<h4 class="schedule-week"><strong>Week 2</strong> Thu, Sep 10 - Thu, Sep 10 2026</h4>
<li id="game-2" class="schedule-game clr">
  <span class="date">Thu, Sep 10</span><span class="time">7:35 PM</span>
  <span class="schedule-tag game-type">Regular Season</span>
  <h3 class="event-title">
    <span class="team-score score"><a href="/leagues/5086028/teams/20">Beta FC</a><strong class="tag">(A)</strong></span>
    at
    <span class="team-score score"><a href="/leagues/5086028/teams/10">Alpha FC</a><strong class="tag">(H)</strong></span>
  </h3>
</li>
"""

STANDINGS_HTML = """
<table class="basic-table standings">
  <thead><tr><th>Team</th><th><abbr title="Games Played">GP</abbr></th><th>W</th></tr></thead>
  <tbody><tr><td><a href="/teams/10">Alpha FC</a></td><td>1</td><td>1</td></tr></tbody>
</table>
"""


class LeagueParsingTests(unittest.TestCase):
    def test_schedule_with_completed_and_upcoming_games(self) -> None:
        games = parse_schedule(SCHEDULE_HTML)

        self.assertEqual(len(games), 2)
        self.assertEqual(games[0].away_team, "Alpha FC")
        self.assertEqual(games[0].home_score, 1)
        self.assertTrue(games[0].is_forfeit)
        self.assertEqual(games[0].played_at.isoformat(), "2026-09-03T18:45:00")
        self.assertIsNone(games[1].away_score)

    def test_standings_table(self) -> None:
        rows = parse_standings(STANDINGS_HTML)

        self.assertEqual(rows, [{"Team": "Alpha FC", "GP": "1", "W": "1"}])


class RatingTests(unittest.TestCase):
    def test_power_rating_has_league_average_anchor(self) -> None:
        self.assertEqual(power_rating(1500.0), 5.0)
        self.assertEqual(power_rating(1600.0), 6.0)
        self.assertEqual(power_rating(2000.0), 10.0)

    def test_forfeit_counts_in_record_but_not_strength(self) -> None:
        forfeit = parse_schedule(SCHEDULE_HTML)[0]

        ratings, _ = calculate_ratings([forfeit])

        self.assertEqual(ratings["Alpha FC"].elo, 1500.0)
        self.assertEqual(ratings["Beta FC"].elo, 1500.0)
        self.assertEqual(ratings["Alpha FC"].wins, 1)
        self.assertEqual(ratings["Beta FC"].losses, 1)

    def test_close_loss_to_dominant_team_can_improve_relative_rank(self) -> None:
        fixture = parse_schedule(SCHEDULE_HTML)[0]
        blowout = replace(
            fixture,
            away_team="Strong FC",
            away_team_id="1",
            home_team="Weak FC",
            home_team_id="2",
            away_score=8,
            home_score=0,
            note="",
        )
        close_loss = replace(
            fixture,
            game_id="2",
            played_at=fixture.played_at + timedelta(days=7),
            away_team="Close FC",
            away_team_id="3",
            home_team="Strong FC",
            home_team_id="1",
            away_score=2,
            home_score=3,
            note="",
        )

        ratings, _ = calculate_ratings([blowout, close_loss])

        self.assertGreater(ratings["Close FC"].elo, 1500.0)
        self.assertGreater(ratings["Close FC"].elo, ratings["Weak FC"].elo)

    def test_margin_changes_rating_strength(self) -> None:
        games = parse_schedule(SCHEDULE_HTML)
        close_game = games[0].__class__(
            **{**games[0].__dict__, "away_score": 2, "home_score": 1, "note": ""}
        )
        wide_game = games[0].__class__(
            **{**games[0].__dict__, "away_score": 6, "home_score": 1, "note": ""}
        )

        close_ratings, _ = calculate_ratings([close_game])
        wide_ratings, _ = calculate_ratings([wide_game])

        self.assertGreater(wide_ratings["Alpha FC"].elo, close_ratings["Alpha FC"].elo)

    def test_rating_uncertainty_shrinks_with_more_games(self) -> None:
        fixture = replace(parse_schedule(SCHEDULE_HTML)[0], note="")
        repeated_games = [
            replace(
                fixture,
                game_id=str(index),
                played_at=fixture.played_at + timedelta(days=7 * index),
            )
            for index in range(3)
        ]

        one_game_ratings, _ = calculate_ratings(repeated_games[:1])
        three_game_ratings, _ = calculate_ratings(repeated_games)

        self.assertGreater(
            one_game_ratings["Alpha FC"].strength_standard_error,
            three_game_ratings["Alpha FC"].strength_standard_error,
        )

    def test_forecast_is_complete_and_favors_stronger_team(self) -> None:
        forecast = forecast_match(1580.0, 1450.0, draw_rate=0.2)

        self.assertAlmostEqual(sum(forecast), 1.0)
        self.assertGreater(forecast[0], forecast[2])
        self.assertGreater(forecast[1], 0.0)


class ResultGraphTests(unittest.TestCase):
    def test_cycle_is_condensed_before_topological_sort(self) -> None:
        fixture = replace(parse_schedule(SCHEDULE_HTML)[0], note="")
        games = [
            replace(fixture, game_id="1", away_team="A", home_team="B", away_score=2, home_score=1),
            replace(fixture, game_id="2", away_team="B", home_team="C", away_score=2, home_score=1),
            replace(fixture, game_id="3", away_team="C", home_team="A", away_score=2, home_score=1),
            replace(fixture, game_id="4", away_team="C", home_team="D", away_score=2, home_score=1),
        ]

        analysis = analyze_result_graph(games)

        self.assertEqual(analysis.cyclic_components, (("A", "B", "C"),))
        self.assertEqual(analysis.topological_layers, ((('A', 'B', 'C'),), (("D",),)))

    def test_cycle_keeps_individual_dashboard_nodes(self) -> None:
        fixture = replace(parse_schedule(SCHEDULE_HTML)[0], note="")
        games = [
            replace(fixture, game_id="1", away_team="A", home_team="B", away_score=2, home_score=1),
            replace(fixture, game_id="2", away_team="B", home_team="C", away_score=2, home_score=1),
            replace(fixture, game_id="3", away_team="C", home_team="A", away_score=2, home_score=1),
        ]

        dashboard = build_dashboard_data(
            games,
            [],
            [],
            generated_at=datetime(2026, 1, 1),
            simulations=1,
        )

        self.assertEqual(len(dashboard["graph"]["nodes"]), 3)
        self.assertEqual(len(dashboard["graph"]["components"]), 1)

    def test_forfeit_is_shown_but_excluded_from_ordering(self) -> None:
        forfeit = parse_schedule(SCHEDULE_HTML)[0]

        analysis = analyze_result_graph([forfeit])

        self.assertEqual(len(analysis.results), 1)
        self.assertTrue(analysis.results[0].is_forfeit)
        self.assertEqual(analysis.component_edges, ())

    def test_dominance_flow_is_conserved_and_rewards_transitive_wins(self) -> None:
        fixture = replace(parse_schedule(SCHEDULE_HTML)[0], note="")
        games = [
            replace(fixture, game_id="1", away_team="A", home_team="B", away_score=2, home_score=1),
            replace(fixture, game_id="2", away_team="B", home_team="C", away_score=2, home_score=1),
        ]
        flow = calculate_dominance_flow(analyze_result_graph(games))

        self.assertAlmostEqual(sum(flow.retained_credit.values()), 3.0)
        self.assertGreater(flow.retained_credit[("A",)], flow.retained_credit[("B",)])
        self.assertGreater(flow.retained_credit[("B",)], flow.retained_credit[("C",)])

    def test_dominance_flow_weights_larger_margins_more(self) -> None:
        fixture = replace(parse_schedule(SCHEDULE_HTML)[0], note="")
        games = [
            replace(fixture, game_id="wide", away_team="A", home_team="C", away_score=5, home_score=1),
            replace(fixture, game_id="close", away_team="B", home_team="C", away_score=2, home_score=1),
        ]
        flow = calculate_dominance_flow(analyze_result_graph(games))

        self.assertGreater(flow.edge_credit["wide"], flow.edge_credit["close"])


class DashboardDataTests(unittest.TestCase):
    def test_played_and_upcoming_opponents(self) -> None:
        """Played and remaining strength of schedule each count only their own opponents."""
        fixture = replace(parse_schedule(SCHEDULE_HTML)[0], note="")
        games = [
            replace(fixture, game_id="1", away_team="A", home_team="B", away_score=4, home_score=0),
            replace(fixture, game_id="2", away_team="C", home_team="A", away_score=1, home_score=1),
            replace(
                fixture,
                game_id="3",
                week=2,
                played_at=fixture.played_at + timedelta(days=7),
                away_team="A",
                home_team="C",
                away_score=None,
                home_score=None,
            ),
        ]

        teams = {
            row["name"]: row
            for row in build_dashboard_data(
                games,
                [],
                [],
                generated_at=datetime(2026, 1, 1),
                simulations=1,
            )["teams"]
        }

        self.assertAlmostEqual(teams["A"]["remainingOpponentPower"], 5.0 + teams["C"]["expectedMarginVsAverage"], places=3)
        self.assertAlmostEqual(
            teams["A"]["playedOpponentPower"],
            5.0 + (teams["B"]["expectedMarginVsAverage"] + teams["C"]["expectedMarginVsAverage"]) / 2,
            places=2,
        )
        self.assertIsNone(teams["B"]["remainingOpponentPower"])

    def test_upcoming_fixture_between_unequal_teams(self) -> None:
        """The browser simulator's margin and noise must reproduce the published match odds."""
        fixture = replace(parse_schedule(SCHEDULE_HTML)[0], note="")
        games = [
            replace(fixture, game_id="1", away_team="A", home_team="B", away_score=3, home_score=1),
            replace(fixture, game_id="2", away_team="C", home_team="A", away_score=1, home_score=1),
            replace(
                fixture,
                game_id="3",
                week=2,
                played_at=fixture.played_at + timedelta(days=7),
                away_team="B",
                home_team="C",
                away_score=None,
                home_score=None,
            ),
        ]

        simulator = build_dashboard_data(
            games,
            [],
            [],
            generated_at=datetime(2026, 1, 1),
            simulations=1,
        )["simulator"]

        (upcoming,) = simulator["fixtures"]
        standardized = (0.5 - upcoming["expectedMargin"]) / (simulator["sigma"] * math.sqrt(2.0))
        self.assertAlmostEqual(1.0 - 0.5 * (1.0 + math.erf(standardized)), upcoming["awayWin"])

    def test_team_schedules_with_home_loss_and_unscheduled_pairing(self) -> None:
        """Each team's schedule is told from its own side and ends with its skipped opponent."""
        fixture = replace(parse_schedule(SCHEDULE_HTML)[0], note="")
        games = [
            replace(fixture, game_id="1", away_team="A", home_team="B", away_score=2, home_score=1),
            replace(fixture, game_id="2", away_team="C", home_team="A", away_score=1, home_score=1),
            replace(
                fixture,
                game_id="3",
                week=2,
                played_at=fixture.played_at + timedelta(days=7),
                away_team="A",
                home_team="C",
                away_score=None,
                home_score=None,
            ),
        ]

        schedules = build_dashboard_data(
            games,
            [],
            [],
            generated_at=datetime(2026, 1, 1),
            simulations=1,
        )["teamSchedules"]

        played, skipped = schedules["B"]
        self.assertEqual(
            (played["kind"], played["opponent"], played["teamScore"], played["opponentScore"], played["outcome"]),
            ("result", "A", 1, 2, "L"),
        )
        self.assertEqual((skipped["kind"], skipped["opponent"]), ("ghost", "C"))
        self.assertGreater(skipped["loss"], skipped["win"])
        self.assertEqual([entry["kind"] for entry in schedules["A"]], ["result", "result", "upcoming"])

    def test_recap_week_with_even_draw_and_underdog_win(self) -> None:
        """A draw between even teams is not an upset, even though draws are individually unlikely."""
        fixture = replace(parse_schedule(SCHEDULE_HTML)[0], note="")
        next_week = fixture.played_at + timedelta(days=7)
        games = [
            replace(fixture, game_id="1", away_team="A", home_team="B", away_score=1, home_score=0),
            replace(fixture, game_id="2", away_team="C", home_team="D", away_score=1, home_score=1),
            replace(fixture, game_id="upset", week=2, played_at=next_week, away_team="B", home_team="A", away_score=1, home_score=0),
            replace(fixture, game_id="draw", week=2, played_at=next_week, away_team="D", home_team="C", away_score=2, home_score=2),
        ]

        recap = build_dashboard_data(
            games,
            [],
            [],
            generated_at=datetime(2026, 1, 1),
            simulations=1,
        )["recap"]

        rows = {row["gameId"]: row for row in recap["games"]}
        self.assertLess(rows["draw"]["actualProbability"], rows["upset"]["actualProbability"])
        self.assertEqual((rows["draw"]["verdict"], rows["upset"]["verdict"]), ("draw", "upset"))
        self.assertEqual(recap["biggestUpset"], "upset")


class SeasonForecastTests(unittest.TestCase):
    def test_seeded_forecast_is_reproducible(self) -> None:
        games = parse_schedule(SCHEDULE_HTML)

        first = forecast_final_standings(games, simulations=500, seed=7)
        second = forecast_final_standings(games, simulations=500, seed=7)

        self.assertEqual(first, second)
        self.assertAlmostEqual(sum(team.first_probability for team in first), 1.0)

    def test_later_week_score_changes(self) -> None:
        """A weekly snapshot must only use results known by that week."""
        fixture = replace(parse_schedule(SCHEDULE_HTML)[0], note="")
        games = [
            replace(fixture, game_id="1", week=1, away_team="A", home_team="B", away_score=2, home_score=1),
            replace(fixture, game_id="2", week=2, away_team="C", home_team="D", away_score=1, home_score=0),
            replace(fixture, game_id="3", week=3, away_team="A", home_team="C", away_score=None, home_score=None),
        ]
        blowout = [*games[:1], replace(games[1], away_score=0, home_score=6), games[2]]

        original = forecast_history(games, simulations=500, seed=7)
        changed = forecast_history(blowout, simulations=500, seed=7)

        self.assertEqual([week for week, _ in original], [0, 1, 2])
        self.assertEqual(original[:2], changed[:2])
        self.assertNotEqual(original[2], changed[2])
        self.assertEqual(original[2][1], forecast_final_standings(games, simulations=500, seed=7))

    def test_week_zero_with_fixed_strengths(self) -> None:
        """Fixed-strength history uses final strengths but only points banked by each week."""
        fixture = replace(parse_schedule(SCHEDULE_HTML)[0], note="")
        games = [
            replace(fixture, game_id="1", week=1, away_team="A", home_team="B", away_score=5, home_score=0),
            replace(fixture, game_id="2", week=2, away_team="B", home_team="A", away_score=None, home_score=None),
        ]

        _, snapshot = forecast_history(games, simulations=500, seed=7, fixed_strengths=True)[0]
        by_team = {item.team: item for item in snapshot}

        self.assertEqual([item.current_points for item in snapshot], [0, 0])
        self.assertGreater(by_team["A"].first_probability, 0.7)

    def test_single_remaining_fixture_between_unbanked_teams(self) -> None:
        """Season simulation and match forecast must use the same margin noise."""
        fixture = replace(parse_schedule(SCHEDULE_HTML)[0], note="")
        strength_games = [replace(fixture, away_team="A", home_team="B", away_score=2, home_score=0)]
        remaining = [replace(strength_games[0], game_id="2", away_score=None, home_score=None)]
        ratings, _ = calculate_ratings(strength_games)
        win, draw, _ = forecast_match(
            ratings["A"].elo,
            ratings["B"].elo,
            draw_rate=estimate_draw_rate(strength_games),
        )

        forecast = forecast_final_standings(
            remaining,
            simulations=40_000,
            seed=7,
            strength_games=strength_games,
        )

        by_team = {item.team: item for item in forecast}
        self.assertAlmostEqual(by_team["A"].first_probability, win + draw / 2, delta=0.01)

    def test_completed_four_team_season(self) -> None:
        """Seeds 1 and 4 meet in one semifinal and seeds 2 and 3 in the other."""
        fixture = replace(parse_schedule(SCHEDULE_HTML)[0], note="")
        games = [
            replace(fixture, game_id="1", away_team="Q", home_team="B", away_score=3, home_score=0),
            replace(fixture, game_id="2", away_team="Q", home_team="Z", away_score=2, home_score=0),
            replace(fixture, game_id="3", away_team="M", home_team="B", away_score=1, home_score=0),
            replace(fixture, game_id="4", away_team="Z", home_team="B", away_score=1, home_score=1),
        ]

        forecast = {item.team: item for item in forecast_final_standings(games, simulations=1, seed=7)}

        self.assertAlmostEqual(forecast["Q"].final_probability + forecast["B"].final_probability, 1.0)
        self.assertAlmostEqual(sum(item.champion_probability for item in forecast.values()), 1.0)
        self.assertEqual(max(forecast.values(), key=lambda item: item.champion_probability).team, "Q")

    def test_two_chasers_meeting_in_last_game(self) -> None:
        """Two chasers who play each other cannot both catch the leader."""
        status = playoff_status(self._chase_games(), spots=2)

        self.assertEqual(
            (status["T"]["clinched"], status["X"]["clinched"], status["X"]["eliminated"], status["Z"]["eliminated"]),
            (True, False, False, True),
        )
        self.assertFalse(playoff_status(self._chase_games(), spots=1)["T"]["clinched"], "a chaser can tie T")

    def test_too_many_remaining_games_for_exact_check(self) -> None:
        """The conservative check never claims a clinch a tie could undo, and still eliminates."""
        status = playoff_status(self._chase_games(), spots=1, exact_limit=0)

        self.assertEqual((status["T"]["clinched"], status["Z"]["eliminated"]), (False, True))

    @staticmethod
    def _chase_games() -> list:
        fixture = replace(parse_schedule(SCHEDULE_HTML)[0], note="")
        return [
            replace(fixture, game_id="1", away_team="T", home_team="Z", away_score=1, home_score=0),
            replace(fixture, game_id="2", away_team="T", home_team="Y", away_score=1, home_score=0),
            replace(fixture, game_id="3", away_team="Y", home_team="Z", away_score=1, home_score=0),
            replace(fixture, game_id="4", away_team="X", home_team="Z", away_score=1, home_score=0),
            replace(
                fixture,
                game_id="5",
                week=2,
                played_at=fixture.played_at + timedelta(days=7),
                away_team="X",
                home_team="Y",
                away_score=None,
                home_score=None,
            ),
        ]

    def test_schedule_with_unscheduled_pairings(self) -> None:
        """Played and still-scheduled pairings in either orientation are not unplayed."""
        fixture = replace(parse_schedule(SCHEDULE_HTML)[0], note="")
        games = [
            replace(fixture, game_id="1", away_team="A", home_team="B", away_score=2, home_score=1),
            replace(fixture, game_id="2", away_team="C", home_team="D", away_score=0, home_score=0),
            replace(fixture, game_id="3", away_team="D", home_team="A", away_score=None, home_score=None),
            replace(fixture, game_id="4", away_team="B", home_team="C", away_score=None, home_score=None),
        ]

        self.assertEqual(unplayed_pairings(games), [("A", "C"), ("B", "D")])

    def test_round_robin_scenario_with_unscheduled_pairings(self) -> None:
        """The round-robin scenario simulates every team against every opponent once."""
        fixture = replace(parse_schedule(SCHEDULE_HTML)[0], note="")
        games = [
            replace(fixture, game_id="1", away_team="A", home_team="B", away_score=2, home_score=1),
            replace(fixture, game_id="2", away_team="C", home_team="D", away_score=0, home_score=0),
            replace(fixture, game_id="3", away_team="D", home_team="A", away_score=None, home_score=None),
            replace(fixture, game_id="4", away_team="B", home_team="C", away_score=None, home_score=None),
        ]

        forecast = forecast_final_standings(complete_round_robin(games), simulations=200, seed=7)

        for item in forecast:
            self.assertAlmostEqual(
                item.expected_wins + item.expected_losses + item.expected_ties,
                3.0,
            )


class HistoricalValidationTests(unittest.TestCase):
    def test_same_night_earlier_kickoff(self) -> None:
        """A walk-forward prediction may only use results from earlier dates, never the same night."""
        fixture = replace(parse_schedule(SCHEDULE_HTML)[0], note="")
        later = fixture.played_at + timedelta(days=7)
        games = [
            replace(fixture, game_id="1", away_team="A", home_team="B", away_score=2, home_score=1),
            replace(
                fixture,
                game_id="2",
                played_at=later + timedelta(minutes=50),
                away_team="A",
                home_team="C",
                away_score=1,
                home_score=0,
            ),
            replace(fixture, game_id="3", played_at=later, away_team="B", home_team="C", away_score=3, home_score=0),
        ]
        blowout = [*games[:2], replace(games[2], away_score=0, home_score=9)]

        original = {item.game_id: item for item in walk_forward_predictions(games)}
        changed = {item.game_id: item for item in walk_forward_predictions(blowout)}

        self.assertEqual(original["2"], changed["2"])

    def test_default_parameters_with_forfeits(self) -> None:
        """The backtest's default configuration is the production model."""
        fixture = replace(parse_schedule(SCHEDULE_HTML)[0], note="")
        later = fixture.played_at + timedelta(days=7)
        games = [
            replace(fixture, game_id="1", away_team="A", home_team="B", away_score=4, home_score=1),
            replace(fixture, game_id="2", away_team="C", home_team="D", away_score=1, home_score=1),
            replace(fixture, game_id="3", away_team="D", home_team="A", away_score=3, home_score=0, note="A FORFEIT"),
            replace(fixture, game_id="4", played_at=later, away_team="B", home_team="C", away_score=2, home_score=2),
            replace(fixture, game_id="5", played_at=later, away_team="A", home_team="D", away_score=0, home_score=3, note="A FORFEIT"),
        ]
        ratings, _ = calculate_ratings(games[:3])

        (prediction,) = walk_forward_predictions(games)

        self.assertEqual(
            prediction.probabilities,
            forecast_match(
                ratings["B"].elo,
                ratings["C"].elo,
                draw_rate=estimate_draw_rate(games[:3]),
            ),
        )

    def test_margin_cap_with_home_blowout(self) -> None:
        """A capped 0-9 home win fits exactly like an uncapped 0-3 home win."""
        fixture = replace(parse_schedule(SCHEDULE_HTML)[0], note="")
        later = fixture.played_at + timedelta(days=7)
        blowout = [
            replace(fixture, game_id="1", away_team="A", home_team="B", away_score=0, home_score=9),
            replace(fixture, game_id="2", away_team="B", home_team="C", away_score=2, home_score=1),
            replace(fixture, game_id="3", played_at=later, away_team="A", home_team="C", away_score=1, home_score=1),
        ]
        three_goal = [replace(blowout[0], home_score=3), *blowout[1:]]

        capped = walk_forward_predictions(blowout, ModelParameters(margin_cap=3))
        uncapped = walk_forward_predictions(three_goal, ModelParameters(margin_cap=None))

        self.assertEqual(capped, uncapped)

    def test_first_three_games_cutoff_never_uses_a_fourth_game(self) -> None:
        fixture = replace(parse_schedule(SCHEDULE_HTML)[0], note="")
        matchups = [
            ("A", "B"),
            ("C", "D"),
            ("A", "C"),
            ("B", "D"),
            ("A", "D"),
            ("B", "C"),
            ("A", "B"),
            ("C", "D"),
        ]
        games = [
            replace(
                fixture,
                game_id=str(index),
                played_at=fixture.played_at + timedelta(days=index),
                away_team=away,
                home_team=home,
            )
            for index, (away, home) in enumerate(matchups)
        ]

        training, holdout = split_first_team_games(games)

        appearances = {
            team: sum(team in (game.away_team, game.home_team) for game in training)
            for team in ("A", "B", "C", "D")
        }
        self.assertEqual(appearances, {"A": 3, "B": 3, "C": 3, "D": 3})
        self.assertEqual(len(holdout), 2)


if __name__ == "__main__":
    unittest.main()