# Model comparison

Generated 2026-10-16 by `uv run python backtest_models.py`. First run: 2026-10-16.

## Protocol

- Walk-forward: every completed, non-forfeit regular-season game is predicted from results on strictly earlier dates in the same league.
- Each challenger family is tuned on the 6 tuning leagues only (lowest pooled log loss), then scored once on the 6 test leagues and on this season.
- The goal-margin model is the production configuration chosen on the same tuning leagues on 2026-10-09. Its test-league score was seen then, so the test set is not fully fresh for it.
- Grids: results + margin 672 configurations (result weight 0 is the plain margin model); Dixon-Coles 420 configurations.
- The first run (2026-10-16) selected edge values (results + margin ridge 0.25; Dixon-Coles rho 0 and half-life 28 days) and scored them on the test leagues. The grids were widened twice past the edges and reselected on the tuning leagues only, so the test leagues have been seen before this selection.
- This season is small and still in progress; treat it as a sanity check, not evidence.

## Results

| Model | Selected parameters | Tuning log loss | Test log loss | Test minus margin (95% CI) | Test accuracy | This season |
|---|---|---:|---:|---|---:|---:|
| Goal margin | ridge 0.5, cap 4, draw prior 17%, sigma x1.2, result weight 0 | 0.8455 | 0.7820 |  | 68.1% | 0.9744 |
| Results + margin | ridge 0.02, cap 2, draw prior 17%, sigma x1.4, result weight 0.75 | 0.8340 | 0.7813 | -0.0007 (-0.0350 to +0.0336) | 65.5% | 1.0280 |
| Dixon-Coles goals | ridge 2, rho 0.15, half-life 28 days, goal cap 4 | 0.8561 | 0.8304 | +0.0485 (-0.0097 to +0.1074) | 68.1% | 1.0203 |
| Coin flip (draw rate only) |  | 0.9723 | 0.9630 |  |  | 0.9424 |

Matches: tuning 131, test 116, this season 24. Lower log loss is better.

Best tuning log loss for each Results + margin knob value:

- `ridge`: 0.02: 0.8340; 0.05: 0.8341; 0.1: 0.8349; 0.25: 0.8374; 0.5: 0.8418; 1: 0.8494; 2: 0.8590
- `margin_cap`: 2: 0.8340; 3: 0.8353; 4: 0.8340; 5: 0.8357
- `sigma_scale`: 1: 0.8353; 1.2: 0.8343; 1.4: 0.8340; 1.7: 0.8357
- `result_weight`: 0: 0.8428; 0.25: 0.8387; 0.5: 0.8345; 0.75: 0.8340; 0.9: 0.8414; 1: 0.8568

Best tuning log loss for each Dixon-Coles goals knob value:

- `ridge`: 1: 0.8567; 2: 0.8561; 4: 0.8578; 8: 0.8638; 16: 0.8781
- `rho`: -0.15: 0.8788; -0.1: 0.8747; -0.05: 0.8709; 0: 0.8672; 0.05: 0.8638; 0.1: 0.8598; 0.15: 0.8561
- `half_life_days`: 14: 0.8572; 28: 0.8561; 56: 0.8580; none: 0.8623
- `goal_cap`: 4: 0.8561; 6: 0.8578; none: 0.8993

## Test leagues

| League | Games | Goal margin | Results + margin | Dixon-Coles goals | Coin flip |
|---|---:|---:|---:|---:|---:|
| [2026 Summer · Downtown Brooklyn · Saturdays](https://nycfooty.leagueapps.com/leagues/4981886/standings) | 18 | 0.9985 | 1.0098 | 0.9830 | 1.0408 |
| [2026 Summer · Chinatown · Sundays](https://nycfooty.leagueapps.com/leagues/4981937/standings) | 21 | 0.7564 | 0.7944 | 0.7961 | 0.9714 |
| [2026 Summer · Williamsburg · Thursdays](https://nycfooty.leagueapps.com/leagues/4987937/standings) | 18 | 0.8830 | 0.8596 | 0.9275 | 0.9796 |
| [2026 Winter · Williamsburg · Saturdays](https://nycfooty.leagueapps.com/leagues/4789879/standings) | 15 | 0.6637 | 0.5963 | 0.7385 | 0.8237 |
| [2026 Summer · Upper East Side · Tuesdays](https://nycfooty.leagueapps.com/leagues/4980765/standings) | 20 | 0.5594 | 0.5842 | 0.6770 | 0.8951 |
| [2026 Winter · West Village · Sundays](https://nycfooty.leagueapps.com/leagues/4783983/standings) | 24 | 0.8255 | 0.8196 | 0.8586 | 1.0286 |

The dashboard's model registry (`MODEL_CHOICES` in `nycfooty/strength_models.py`) matches the selected parameters.
