# Limitations

Honest constraints on what these results mean. Written for the README; every
number here comes from the scripts named in each section.

---

## 1. Small sample

Walk-forward validation starts after `MIN_TRAIN_RACES = 20`, so the model is
scored on **69 races / 1,416 driver rows** out of 89 races / 1,816 rows.

- **MAE and Spearman** are averaged over 69 races and are the numbers to trust.
- **Winner and podium hit rates are weak evidence.** One lucky or unlucky race
  moves them by `100/69 ≈ 1.4` percentage points. A winner is a 1-in-22 draw, so
  a uniform guess scores about 5%.
- Feature-group effects are similarly fragile. The practice group's −0.023
  positions MAE has a 95% bootstrap CI of **[−0.033, −0.014]** over races
  (`scripts/paired_practice_effect.py`), but that interval **assumes races are
  independent**, and they are not: expanding-window folds share almost all of
  their training data, and consecutive races share drivers, teams and
  regulations. The effective sample is smaller than 69, so treat the interval
  as optimistic rather than as a formal proof.
- Never tune alpha or features on these same folds. `RIDGE_ALPHA` is fixed at
  1.0 for exactly this reason. `scripts/check_alpha_window.py` demonstrates
  the compliant alternative — re-selecting alpha *inside* each training
  window, never seeing the fold's own race — and finds it scores 3.0786
  against the fixed alpha's 3.0756, i.e. tuning would have been slightly
  *worse*. The fixed value is not a hidden advantage (see section 9).

## 2. F1 itself is noisy

Safety cars, red flags, weather, reliability, strategy and punctures all move
the finishing order for reasons no pre-race feature can see. Some consequences:

- The **grid baseline is strong** (MAE 3.241, Spearman 0.678) and the full
  model only beats it by about **5.3%**. Do not present this as a large gain.
- 14.6% of driver-races (266/1,816) are non-finishes — Retired, Accident,
  Collision damage and similar — and those outcomes are largely unpredictable
  from grid or pace.
- Results are **weak evidence**, not proof. The shuffled-label check
  (scrambled training labels collapse to ~5.14 vs 3.07 MAE) confirms the
  pipeline learns something real, but it does not make any single prediction
  reliable.

## 3. Practice data quality

Practice comes from **OpenF1**, not FastF1, and has needed two repairs.

### Miami 2026 R4 — corrupt reference lap (fixed)

PIA's stored `best_practice_s` was **60.351 s** while his own three sectors
summed to **202.620 s** and the other 21 cars ran 89.3–93.0 s. Miami's lap time
is ~89 s, so 60.351 s cannot be a full flying lap.

Because `gap_to_best_pct` is measured against the weekend's fastest lap, that
one bad record corrupted **all 22 cars' gap values** (up to 54.03%) and moved
3 cars' `practice_rank` (PIA 1→3, LEC 2→1, VER 3→2). It was also what made
the practice group look harmful in Phase 3 (that race alone cost +2.204 MAE).

Fixed by two validity rules in `f1pred/openf1.py` (`classify_laps`):

| rule | threshold | rationale |
|---|---|---|
| sector arithmetic | `SECTOR_TOLERANCE_S = 0.1 s` | values are stored to 3 dp, so rounding contributes ≤ 0.002 s; 0.1 s sits in a real gap (kept laps deviate by **0.0000 s**, rejected laps by **≥ 0.514 s**) |
| missing sectors | **never rejected** | no sectors means no verdict — we only reject what we can prove is wrong |
| implausible speed | `MIN_LAP_FRACTION = 0.90` of the session's **2nd**-fastest lap | largest legitimate fastest-vs-2nd gap across 89 races was 0.8%, so 10% leaves a 12× margin; only *faster* laps can be rejected, so slow drivers are never touched |
| minimum sample | `MIN_LAPS_FOR_REFERENCE = 10` usable laps | below that the reference is untrustworthy and nothing is rejected |

These were fixed **before** any Phase 3 metric was inspected and are not tuned
against results. `scripts/test_lap_rules.py` (13 checks) proves rule 2 fires at
all, since it never triggered on real data — rule 1 catches the corrupt laps
first.

Re-fetching only Miami 2026 R4 left the other 88 races **byte-identical by
hash**. Backup: `f1_backup_before_miami_practice_refetch_20261106_132934.db`.

