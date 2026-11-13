"""Which venue does each event name actually refer to, and in which years?

The weather fetch has to turn `event` + `event_date` into a latitude and a
longitude, and the database holds no coordinates at all (proved in
scripts/probe_weather_provider.py). Two names in the list look like the same
circuit - "Spanish Grand Prix" and "Barcelona Grand Prix" - so keying a
coordinate table by event name is only safe if they never overlap in years.

READ-ONLY. Prints the answer; writes nothing.

Run:  python scripts/list_venues.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from f1pred import db  # noqa: E402


def rule(t: str = "") -> None:
    print("=" * 78)
    if t:
        print(t)
        print("=" * 78)


con = db.connect()
con.row_factory = None

rule("EVENT NAME -> YEARS, ROUNDS AND RACE DATES")
rows = con.execute(
    "SELECT event, GROUP_CONCAT(DISTINCT year) AS years,"
    "       COUNT(*) AS n, MIN(event_date) AS first, MAX(event_date) AS last"
    " FROM sessions GROUP BY event ORDER BY event").fetchall()
print(f"  {'event':<30} {'n':>3} {'years':<22} {'first':<11} {'last':<11}")
print(f"  {'-'*30} {'-'*3} {'-'*22} {'-'*11} {'-'*11}")
for ev, years, n, first, last in rows:
    ys = sorted(int(y) for y in str(years).split(","))
    span = f"{ys[0]}-{ys[-1]}" if len(ys) > 1 else str(ys[0])
    print(f"  {ev:<30} {n:>3} {span:<22} {first:<11} {last:<11}")

rule("THE TWO THAT LOOK LIKE THE SAME CIRCUIT")
for ev in ("Spanish Grand Prix", "Barcelona Grand Prix"):
    got = con.execute(
        "SELECT year, round, event_date FROM sessions WHERE event=?"
        " ORDER BY year, round", (ev,)).fetchall()
    print(f"  {ev}:")
    for y, r, d in got:
        print(f"      {y} R{r}  {d}")

rule("SPRINT WEEKENDS - confirm event_format matches the sprint tables")
fmt = con.execute(
    "SELECT event_format, COUNT(*) FROM sessions GROUP BY event_format"
).fetchall()
print(f"  event_format counts: {dict(fmt)}")
sprint_races = {(y, r) for y, r in con.execute(
    "SELECT DISTINCT year, round FROM sprint").fetchall()}
flagged = {(y, r) for y, r in con.execute(
    "SELECT year, round FROM sessions WHERE event_format != 'conventional'"
).fetchall()}
print(f"  races in the sprint tables      : {len(sprint_races)}")
print(f"  races not marked 'conventional' : {len(flagged)}")
print(f"  identical sets? {sprint_races == flagged}")
if sprint_races != flagged:
    print(f"    only in sprint tables : {sorted(sprint_races - flagged)[:6]}")
    print(f"    only in event_format  : {sorted(flagged - sprint_races)[:6]}")

rule("RACE DATE RANGE (the weather key)")
r = con.execute(
    "SELECT MIN(event_date), MAX(event_date), COUNT(DISTINCT event_date)"
    " FROM sessions").fetchone()
print(f"  {r[0]} .. {r[1]}  ({r[2]} distinct dates for 89 races)")

rule("DID ANY TWO RACES SHARE A DATE?")
dupes = con.execute(
    "SELECT event_date, COUNT(*) c FROM sessions GROUP BY event_date"
    " HAVING c > 1").fetchall()
print(f"  dates used by more than one race: {len(dupes)} {dupes[:5]}")

con.close()
print()
rule("DONE")
sys.exit(0)
