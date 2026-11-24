# Forecast scorecard - 2026 round 21 (early mode)

- **Forecast written:** 2026-11-22T01:35:29+00:00
- **Race scheduled to start:** 2026-11-22T04:00
- **No-peeking check:** PASSED - written before lights out
- **Model:** phase7-xgboost-1.0, alpha 1.0, 193 training races
- **Features (7):** driver_form, team_form, non_finish_rate, practice_pos, practice_gap_pct, practice_laps_30, no_practice_time
- **Note:** generated before qualifying, practice-only features
- **Scored on:** 22 of 22 forecast drivers
- **Scorecard written:** 2026-11-24T11:02:52+00:00

## Predicted top 3 vs Actual top 3

*See console output for the full predicted vs actual top-3 table with match markers.*

## Top-10 actual vs predicted (see console output)

## Model vs ALL baselines (this race only)

| Ranking | MAE | Spearman | Winner hit | Podium hit | Source |
|---|---:|---:|---:|---:|---|
| **MODEL** | 3.950 | 0.6940 | 0% | 33% | — |
| practice-order baseline | 4.273 | 0.6894 | 0% | 33% | — |
| recent-form baseline | 4.555 | 0.5755 | 100% | 33% | — |

**Improvement = model MAE - best baseline MAE = -0.323** (better by 7.56%, best baseline: practice-order baseline).

## Winner and podium

- **Predicted winner:** ANT
- **Actual winner:** VER

## Small-sample warning

This is **one race**. A winner or podium hit rate over 1 race can only be 0% or 100%, and a single MAE is one draw from a wide distribution. Nothing here supports a claim about model quality - that is what the 69-race walk-forward evaluation in Phases 3/4/5 is for. Compare this race against its own baselines only, and re-check after several more forecasts have been saved and scored.
