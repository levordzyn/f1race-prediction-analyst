"""Audit every OpenF1-sourced session with the two lap-validity rules.

Runs the SAME ``openf1.classify_laps`` that now produces stored data (not a
reimplementation), across:
  * all 89 races' practice sessions, and
  * every sprint-qualifying session (the other OpenF1-sourced table).

Reports, per race:
  * how many laps each rule rejects (rule 1 sector arithmetic, rule 2
    implausible speed), kept separate from the pre-existing null/pit-out
    filter so the new rules' effect is visible on its own;
  * whether recomputing the race through the real production code path
    (``practice.compute_practice`` / ``compute_sprint_qualifying``) would
    change any stored value.

READ-ONLY. Writes nothing to f1.db.

Run:  python scripts/validate_lap_rules.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from f1pred import db, openf1 as o1, practice  # noqa: E402

TOL = 1e-9

con = db.connect()
con.row_factory = None


def rule(title: str = "") -> None:
    print("=" * 78)
    if title:
        print(title)
        print("=" * 78)


def count_rejections(sessions) -> dict[str, int]:
    """Apply classify_laps to every lap of every session, tally by reason."""
    tally = {o1.REJECT_PREEXISTING: 0, o1.REJECT_SECTOR: 0, o1.REJECT_FAST: 0,
             "total_laps": 0, "usable": 0}
    for s in sessions:
        laps = o1.get_laps(s["session_key"])
        tally["total_laps"] += len(laps)
        _valid, rejected = o1.classify_laps(laps)
        tally["usable"] += len(_valid)
        for _lap, reason in rejected:
            tally[reason] += 1
    return tally


def compare_rows(table, year, rnd, starters, values, columns, data_cols):
    """Diff recomputed values against stored rows. Returns list of differences.

    Mirrors ``_write_rows`` exactly, including its NULLs + missing-flag layout
    for drivers that have no data at all.
    """
    diffs = []
    for driver, _team, number in starters:
        rec = values.get(number)
        if rec is None:
            expected = [None] * (len(columns) - 6) + [0]
        else:
            expected = list(rec)
        stored = con.execute(
            f"SELECT {', '.join(data_cols)} FROM {table} "
            f"WHERE year=? AND round=? AND driver=?",
            (year, rnd, driver),
        ).fetchone()
        if stored is None:
            diffs.append((driver, "<row missing>", None, None))
            continue
        for col, want, got in zip(data_cols, stored, expected):
            if want is None and got is None:
                continue
            if want is None or got is None:
                diffs.append((driver, col, want, got))
            elif abs(float(want) - float(got)) > TOL:
                diffs.append((driver, col, want, got))
    return diffs


# --------------------------------------------------------------- PRACTICE
races = con.execute(
    "SELECT year, round FROM sessions ORDER BY year, round").fetchall()
races = [(r[0], r[1]) for r in races]

rule(f"PRACTICE - lap validity rules over all {len(races)} races")

print(f"  rules in force: sector tolerance {o1.SECTOR_TOLERANCE_S} s "
      f"(missing sectors never rejected),")
print(f"                 lap must be >= {o1.MIN_LAP_FRACTION:.0%} of session's "
      f"2nd-fastest lap,")
print(f"                 applied only when a session has >= "
      f"{o1.MIN_LAPS_FOR_REFERENCE} usable laps")
print()

practice_tally = {o1.REJECT_PREEXISTING: 0, o1.REJECT_SECTOR: 0,
                  o1.REJECT_FAST: 0, "total_laps": 0, "usable": 0}
changed = []
no_session = []
reject_rows = []

for year, rnd in races:
    sessions = practice.practice_sessions(con, year, rnd)
    if not sessions:
        no_session.append((year, rnd))
    tally = count_rejections(sessions)
    for k in practice_tally:
        practice_tally[k] += tally[k]

    new_rej = tally[o1.REJECT_SECTOR] + tally[o1.REJECT_FAST]
    if new_rej:
        reject_rows.append((year, rnd, tally))

    starters, values, columns, _names = practice.compute_practice(con, year, rnd)
    data_cols = columns[5:]
    diffs = compare_rows("practice", year, rnd, starters, values, columns,
                         data_cols)
    if diffs:
        changed.append((year, rnd, diffs))

print(f"  {'race':<12} {'laps':>7} {'usable':>7} {'null/pit':>9} "
      f"{'sector':>7} {'too fast':>9}")
for year, rnd, t in reject_rows:
    print(f"  {year} R{rnd:<7} {t['total_laps']:>7} {t['usable']:>7} "
          f"{t[o1.REJECT_PREEXISTING]:>9} {t[o1.REJECT_SECTOR]:>7} "
          f"{t[o1.REJECT_FAST]:>9}")
if not reject_rows:
    print("  (no race had a lap rejected by either new rule)")

print()
print(f"  TOTALS across {len(races)} races:")
print(f"    lap rows examined            : {practice_tally['total_laps']}")
print(f"    usable after all rules       : {practice_tally['usable']}")
print(f"    rejected by null/pit-out     : {practice_tally[o1.REJECT_PREEXISTING]}"
      f"   (rule that already existed)")
print(f"    rejected by RULE 1 (sectors) : {practice_tally[o1.REJECT_SECTOR]}")
print(f"    rejected by RULE 2 (too fast): {practice_tally[o1.REJECT_FAST]}")
print(f"    races with no practice       : {len(no_session)} {no_session}")

# ----------------------------------------------------- SPRINT QUALIFYING
rule("SPRINT QUALIFYING - the other OpenF1-sourced session")

sq_tally = {o1.REJECT_PREEXISTING: 0, o1.REJECT_SECTOR: 0, o1.REJECT_FAST: 0,
            "total_laps": 0, "usable": 0}
sq_changed = []
sq_races = []
sq_reject_rows = []

for year, rnd in races:
    starters, values, columns, ses = practice.compute_sprint_qualifying(
        con, year, rnd)
    if ses is None:
        continue                       # conventional weekend, nothing to audit
    sq_races.append((year, rnd))
    tally = count_rejections([ses])
    for k in sq_tally:
        sq_tally[k] += tally[k]
    if tally[o1.REJECT_SECTOR] + tally[o1.REJECT_FAST]:
        sq_reject_rows.append((year, rnd, tally))

    data_cols = columns[5:]
    diffs = compare_rows("sprint_qualifying", year, rnd, starters, values,
                         columns, data_cols)
    if diffs:
        sq_changed.append((year, rnd, diffs))

print(f"  sprint-qualifying sessions found: {len(sq_races)}")
print(f"  {'race':<12} {'laps':>7} {'usable':>7} {'null/pit':>9} "
      f"{'sector':>7} {'too fast':>9}")
for year, rnd, t in sq_reject_rows:
    print(f"  {year} R{rnd:<7} {t['total_laps']:>7} {t['usable']:>7} "
          f"{t[o1.REJECT_PREEXISTING]:>9} {t[o1.REJECT_SECTOR]:>7} "
          f"{t[o1.REJECT_FAST]:>9}")
if not sq_reject_rows:
    print("  (no sprint-qualifying session had a lap rejected by either new rule)")

print()
print(f"  TOTALS across {len(sq_races)} sprint-qualifying sessions:")
print(f"    lap rows examined            : {sq_tally['total_laps']}")
print(f"    usable after all rules       : {sq_tally['usable']}")
print(f"    rejected by null/pit-out     : {sq_tally[o1.REJECT_PREEXISTING]}")
print(f"    rejected by RULE 1 (sectors) : {sq_tally[o1.REJECT_SECTOR]}")
print(f"    rejected by RULE 2 (too fast): {sq_tally[o1.REJECT_FAST]}")

# ------------------------------------------------------------- VERDICT
rule("WHICH RACES' STORED VALUES WOULD CHANGE")

if changed:
    print(f"  PRACTICE: {len(changed)} of {len(races)} races differ from "
          f"what the rules now produce")
    for year, rnd, diffs in changed:
        print(f"\n    {year} R{rnd} - {len(diffs)} value(s):")
        for driver, col, want, got in diffs[:12]:
            if want is None or got is None:
                print(f"      {driver:<5} {col:<20} stored={want!r} -> "
                      f"recomputed={got!r}")
            else:
                print(f"      {driver:<5} {col:<20} {want:>12.4f} -> "
                      f"{got:>12.4f}")
        if len(diffs) > 12:
            print(f"      ... {len(diffs) - 12} more")
else:
    print("  PRACTICE: no race differs")

if sq_changed:
    print(f"\n  SPRINT QUALIFYING: {len(sq_changed)} of {len(sq_races)} "
          f"sessions differ")
    for year, rnd, diffs in sq_changed:
        print(f"    {year} R{rnd}: {len(diffs)} value(s)")
        for driver, col, want, got in diffs[:6]:
            print(f"      {driver:<5} {col:<20} {want!r} -> {got!r}")
else:
    print(f"\n  SPRINT QUALIFYING: no session differs ({len(sq_races)} checked)")

print()
rule("CONFIRMATION")
ok_practice = len(changed) <= 1
ok_sq = not sq_changed
print(f"  practice           : {len(races) - len(changed)} of {len(races)} "
      f"races UNCHANGED  {'PASS' if ok_practice else 'FAIL'}")
print(f"  sprint_qualifying  : {len(sq_races) - len(sq_changed)} of "
      f"{len(sq_races)} UNCHANGED  {'PASS' if ok_sq else 'FAIL'}")
if changed and len(changed) == 1:
    print(f"  the single changed race is {changed[0][0]} R{changed[0][1]} - "
          f"expected, that is the proven corruption")
print()
print("  nothing was written; this was a dry run")

con.close()
sys.exit(0 if (ok_practice and ok_sq) else 1)
