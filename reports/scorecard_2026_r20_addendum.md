# ADDENDUM - 2026 Round 20 (Sao Paulo) forecast scorecard

> ## THIS FILE WAS WRITTEN AFTER THE RESULT WAS SEEN
>
> It is **not** a forecast-time artifact and must never be read as one. It was
> created on 2026-11-09, after `results` for 2026 R20 already existed and after
> the original scorecards had been produced.
>
> **Why it exists.** The original scorer built the grid baseline from
> `results.grid`, and FastF1 published **no starting grid for this race**:
> `GridPosition` is `-1` for all 22 cars. `features.py:417` treats any
> `grid <= 0` as "no slot" and fills it with `field size + 1`, i.e. **23 for
> every car**. A constant prediction has no ranking, so that row came out as
> MAE 11.500 with an undefined Spearman - a meaningless comparator, reported
> here only so the defect is on the record.
>
> **The original scorecards are unchanged.** `scorecard_2026_r20_full.md`
> (1,553 bytes) and `scorecard_2026_r20_early.md` (1,460 bytes) still hold
> exactly what was written at 21:50:21 UTC on 2026-11-08. Nothing in this
> addendum edits them.
>
> **Nothing else changed either.** No saved forecast was touched (still 44
> rows at 13:47:39 and 13:48:57), no model file was modified, and no alpha,
> feature or parameter was tuned after seeing the result. Every number below
> is recomputed from artifacts that already existed **before** the race - the
> `grid_pred` column saved alongside each forecast, which is exactly what it
> was saved for.

## 1. Grid baseline, rebuilt from the saved `grid_pred`

`grid_pred` is the qualifying order, saved pre-race. Same 22 drivers, same
actual results, same hit functions the model uses.

| Ranking | MAE | Spearman | Winner hit | Podium hit |
|---|---:|---:|---:|---:|
| **grid baseline (from `grid_pred`)** | **4.182** | **0.6793** | **100%** (1/1) | **33.3%** (1/3) |

For the record, the broken row the original scorer printed was MAE 11.500,
Spearman `nan` - `mean|23 - finish| = 23 - 11.5 = 11.5`, which is how the
constant-23 fill shows up arithmetically.

## 2. Pole-sitter wins baseline

**Lando Norris (NOR) started on pole** - fastest in qualifying (1:27.470) and
P1 on the official starting grid, the one car that kept its qualifying slot.

| Ranking | Winner hit | Podium hit |
|---|---:|---:|
| **pole-sitter wins (NOR)** | **100%** (1/1) | **33.3%** (1/3) |

NOR won the race, so the winner hit is 1/1. The podium hit is the overlap of
its top three with the actual top three: ranking by `grid` gives NOR / RUS /
ANT, and only NOR finished top three.

This baseline ranks by `grid`, the same column the grid baseline predicts
from, so the two coincide on this race. They are not the same baseline in
general - on history "pole-sitter wins" scores 59.4% winner / 68.1% podium
over 69 races, whereas the grid baseline's MAE is 3.241.

## 3. Both models against the best of ALL baselines (recomputed)

### MAE

| Ranking | MAE |
|---|---:|
| MODEL (full, 12 features) | 2.777 |
| MODEL (early, 7 features) | 2.934 |
| grid baseline (rebuilt, §1) | 4.182 |
| practice-order baseline | **3.000** |
| recent-form baseline | 3.041 |
| **best baseline of all** | **practice-order, 3.000** |

**Improvement = model MAE - best baseline MAE**

| | figure | |
|---|---:|---|
| **full mode** | **-0.223** | better by 7.45% |
| **early mode** | **-0.066** | better by 2.20% |

**These are identical to the original scorecards.** Restoring the grid
baseline does not move the headline, because 4.182 still loses to
practice-order's 3.000 - the best baseline is unchanged, so the improvement
figure is unchanged.

### Winner and podium hit rates

| Ranking | Winner | Podium |
|---|---:|---:|
| MODEL (full) | 100% | 33.3% |
| MODEL (early) | 0% | 33.3% |
| grid baseline (rebuilt) | 100% | 33.3% |
| pole-sitter wins (NOR) | 100% | 33.3% |
| practice-order | 0% | **66.7%** |
| recent-form | 0% | 33.3% |
| **best baseline of all** | **100%** | **66.7%** |

| | Winner vs best | Podium vs best |
|---|---:|---:|
| **full mode** | 0.0 pp | **-33.3 pp** |
| **early mode** | **-100.0 pp** | **-33.3 pp** |

Read honestly: full mode **matched** the best winner baseline (the pole-sitter
and the grid both had NOR, so 100% was available to a naive ranking) and
**lost clearly on podium** to practice-order. Early mode missed the winner
entirely. One race - see §7.

## 4. Actual top 10 next to both predicted orders

`err = predicted position - actual finish`. **Negative means the model expected
a better finish than the driver delivered.**

