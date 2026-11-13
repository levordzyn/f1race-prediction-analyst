"""Does TEAM_ALIASES cover the team column in EVERY table, not just results?

The review issue was "team-rename normalization at feature time". I verified
results (18 raw labels -> 11 canonical). But practice and sprint_qualifying
come from OpenF1, which may spell constructors differently than FastF1, and
qualifying/sprint come from FastF1.

A name that is missing from TEAM_ALIASES is returned unchanged and logged, so
an OpenF1 spelling would silently become its own "team" and split team_form.

Run:  python scripts/check_team_names_all_tables.py
"""
from __future__ import annotations

import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from f1pred import clean  # noqa: E402

TABLES = ("results", "qualifying", "sprint", "practice", "sprint_qualifying")

con = sqlite3.connect("f1.db")
con.row_factory = sqlite3.Row

all_raw: dict[str, set[str]] = defaultdict(set)

print("=" * 78)
print("RAW TEAM LABELS PER TABLE")
print("=" * 78)
for t in TABLES:
    try:
        rows = con.execute(
            f'SELECT DISTINCT team FROM "{t}" ORDER BY team'
        ).fetchall()
    except sqlite3.Error as exc:
        print(f"  {t}: {exc}")
        continue
    names = [r["team"] for r in rows if r["team"] is not None]
    print(f"  {t} ({len(names)}): {names}")
    for n in names:
        all_raw[n].add(t)

print()
print("=" * 78)
print("UNION ACROSS ALL TABLES -> clean_team_name()")
print("=" * 78)
print(f"  distinct raw labels across every table: {len(all_raw)}")

missing = []
for name in sorted(all_raw):
    key = clean._key(name)
    if key not in clean.TEAM_ALIASES:
        missing.append(name)
    canon = clean.clean_team_name(name)
    where = ",".join(sorted(all_raw[name]))
    flag = "  <-- NO ALIAS" if key not in clean.TEAM_ALIASES else ""
    print(f"    {name:<24} -> {canon:<14} [{where}]{flag}")

print()
print("=" * 78)
print("DO OpenF1 AND FastF1 SPELL CONSTRUCTORS DIFFERENTLY?")
print("=" * 78)
# practice + sprint_qualifying come from OpenF1; results/qualifying/sprint
# come from FastF1. If OpenF1 used a different spelling, joining on team
# would silently miss. Compare the label SETS, not which tables contain them.
fastf1_tables = ("results", "qualifying", "sprint")
openf1_tables = ("practice", "sprint_qualifying")

ff1_labels: set[str] = set()
for t in fastf1_tables:
    ff1_labels |= {
        r["team"] for r in con.execute(f'SELECT DISTINCT team FROM "{t}"')
        if r["team"] is not None
    }
of1_labels: set[str] = set()
for t in openf1_tables:
    of1_labels |= {
        r["team"] for r in con.execute(f'SELECT DISTINCT team FROM "{t}"')
        if r["team"] is not None
    }

print(f"  FastF1 labels ({len(ff1_labels)}): {sorted(ff1_labels)}")
print(f"  OpenF1 labels ({len(of1_labels)}): {sorted(of1_labels)}")
print()
only_ff1 = ff1_labels - of1_labels
only_of1 = of1_labels - ff1_labels
if not only_ff1 and not only_of1:
    print("  IDENTICAL - OpenF1 uses exactly the same spellings as FastF1.")
    print("  No cross-source team mismatch is possible.")
else:
    if only_ff1:
        print(f"  only in FastF1: {sorted(only_ff1)}")
    if only_of1:
        print(f"  only in OpenF1: {sorted(only_of1)}")
    print("  -> these must stay in TEAM_ALIASES or a join on team will miss.")

print()
print("=" * 78)
print("VERDICT")
print("=" * 78)
if missing:
    print("  UNMAPPED labels (would become their own team):")
    for n in missing:
        print(f"      {n!r}  tables={sorted(all_raw[n])}")
else:
    print("  PASS - every team label in every table has an alias entry.")

# Do the canonical sets agree across tables? They should, since all five
# tables describe the same field.
print()
print("=" * 78)
print("CANONICAL SET PER TABLE (must be the same 11 constructors)")
print("=" * 78)
ref = None
for t in TABLES:
    try:
        rows = con.execute(f'SELECT DISTINCT team FROM "{t}"').fetchall()
    except sqlite3.Error:
        continue
    canon = {clean.clean_team_name(r["team"]) for r in rows if r["team"]}
    marker = ""
    if ref is None:
        ref = canon
    elif canon == ref:
        marker = "  (matches results)"
    else:
        marker = f"  <-- DIFFERS: only here={sorted(canon - ref)} " \
                 f"only in results={sorted(ref - canon)}"
    print(f"  {t:<20} {len(canon):>2} teams{marker}")

con.close()
