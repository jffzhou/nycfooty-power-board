# NYC Footy Two Bridges ratings

This project fetches the public LeagueApps schedule and standings for league
`5086028`, calculates opponent-adjusted margin and 1-10 power ratings, estimates each
remaining fixture's win/draw/win probabilities, and builds a standalone HTML
dashboard.

## Install and setup

Requirements:

- `git`
- [uv](https://docs.astral.sh/uv/getting-started/installation/), which also
  installs Python 3.12 from `.python-version`. There are no third-party Python
  packages.
- Node.js 22.12 or newer. `.node-version` pins 24.21.0 for nvm, fnm, or Volta.

```bash
git clone https://github.com/jffzhou/nycfooty-power-board.git
cd nycfooty-power-board
uv sync                       # create .venv with Python 3.12
npm ci                        # install the pinned frontend packages
uv run python -m unittest -v  # optional: run the tests
uv run python -m nycfooty     # fetch live data, simulate, build dashboard.html
```

Then open `dashboard.html` in a browser. If the browser blocks local files,
serve the folder with `uv run python -m http.server 8000` and open
`http://127.0.0.1:8000/dashboard.html`.

The refresh only reads public LeagueApps pages, needs no account or API key,
and takes about 30 seconds. `web/generated-data.json` is not committed, so run
the refresh once before using `npm run build` or `npm run dev` directly. The
build uses a project-local Node in `.node/bin` when present, otherwise `npm`
from `PATH`.

## Hosting

GitHub Pages serves the repository root. Enable it under **Settings → Pages →
Deploy from a branch → `main` / `(root)`**. The root `index.html` forwards to
`dashboard.html`, keeping tab links such as `#teams`, so the short link
`https://jffzhou.github.io/nycfooty-power-board/` opens the dashboard.
`.nojekyll` makes Pages serve the files as-is. Commit and push the regenerated
`dashboard.html` after each refresh to update the site.

## Refresh

```bash
uv run python -m nycfooty
```

The refresh command fetches the data, runs 25,000 seeded season simulations,
exports CSV/JSON, and invokes Vite to rebuild the standalone dashboard.

Open `dashboard.html` directly in a browser. Each refresh writes:

- `dashboard.html`: tabbed dashboard. Rankings (power table, rating paths),
  Teams (each team's results with margin vs expectation, upcoming forecasts,
  schedule strength so far and remaining, consistency, and a translucent "ghost"
  forecast for the opponent it never plays, with opponent power, then
  league-wide strength of schedule played vs still to play and the pairings
  that never meet with a hypothetical forecast and their top-four odds impact),
  Standings race (projected standings and weekly playoff odds with an
  actual-schedule / full-round-robin toggle), Simulator (enter or pick
  results for upcoming games and see first-place and top-four odds move;
  strengths stay at the latest real ratings and are never refit on entered
  results), Matches (weekly recap scored against point-in-time forecasts,
  fixtures, matchup lab,
  results), Result graph, and Method. Click any team name to open its schedule;
  `#teams`-style hashes deep-link to a tab
- `data/schedule.csv`: all scheduled and completed matches
- `data/standings.csv`: the source standings table
- `data/ratings.csv`: current model ratings and result totals
- `data/forecasts.csv`: all remaining fixture probabilities
- `data/projected_standings.csv`: 25,000-simulation final-table projection,
  including playoff final and championship odds
- `data/projection_history.csv`: weekly first-place and top-four odds, both
  point-in-time (`first_pct`, `top_four_pct`) and hindsight (`*_hindsight`)
- `data/projected_standings_round_robin.csv` and
  `data/projection_history_round_robin.csv`: the same outputs if every team
  played every opponent once
- `data/dominance_flow.csv`: score-weighted transitive résumé credit

Before each weekly refresh, copy the previous `forecasts.csv`,
`projected_standings.csv`, and `ratings.csv` to
`data/archive/*_pre_week<N>.csv` so the new results can be scored against the
pre-game forecast.

## Model

The model jointly fits each non-forfeit score margin against both teams. Each
margin is capped at 4 goals, and ridge regularization adds half an
average-performance pseudo-game per team. Game `13852824`, the September 3
forfeit by The Other Secret Team, remains
in official W-L and goal totals but receives zero strength weight. A 5.0 power
rating is league average, and one rating point represents one expected goal
versus an average team. The secondary Elo-like scale uses 100 points per goal.
The displayed approximate 80% intervals use the Gaussian-ridge covariance with
a two-goal observation-noise assumption. They are widest for teams with the
least evidence.

Three-way forecasts use the fitted score-margin difference and a draw rate
regularized toward a 17% prior over 20 pseudo-games. The margin noise is the
draw-implied value scaled by 1.2, and the season simulations use the same
noise. There is no home advantage: every game is played at the same field.
Early-season estimates are
directional and should not be treated as betting odds.
Current fixture and standings forecasts condition on the best-fit strengths;
they do not yet integrate rating-parameter uncertainty.

Projected standings run 25,000 reproducible simulations with current strengths
held fixed. Official points and goal difference are carried forward, then each
remaining result and margin is sampled. Teams are ordered by points, goal
difference, and fewer goals against within each simulation; the displayed table
is ordered by average finishing position.

The top four make the playoffs: 1st plays 4th and 2nd plays 3rd, then the
final, at the shared venue. A drawn knockout game is settled 50/50. For each
simulated final table the bracket odds are computed exactly from the four
seeds, so they add no random draws and leave first-place and top-four odds
unchanged. Clinched and eliminated flags count points only, with ties against
the team because goal-difference tiebreakers are unknown. They are exact over
every win/draw/loss outcome once at most 10 games remain, and conservative
before that.

The Teams tab adds hindsight diagnostics from today's fit: average opponent
power played and remaining, each result's capped margin minus the margin
today's ratings expect, and consistency, the root-mean-square of those gaps.
The weekly recap replays point-in-time pre-game odds with today's settings and
scores them against a coin flip. Each result is labelled favorite won, draw, or
upset (underdog won). A draw is half a result for each side, so a draw between
even teams is unremarkable even though any specific draw is unlikely. The
biggest upset is the underdog win with the largest favorite shortfall: the
favorite's win chance plus half its draw chance, minus its actual result.

The regular season is not a full round robin: 10 teams play 8 games each, so
every team skips exactly one of its nine possible opponents (five unscheduled
pairings). Ratings are opponent-adjusted, so a skipped opponent does not bias
strength. The default projection simulates only the fixtures actually
scheduled, so each team's remaining slate is already priced in. The
round-robin scenario (`complete_round_robin`) appends one hypothetical
fixture per unscheduled pairing and reruns the same seeded
simulations; the dashboard toggle swaps the projected table and the four
weekly-odds charts between the two scenarios. Round-robin teams play nine
games, so compare odds, not raw points, across scenarios.

The result graph points from each winner to each loser. It condenses strongly
connected components before topologically sorting the resulting DAG. The
administrative forfeit is drawn separately and excluded from this ordering.
Result-edge width uses `log(1 + goal margin)`, so larger wins are stronger
without allowing one blowout to dominate visually.

The optional dominance-flow mode is a résumé metric, not an ability estimate.
Each SCC starts with one credit per team, retains 40%, and transfers 60% toward
the teams that beat it. When several results feed the same loser, transfer is
split by `log(1 + goal margin)`. The total credit remains equal to the number of
teams. Team-level flow is not identifiable inside a strongly connected cycle, so
the dashboard disables flow while most teams share one cycle.

## Model history

### 2026-10-09: tuned ridge, margin cap, draw prior, and noise scale

| Parameter | Before | After |
|---|---:|---:|
| Ridge pseudo-games (`MARGIN_RIDGE`) | 2 | 0.5 |
| Goal-margin cap (`MARGIN_CAP`) | none | 4 |
| Draw prior rate (`DRAW_PRIOR_RATE`) | 22% | 17% |
| Forecast noise multiplier (`FORECAST_SIGMA_SCALE`) | 1.0 | 1.2 |

Findings (log loss, lower is better; full tables in
`hyperparameter_backtest.md`):

- Walk-forward search over 864 settings on the six historical-validation
  leagues (131 games): 0.919 before, 0.846 after. This is optimistic because
  the same games chose the settings.
- The six never-before-scored eligible leagues (116 games): 0.810 before,
  0.782 after, a difference of -0.028 (95% CI -0.079 to +0.020). The new
  settings were better in 5 of 6 leagues. This is directional, not
  statistically significant.
- Capping margins at 4-5 goals scored best; uncapped was worse, and
  win/draw/loss only was worst. Less shrinkage scored better down to 0.5, the
  smallest value tried. The draw prior and noise multiplier are
  interchangeable: only their combined confidence matters.
- This season (league `5086028`, Weeks 2-6, 20 games): point-in-time
  forecasts with the old settings scored 0.978 against 0.921 for a coin flip
  (difference CI includes zero). Three upsets account for the whole gap. The
  new settings score 0.938. Their margin cap was partly motivated by this
  season's 9-0, so that comparison is not clean.
- Leave-one-out hindsight (each game predicted from every other result this
  season) also loses to a coin flip: 1.018 old and 0.933 new, against 0.890.
  In the 12 archived leagues the same measure beats the coin flip (0.816 old
  and 0.795 new, against 0.955). Through Week 6, this season's results do not
  yet form a consistent order, so no strength model forecasts it well.
- The walk-forward replay reproduced the forecasts archived before Weeks 5
  and 6 exactly, confirming that the backtest has no lookahead.
- All 12 eligible archived leagues have now been scored. Further tuning needs
  newly completed leagues as a holdout. Pre-switch outputs are kept in
  `data/archive/*_pre_tuning_2026-10-09.csv`.

## Known limitations

- The 2026-09-18 three-game validation found about +10 percentage points of
  favorite overconfidence in the pre-tuning model. Week-to-week walk-forward
  calibration was close for both settings (see Model history).
- Season simulations hold strengths fixed; they do not model form, roster
  changes, or forfeits.
- Rating intervals are displayed but not propagated into forecasts.
- Even with a 4-goal cap, one result can move a team with few rated games a
  long way.
- Rating intervals assume 2-goal margin noise, below the forecast noise, so
  the displayed 80% ranges are likely too narrow.
- Simulated goal differences use the scaled forecast noise, so goal-difference
  tiebreaks in simulations are noisier than real ones.
- One strength dimension; attack and defense are not separated.
- Only explicit forfeits are excluded from strength. Inspect game notes when a
  new forfeit appears.

## Structure

- `nycfooty/parsing.py` and `nycfooty/client.py`: LeagueApps ingestion
- `nycfooty/ratings.py`: opponent-adjusted margin ratings
- `nycfooty/graph.py`: SCC condensation and topological layers
- `nycfooty/forecast.py`: match and season simulations, unscheduled pairings,
  and round-robin completion
- `nycfooty/flow.py`: dominance flow
- `nycfooty/validation.py`: historical validation
- `nycfooty/dashboard_data.py`: browser data contract
- `nycfooty/export.py`: CSV export and Vite build orchestration
- `web/src/graph.js`: Cytoscape.js result graph
- `web/src/team-line-chart.js`: shared Chart.js line chart with team focus
- `web/src/rating-chart.js` and `web/src/odds-chart.js`: rating history and
  weekly playoff odds
- `web/src/render.js`: tables, team view, and the schedule-scenario toggle
- `web/src/tabs.js`: tab navigation and hash deep links
- `web/src/simulator.js`: in-browser season simulation for the Simulator tab;
  mirrors `forecast_final_standings`
- `web/styles.css`: dashboard styling
- `.github/copilot-instructions.md`: agent guidance and project invariants

## Historical validation

Run the model against the fixed-seed sample of six completed 7v7 P4/P5
leagues using at most each team's first three games:

```bash
uv run python validate_history.py
```

This writes `historical_validation.md`,
`data/historical_validation_by_league.csv`, and
`data/historical_validation_matches.csv`. The validation does not alter or fit
any model parameter. The committed report is the 2026-09-18 run of the
pre-tuning model. Since the 2026-10-09 parameters were tuned on these same six
leagues, a rerun now measures in-sample fit.

## Hyperparameter backtest

```bash
uv run python backtest_hyperparameters.py
```

Walk-forward backtest: each completed, non-forfeit regular-season game is
predicted from results on strictly earlier dates. It searches 864
combinations of ridge pseudo-games, goal-margin cap, draw prior, and a
multiplier on the draw-implied margin noise. Tuning uses the six
historical-validation leagues; the lowest pooled log loss is then scored once
against the current model on the other six eligible leagues. Writes
`hyperparameter_backtest.md`, `data/backtest_grid.csv`, and
`data/backtest_test_by_league.csv`. Production parameters are not changed by
this script.

Source: <https://nycfooty.leagueapps.com/leagues/5086028/standings>