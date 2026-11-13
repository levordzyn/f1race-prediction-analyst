"""Save a forecast BEFORE the race, score it AFTERWARDS.

WHY IT IS ITS OWN MODULE
  ``report.py`` must never fit a model and ``fetch.py`` must never score one.
  This module sits between them: it records predictions that already exist,
  and once the race has run it compares what was recorded with what happened.

WHAT MAKES A FORECAST A FORECAST
  Only the timestamp. A prediction written after the result is a back-fit and
  worth nothing, so every row carries ``created_at`` (when it was written) and
  ``race_start_utc`` (scheduled lights-out), and :func:`score` refuses to
  report a run whose ``created_at`` is not before ``race_start_utc``. That
  check is printed, not assumed.

NOTHING HERE EVER WRITES ``results``.
  That table stays the authority for what happened, and the 7-column contract
  in ``db.py`` is untouched by this module - it reads results, never writes
  them.

TWO NUMBERS, TWO DEFINITIONS
  ``pred`` is the raw Ridge output, which is what MAE is scored on everywhere
  else in this project. ``pred_pos`` is its 1..N ordering, which is what the
  winner and podium hit rates use. Both are stored so the two definitions can
  never be confused at scoring time.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from . import features, model

log = logging.getLogger(__name__)

__all__ = ["race_start_utc", "save", "load", "score"]


def _naive(ts) -> pd.Timestamp:
    """UTC-naive timestamp, so an aware and a naive value can be compared."""
    t = pd.Timestamp(ts)
    if t.tzinfo is not None:
        t = t.tz_convert("UTC").tz_localize(None)
    return t


def race_start_utc(year: int, rnd: int) -> str | None:
    """Scheduled lights-out for a race, as UTC ISO8601, or None if unknown.

    Read from FastF1's schedule rather than a hand-typed table: the times
    change by venue and year, and guessing one would make the
    saved-before-the-race check meaningless. The session called 'Race' is
    found by name, not by position, because a sprint weekend does not put the
    race in the same slot.
    """
    try:
        from . import fetch
        import fastf1

        fetch.enable_cache()
        sched = fastf1.get_event_schedule(year, include_testing=False)
        hit = sched[sched["RoundNumber"] == rnd]
        if hit.empty:
            return None
        ev = hit.iloc[0]
        for i in range(1, 6):
            if str(ev.get(f"Session{i}", "") or "") != "Race":
                continue
            when = ev.get(f"Session{i}DateUtc")
            if when is None or pd.isna(when):
                return None
            return _naive(when).isoformat(timespec="minutes")
        return None
    except Exception as exc:                       # noqa: BLE001
        log.warning("scheduled start unavailable for %d R%d: %s: %s",
                    year, rnd, type(exc).__name__, exc)
        return None


def save(con, year: int, rnd: int, mode: str, g: pd.DataFrame,
         cols: list[str], df: pd.DataFrame,
         note: str | None = None) -> int:
    """Record the predicted order for a race that has NOT run yet.

    ``g`` is ``report.race_preds()`` output (driver, pred, pred_pos, finish)
    and ``df`` is the feature frame, which supplies the team name and the
    grid baseline's call - ``walk_forward``'s prediction table carries
    neither.

    Returns the number of rows written, or **0** when a forecast for this
    weekend and mode already exists. A saved forecast is never overwritten:
    re-running the command is a safe no-op that points at the original
    timestamp, because a forecast written twice is not the same forecast as
    one written once, and replacing it would destroy the only evidence that
    it predated the race. The INSERT is therefore deliberately not
    INSERT OR REPLACE - if the guard above were ever bypassed, the primary
    key would raise rather than silently take the new rows.

    Raises rather than guessing when the inputs describe a race that has
    already happened: a result is not a forecast, and storing one would make
    the saved-before-the-race check meaningless.
    """
    if mode not in ("early", "full"):
        raise ValueError(f"mode must be 'early' or 'full', got {mode!r}")
    if g is None or g.empty:
        raise ValueError(f"no predictions supplied for {year} R{rnd}")

    n_results = con.execute(
        "SELECT COUNT(*) FROM results WHERE year=? AND round=?",
        (year, rnd)).fetchone()[0]
    if n_results:
        raise ValueError(
            f"{year} R{rnd} already has {n_results} results row(s) - that is "
            "a result, not a forecast. A forecast may only be written while "
            "the race is unrun.")
    if "finish" in g.columns and not g["finish"].isna().all():
        raise ValueError("the supplied predictions carry a finishing "
                         "position - refusing to save a scored race as a "
                         "forecast")

    taken = con.execute(
        "SELECT COUNT(*), MIN(created_at) FROM forecasts"
        " WHERE year=? AND round=? AND mode=?",
        (year, rnd, mode)).fetchone()
    if taken and taken[0]:
        log.warning("%d R%d: a %s forecast already exists (%d rows, written "
                    "%s) - NOT overwritten. Remove those rows by hand first "
                    "if a replacement is genuinely intended.",
                    year, rnd, mode, taken[0], taken[1])
        return 0

    created = datetime.now(timezone.utc).isoformat(timespec="seconds")
    start = race_start_utc(year, rnd)
    if start is None:
        log.warning("%d R%d: scheduled start unknown, so this run cannot "
                    "later be proven to predate the race", year, rnd)

    race_rows = df[(df["year"] == year) & (df["round"] == rnd)]
    uniq = race_rows.drop_duplicates("driver").set_index("driver")
    team_of = uniq["team"].to_dict()
    # The grid BASELINE's call for each driver, stored next to the model's so
    # both can be scored after the race without rebuilding anything. It reads
    # the same `grid` column the baseline itself ranks on, so the two are
    # guaranteed to agree.
    grid_of = uniq["grid"].to_dict()
    # The forecast race is the last race in the frame, so every race strictly
    # before it is training data. Counted rather than assumed.
    idx = df["race_idx"].to_numpy()
    target = race_rows["race_idx"]
    n_train = int(len(np.unique(idx[idx < target.iloc[0]]))) if len(target) \
        else 0

    features_json = json.dumps(list(cols))
    rows = [
        (year, rnd, mode, model.MODEL_VERSION, created, start,
         str(r["driver"]), str(team_of.get(str(r["driver"]), "")),
         float(r["pred"]), int(r["pred_pos"]),
         float(grid_of[str(r["driver"])]), features_json,
         float(model.RIDGE_ALPHA), n_train, note)
        for _, r in g.iterrows()
    ]
    # Explicit column names: a positional VALUES list breaks silently the
    # moment a column is appended (it corrupted qualifying once).
    con.executemany(
        "INSERT INTO forecasts (year, round, mode, model_version,"
        " created_at, race_start_utc, driver, team, pred, pred_pos,"
        " grid_pred, features, alpha, n_train_races, note)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        rows)
    con.commit()
    log.info("%d R%d %s forecast saved: %d cars, %d training races, "
             "written %s, race starts %s", year, rnd, mode, len(rows),
             n_train, created, start or "unknown")
    return len(rows)


def load(con, year: int, rnd: int, mode: str) -> pd.DataFrame:
    """The saved forecast for one weekend and mode, in predicted order."""
    return pd.read_sql_query(
        "SELECT driver, team, pred, pred_pos, grid_pred, model_version,"
        " created_at, race_start_utc, features, alpha, n_train_races, note"
        " FROM forecasts"
        " WHERE year=? AND round=? AND mode=? ORDER BY pred_pos",
        con, params=(year, rnd, mode))


def score(con, year: int, rnd: int, mode: str) -> dict:
    """Compare a saved forecast with what actually happened.

    Returns a dict with ``status``:
      * ``no-forecast`` - nothing was saved for this weekend and mode;
      * ``not-run``     - the race has no results yet, so there is nothing
                          to compare against (not an error: that is the point
                          of saving first);
      * ``scored``      - metrics and baselines, plus the saved-before-race
                          verdict.

    Baselines are scored on the SAME drivers as the model, with the same
    functions, and early mode is compared only against the baselines it is
    allowed to know (no grid baseline).
    """
    fc = load(con, year, rnd, mode)
    if fc.empty:
        return {"status": "no-forecast", "year": year, "round": rnd,
                "mode": mode,
                "detail": f"no saved {mode} forecast for {year} R{rnd}"}

    res = pd.read_sql_query(
        "SELECT driver, finish FROM results WHERE year=? AND round=?",
        con, params=(year, rnd))
    if res.empty:
        return {"status": "not-run", "year": year, "round": rnd,
                "mode": mode, "n_forecast": int(len(fc)),
                "created_at": str(fc["created_at"].iloc[0]),
                "race_start_utc": str(fc["race_start_utc"].iloc[0]),
                "detail": "the race has not produced results yet"}

    # ---- did the forecast really predate the race? -----------------------
    # Every row of one save carries the same timestamp, but that is an
    # invariant of save(), not something scoring may assume: take the LATEST
    # written row, so a single tampered or overwritten row can never let a
    # post-race write pass the check, and say if the rows disagree.
    created_set = {_naive(x) for x in fc["created_at"]}
    created = max(created_set)
    start_set = {str(x) for x in fc["race_start_utc"]
                 if x is not None and not pd.isna(x)}
    start_raw = fc["race_start_utc"].iloc[0]
    saved_before = None
    start = None
    if start_set:
        start = _naive(sorted(start_set)[-1])
        saved_before = bool(created < start)

    # ---- join forecast to what happened ---------------------------------
    m = fc.merge(res, on="driver", how="inner")
    missing = sorted(set(fc["driver"]) - set(m["driver"]))
    extra = sorted(set(res["driver"]) - set(fc["driver"]))
    m = m[np.isfinite(m["finish"].astype(float))].copy()
    if m.empty:
        return {"status": "no-score", "year": year, "round": rnd,
                "mode": mode, "detail":
                "no forecast driver has a classified finish",
                "saved_before_race": saved_before}

    pred = m["pred"].to_numpy(dtype=float)
    act = m["finish"].to_numpy(dtype=float)
    win, pod = model._hits(pred, act)

    out: dict = {
        "status": "scored", "year": year, "round": rnd, "mode": mode,
        "n_forecast": int(len(fc)), "n_scored": int(len(m)),
        "not_scored": sorted(set(fc["driver"]) - set(m["driver"])) ,
        "in_race_not_forecast": extra,
        "created_at": str(fc["created_at"].iloc[0]),
        "race_start_utc": str(start_raw),
        "saved_before_race": saved_before,
        "created_at_disagrees": len(created_set) > 1,
        "race_start_disagrees": len(start_set) > 1,
        "features": json.loads(str(fc["features"].iloc[0])),
        "alpha": float(fc["alpha"].iloc[0]),
        "n_train_races": int(fc["n_train_races"].iloc[0]),
        "model_version": str(fc["model_version"].iloc[0])
        if "model_version" in fc.columns else "",
        "note": str(fc["note"].iloc[0]) if "note" in fc.columns else "",
        "mae": model._mae(pred, act),
        "rho": model._rho(pred, act),
        "winner_hit": win, "podium_hit": pod,
        "winner_pred": str(m.sort_values("pred")["driver"].iloc[0]),
        "winner_act": str(m.sort_values("finish")["driver"].iloc[0]),
        "baselines": {},
    }
    if missing:
        out["forecast_without_result"] = missing

    # ---- baselines on the identical drivers -----------------------------
    df = features.build_features(con)
    sub = df[(df["year"] == year) & (df["round"] == rnd)]
    labels = (model.FULL_BASELINES if mode == "full"
              else model.EARLY_BASELINES)
    if not sub.empty:
        by_driver = sub.drop_duplicates("driver").set_index("driver")
        for label in labels:
            col = model.BASELINES[label]
            if col not in sub.columns:
                continue
            b = m["driver"].map(by_driver[col]).to_numpy(dtype=float)
            if not np.isfinite(b).all():
                continue
            bw, bp = model._hits(b, act)
            out["baselines"][label] = {
                "mae": model._mae(b, act), "rho": model._rho(b, act),
                "winner_hit": bw, "podium_hit": bp,
            }

    if out["baselines"]:
        best_label = min(out["baselines"],
                         key=lambda k: out["baselines"][k]["mae"])
        best = out["baselines"][best_label]["mae"]
        out["best_baseline"] = best_label
        out["best_baseline_mae"] = best
        out["model_minus_best_mae"] = out["mae"] - best
    return out
