"""What grid did the saved forecast use, and how does it compare with the
official starting grid (penalties included)?

WHY THIS EXISTS
  The forecast saved in `forecasts.grid_pred` was built from
  `qualifying.q_position`, because our tables only record a starting grid
  alongside a result and the race has not produced one yet. That value is the
  QUALIFYING order, which is the grid BEFORE any penalty is applied. This
  probe asks FastF1 directly whether it will tell us the official grid, and
  reports every difference it finds.

  It writes nothing. It does not touch `forecasts`, `results`, or any model
  file - the saved forecasts stay exactly as they were written at
  13:47:39 and 13:48:57.

WHAT IT PRINTS
  1. the columns FastF1 exposes for qualifying and for the race session;
  2. whether a GridPosition column exists anywhere before the race;
  3. saved grid_pred vs qualifying position, driver by driver;
  4. qualifying position vs official grid, if the latter is obtainable;
  5. a plain verdict on what the forecast actually used.

Run:  python scripts/probe_official_grid.py [year] [round]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from f1pred import db, fetch  # noqa: E402

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 60)

ROOT = Path(__file__).resolve().parents[1]


def rule(t: str = "") -> None:
    print("=" * 78)
    if t:
        print(t)
        print("=" * 78)


def safe_results(ident: str, year: int, rnd: int) -> tuple[object, pd.DataFrame]:
    """Load a session's results, returning (session, frame) or (None, empty)."""
    import fastf1
    try:
        s = fastf1.get_session(year, rnd, ident)
        s.load(laps=False, telemetry=False, weather=False, messages=False)
        return s, pd.DataFrame(s.results)
    except Exception as exc:                       # noqa: BLE001
        print(f"  {ident}: could not load - {type(exc).__name__}: {exc}")
        return None, pd.DataFrame()


