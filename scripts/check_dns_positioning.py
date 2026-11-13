"""Where exactly do 'Did not start' drivers sit in the classification?

If FastF1 places every DNS driver in the LAST |DNS| positions, they are a
legitimately classified block at the back and results.finish is fine as a
target. If they sit AHEAD of a driver who actually raced, then a DNS driver
is displacing a real result and the target is questionable for those rows.

Run:  python scripts/check_dns_positioning.py
"""
from __future__ import annotations

import sqlite3

con = sqlite3.connect("f1.db")
con.row_factory = sqlite3.Row

races = con.execute("""
    SELECT year, round FROM race_status
    WHERE status = 'Did not start'
    GROUP BY year, round ORDER BY year, round""").fetchall()

print("=" * 78)
print("FOR EACH RACE WITH A DNS DRIVER: do they occupy the last positions?")
print("=" * 78)
all_back = True
for r in races:
    y, rd = r["year"], r["round"]
    rows = con.execute("""
        SELECT rs.driver AS drv, rs.status, res.finish, res.grid
        FROM race_status rs
        JOIN results res ON res.year=rs.year AND res.round=rs.round
                        AND res.driver=rs.driver
        WHERE rs.year=? AND rs.round=? ORDER BY res.finish""", (y, rd)).fetchall()
    field = len(rows)
    dns_pos = sorted(int(x["finish"]) for x in rows if x["status"] == "Did not start")
    n_dns = len(dns_pos)
    last_k = list(range(field - n_dns + 1, field + 1))   # the last |DNS| slots
    ok_here = dns_pos == last_k
    all_back &= ok_here
    verdict = "OK - exactly the last slots" if ok_here else "NOT at the back"
    print(f"\n  {y} R{rd:>2}  field={field}  DNS={n_dns}  "
          f"DNS positions={dns_pos}  expected last {n_dns}={last_k}")
    print(f"      {verdict}")
    if not ok_here:
        # show who is in those slots and who sits behind them
        for x in rows:
            mark = ""
            if x["status"] == "Did not start":
                mark = "   <-- DNS"
            if int(x["finish"]) >= (field - n_dns):
                print(f"        P{int(x['finish']):>2} {x['drv']:<5} "
                      f"grid={int(x['grid']) if x['grid'] else '-':>3}  "
                      f"{x['status']:<20}{mark}")

print()
print("=" * 78)
print("VERDICT")
print("=" * 78)
if all_back:
    print("  In EVERY race, DNS drivers occupy exactly the last |DNS|")
    print("  positions. FastF1 classifies them at the back, so")
    print("  results.finish is a real classification and stays a valid")
    print("  target. They are just uncompetitive, which is honest data.")
else:
    print("  Some DNS drivers sit ahead of drivers who actually raced.")
    print("  Those rows do not represent a result that happened and are")
    print("  candidates for exclusion from the training set.")

# How many rows would exclusion remove?
n_dns = con.execute(
    "SELECT COUNT(*) FROM race_status WHERE status='Did not start'"
).fetchone()[0]
n_race = con.execute(
    "SELECT COUNT(DISTINCT year || '-' || round) FROM race_status "
    "WHERE status='Did not start'").fetchone()[0]
print()
print(f"  Impact if excluded: {n_dns} of 1816 rows "
      f"({100*n_dns/1816:.2f}%), across {n_dns and n_race} races")

con.close()
raise SystemExit(0 if all_back else 1)
