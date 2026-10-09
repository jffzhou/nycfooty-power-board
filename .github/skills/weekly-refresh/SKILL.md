---
name: weekly-refresh
description: 'Refresh NYC Footy league 5086028 after a new week of results: archive pre-week forecasts, fetch LeagueApps, check forfeits, rerun ratings and both schedule scenarios, rebuild the dashboard, and score upsets against the archived forecast. Use when: another week of results, new week, weekly update, refresh dashboard, update standings.'
---

# Weekly refresh

## Procedure

1. Run `date`. Find the last completed week in `data/schedule.csv`; the week to add is `N`.
2. Archive the pre-game outputs. Use `cp -n` so a rerun never overwrites them:
   ```bash
   cp -n data/forecasts.csv data/archive/forecasts_pre_week<N>.csv
   cp -n data/projected_standings.csv data/archive/projected_pre_week<N>.csv
   cp -n data/ratings.csv data/archive/ratings_pre_week<N>.csv
   ```
3. Inspect the new results before writing any output:
   ```bash
   uv run python -c "from nycfooty import fetch_league_data; games, standings = fetch_league_data(); [print(g.game_id, g.week, g.away_team, g.away_score, g.home_score, g.home_team, repr(g.note), g.is_forfeit) for g in games if g.completed]"
   ```
   - Notes containing "forfeit" are excluded from strength automatically. If a forfeit has no note, add its game ID to `KNOWN_FORFEIT_GAME_IDS`.
   - If a fixture was postponed or rescheduled, check that week labels and `unplayed_pairings` still make sense.
4. Run `uv run python -m unittest`, then `uv run python -m nycfooty`.
5. Score the week against the archived forecast: `uv run python .github/skills/weekly-refresh/scripts/score_week.py <N>`.
6. Report from the regenerated CSVs, not from memory:
   - ratings and 80% ranges: `data/ratings.csv`
   - projections for both scenarios: `data/projected_standings.csv` and `data/projected_standings_round_robin.csv`
   - whether the SCC and flow availability changed: `data/dominance_flow.csv`
7. Check the dashboard over local HTTP (see the port rules in `copilot-instructions.md`). Toggle both schedule scenarios.
8. Update `README.md` only with durable facts. Keep weekly numbers out of the docs; the dashboard and CSVs carry them.