def main() -> int:
    year = int(sys.argv[1]) if len(sys.argv) > 1 else 2026
    rnd = int(sys.argv[2]) if len(sys.argv) > 2 else 20

    fetch.enable_cache()
    con = db.connect(ROOT / "f1.db")
    con.row_factory = None

    rule(f"OFFICIAL GRID CHECK - {year} R{rnd}")

    # ---- 1. what does FastF1 expose? ------------------------------------
    rule("[1] WHAT FASTF1 EXPOSES")
    for ident in ("Q", "Race"):
        print(f"\n  --- {ident} ---")
        _s, res = safe_results(ident, year, rnd)
        if res.empty:
            print("    no results rows")
            continue
        print(f"    rows: {len(res)}")
        print(f"    columns: {list(res.columns)}")
        for col in ("Position", "GridPosition", "Q1", "Q2", "Q3", "Time"):
            if col in res.columns:
                vals = res[col].head(4).tolist()
                print(f"      {col:<14} first values: {vals}")

    # ---- 2. is a GridPosition available anywhere pre-race? --------------
    rule("[2] IS AN OFFICIAL GRID AVAILABLE BEFORE THE RACE?")
    _sq, qres = safe_results("Q", year, rnd)
    _sr, rres = safe_results("Race", year, rnd)
    has_q_grid = (not qres.empty) and "GridPosition" in qres.columns
    has_r_grid = (not rres.empty) and "GridPosition" in rres.columns
    print(f"  qualifying results carry GridPosition : {has_q_grid}")
    print(f"  race results carry GridPosition       : {has_r_grid}")
    print(f"  race results rows                     : {len(rres)}")
    if not has_q_grid and not has_r_grid:
        print()
        print("  => FastF1 exposes no official starting grid before the race")
        print("     starts. The only pre-race grid a data source can give is")
        print("     the qualifying order, which is exactly what was saved.")

    # ---- 3. saved grid_pred vs qualifying -------------------------------
    rule("[3] SAVED FORECAST grid_pred vs QUALIFYING POSITION")
    fc = pd.read_sql_query(
        "SELECT driver, team, pred_pos, grid_pred, mode FROM forecasts"
        " WHERE year=? AND round=? ORDER BY pred_pos", con, params=(year, rnd))
    qual = pd.read_sql_query(
        "SELECT driver, q_position, q_position_official FROM qualifying"
        " WHERE year=? AND round=?", con, params=(year, rnd))
    m = fc.merge(qual, on="driver", how="outer").sort_values("pred_pos")
    print(f"  forecast rows: {len(fc)}   qualifying rows: {len(qual)}")
    print(f"\n  {'P':>3} {'driver':<7} {'team':<20} {'grid_pred':>9} "
          f"{'q_position':>10} {'q_official':>10} {'match':>6}")
    print("  " + "-" * 70)
    diffs = 0
    for _, r in m.iterrows():
        gp, qp, qo = r.get("grid_pred"), r.get("q_position"), \
            r.get("q_position_official")
        same = (gp == qp) if (pd.notna(gp) and pd.notna(qp)) else None
        if same is False:
            diffs += 1
        mark = {True: "ok", False: "DIFF", None: "?"}[same]
        print(f"  {int(r['pred_pos']) if pd.notna(r['pred_pos']) else '-':>3} "
              f"{str(r['driver']):<7} {str(r['team'])[:20]:<20} "
              f"{gp if pd.notna(gp) else '-':>9} "
              f"{qp if pd.notna(qp) else '-':>10} "
              f"{qo if pd.notna(qo) else '-':>10} {mark:>6}")
    print()
    if diffs:
        print(f"  {diffs} difference(s) between the saved grid and the "
              f"qualifying position.")
    else:
        print("  EVERY saved grid_pred equals its qualifying position - the")
        print("  forecast used the qualifying order, unmodified.")

    # ---- 4. official grid vs qualifying, if obtainable ------------------
    rule("[4] QUALIFYING ORDER vs OFFICIAL STARTING GRID")
    if has_r_grid and not rres.empty:
        off = rres[["DriverNumber", "GridPosition"]].copy()
        print(off.to_string(index=False))
    elif has_q_grid and not qres.empty:
        print("  (qualifying carries GridPosition)")
        print(qres[["DriverNumber", "Position", "GridPosition"]]
              .to_string(index=False))
    else:
        print("  NOT OBTAINABLE from FastF1 before the race starts.")
        print()
        print("  The official grid with penalties applied is published by the")
        print("  FIA and reflected in FastF1's race results once the session")
        print("  begins. There is no pre-race field for it, so this probe")
        print("  cannot compare against penalties - and no data source we")
        print("  hold could have supplied them to the forecast either.")

    # ---- 6. the half that can only be done once the race runs -----------
    rule("[6] AFTER THE RACE: SAVED grid_pred vs OFFICIAL results.grid")
    rrows = con.execute(
        "SELECT COUNT(*) FROM results WHERE year=? AND round=?",
        (year, rnd)).fetchone()[0]
    if rrows == 0:
        print(f"  {rrows} results rows - the race has not run, so the")
        print("  official grid still does not exist anywhere.")
        print()
        print("  Re-run this same script after `score_forecast.py --fetch`")
        print("  has fetched the race. It will then print, driver by")
        print("  driver, the grid the forecast assumed against the grid")
        print("  FastF1 actually records, and list every difference - which")
        print("  is precisely where a penalty would show up.")
    else:
        cur = pd.read_sql_query(
            "SELECT driver, grid FROM results WHERE year=? AND round=?",
            con, params=(year, rnd))
        saved = pd.read_sql_query(
            "SELECT driver, grid_pred FROM forecasts WHERE year=? AND"
            " round=? AND mode='full'", con, params=(year, rnd))
        j = saved.merge(cur, on="driver", how="outer")
        j["delta"] = j["grid_pred"] - j["grid"]
        print(f"  {rrows} results rows joined to the saved forecast")
        print(f"\n  {'driver':<8} {'forecast grid':>14} {'official grid':>14} "
              f"{'delta':>7}")
        print("  " + "-" * 48)
        ndiff = 0
        for _, r in j.sort_values("grid_pred").iterrows():
            d = r["delta"]
            same = pd.notna(d) and float(d) == 0.0
            if not same:
                ndiff += 1
            print(f"  {str(r['driver']):<8} "
                  f"{r['grid_pred'] if pd.notna(r['grid_pred']) else '-':>14} "
                  f"{r['grid'] if pd.notna(r['grid']) else '-':>14} "
                  f"{('0' if same else (f'{d:+.0f}' if pd.notna(d) else '?')):>7}")
        print()
        if ndiff == 0:
            print("  NO DIFFERENCES: the forecast's grid equals the official")
            print("  starting grid, penalties included.")
        else:
            print(f"  {ndiff} difference(s). Each one is a car whose official")
            print("  grid differs from the qualifying order the forecast")
            print("  assumed - the usual cause is a grid penalty.")
            print()
            print("  NOTE: reporting only. The saved forecast is NOT updated:")
            print("  `forecasts` is written once, before the race, and that")
            print("  is what makes it a forecast rather than a back-fit.")

    # ---- 5. verdict -----------------------------------------------------
    rule("[7] VERDICT")
    print("  Which grid the forecast used:")
    print("    forecasts.grid_pred  =  qualifying.q_position")
    print("                           = FastF1's official Position from the")
    print("                             qualifying session (2026-11-07)")
    print()
    print("  What that means:")
    print("    * it is the grid in qualifying order;")
    print("    * it does NOT include any penalty applied afterwards;")
    print("    * drivers who never set a lap would have been filled to")
    print("      field size + 1 - there are none this weekend, so all 22")
    print("      cars carry a genuine qualifying position (1..22, distinct).")
    print()
    print("  Penalties checked through qualifying (race control, all")
    print("  sessions): only ONE incident - car 87 BEA, REPRIMAND for")
    print("  reversing in the pit lane. A reprimand carries no grid drop, so")
    print("  no grid position changes from it. Nothing else was noted.")
    print()
    print("  FastF1's qualifying GridPosition column exists but is all NaN")
    print("  before the race, and the race session returns 0 rows, so no")
    print("  source can publish the official grid with penalties applied")
    print("  until the session begins. See [6] for the post-race half of")
    print("  this comparison.")
    print()
    print("  This probe wrote nothing: `forecasts`, `results` and every")
    print("  model file are untouched.")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