### 2025 R22 — systematic small sector offset (known, harmless today)

**72 of the 87** practice laps rejected worldwide belong to this one race.
Unlike every other rejected lap (which deviate by 8.7–1037.8 s), these miss by
only **0.514–1.492 s (median 0.542 s)**, and all are early laps (lap 3–7).

This is a **different defect** from the Miami corruption, not the same one at
smaller scale.

**Confirmed harmless:** none of the 72 was any driver's best lap
(`scripts/check_r22_rejected_best.py`), so 2025 R22's stored values are
unchanged. Across all 89 races exactly **one** rejected lap was ever a driver's
best — PIA's 60.351 s at Miami, the corruption already fixed.

**Watch-out:** if a future re-fetch or a data revision ever promotes one of
these 72 laps to a driver's fastest, 2025 R22 would be the first race to
change. If `validate_lap_rules.py` ever reports a second changed race, check
R22 first.

## 4. One-lap-speed proxies

Two features stand in for pace using a **single lap**, which is a proxy rather
than a measurement of race pace:

- `practice_pos` / `practice_gap_pct` — the weekend's fastest practice lap.
  Practice is run on varying fuel loads, tyre compounds and run plans, and is
  often spent testing rather than optimising. A driver can be fastest in
  practice and finish mid-field.
- `best_sq_s` / `sq_rank` — sprint qualifying, a one-lap shootout.

Neither reflects long-run pace, tyre degradation, fuel-corrected pace or race
strategy. They are included because they are cheap, pre-race and available for
every weekend, not because they are strong signals — the practice group's
measured contribution is about −0.023 positions MAE, i.e. small.

## 5. Missing data and edge cases (documented, not hidden)

| case | handling |
|---|---|
| missing qualifying time | `q_position` → `field_n + 1`; `no_q_time = 1` flag; 22 rows affected |
| fully unknown qualifying | 6 drivers: 2025 R21 BOR; 2026 R1 SAI/STR/VER; 2026 R14 BEA/STR — all six **did** race |
| missing practice lap | `practice_pos` → `field_n + 1`; `no_practice_time = 1` flag |
| pit-lane start (`grid` 0/NULL) | 5 rows, filled with `field_n + 1`, **never 0** |
| driver with no history (debut) | `driver_form` → `(field_n + 1)/2`, `non_finish_rate` → 0.0 (constants, so no leakage) |
| DNS rows kept as targets | 16 rows (0.88%). FastF1 classifies them at the back; excluding unpredictable outcomes would flatter MAE and break the 1,816-row invariant |
| team renames | fixed at alias level via `clean_team_name()`; 18 raw labels → 11 canonical |
| field size | **22 cars in 2026** — never hard-coded; 2023–2025 run 19/20/22 |

## 6. Coefficient signs are not all interpretable

`scripts/check_coef_signs.py` compares each feature's plain Spearman
correlation with finishing position against its Ridge coefficient. **4 of the
12 disagree in sign**, and they are exactly the cases where two features
encode the same underlying quantity:

| pair | marginal ρ | Ridge coef | shared meaning |
|---|---|---|---|
| `q_position` | +0.678 | **+1.90** | qualifying pace |
| `q_gap_pct` | +0.613 | **−0.03** | qualifying pace |
| `practice_pos` | +0.553 | **+0.17** | practice pace |
| `practice_gap_pct` | +0.513 | **−0.18** | practice pace |
| `driver_form` | +0.587 | **+1.35** | recent performance |
| `non_finish_rate` | +0.173 | **−0.47** | recent performance |

**This is not a data bug.** The raw relationship is correct and monotonic —
mean finish is **9.84** for drivers with no DNFs in their last 5 races,
**12.70** at a 40–80% DNF rate and **13.82** above 80%. What happens is
Ridge sharing the correlated signal: the dominant feature takes the weight
and the smaller partner is left with a residual that can flip sign.

Practical consequences:

- Do **not** read an individual coefficient as "changing this feature changes
  the result by X positions". That reading is only safe for the well-separated
  features (`grid`, `q_position`, `on_pole`).
- Interpret the **feature group** instead — the Phase 3 ladder measures each
  group's real contribution (grid_form −2.012, practice −0.023, qualifying
  −0.037), which is unaffected by this problem.
- The chart itself is still correct as a display of fitted weights; only the
  causal reading of individual bars is unsafe.

