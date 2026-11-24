# Forecast scorecard - 2026 round 20 (early mode)

- **Forecast written:** 2026-11-08T13:47:39+00:00
- **Race scheduled to start:** 2026-11-08T17:00
- **No-peeking check:** PASSED - written before lights out
- **Model:** phase5-ridge-1.0, alpha 1.0, 89 training races
- **Features (7):** driver_form, team_form, non_finish_rate, practice_pos, practice_gap_pct, practice_laps_30, no_practice_time
- **Note:** generated after qualifying, practice-only features
- **Scored on:** 22 of 22 forecast drivers
- **Scorecard written:** 2026-11-24T11:04:02+00:00

## Predicted top 3 vs Actual top 3

*See console output for the full predicted vs actual top-3 table with match markers.*

## Top-10 actual vs predicted (see console output)

## Model vs ALL baselines (this race only)

| Ranking | MAE | Spearman | Winner hit | Podium hit | Source |
|---|---:|---:|---:|---:|---|
| **MODEL** | 2.934 | 0.8499 | 0% | 33% | — |
| practice-order baseline | 2.500 | 0.8641 | 0% | 67% | — |
| recent-form baseline | 2.814 | 0.8556 | 0% | 67% | — |

**Improvement = model MAE - best baseline MAE = +0.434** (worse by 17.35%, best baseline: practice-order baseline).

## Winner and podium

- **Predicted winner:** VER
- **Actual winner:** NOR

## Small-sample warning

This is **one race**. A winner or podium hit rate over 1 race can only be 0% or 100%, and a single MAE is one draw from a wide distribution. Nothing here supports a claim about model quality - that is what the 69-race walk-forward evaluation in Phases 3/4/5 is for. Compare this race against its own baselines only, and re-check after several more forecasts have been saved and scored.
