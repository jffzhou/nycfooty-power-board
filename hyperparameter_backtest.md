# Hyperparameter backtest

Generated 2026-10-09 by `uv run python backtest_hyperparameters.py`. First run and adoption: 2026-10-09.

## Protocol

- Walk-forward: every completed, non-forfeit regular-season game is predicted from results on strictly earlier dates in the same league. The first match date of each league is skipped.
- Tuning set: the 6 leagues sampled for `historical_validation.md`. Test set: the other 6 eligible leagues, first scored on 2026-10-09; later runs re-score them in-sample.
- Grid: 864 configurations over ridge pseudo-games, goal-margin cap, draw prior rate (20 pseudo-games), and a sigma multiplier on the draw-implied margin noise.
- Selection rule, fixed before the test set was fetched: lowest pooled tuning log loss. Only the pre-tuning and selected configurations were scored on the test set.
- "Pre-tuning" means the production parameters before 2026-10-09. The selected configuration is the production default in `nycfooty/constants.py`.

## Tuning set

- Predictions: **131**; neutral baseline log loss **0.9723**
- Pre-tuning (ridge 2, cap none, draw prior 22%, sigma x1): log loss **0.9192**, rank 588 of 864
- Selected (ridge 0.5, cap 4, draw prior 17%, sigma x1.2): log loss **0.8455**
- Selected minus pre-tuning: -0.0738 (95% CI -0.1659 to +0.0012); optimistic because the same games chose it

Best tuning log loss for each knob value, minimizing over the other knobs:

- `ridge`: 0.5: 0.8455; 1: 0.8512; 2: 0.8598; 4: 0.8723; 8: 0.8918; 16: 0.9132
- `margin_cap`: 1: 0.8871; 2: 0.8550; 3: 0.8491; 4: 0.8455; 5: 0.8467; none: 0.8604
- `draw_prior_rate`: 0.12: 0.8467; 0.17: 0.8455; 0.22: 0.8457; 0.27: 0.8460
- `sigma_scale`: 0.8: 0.8492; 1: 0.8467; 1.2: 0.8455; 1.4: 0.8457; 1.7: 0.8460; 2: 0.8488

Top 10 tuning configurations:

| Rank | Ridge | Cap | Draw prior | Sigma x | Log loss |
|---:|---:|---:|---:|---:|---:|
| 1 | 0.5 | 4 | 17% | 1.2 | 0.8455 |
| 2 | 0.5 | 4 | 22% | 1.4 | 0.8457 |
| 3 | 0.5 | 4 | 27% | 1.7 | 0.8460 |
| 4 | 0.5 | 4 | 12% | 1 | 0.8467 |
| 5 | 0.5 | 5 | 12% | 1 | 0.8467 |
| 6 | 0.5 | 5 | 17% | 1.2 | 0.8475 |
| 7 | 0.5 | 5 | 17% | 1.4 | 0.8477 |
| 8 | 0.5 | 5 | 22% | 1.7 | 0.8482 |
| 9 | 0.5 | 5 | 27% | 2 | 0.8488 |
| 10 | 0.5 | 3 | 17% | 1 | 0.8491 |

## Untouched test set

Predictions: **116**

| Model | Log loss | Brier | Accuracy | Avg favorite prob | Confidence gap |
|---|---:|---:|---:|---:|---:|
| Neutral baseline | 0.9630 | | | | |
| Pre-tuning | 0.8098 | 0.4642 | 67.2% | 67.8% | +0.5% |
| Selected | 0.7820 | 0.4513 | 68.1% | 64.7% | -3.4% |

Selected minus pre-tuning log loss: **-0.0278** (95% match-bootstrap CI -0.0785 to +0.0197).

| League | Games | Pre-tuning | Selected | Baseline |
|---|---:|---:|---:|---:|
| [2026 Summer · Downtown Brooklyn · Saturdays](https://nycfooty.leagueapps.com/leagues/4981886/standings) | 18 | 1.0210 | 0.9985 | 1.0408 |
| [2026 Summer · Chinatown · Sundays](https://nycfooty.leagueapps.com/leagues/4981937/standings) | 21 | 0.7712 | 0.7564 | 0.9714 |
| [2026 Summer · Williamsburg · Thursdays](https://nycfooty.leagueapps.com/leagues/4987937/standings) | 18 | 0.9185 | 0.8830 | 0.9796 |
| [2026 Winter · Williamsburg · Saturdays](https://nycfooty.leagueapps.com/leagues/4789879/standings) | 15 | 0.7220 | 0.6637 | 0.8237 |
| [2026 Summer · Upper East Side · Tuesdays](https://nycfooty.leagueapps.com/leagues/4980765/standings) | 20 | 0.5093 | 0.5594 | 0.8951 |
| [2026 Winter · West Village · Sundays](https://nycfooty.leagueapps.com/leagues/4783983/standings) | 24 | 0.9089 | 0.8255 | 1.0286 |

Selected beat pre-tuning in 5 of 6 test leagues.

The test set has now been used. Any further tuning that looks at these results makes them in-sample.
