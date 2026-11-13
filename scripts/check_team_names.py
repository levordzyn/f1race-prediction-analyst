"""Which team names appear in the DB, and does TEAM_ALIASES cover them?

The review flagged "team-rename normalization at feature time": Appendix A
builds team_form from the raw TeamName, so a team that renames mid-dataset
splits into two and its form history resets.

This answers three questions without touching Phase 3:

  1. What distinct team names exist, per year?
  2. Which ones does clean_team_name() map, and which does it leave alone?
  3. Does any team appear under MORE THAN ONE name (the actual bug)?

Run:  python scripts/check_team_names.py
"""
from __future__ import annotations

import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from f1pred import clean  # noqa: E402

con = sqlite3.connect("f1.db")
con.row_factory = sqlite3.Row

rows = con.execute(
    "SELECT year, team, COUNT(*) n FROM results "
    "GROUP BY year, team ORDER BY team, year"
).fetchall()

by_team: dict[str, list[tuple[int, int]]] = defaultdict(list)
for r in rows:
    by_team[r["team"]].append((r["year"], r["n"]))

print("=" * 78)
print("DISTINCT TEAM NAMES PER YEAR (raw, as stored)")
print("=" * 78)
for team in sorted(by_team):
    years = ", ".join(f"{y}({n})" for y, n in by_team[team])
    print(f"  {team:<28} {years}")

print()
print("=" * 78)
print("WHAT clean_team_name() DOES TO EACH")
print("=" * 78)
mapping: dict[str, str] = {}
for team in sorted(by_team):
    out = clean.clean_team_name(team)
    mapping[team] = out
    changed = "  <-- RENAMED" if out != team else ""
    print(f"  {team:<28} -> {out:<28}{changed}")

print()
print("=" * 78)
print("DOES ANY TEAM APPEAR UNDER MORE THAN ONE NAME?")
print("=" * 78)
# group raw names by their cleaned name: if two raw names clean to the SAME
# canonical name, they are one team split across two labels.
inv: dict[str, list[str]] = defaultdict(list)
for raw, canon in mapping.items():
    inv[canon].append(raw)

splits = {k: v for k, v in inv.items() if len(v) > 1}
if not splits:
    print("  No. Every raw name is already unique, so no team is split")
    print("  across two labels in the raw data.")
else:
    print("  YES - these are the same team under different labels:")
    for canon, raws in sorted(splits.items()):
        print(f"      {canon}: {raws}")

print()
print("=" * 78)
print("DOES THE CLEANED NAME COLLIDE OR LEAVE ANYTHING UNMAPPED?")
print("=" * 78)
unknown = [t for t in sorted(by_team)
           if t not in clean.TEAM_ALIASES and mapping[t] == t]
print(f"  raw names with no TEAM_ALIASES entry: {len(unknown)}")
for t in unknown:
    print(f"      {t}")

# a rename that is NOT in TEAM_ALIASES is the real risk: the model would see
# two teams where there is one.
print()
print("=" * 78)
print("RISK TO team_form (Phase 3)")
print("=" * 78)
if splits:
    print("  A team's form history would RESET at each rename, because")
    print("  groupby('team') treats the new label as a brand-new team.")
    print("  Fix: run every team value through clean_team_name() when the")
    print("  feature frame is built - not at fetch time.")
else:
    print("  No raw name maps onto another, so groupby('team') already")
    print("  sees one label per team across 2023-2026.")
    print("  Normalisation is still required at feature time as a guard:")
    print("  any future rename would otherwise silently split team_form.")
    print(f"  TEAM_ALIASES currently holds {len(clean.TEAM_ALIASES)} entries.")

print()
print("=" * 78)
print("COVERAGE OF TEAM_ALIASES")
print("=" * 78)
print(f"  entries in TEAM_ALIASES : {len(clean.TEAM_ALIASES)}")
for k, v in sorted(clean.TEAM_ALIASES.items()):
    print(f"      {k!r} -> {v!r}")

# Coverage must use the same normalisation clean_team_name uses (_key lowercases
# and collapses whitespace). Comparing raw mixed-case names against the
# lowercase keys would report every name as missing.
print()
print("=" * 78)
print("RAW NAMES WITH NO ALIAS ENTRY (left unchanged by the normaliser)")
print("=" * 78)
missing = [t for t in sorted(by_team)
           if clean._key(t) not in clean.TEAM_ALIASES]
if not missing:
    print("  none - every team name in the DB has an alias entry")
else:
    for t in missing:
        print(f"      {t!r}  (key={clean._key(t)!r})")

print()
print("=" * 78)
print("FINAL: does normalisation unify the split labels?")
print("=" * 78)
# Correct direction: several raw labels SHOULD collapse onto one canonical
# name - that is the whole point of the alias table. What would be a bug is a
# raw name left unmapped (checked above) or two DIFFERENT constructors ending
# up under the same canonical name.
n_raw = len(by_team)
canon_of = {raw: clean.clean_team_name(raw) for raw in by_team}
n_canon = len(set(canon_of.values()))
print(f"  distinct raw labels      : {n_raw}")
print(f"  after normalisation      : {n_canon}")
print(f"  duplicate labels merged  : {n_raw - n_canon}")
print()
if n_raw == n_canon:
    print("  Nothing was merged - the alias table is doing no work.")
else:
    print("  Merged (same constructor, several source spellings):")
    inv3: dict[str, list[str]] = defaultdict(list)
    for raw, canon in canon_of.items():
        inv3[canon].append(raw)
    for canon, raws in sorted(inv3.items()):
        if len(raws) > 1:
            print(f"      {canon:<14} <- {sorted(raws)}")
print()
print("  2026 has 11 constructors x 2 cars = the 22-car grid, so the")
print("  normalised label count must be 11 for the 2026 field.")
n_2026 = len({clean.clean_team_name(r['team']) for r in con.execute(
    "SELECT DISTINCT team FROM results WHERE year=2026")})
print(f"  canonical team labels in 2026 : {n_2026}")
print("  OK" if n_2026 == 11 else "  CHECK - expected 11")
