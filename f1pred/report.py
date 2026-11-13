"""Console and PNG reports for Phase 4.

Every number here is derived from ``model.walk_forward`` output - the
per-race metrics, the held-out predictions and the fold-averaged
coefficients. Nothing in this module fits a model, so no report can silently
invent a prediction that walk-forward validation did not produce.

Outputs (spec line 89, detail in lines 49-51):
  * top-3 predicted finishers printed with medals;
  * the full predicted-order table;
  * winner hit rate, podium hit rate, and the rank the model gave the
    ACTUAL winner (spec line 78);
  * gap-vs-prediction scatter, inverted y-axis, every point labelled with
    the driver code, saved as PNG;
  * horizontal Ridge coefficient chart with the title and x-axis label the
    spec asks for, saved as PNG.

WHY THE SCATTER DROPS CARS
--------------------------
``q_gap_pct`` is filled with 0.0 when qualifying time is missing and flagged
by ``no_q_time``. Plotting those would place a car at x=0 as though it had
the smallest gap of all, which is exactly backwards. They are excluded from
the plot and counted in a note instead.
"""
from __future__ import annotations

import textwrap
from pathlib import Path

import matplotlib

matplotlib.use("Agg")            # headless: no display needed, saves reliably
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np               # noqa: E402
import pandas as pd              # noqa: E402

from .model import PODIUM_DEF, WINNER_DEF   # definition and number cannot drift

REPORT_DIR = Path("reports")

MEDALS = {1: "\U0001f947", 2: "\U0001f948", 3: "\U0001f949"}   # gold silver bronze


def _rule(title: str = "") -> None:
    print("=" * 78)
    if title:
        print(title)
        print("=" * 78)


def race_preds(preds: pd.DataFrame, year: int, rnd: int) -> pd.DataFrame:
    """Walk-forward predictions for one race, ordered by predicted position."""
    g = preds[(preds["year"] == year) & (preds["round"] == rnd)].copy()
    if g.empty:
        raise ValueError(
            f"no walk-forward predictions for {year} R{rnd}. Validation starts "
            f"after the first 20 races, so early races have no predictions.")
    g["pred_pos"] = g["pred"].rank(method="first", ascending=True).astype(int)
    return g.sort_values("pred_pos").reset_index(drop=True)


# ------------------------------------------------------------------ console
def top3_printout(g: pd.DataFrame, year: int, rnd: int) -> None:
    """Medal printout of the three drivers the model expects on the podium."""
    _rule(f"PREDICTED TOP 3 - {year} R{rnd} (walk-forward)")
    # A forecast race has no result at all: every finish is NULL, so there is
    # deliberately nothing to compare against rather than something wrong.
    has_actual = bool(np.isfinite(g["finish"]).all())
    for i in range(min(3, len(g))):
        row = g.iloc[i]
        medal = MEDALS.get(i + 1, " ")
        if not has_actual:
            print(f"  {medal} {row['driver']:<5} predicted P{row['pred_pos']:<2}"
                  f"   actual P-  (not run yet)")
            continue
        actual = int(row["finish"])
        marker = " <= ACTUAL WINNER" if actual == 1 else ""
        err = abs(int(row["pred_pos"]) - actual)
        print(f"  {medal} {row['driver']:<5} predicted P{row['pred_pos']:<2}"
              f"   actual P{actual:<2}  off by {err}{marker}")
    print()
    if has_actual:
        print(f"  'predicted P#' is the model's ordering of this race's "
              f"{len(g)} cars;")
        print("  'actual P#' is where they really finished.")
    else:
        print("  TRUE FORECAST - this race has not been run, so there is no")
        print("  'actual P#' and none of these numbers are scored.")
    print()


