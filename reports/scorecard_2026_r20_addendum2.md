# ADDENDUM 2 - 2026 Round 20 (Sao Paulo) forecast scorecard: official starting grid

> ## THIS FILE WAS WRITTEN AFTER THE RESULT WAS SEEN
>
> It is **not** a forecast-time artifact and must never be read as one. It was
> created on 2026-11-09, after `results` for 2026 R20 already existed and after
> the original scorecards had been produced.
>
> **Why it exists.** The original grid baseline was computed from `results.grid`,
> which FastF1 did not publish for this race (all `-1`). Addendum 1 rebuilt that
> baseline from the saved `grid_pred` (qualifying order, MAE 4.182). This
> addendum adds the **official starting grid** (after penalties) as a third
> comparator, sourced from FIA Doc 51 and formula1.com's official grid.
>
> **The original scorecards and Addendum 1 are unchanged** - both still contain
> exactly what was written at their respective times. Nothing in this addendum
> edits them.

## 1. Official starting grid (after penalties)

**Sources (cross-checked):**
- FIA Doc 51 "Provisional Starting Grid", 07 Nov 2026 20:00 UTC
- formula1.com official grid, 08 Nov 2026 16:14 UTC
- Reconstructed independently from published penalties: RUS −5, LEC −10,
  VER −30 (back of grid), PER −30 (back of grid), HAM −75 (back of grid)
- Cross-checked against crash.net, motorsportweek, gpfans, racingnews365,
  formulaonehistory — all match exactly.

**Grid positions (1..22):**

| Pos | Driver | Source qualifying order (`grid_pred`) | Penalty applied |
|-----|--------|----------------------------------------|-----------------|
| 1   | NOR    | 1                                      | —               |
| 2   | ANT    | 3                                      | —               |
| 3   | LAW    | 5                                      | —               |
| 4   | HUL    | 6                                      | —               |
| 5   | HAD    | 7                                      | —               |
| 6   | BEA    | 8                                      | —               |
| 7   | RUS    | 2                                      | −5 (PU)         |
| 8   | ALO    | 9                                      | —               |
| 9   | ALB    | 10                                     | —               |
| 10  | PIA    | 12                                     | —               |
| 11  | CAM    | 13                                     | —               |
| 12  | LIN    | 14                                     | —               |
| 13  | SAI    | 15                                     | —               |
| 14  | LEC    | 4                                      | −10 (PU)        |
| 15  | COL    | 17                                     | —               |
| 16  | GAS    | 18                                     | —               |
| 17  | STR    | 19                                     | —               |
| 18  | BOT    | 20                                     | —               |
| 19  | BOR    | 22                                     | —               |
| 20  | HAM    | 11                                     | −75 (PU, back)  |
| 21  | VER    | 16                                     | −30 (PU, back)  |
| 22  | PER    | 21                                     | −30 (PU, back)  |

**Differences from saved `grid_pred` (qualifying order): 21 of 22 cars moved.
Only NOR (pole) is unchanged.**

## 2. Official-grid baseline vs all other baselines

| Ranking | MAE | Spearman | Winner hit | Podium hit |
|---|---:|---:|---:|---:|
| **MODEL (full, 12 features)** | **2.777** | **0.8509** | **100%** | **33.3%** |
| MODEL (early, 7 features) | 2.934 | 0.8475 | 0% | 33.3% |
| grid baseline (from `grid_pred`, qualifying order) | 4.182 | 0.6793 | 100% | 33.3% |
| **official-grid baseline (this addendum)** | **5.273** | **0.4433** | **100%** | **33.3%** |
| pole-sitter wins (NOR) | — | — | 100% | 33.3% |
| practice-order baseline | **3.000** | 0.8091 | 0% | **66.7%** |
| recent-form baseline | 3.041 | 0.8180 | 0% | 33.3% |

