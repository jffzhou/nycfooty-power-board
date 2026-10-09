# Historical three-game validation

> 2026-09-18 run of the pre-tuning model (ridge 2, no margin cap, 22% draw prior, noise x1.0). The production parameters were tuned on these six leagues on 2026-10-09; see `hyperparameter_backtest.md`.

No model parameters were fitted or changed for this exercise.

## Selection and cutoff

The completed archive contained 17 exact P4/P5 outdoor listings. After requiring 7v7, a posted schedule, eight completed regular-season games per team, and a post-cutoff holdout, 12 leagues remained. Six were sampled with `random.Random(5086028)`.

For every team, only results that were within both teams' first three chronological regular-season games entered training. This yields 2-3 training games per team, comparable to the current league. Playoffs and all later scores were hidden. Administrative forfeits were excluded from match scoring.

The neutral baseline uses the same training-snapshot draw prior but assigns equal probability to either team. Lower log loss, Brier score, and margin MAE are better.

## Pooled holdout results

- Scored matches: **94**; excluded future forfeits: **4**
- Log loss: **0.957** vs baseline **0.993**
- Multiclass Brier: **0.550** vs baseline **0.605**
- Most-likely-outcome accuracy: **57.4%**
- Average favorite probability: **67.1%**; confidence minus accuracy: **+9.7%**
- Goal-margin MAE: **2.61** vs zero-margin baseline **3.04**

## By league

| League | Train/team | Holdout | Log loss (base) | Accuracy | Margin MAE (base) | Strength ρ | Projection ρ | Champion | Top 4 |
|---|---:|---:|---:|---:|---:|---:|---:|:---:|:---:|
| [2026 Summer · Lower East Side · Mondays](https://nycfooty.leagueapps.com/leagues/4978774/standings) | 3-3 | 13 | 1.369 (1.092) | 46.2% | 3.93 (4.00) | +0.37 | +0.83 | yes | 3/4 |
| [2025 Fall · Harlem Riverbank · Wednesdays](https://nycfooty.leagueapps.com/leagues/4688994/standings) | 2-3 | 26 | 0.651 (0.941) | 69.2% | 2.41 (3.42) | +0.82 | +0.85 | no | 3/4 |
| [2026 Spring · Chinatown · Sundays](https://nycfooty.leagueapps.com/leagues/4887792/standings) | 3-3 | 14 | 0.824 (0.899) | 71.4% | 2.57 (3.21) | +0.89 | +0.94 | yes | 3/4 |
| [2026 Spring · Brooklyn Heights · Saturdays](https://nycfooty.leagueapps.com/leagues/4887195/standings) | 3-3 | 15 | 1.240 (1.018) | 46.7% | 3.12 (2.87) | +0.66 | +0.66 | yes | 3/4 |
| [2026 Winter · Chinatown · Sundays](https://nycfooty.leagueapps.com/leagues/4783265/standings) | 2-3 | 12 | 0.910 (1.060) | 41.7% | 1.81 (2.00) | +0.00 | +0.10 | yes | 3/4 |
| [2026 Summer · Two Bridges · Tuesdays](https://nycfooty.leagueapps.com/leagues/5029631/standings) | 2-3 | 14 | 1.014 (1.007) | 57.1% | 1.96 (2.36) | +0.70 | +0.90 | yes | 4/4 |

## Final-table summary

- Mean strength-rank Spearman ρ: **0.572**
- Mean Week-3 table Spearman ρ: **0.751**
- Mean projected-table Spearman ρ: **0.714**
- Projected champion correct: **5/6**
- Projected top-four overlap: **19/24**

## Interpretation

The model has real early-season signal: pooled proper scores and margin error beat neutral baselines. The evidence is not uniformly strong: log loss lost to baseline in three of six leagues, and average confidence exceeded favorite accuracy by roughly ten percentage points.

For final ordering, the simulation did not improve on the raw Week-3 table in this sample: mean projected-table rank correlation was lower. Its 5/6 champion hit rate is encouraging, but the six-league sample is too small for a strong claim.

This is an external check of the frozen model, not parameter selection. These results must not be used to tune the same model and then quoted as out-of-sample evidence.