def order_table(g: pd.DataFrame, year: int, rnd: int) -> None:
    """Full predicted finishing order next to what actually happened."""
    _rule(f"PREDICTED ORDER TABLE - {year} R{rnd}")
    has_actual = bool(np.isfinite(g["finish"]).all())
    print(f"  {'#':>3}  {'driver':<6} {'predicted':>10} {'actual':>7} "
          f"{'error':>6}   note")
    print(f"  {'-'*3}  {'-'*6} {'-'*10} {'-'*7} {'-'*6}   {'-'*34}")
    for _, row in g.iterrows():
        p = int(row["pred_pos"])
        if not has_actual:
            # int(nan) would raise; there is simply no result to show.
            print(f"  {p:>3}  {row['driver']:<6} {p:>10} {'-':>7} {'-':>6}   "
                  f"forecast - race not run yet")
            continue
        a = int(row["finish"])
        err = p - a
        notes = []
        if a == 1:
            notes.append("ACTUAL WINNER")
        if p == 1 and a != 1:
            notes.append("model's pick to win")
        if p <= 3 and a > 3:
            notes.append("predicted podium, missed")
        if a <= 3 and p > 3:
            notes.append("podium not predicted")
        print(f"  {p:>3}  {row['driver']:<6} {p:>10} {a:>7} {err:>+6}   "
              f"{', '.join(notes)}")
    print()
    if not has_actual:
        print("  No result exists for this race yet, so there is no error")
        print("  column and nothing here is scored.")
        return
    print(f"  {'rank the model gave the actual winner:'}", end=" ")
    winner = g[g["finish"] == 1]
    if len(winner) == 1:
        print(f"P{int(winner['pred_pos'].iloc[0])}")
    else:
        print("not found in this race")