| Actual | Driver | FULL pred | err | EARLY pred | err |
|---:|---|---:|---:|---:|---:|
| 1 | NOR | 1 | 0 | 5 | +4 |
| 2 | VER | 8 | +6 | 1 | -1 |
| 3 | HAD | 5 | +2 | 7 | +4 |
| 4 | RUS | 4 | 0 | 6 | +2 |
| 5 | ANT | 2 | -3 | 2 | -3 |
| 6 | PIA | 11 | +5 | 8 | +2 |
| 7 | LEC | 3 | -4 | 3 | -4 |
| 8 | LAW | 6 | -2 | 9 | +1 |
| 9 | HAM | 7 | -2 | 4 | -5 |
| 10 | HUL | 9 | -1 | 15 | +5 |

Both modes put NOR first or close to it and both called ANT and LEC far too
strong (5th and 7th actual). The full mode's biggest single win was VER - it
had him 8th, he finished 2nd.

## 5. Largest per-driver errors

**FULL mode (12 features)**

| Driver | Predicted | Actual | err |
|---|---:|---:|---:|
| BEA | 10 | 17 | **-7** |
| VER | 8 | 2 | **+6** |
| PIA | 11 | 6 | +5 |
| CAM | 15 | 20 | -5 |
| PER | 22 | 18 | +4 |

**EARLY mode (7 features)**

| Driver | Predicted | Actual | err |
|---|---:|---:|---:|
| CAM | 14 | 20 | **-6** |
| BEA | 11 | 17 | **-6** |
| HUL | 15 | 10 | +5 |
| HAM | 4 | 9 | -5 |
| ALO | 17 | 12 | +5 |

The common failure in both modes is **BEA**, predicted around 10th-11th and
finished 17th, and **the two Ferraris**, both predicted far higher than they
finished (LEC 3rd vs 7th, HAM 4th-7th vs 9th) after their penalties.

## 6. Official starting grid and penalties - the differences

**An official grid with penalties does exist**, but not from any data source
this project can query:

| source | what it holds |
|---|---|
| FastF1 qualifying `GridPosition` | all `NaN` |
| FastF1 race `GridPosition` | **all `-1`** |
| OpenF1 | no grid field at all (`position` is live race position) |
| **FIA Doc 51, "Provisional Starting Grid", 07 Nov 2026 20:00** | **the real grid** |
| **formula1.com official grid, 08 Nov 2026 16:14 UTC** | **the real grid** |

**Penalties applied (FIA Doc 51):**

- Car 63 **RUS** - 5 place grid penalty, additional power unit element (doc 15)
- Cars 3 **VER** and 11 **PER** - 30 place grid penalties, additional power
  unit elements (docs 33 and 39); over 15 places means starting at the back
- Car 16 **LEC** - 10 place grid penalty, additional power unit element (doc 35)
- Car 44 **HAM** - 75 place grid penalty, additional power unit elements
  (docs 37 and 43); back of the grid

**Differences from the saved `grid_pred`: 21 of 22 cars moved. Only NOR is
unchanged** - he kept pole.

| Official | Driver | saved `grid_pred` (Q order) | moved |
|---:|---|---:|---:|
| 1 | NOR | 1 | 0 |
| 2 | ANT | 3 | +1 |
| 3 | LAW | 5 | +2 |
| 4 | HUL | 6 | +2 |
| 5 | HAD | 7 | +2 |
| 6 | BEA | 8 | +2 |
| 7 | RUS | 2 | **-5** |
| 8 | ALO | 9 | +1 |
| 9 | ALB | 10 | +1 |
| 10 | PIA | 12 | +2 |
| 11 | CAM | 13 | +2 |
| 12 | LIN | 14 | +2 |
| 13 | SAI | 15 | +2 |
| 14 | LEC | 4 | **-10** |
| 15 | COL | 17 | +2 |
| 16 | GAS | 18 | +2 |
| 17 | STR | 19 | +2 |
| 18 | BOT | 20 | +2 |
| 19 | BOR | 22 | +3 |
| 20 | HAM | 11 | **-9** (back of grid) |
| 21 | VER | 16 | **-5** (back of grid) |
| 22 | PER | 21 | -1 (back of grid) |

The grid above was reconstructed independently from those penalties and
matches FIA Doc 51 and formula1.com exactly, cross-checked against five
further published grids. Note also that **BOT did not start** (technical
problem on the grid) - 21 cars took the start, and he is classified 22nd.

**For reference only, computed after the result:** the grid baseline scored
against the *official* grid would have been MAE 5.273, Spearman 0.4433,
winner 100%, podium 33.3% - i.e. **worse** than the 4.182 obtained from the
qualifying order. That is a coincidence of one race, not a general finding,
and it is not used anywhere in the headline figures of §3.

## 7. Small-sample warning

This is **one race**. A winner hit rate over one race can only be 0% or 100%,
a podium hit rate only 0%, 33%, 67% or 100%, and a single MAE is one draw
from a wide distribution. Nothing in this addendum supports a claim about
model quality - that is what the 69-race walk-forward evaluation in Phase
3/4/5 is for. The scorecards stand as scored; this file only repairs one
comparator that a missing data source had made undefined.
