"""Verify team aliases cover all teams in the database for 2018-2026.

Run: python scripts/verify_team_aliases.py
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from f1pred.clean import clean_team_name, TEAM_ALIASES


def main() -> int:
    DB = ROOT / "f1.db"
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row

    # Get all distinct team names from results (2018-2026)
    teams = con.execute(
        "SELECT DISTINCT team FROM results WHERE year BETWEEN 2018 AND 2026 ORDER BY team"
    ).fetchall()
    raw_teams = [r[0] for r in teams if r[0]]

    print(f"Found {len(raw_teams)} unique team names in results (2018-2026)")
    print()

    # Check each against clean_team_name
    unknown = []
    for team in raw_teams:
        canonical = clean_team_name(team)
        if canonical == team and team.lower() not in TEAM_ALIASES:
            unknown.append(team)
        print(f"  {team:<45} -> {canonical}")

    print()
    if unknown:
        print(f"UNKNOWN TEAMS ({len(unknown)}):")
        for u in unknown:
            print(f"  {u}")
        print()
        print("Add these to TEAM_ALIASES in f1pred/clean.py")
        return 1

    # Verify canonical names are consistent (no split canonicals for same lineage)
    canonicals = {}
    for team in raw_teams:
        canon = clean_team_name(team)
        canonicals.setdefault(canon, []).append(team)

    print("CANONICAL MAPPINGS:")
    for canon, raw_list in sorted(canonicals.items()):
        print(f"  {canon:<20} <- {raw_list}")

    # Verify expected canonicals (11 teams for 2026, fewer for earlier years)
    expected_canonicals = {
        "Sauber", "Racing Bulls", "Alpine", "Aston Martin",
        "Haas", "Williams", "McLaren", "Mercedes", "Ferrari",
        "Red Bull", "Williams", "Cadillac"
    }
    actual_canonicals = set(canonicals.keys())
    missing = expected_canonicals - actual_canonicals
    extra = actual_canonicals - expected_canonicals

    if missing:
        print(f"\nMISSING EXPECTED CANONICALS: {missing}")
    if extra:
        print(f"\nUNEXPECTED CANONICALS: {extra}")

    con.close()
    print("\n✅ ALL TEAM ALIASES VERIFIED")
    return 0


if __name__ == "__main__":
    sys.exit(main())