def hit_rates(wf: dict, baselines: dict | None = None) -> None:
    """Winner / podium hit rates: definitions, baselines, season split.

    Spec line 78 requires winner hit rate, podium hit rate, the rank given to
    the actual winner and a small-sample warning. The ML rules (line 76)
    additionally require baselines next to the model, so the three ranking
    baselines are scored here with the SAME _hits() code on the SAME races.
    """
    pr = wf["per_race"]
    n_rows = int(pr["n"].sum())
    n_races = int(len(pr))

    # --------------------------------------------------------- definitions
    _rule("WINNER / PODIUM HIT RATES - EXACT DEFINITIONS")
    print(textwrap.fill(WINNER_DEF, width=74, initial_indent="  ",
                        subsequent_indent="  "))
    print()
    print(textwrap.fill(PODIUM_DEF, width=74, initial_indent="  ",
                        subsequent_indent="  "))

    # ---------------------------------------------------------- headline
    model_wr = float(pr["winner_hit"].mean())
    model_pr = float(pr["podium_hit"].mean())
    _rule(f"HEADLINE - {n_races} validation races, {n_rows} driver rows")
    print(f"  model winner hit rate : {model_wr:6.1%}")
    print(f"  model podium hit rate : {model_pr:6.1%}")
    print()
    print(f"  WARNING - small sample. One lucky or unlucky race moves either")
    print(f"  number by {100 / n_races:.1f} percentage points.")
    field = int(wf["preds"].groupby(["year", "round"]).size().max())
    print(f"  Blind floors for a {field}-car field: winner 1/{field} = "
          f"{1 / field:.1%}, podium {3}/{field} = {3 / field:.1%}.")

    if not baselines:
        print()
        print("  (no baselines supplied to this report)")
        return

    # --------------------------------------------------- baseline table
    _rule("MODEL vs RANKING BASELINES - IDENTICAL RACES, IDENTICAL METRIC")
    print(f"  {'winner':<40} {'winner':>9} {'podium':>9}")
    print(f"  {'name':<40} {'hit':>9} {'hit':>9}")
    print(f"  {'-' * 40} {'-' * 9} {'-' * 9}")
    print(f"  {'MODEL (ridge, walk-forward)':<40} {model_wr:>9.1%} "
          f"{model_pr:>9.1%}")
    for label, b in baselines.items():
        print(f"  {label:<40} {b['winner_hit']:>9.1%} "
              f"{b['podium_hit']:>9.1%}")

    best_wr = max(b["winner_hit"] for b in baselines.values())
    best_pr = max(b["podium_hit"] for b in baselines.values())
    print(f"  {'-' * 40} {'-' * 9} {'-' * 9}")
    print(f"  {'best BASELINE':<40} {best_wr:>9.1%} {best_pr:>9.1%}")

    d_wr, d_pr = model_wr - best_wr, model_pr - best_pr
    print(f"  {'MODEL - best BASELINE  (pp)':<40} {d_wr * 100:>+9.1f} "
          f"{d_pr * 100:>+9.1f}")

    def _rel(model: float, best: float) -> str:
        return "n/a (best = 0)" if best == 0 else f"{(model - best) / best:+.1%}"

    print(f"  {'relative improvement':<40} {_rel(model_wr, best_wr):>9} "
          f"{_rel(model_pr, best_pr):>9}")
    print()
    print(textwrap.fill(
        "formula:  improvement (pp) = model hit rate - max(baseline hit "
        "rates);  relative = (model - best) / best.  'best' is taken "
        "separately per column, i.e. the strongest competitor for that "
        "metric - the hardest bar to clear and therefore the honest one.",
        width=74, initial_indent="  ", subsequent_indent="  "))
    print()
    print(textwrap.fill(
        "pole-sitter and best-qualifying-gap are different baselines: a "
        "penalty can put the pole sitter somewhere other than the fastest "
        "qualifier. Best qualifying gap ignores cars flagged no_q_time, "
        "whose gap is filled with 0.0 for the model and would otherwise "
        "rank as fastest having set no lap at all.",
        width=74, initial_indent="  ", subsequent_indent="  "))

    # ------------------------------------------------------ season split
    years = sorted(int(y) for y in pr["year"].unique())
    for metric, label in (("winner_hit", "WINNER HIT RATE"),
                          ("podium_hit", "PODIUM HIT RATE")):
        print()
        _rule(f"BY SEASON - {label}  (tiny per-season samples)")
        hdr = (f"  {'season':<8} {'races':>6} {'model':>8}"
               f"  {'pole-sitter':>12} {'best q-gap':>11} {'best form':>10}"
               f"  {'best base':>10} {'model-best':>11}")
        print(hdr)
        print("  " + "-" * (len(hdr) - 2))
        for y in years:
            m = pr[pr["year"] == y]
            mm = float(m[metric].mean())
            # fixed order so the columns line up whatever the caller passed
            order = ["pole-sitter wins", "best qualifying gap wins",
                     "best driver form wins"]
            cells = []
            vals = []
            for lb in order:
                if lb not in baselines:
                    cells.append(f"{'-':>12}")
                    vals.append(float("nan"))
                    continue
                s = baselines[lb]["per_race"]
                sub = s[s["year"] == y]
                v = float(sub[metric].mean()) if len(sub) else float("nan")
                vals.append(v)
                cells.append(f"{v:>12.1%}")
            best = float(np.nanmax(vals)) if vals else float("nan")
            diff = mm - best
            print(f"  {y:<8} {len(m):>6} {mm:>8.1%}  {cells[0]} {cells[1]} "
                  f"{cells[2]}  {best:>10.1%} {diff * 100:>+10.1f} pp")
        print()
        print(f"  Each season is far too small to read on its own - "
              f"{min(len(pr[pr['year'] == y]) for y in years)}-race seasons")
        print(f"  swing by {100 / max(1, min(len(pr[pr['year'] == y]) for y in years)):.0f} "
              f"pp on a single result. Use the season split to spot a")
        print("  trend, not to judge skill.")

    # ------------------------------------------------- rank given to winner
    preds = wf["preds"]
    winner_ranks = []
    for (_y, _r), grp in preds.groupby(["year", "round"]):
        w = grp[grp["finish"] == 1]
        if len(w) != 1:
            continue
        ranked = grp["pred"].rank(method="min", ascending=True)
        winner_ranks.append(int(ranked.loc[w.index[0]]))
    wr = np.array(winner_ranks, dtype=float)

    print()
    _rule("RANK THE MODEL GAVE THE ACTUAL WINNER (spec line 78)")
    print(f"  mean {wr.mean():.2f}    median {np.median(wr):.1f}    "
          f"worst {int(wr.max())}")
    hist = pd.Series(wr.astype(int)).value_counts().sort_index()
    for rank, cnt in hist.items():
        print(f"    P{rank:<2} {cnt:>2} races {'#' * int(cnt)}")
    print()
    print("  Reading it: if the model usually ranks the real winner in the")
    print("  top 5, it identifies the likely winner's group even when it")
    print("  does not call the exact car.")