## 7. What this project does not do

- **No tyre strategy or pit-stop model.** Strategy, safety cars and pit windows
  are the largest unmodelled causes of variation (section 2).
- **Weather is race-level, which structurally limits it.** `temp_c`,
  `humidity_pct`, `rain_mm` and `wind_kmh` are **one value shared by every car
  in a race**. In a linear model with an intercept, adding the same constant
  to all 22 predictions **cannot change their order** — so those four cannot
  move within-race rank correlation or the hit rates at all; they only shift
  the predicted *level*, which is why they can affect MAE but never the
  ranking. Only the three interaction terms can reorder cars. Section 9
  measures what that buys: nothing measurable.
- **No causal claims.** A Ridge coefficient is a conditional association over
  these 69 races, not evidence that changing a feature changes a result.
- **Not a betting tool.** The model beats the grid baseline by ~5%; that edge
  is far too small and too uncertain to act on.

## 8. Weather: observed history is not a weather forecast

Phase 6b added `temp_c`, `humidity_pct`, `rain_mm`, `wind_kmh` plus three
pre-chosen interactions. Every one of them has a mismatch that matters at
prediction time.

### The values are OBSERVED, but a prediction happens before the day

The numbers come from Open-Meteo's historical archive and describe **what the
weather actually was**. A real prediction for a future race cannot have that:
it needs a weather *forecast*, which is a different and less accurate product.

So the Phase 6 ladder answers "would knowing the race-day weather have helped,
given that we already know it?" That is an **upper bound** on what a
forecast-driven model could achieve, not an estimate of it — a forecast adds
its own error on top. For a race whose date has not passed, `build_features`
deliberately **omits the weather columns entirely rather than filling them**
(`scripts/fetch_weather.py` only fetches dates that exist), so a future race
must be given a supplied forecast.

### Whole-day totals, not race-time readings

`rain_mm` is `rain_sum` for the **entire day** and `temp_c` the **daily
mean** — neither describes the condition at lights-out.

**2023 Spain is the proof.** Open-Meteo records 10.8 mm and an 18.7 °C daily
mean for 2023-06-04, and AEMET (*"intervalos nubosos con lluvia escasa"*) and
Weather Spark both confirm a drizzly day — yet race-day reporting records a
**dry race**, with air temperature at race time of 22.7 °C. The rain fell
while the cars were in the garage.

Consequence: `rain_mm` honestly means "was it a wet *day*", which is a weaker
and different claim from "was it wet *during the race*". A model built to
predict a specific Sunday afternoon would want session-time observations.

### Verification performed before any of this was trusted

- Provider, variable names and units were confirmed against **one real
  response before any parsing code existed** (`scripts/probe_weather_provider.py`,
  HTTP 200, keys printed): `temperature_2m_mean`, `relative_humidity_2m_mean`,
  `rain_sum`, `wind_speed_10m_max`.
- 89/89 races fetched, zero NULLs, dates identical to `sessions.event_date`
  (`scripts/fetch_weather.py`, section [3]).
- Coordinates are hand-entered because the database holds none at all.
  **"Spanish Grand Prix" is Barcelona for 2023–2025 but the Madring in Madrid
  from 2026**; keying on the event name alone would have silently given 2026
  R14 Barcelona's weather. `fetch_weather.py` overrides that one case
  explicitly and prints an `OVERRIDE` marker (`--dry-run` shows the full
  venue table with no network access).
- Independent spot-checks agree: Bahrain 33.8 °C / 59%, Singapore 28.4 °C /
  80%, Mexico City 18.4 °C, Melbourne 12.5 °C / 76% — all correct for those
  venues, which would not hold if a coordinate were wrong.
- Data independent of Open-Meteo confirms 2023-06-04 Barcelona was wet
  (AEMET: *"intervalos nubosos con lluvia escasa"*, Weather Spark: observed
  light drizzle), so the provider is not inventing rain.

## 9. Phase 6 feature groups did not measurably help

Both Phase 6 groups were added **one at a time** on identical walk-forward
splits, with alpha fixed at 1.0 for every stage so each delta measures only
the new group. **Neither beat the 12-feature model:**

| group | features | MAE before → after | Δ | paired 95% CI | verdict |
|---|---|---|---|---|---|
| sprint | 6 | 3.069 → 3.073 | **+0.004** (+0.127%) | [−0.007, +0.017] | contains 0 |
| weather | 7 | 3.073 → 3.076 | **+0.003** (+0.095%) | [−0.018, +0.027] | contains 0 |

