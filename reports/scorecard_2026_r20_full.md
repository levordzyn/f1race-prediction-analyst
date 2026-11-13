# Forecast scorecard - 2026 round 20 (full mode)

- **Forecast written:** 2026-11-08T13:48:57+00:00
- **Race scheduled to start:** 2026-11-08T17:00
- **No-peeking check:** PASSED - written before lights out
- **Model:** phase5-ridge-1.0, alpha 1.0, 89 training races
- **Features (12):** grid, driver_form, team_form, non_finish_rate, practice_pos, practice_gap_pct, practice_laps_30, no_practice_time, q_position, q_gap_pct, no_q_time, on_pole
- **Note:** generated after qualifying, full feature set
- **Scored on:** 22 of 22 forecast drivers
- **Scorecard written:** 2026-11-11T02:28:25+00:00

## Predicted top 3 vs Actual top 3

*See console output for the full predicted vs actual top-3 table with match markers.*

## Top-10 actual vs predicted (see console output)

## Model vs ALL baselines (this race only)

| Ranking | MAE | Spearman | Winner hit | Podium hit | Source |
|---|---:|---:|---:|---:|---|
| **MODEL** | 2.777 | 0.8509 | 100% | 33% | — |
| grid baseline | 11.500 | n/a | n/a | n/a | — |
| practice-order baseline | 3.000 | 0.8091 | 0% | 67% | — |
| recent-form baseline | 3.041 | 0.8180 | 0% | 33% | — |

**Improvement = model MAE - best baseline MAE = -0.223** (better by 7.45%, best baseline: practice-order baseline).

**n/a:** grid baseline produced one identical value for every car in this race, so its ranking is constant: rank correlation is undefined and there is no distinct car to rank first. For the grid baseline that means no valid starting grid exists in `results` - either the race has not been fetched yet, or FastF1 published no grid at all (GridPosition of 0, -1 or NULL; 2026 R20 returned -1 for all 22 cars). Every slot is then filled with field size + 1, which is right for a pit-lane start but identical across the whole field.

## Winner and podium

- **Predicted winner:** NOR
- **Actual winner:** NOR

## Small-sample warning

This is **one race**. A winner or podium hit rate over 1 race can only be 0% or 100%, and a single MAE is one draw from a wide distribution. Nothing here supports a claim about model quality - that is what the 69-race walk-forward evaluation in Phases 3/4/5 is for. Compare this race against its own baselines only, and re-check after several more forecasts have been saved and scored.