# ------------------------------------------------- permutation importance
def permutation_table(pi: pd.DataFrame, mode_label: str = "full") -> None:
    """Print grouped permutation importance as a walk-forward MAE increase."""
    _rule(f"GROUPED PERMUTATION IMPORTANCE ({mode_label} mode)")
    print(textwrap.fill(
        "Shuffling a group's values WITHIN each validation race destroys what "
        "that group knows about the drivers while leaving the race's "
        "distribution untouched. Whatever MAE rises by is how much the model "
        "actually relied on that block. Unlike Ridge coefficients this does "
        "not inspect a weight, so collinearity cannot flip a sign: two "
        "correlated groups share the loss, which is the honest answer.",
        width=74, initial_indent="  ", subsequent_indent="  "))
    print()
    print(f"  {'group':<12} {'feats':>5} {'MAE base':>9} {'MAE shuffled':>13} "
          f"{'increase':>9} {'%':>7} {'folds helped':>13}")
    print(f"  {'-' * 12} {'-' * 5} {'-' * 9} {'-' * 13} {'-' * 9} {'-' * 7} "
          f"{'-' * 13}")
    for _, r in pi.iterrows():
        print(f"  {r['group']:<12} {int(r['n_features']):>5} "
              f"{r['mae_base']:>9.3f} {r['mae_perm']:>13.3f} "
              f"{r['delta']:>+9.3f} {r['pct_increase']:>+6.1f}% "
              f"{int(r['folds_helped']):>7}/{int(r['n_folds'])}")
    print()
    print(f"  Repeats per fold: {int(pi['n_repeats'].iloc[0])}, seed fixed, "
          f"so the table is reproducible.")
    print(f"  'folds helped' counts validation races where shuffling this "
          f"group made")
    print(f"  MAE worse - far more informative than the mean alone if it is "
          f"close to half.")