A positive Δ is a **regression**. Both intervals contain zero, so **neither
group has been shown to help**, and reporting either as an improvement would
be wrong. Rank correlation drifts the same way: 0.7084 → 0.7061 → 0.7036.

### The two results are not the same kind of "null"

- **Sprint** (`scripts/run_phase6a.py`): 45 of 69 races *improved*
  (sign test p = 0.015) yet the mean got worse, because the median is −0.005
  while the tail reaches **+0.221**. **13 of the 18 sprint weekends** in the
  validation set are among the 24 that got worse — the group hurts most on the
  very weekends it describes, almost certainly because sprint qualifying and
  the sprint race only weakly predict the Grand Prix (rank correlation
  between `sprint_pos` and `finish` is 0.485). Wilcoxon p = 0.098, so even
  the sign result is not robust once magnitudes are used.
- **Weather** (`scripts/run_phase6b.py`): 39 improved / 30 worse,
  sign p = 0.34, Wilcoxon p = 0.40 — no signal at all. This is the expected
  outcome given section 7: four of the seven features are race-level
  constants that cannot reorder anything, and only three interactions can.

### Why this is believable rather than a bug

- **No units error.** `sq_gap_pct` sits on the same scale as the other gap
  features — median 1.45% against 1.22% (qualifying) and 1.22% (practice) —
  so it is a real percentage, not a 0..1 ratio that would have made the
  feature near-constant and invisible.
- **No leakage.** `sprint_pos` equals the Grand Prix result in only 10.2% of
  rows (rank correlation 0.485); it is plainly a different race. Shuffled-label
  controls on the 18- and 25-feature sets collapse to **5.19** and **5.23**
  against 3.07, so neither group smuggled the answer in.