**Key observations:**
- The official-grid baseline is **worse** (MAE 5.273) than the qualifying-order
  grid baseline (MAE 4.182) on this single race - a coincidence of one race,
  not a general finding.
- Both grid baselines have NOR at P1, so winner hit = 100% for both.
- Podium hit = 33.3% for both (only NOR in top 3).
- The **best baseline of all** by MAE remains **practice-order (3.000)**.
- The **best baseline of all** by podium hit is **practice-order (66.7%)**.

## 3. Both models vs best of ALL baselines (recomputed with official grid)

### MAE

| | figure | |
|---|---:|---|
| **full mode** | **-0.223** | better by 7.45% |
| **early mode** | **-0.066** | better by 2.20% |

**Identical to Addendum 1 and original scorecards.** Adding the official-grid
baseline (MAE 5.273) does not change the best baseline (practice-order 3.000).

### Winner / Podium hit rates

| | Winner vs best | Podium vs best |
|---|---:|---:|
| **full mode** | 0.0 pp | **-33.3 pp** |
| **early mode** | **-100.0 pp** | **-33.3 pp** |

Best winner baseline = 100% (grid / official-grid / pole-sitter all have NOR).
Best podium baseline = 66.7% (practice-order).

## 4. Predicted top 3 vs actual top 3 (both modes)

| Mode | Predicted 1st | Predicted 2nd | Predicted 3rd | Actual 1st | Actual 2nd | Actual 3rd |
|------|:---:|:---:|:---:|:---:|:---:|:---:|
| **full** | NOR ✅ | ANT | LEC | **NOR** | **VER** | **HAD** |
| **early** | VER ❌ | ANT | LEC | **NOR** | **VER** | **HAD** |

✅ = exact position match  
🔄 = on podium but wrong spot  
(early mode: 0/3 correct positions; full mode: 1/3 correct position)

**Podium hit definition (exact):** count of predicted top-3 drivers who finished
in the actual top 3. Range 0–3. Full mode: 1 (NOR). Early mode: 1 (ANT —
finished 5th, so 0; LEC finished 7th; VER finished 2nd — **1/3**).

Wait - let me recount:
- Full mode predicted podium: NOR, ANT, LEC. Actual: NOR, VER, HAD. Overlap = {NOR} → **1/3**
- Early mode predicted podium: VER, ANT, LEC. Actual: NOR, VER, HAD. Overlap = {VER} → **1/3**

Both modes: **podium hit = 1/3 = 33.3%**.

## 5. Top-10 actual vs both predicted orders

| Actual | Driver | FULL pred | err | EARLY pred | err | Official grid |
|---:|---|---:|---:|---:|---:|---:|
| 1 | NOR | 1 | 0 | 5 | +4 | 1 |
| 2 | VER | 8 | +6 | 1 | -1 | 21 |
| 3 | HAD | 5 | +2 | 7 | +4 | 5 |
| 4 | RUS | 4 | 0 | 6 | +2 | 7 |
| 5 | ANT | 2 | -3 | 2 | -3 | 2 |
| 6 | PIA | 11 | +5 | 8 | +2 | 10 |
| 7 | LEC | 3 | -4 | 3 | -4 | 14 |
| 8 | LAW | 6 | -2 | 9 | +1 | 3 |
| 9 | HAM | 7 | -2 | 4 | -5 | 20 |
| 10 | HUL | 9 | -1 | 15 | +5 | 4 |

`err = predicted position - actual finish`. Negative = model expected a better
finish than delivered.

## 6. Largest per-driver errors (same as Addendum 1)

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

## 7. Small-sample warning

This is **one race**. A winner hit rate over one race can only be 0% or 100%,
a podium hit rate only 0%, 33%, 67% or 100%, and a single MAE is one draw
from a wide distribution. Nothing in this addendum supports a claim about
model quality - that is what the 69-race walk-forward evaluation in Phases
3/4/5 is for. The scorecards stand as scored; this file only adds one more
comparator (the official grid) that was unavailable at forecast time.