# --------------------------------------------------------------------- plots
def gap_scatter(g: pd.DataFrame, features: pd.DataFrame, year: int, rnd: int,
                out_dir: Path = REPORT_DIR, x_col: str = "q_gap_pct",
                missing_col: str = "no_q_time",
                x_label: str = "qualifying gap to fastest lap (%)") -> Path:
    """x = a pre-race pace gap (%), y = predicted finish (inverted).

    `x_col`/`missing_col`/`x_label` switch the axis to practice, because early
    mode has no qualifying to plot. Cars whose value is a missing-fill
    (`missing_col` == 1) are dropped: for q_gap_pct that fill is 0.0, which
    would put a driver who set NO lap at the very front of the chart.
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    if x_col not in features.columns:
        raise KeyError(f"gap_scatter: column {x_col!r} not in features")

    cols = ["year", "round", "driver", x_col] + (
        [missing_col] if missing_col in features.columns else [])
    extra = features[[c for c in cols if c in features.columns]]
    m = g.merge(extra, on=["year", "round", "driver"], how="left")

    has_flag = missing_col in m.columns
    missing = int((m[missing_col] == 1).sum()) if has_flag else 0
    plottable = m[m[missing_col] != 1].copy() if has_flag else m.copy()

    # A forecast race has no result, so every finish is NULL: int(nan) raises,
    # so the axis is sized from the predictions alone in that case.
    actual = m[m["finish"].notna()]
    top = int(max(m["pred_pos"].max(),
                  actual["finish"].max() if len(actual) else 0))

    fig, ax = plt.subplots(figsize=(9, 7))
    ax.scatter(plottable[x_col], plottable["pred_pos"],
               s=70, c="#1f77b4", edgecolors="white", zorder=3)
    for _, row in plottable.iterrows():
        # The axis is inverted (P1 at the top), so the bottom of the chart is
        # the BACK of the field. Drawing every label below its point puts a
        # rear-ward car's code past the axis edge - BOR was being clipped -
        # so those few flip above instead.
        near_back = row["pred_pos"] > top - 3
        ax.annotate(str(row["driver"]),
                    xy=(row[x_col], row["pred_pos"]),
                    xytext=(5, 10 if near_back else -10),
                    textcoords="offset points",
                    fontsize=8, zorder=4)

    # the actual finishing order, so the reader can see agreement/disagreement;
    # skipped entirely for a forecast race, where there is none yet
    if len(actual):
        ax.scatter(actual[x_col], actual["finish"], s=28, c="#999999",
                   marker="x", zorder=2, label="actual finish")

    ax.set_ylim(top + 0.5, 0.5)          # inverted: P1 at the top
    ax.set_xlim(left=0)
    pace = "practice" if x_col.startswith("practice") else "qualifying"
    ax.set_xlabel(x_label)
    ax.set_ylabel("predicted finishing position")
    ax.set_title(f"{year} R{rnd} - {pace} gap vs predicted finish")
    ax.grid(alpha=0.3, zorder=0)
    # upper right: slow-but-quickly-predicted cars are rare, so it stays clear
    # on both the qualifying and practice charts; lower right collided with
    # the rear-of-field labels. Only drawn when there is a labelled artist -
    # a forecast race has no "actual finish" series and matplotlib warns.
    if len(actual):
        ax.legend(loc="upper right", fontsize=8)

    missing_txt = f"; {missing} excluded (no {pace} time)" if missing else ""
    if not len(actual):
        missing_txt += "; race not run yet, no actual finish to plot"
    note = f"{len(plottable)} cars plotted{missing_txt}"
    ax.text(0.01, 0.01, note, transform=ax.transAxes, fontsize=8,
            verticalalignment="bottom")

    fig.tight_layout()
    path = out_dir / f"gap_vs_prediction_{year}_r{rnd}_{pace}.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def coefficient_chart(coef_mean: dict[str, float], out_dir: Path = REPORT_DIR,
                      year: int | None = None, rnd: int | None = None) -> Path:
    """Horizontal bar chart of standardized Ridge coefficients.

    Title and x-axis label are the exact strings the spec asks for (line 51)
    and are left untouched. The chart's KNOWN DEFECT - that these weights are
    collinearity-affected - is added as a footnote instead, so a reader cannot
    take the bars at face value.
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    items = sorted(coef_mean.items(), key=lambda kv: kv[1], reverse=True)
    labels = [k for k, _ in items]
    values = [v for _, v in items]

    fig, ax = plt.subplots(figsize=(9, 6.5))
    colours = ["#d62728" if v > 0 else "#2ca02c" for v in values]
    ax.barh(labels, values, color=colours)
    ax.invert_yaxis()                    # largest positive at the top
    ax.axvline(0, color="black", lw=0.8)
    ax.set_title("ridge feature coefficients (positive = worse finish)")
    ax.set_xlabel("predicted finish change per feature standard deviation "
                  "(positions)")
    ax.set_ylabel("feature")
    ax.grid(axis="x", alpha=0.3)

    # Spec line 51 fixes the title and x-axis text, so the caveat is a
    # footnote rather than an edit to those strings.
    fig.text(0.5, 0.012,
             "COLLINEARITY-AFFECTED - do not read individual bars as effects.\n"
             "Where two features carry the same information (q_position vs "
             "q_gap_pct, practice_pos vs practice_gap_pct,\n"
             "driver_form vs non_finish_rate) Ridge splits the shared weight "
             "and the smaller bar can flip sign.",
             ha="center", va="bottom", fontsize=7.5, color="#b22222")

    fig.tight_layout(rect=(0, 0.075, 1, 1))
    path = out_dir / ("ridge_coefficients.png" if not year
                      else f"ridge_coefficients_{year}_r{rnd}.png")
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path