- **Alpha is not the explanation.** `scripts/check_alpha_window.py`
  re-selects alpha inside each training window (races strictly before the
  fold's own race) and scores **3.0786** against the fixed alpha's
  **3.0756** — tuning would have been *worse*. The same script asserts it
  reproduces `walk_forward`'s stage-5 MAE to six decimals before reporting
  anything.
- **The model still works.** Both extensions beat the best baseline (grid,
  3.241) at 3.073 and 3.076.

### A known redundancy inside the sprint group

`no_sprint_result` equals `1 − has_sprint` for **all 1,816 rows** (no sprint
has ever had a starter without a result), so Ridge cannot separate the two
weights. It is kept because the spec asks for a missing flag, and the
duplication is reported — `scripts/check_sprint_features.py`, check [8] —
rather than silently dropped, the same policy already applied to
`q_position` / `q_gap_pct`. `no_sq_lap` is *not* redundant: it differs in 3
rows where a driver set no sprint-qualifying lap.

### Production feature set

**Both weekend types use the same feature set.** `f1pred/cli.py` wires only
`MODE_FEATURES = {"early": EARLY_FEATURES, "full": FULL_FEATURES}` — the
sprint and weather columns are never passed to a production prediction.

| mode | features | count |
|---|---|---|
| early (unknown qualifying) | `driver_form`, `team_form`, `non_finish_rate`, `practice_pos`, `practice_gap_pct`, `practice_laps_30`, `no_practice_time` | 7 |
| full | the 7 above + `grid`, `q_position`, `q_gap_pct`, `no_q_time`, `on_pole` | 12 |

- **Conventional weekends** — exactly the table above. The six sprint columns
  would all be constant on a conventional weekend (`has_sprint` = 0 for every
  car), so they cannot reorder anything; they are not in the model.
- **Sprint weekends** — the *same* 7/12. The sprint group is excluded because
  it measurably hurt (13 of 18 sprint weekends got worse, §9), and the weather
  group is excluded because it showed no effect at all.
- **The two Phase 6 groups are kept as documented experiments**, not deleted:
  they stay in `SPRINT_FEATURES` / `WEATHER_FEATURES` / `PHASE6_LADDER` so the
  measurement in this section stays reproducible, and they stay out of
  `ALL_FEATURES` / `FEATURE_GROUPS` so no already-accepted Phase 3/4/5 number
  can move.

**Nothing is tuned on validation data.** `RIDGE_ALPHA` is fixed at 1.0 for
every stage of every ladder, decided before any stage-4 or stage-5 MAE
existed. `scripts/check_alpha_window.py` shows the compliant alternative
(selecting alpha strictly inside each training window) scoring *worse* than
the fixed value, so no hidden selection is at work. No feature group was kept
or dropped on the strength of a validation result either — the production set
above is the pre-registered Phase 3 set, and Phase 6 groups are excluded on
the basis of *no measurable effect*, which is the honest reading of an
interval containing zero.

**Winner/podium baselines.** The 63.8% winner hit rate is always reported
against ranking baselines scored on the same 69 races by the same `_hits()`
(`HIT_BASELINES` in `f1pred/model.py`), printed in full by
`scripts/run_phase4.py`:

| | winner | podium |
|---|---|---|
| MODEL (ridge, walk-forward) | 63.8% | 67.6% |
| pole-sitter wins | 59.4% | 68.1% |
| best qualifying gap wins | 60.9% | 67.6% |
| best driver form wins | 21.7% | 49.3% |
| **best BASELINE** | **60.9%** | **68.1%** |
| MODEL − best BASELINE (pp) | **+2.9** | **−0.5** |

The model beats the best winner baseline by 2.9 pp and is 0.5 pp **behind**
the best podium baseline — both stated as-is. Baseline scores are small-sample
(69 races) and each race contributes at most 1/69, so the ±1.4 pp-per-race
caveat in §1 applies to these too.

---

## 10. Freeze boundary and change log — São Paulo 2026 R20

### Correction: the earlier "no change after seeing a prediction" claim was wrong

An earlier statement in this project claimed that **no code was changed after a
prediction had been seen**. **That claim was wrong** and is withdrawn here.

Predicted orders were printed by the flow-test runs at **13:07** and **13:12**
UTC on 2026-11-08 — both *before* the 13:31 backup — and every edit in the
change log below was made afterwards. This section exists so the record is
accurate, not to soften the claim.

### Corrected freeze statement

**The freeze applies from the 13:48 save.** The forecasts were written at
`2026-11-08T13:47:39Z` (early mode) and `2026-11-08T13:48:57Z` (full mode),
and `f1.db` was last written at **13:48:59**. No model file has been modified
since, and no forecast row has been rewritten. Earlier framings anchored the
freeze to the 13:31 backup, or to "every file predates the 13:47:39 early
save" — those describe file timestamps only, and they were used to support the
stronger claim corrected above.

### Change log: backup (13:31:00) → early save (13:47:39)

| time (UTC) | file | what changed |
|---|---|---|
| 13:32:04 | `f1pred/db.py` | `forecasts` gains `model_version`, `grid_pred`, `note`; the migration refuses to ALTER a non-empty `forecasts` |
| 13:33:08 | `f1pred/model.py` | adds `MODEL_VERSION = "phase5-ridge-1.0"`; moves `EARLY_BASELINES` / `FULL_BASELINES` here to break the cli ↔ forecast import cycle |
| 13:34:09 | `f1pred/features.py` | **`_forecast_spine` now fills `grid` from `qualifying.q_position`** (previously NULL → `field_n + 1`) |
| 13:40:23 | `f1pred/forecast.py` | `save()` gains the no-overwrite guard and the three new columns |
| 13:47:12 | `f1pred/cli.py` | adds `--fetch`; the save banner shows model version, note and car count |

Outside the window: `f1pred/fetch.py` 12:43:51 and
`scripts/test_upcoming_fetch.py` 12:45:51 (before); `f1.db` 13:48:59, the
early scatter 13:47:43, `scripts/test_forecast_flow.py` 14:02:25 and
`scripts/score_forecast.py` 14:05:03 (after).

**Caveat on this log.** A file's mtime records only its *last* write.
`scripts/score_forecast.py` (created 13:00:56, last written 14:05:03) and
`scripts/test_forecast_flow.py` (created 13:05:49, last written 14:02:25) both
predate the backup, so timestamps alone cannot prove whether either was edited
inside the window. Both are tooling; neither is imported by `build_features`,
`walk_forward` or `forecast.save`.

### The one edit that followed seeing a prediction and changed what was saved

**`f1pred/features.py` at 13:34:09 followed seeing predictions, and it changed
the saved forecast.**

Its stated trigger was the requirement to save the grid-baseline prediction
alongside the model's own call — meaningless while `grid` was a constant
`field_n + 1` for every car — together with the already-documented fact that
the `grid` feature was constant for this race. Neither reason is a prediction
value. But the edit still came after the 13:07 and 13:12 runs had printed an
order, so the honest description is: **it followed seeing predictions.**

**Reconstructed effect (full mode only):**

- every full-mode prediction moved by `−0.0447 × (23 − grid)`, where 0.0447 is
  the fitted shift per grid slot, recovered from the five before/after pairs
  the 13:12 output printed — those five were observed directly; the other 17
  before-values are reconstructed from that fitted relationship;
- **the top 3 did not change: NOR, ANT, LEC both before and after**;
- **8 of 22 ranks changed**, four swaps in the middle and back of the field:
  HAM/LAW (6↔7), PIA/BEA (10↔11), COL/SAI (16↔17), BOR/STR (19↔20);
- **early mode is unaffected**: `grid` is not one of the seven
  `EARLY_FEATURES`, so no early-mode input changed. No early-mode prediction
  was printed before the fix, so there is nothing to diff against — this rests
  on `grid` being absent from that feature list, and on no other in-window edit
  touching a computation.

**Why the shift is exactly proportional to `23 − grid`.** `StandardScaler` is
fitted on the *training* rows, where `grid` varies, then applied to the forecast
rows. Before the fix every forecast row carried `grid` = 23, so they all
received the *same* standardised value and the feature shifted every score
equally — it could not reorder anything, which is the part of the old warning
text that was accurate. After the fix each row carries its own qualifying
position. The difference between the two is therefore exactly
`coefficient × (grid − 23) / scale`, i.e. proportional to `23 − grid`, which is
what the five observed pairs confirm to three decimal places.

What the fix actually restored was **per-car information**: with a constant
forecast column the saved grid baseline would have called every one of the 22
cars 23rd, so the grid comparator the forecast is meant to be scored against
would have been degenerate. It is still recorded here as a post-sighting
change, because that is what it was.

### The scorer's grid-source bug (found after the race)

**What went wrong.** `score_forecast.py` scores the grid baseline from
`results.grid`. For 2026 R20 FastF1 published **no starting grid at all** —
`GridPosition` is `-1` for every one of the 22 cars. `features.py:417`
(`bad_grid = isna() | (grid <= 0)`) reads that as "no slot" and fills it with
`field size + 1`, so **all 22 cars got `grid` = 23**. A constant prediction has
no ranking, so the row came out as **MAE 11.500, Spearman undefined** — and
`mean|23 − finish| = 23 − 11.5 = 11.5` reproduces that MAE exactly, which is
how the cause was identified.

**Scope: one comparator row, and nothing else.** The forecast was written
before the race from `qualifying.q_position` (verified 44/44), and scoring only
compares those saved predictions against what happened — it never re-fits. So
the model's MAE, Spearman, winner and podium figures in both scorecards are
unaffected, as are the practice-order and recent-form baselines. Restoring the
grid baseline does not move the headline either: its correct MAE (4.182) still
loses to practice-order (3.000), so "best baseline" and the −0.223 / −0.066
improvement figures are identical to what was originally scored.

**Why preflight did not catch it.** The pre-race check validates
`forecasts.grid_pred`, which was correct (1..22, all from qualifying). Nothing
checked `results.grid` after the race was fetched, because that column is only
read once a race exists.

**An earlier claim of mine was wrong.** After the race I reported that *no grid
differences from penalties were found*, based on FastF1's race-control
messages. That was **incorrect**: grid penalties are published in FIA steward
documents, not in race control, and this weekend carried five of them — RUS
−5, LEC −10, VER and −30 and PER −30 to the back, HAM −75 to the back. The
official grid (FIA Doc 51, confirmed by formula1.com) **differs from the saved
`grid_pred` for 21 of 22 cars; only the pole-sitter, NOR, is unchanged.**
Neither FastF1 nor OpenF1 exposes that grid in any field, which is also why the
scorer could not have read it.

**Consequence for the model, stated plainly.** The `grid` feature used at
forecast time was the qualifying order, which was wrong for 21 of 22 cars.
That is a data-availability limitation, not a modelling choice, and it cannot
be repaired after the fact without destroying what makes the forecast
meaningful — that it was written before the result existed. It is recorded
here rather than corrected.

**The repair is an addendum, not an edit.**
`reports/scorecard_2026_r20_addendum.md` was written *after* seeing the
result, rebuilds the grid baseline from the pre-race `grid_pred`, and says so
at the top. The original scorecards are byte-for-byte unchanged.

**Message-only fixes applied after the race** (no model file, no forecast, no
tuning): `score_forecast.py` now prints `n/a` instead of `nan` for an undefined
metric and explains it, and `cli.py`'s `n/a` note now covers both causes of a
flat grid — a race that has not run, and a race that *has* run but whose grid
FastF1 never published, which is what happened here.

---

## 11. Phase 7B: XGBoost Bug and Resolution

### The Bug

XGBoost's original Phase 7B run reported **podium hit 35.5%** vs Ridge's **68.0%**
— a 32.5 pp gap that suggested a fundamental trade-off (MAE wins, hit rates
collapse).

**Root cause:** XGBoost's metric computation used **position-by-position match**
(P1 vs actual P1, P2 vs actual P2, P3 vs actual P3) instead of the
**set-intersection recall** used by Ridge's `_hits()` function:

```python
# Ridge _hits() — correct (set-intersection recall)
pred_top = set(np.argsort(pred)[:k])
act_top = set(np.argsort(act)[:k])
return len(pred_top & act_top) / k

# XGBoost original — BUGGY (position-by-position)
for i in range(k):
    if pred_sorted[i] == act_sorted[i]:
        matches += 1
```

**Effect:** Position-by-position is stricter — it requires the *same driver* to
be in the *same podium position*, whereas recall@3 only asks "is the actual
P1 in predicted top-3?"

### Resolution Timeline

| Date | Event |
|------|-------|
| 2026-11-10 | Phase 7B run: XGBoost MAE=3.238, podium=35.5%, winner=54.9% |
| 2026-11-10 | Phase 7B diagnosis: identified metric discrepancy (Blocker #1, #2) |
| 2026-11-10 | Fixed XGBoost to use set-intersection recall (matching Ridge `_hits()`) |
| 2026-11-10 | Re-run: XGBoost MAE=3.238, podium=68.4%, winner=54.9% |

### Corrected XGBoost Metrics

| Metric | XGBoost (corrected) | Ridge | Δ |
|--------|---------------------|-------|---|
| MAE | 3.2376 | 3.2784 | **−0.0409** (delta of means) |
| Spearman ρ | 0.6715 | 0.6668 | +0.0047 |
| Winner hit | 95/173 = 54.91% | 94/173 = 54.34% | +0.57 pp |
| Podium hit (recall@3) | 355/519 = 68.40% | 353/519 = 68.02% | +0.38 pp |
| Overfit gap | 0.0841 | ~0.08 | — |
| Paired ΔMAE (per-race deltas) | **−0.0372** | — | CI: [−0.065, −0.006] |
| Shuffled-label gap | 1.53 | — | PASS (>1.5) |

**Verdict:** **ACCEPTED** — MAE improvement statistically significant (CI excludes 0),
hit rates match Ridge, no overfitting, shuffled-label passes.

---

## 12. Phase 7C: LightGBM Variants

### Variant C1: `regression_l1` (MAE-native)

| Metric | Value | Threshold | Pass |
|--------|-------|-----------|------|
| MAE | **3.1193** | < 3.278 | ✅ |
| ΔMAE (delta of means) | **−0.1545** | CI excludes 0 | ✅ |
| Podium hit | 67.82% | ≥ 65% | ✅ |
| Winner hit | 51.45% | ≥ 55% | ❌ |
| Overfit gap | **0.5008** | < 0.15 | ❌ |

**Verdict: REJECTED** — severe overfitting (gap 0.501 >> 0.15). LightGBM's
`regression_l1` does not support monotone constraints, so the model memorized
noise. Test MAE 3.12 unreliable for future races.

### Variant C2: `regression` + `metric=mae` (MSE objective)

| Metric | Value | Threshold | Pass |
|--------|-------|-----------|------|
| MAE | **3.2381** | < 3.278 | ✅ |
| ΔMAE (delta of means) | **−0.0403** | CI excludes 0 | ✅ |
| Podium hit | 67.82% | ≥ 65% | ✅ |
| Winner hit | 53.18% (92/173) | ≥ 55% | ❌ |
| Overfit gap | 0.0770 | < 0.15 | ✅ |
| Shuffled-label gap | 1.56 | > 1.5 | ✅ |

**Verdict: NULL** — MAE improvement real (Δ = −0.0403, CI excludes 0) but
**winner hit regression** fails tertiary criterion (92/173 = 53.18% vs Ridge
94/173 = 54.34%, lost 2 races). Not promoted; XGBoost chosen for final model.

### Pre-Registration Threshold Note
The 55% winner hit threshold for LGB C2 was pre-registered but set without
power analysis. With n=173 and baseline winner hit ~54%, the minimum detectable
effect (MDE) is approximately 7.5pp (2×SE where SE=3.78%). The 55% threshold
requires 0pp difference from baseline, which is statistically impossible to
achieve reliably. C2's 53.18% (92/173) is within 1 SE of Ridge's 54.34%
(94/173), meaning C2 vs Ridge winner hit difference is within noise.

Verdict remains NULL per strict pre-registration rules (honoring the process),
but this note documents that the threshold was over-specified. Future
experiments should use power-analysis-based thresholds (e.g., MDE-aware criteria).

This is transparency about process limitation, NOT retroactive verdict change.

---

## 13. Phase 7D: Head-to-Head Consolidation

### Final Ladder

| Model | MAE | ρ | Winner hit | Podium hit | Overfit | Status |
|-------|-----|---|------------|------------|---------|--------|
| Ridge (baseline) | 3.2784 | 0.6668 | 54.34% (94/173) | 68.02% | ~0.08 | Baseline |
| **XGBoost** | **3.2376** | 0.6715 | 54.91% (95/173) | 68.40% | 0.084 | **ACCEPTED** |
| LightGBM C2 | 3.2381 | 0.6708 | 53.18% (92/173) | 67.82% | 0.077 | **NULL** |
| LightGBM C1 | 3.1193 | 0.6683 | 51.45% | 67.82% | 0.501 | **REJECTED** |

### Head-to-Head: XGBoost vs LightGBM C2

- **MAE:** statistically indistinguishable (XGB − LGB = −0.0008, CI: [−0.0097, +0.0082])
- **Winner hit:** XGBoost 95/173 vs LGB 92/173 → **+3 races** for XGBoost
- **Podium hit:** essentially tied (68.40% vs 67.82%)
- **Feature importance correlation:** ρ = 0.9301 (very high consistency)

### Ensemble (50/50)

- Ensemble MAE: 3.2365 vs best single 3.2376 → gain 0.0011
- **Not warranted** — gain smaller than noise floor

### Final Decision

**XGBoost selected as final model** — statistically indistinguishable on MAE,
winner hit advantage (+3 races), monotone constraints supported, mature
ecosystem.

### Note on 2026 Season Tail

Earlier documentation assumed the 2026 season concluded at R20 (São Paulo).
Correction: the 2026 season has **3 remaining races** — R21 Las Vegas (Nov 21),
R22 Qatar (Nov 29), R23 Abu Dhabi (Dec 6). **Phase 7P (Production Validation)** will execute production
forecasts for these 3 races using the selected XGBoost model (phase7-xgboost-1.0).
Previous documentation stating "season complete" or "deferred to 2027" has been
corrected; **Phase 7P** will execute production forecasts for these 3 remaining races.

---

## 14. MODEL_VERSION Update

**2026-11-10:** Bumped `MODEL_VERSION` from `"phase5-ridge-1.0"` to
`"phase7-xgboost-1.0"` in `f1pred/model.py:57`.

**All Phase 7 scripts, reports and diagnostics preserved:**
- `reports/phase7a_linear_diagnostics.*` — linear diagnostics (H0 rejected)
- `reports/phase7b_xgboost.*` — XGBoost evaluation (bug fixed, ACCEPTED)
- `reports/phase7b_diagnosis.*` — 6-test deep dive (blockers resolved)
- `reports/phase7c_lightgbm.*` — LightGBM C1/C2 (C1 REJECTED, C2 NULL)
- `reports/phase7d_final.*` — head-to-head + consolidation (XGBoost selected)
- `f1pred/xgboost_model.py` — XGBoost implementation with fixed metrics
- `f1pred/lightgbm_model.py` — LightGBM implementation
- `f1_backup_20261110_023048_pre_taskC_lightgbm.db` — pre-Phase 7C backup
