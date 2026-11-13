"""Team-name normalisation and row validation (spec sections 5 and 6).

Why normalise: ``team_form`` in Appendix A groups by the raw TeamName, so
every rename resets the rolling history to the default. Verified renames in
our own database:

    2023 Alfa Romeo   -> 2024 Sauber   -> 2026 Audi      (same entry)
    2023 AlphaTauri   -> 2024 RB F1 Team                 (same entry)
    2026 Cadillac F1 Team                                (brand new, 11th team)

We keep BOTH: ``team_raw`` exactly as the source reported it, and
``team`` normalised so the form features see one continuous history.
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)

# raw name (lower-cased, punctuation stripped) -> stable canonical name
# History (canonical -> historical names):
#   Sauber: Sauber (2018), Alfa Romeo (2019-2023), Sauber (2024-2025), Audi (2026+)
#   Racing Bulls: Toro Rosso (2018-2019), AlphaTauri (2020-2023), RB F1 Team / Visa Cash App RB / VCARB (2024+)
#   Alpine: Renault (2018-2020), Alpine (2021+)
#   Aston Martin: Force India (2018), Racing Point (2019-2020), Aston Martin (2021+)
#   Mercedes, Ferrari, McLaren, Red Bull, Williams, Haas: unchanged
#   Cadillac: new entry 2026
TEAM_ALIASES: dict[str, str] = {
    # Sauber lineage: 2018 Sauber -> 2019-2023 Alfa Romeo -> 2024-2025 Sauber -> 2026 Audi
    "sauber": "Sauber",
    "alfa romeo": "Sauber",
    "alfa romeo racing": "Sauber",
    "alfa romeo racing equipe": "Sauber",
    "audi": "Sauber",
    "audi f1": "Sauber",

    # Racing Bulls lineage: 2018-2019 Toro Rosso -> 2020-2023 AlphaTauri -> 2024 RB -> 2025 Racing Bulls
    "toro rosso": "Racing Bulls",
    "red bull toro rosso": "Racing Bulls",
    "alphatauri": "Racing Bulls",
    "scuderia alphatauri": "Racing Bulls",
    "rb f1 team": "Racing Bulls",
    "rb": "Racing Bulls",
    "visacashapp rb": "Racing Bulls",
    "visa cash app rb": "Racing Bulls",
    "vcarb": "Racing Bulls",
    "racing bulls": "Racing Bulls",

    # Alpine lineage: 2018-2020 Renault -> 2021+ Alpine
    "renault": "Alpine",
    "renault f1 team": "Alpine",
    "renault sport": "Alpine",
    "alpine f1 team": "Alpine",
    "alpine": "Alpine",

    # Aston Martin lineage: 2018 Force India -> 2019-2020 Racing Point -> 2021+ Aston Martin
    "force india": "Aston Martin",
    "sahara force india": "Aston Martin",
    "racing point": "Aston Martin",
    "bwt racing point": "Aston Martin",
    "aston martin": "Aston Martin",
    "aston martin f1 team": "Aston Martin",
    "aston martin aramco": "Aston Martin",
    "aston martin aramco f1 team": "Aston Martin",

    # Unchanged teams
    "haas f1 team": "Haas",
    "haas": "Haas",
    "moneygram haas f1 team": "Haas",
    "williams": "Williams",
    "williams racing": "Williams",
    "mclaren": "McLaren",
    "mclaren f1 team": "McLaren",
    "mercedes": "Mercedes",
    "mercedes-amg petronas f1 team": "Mercedes",
    "ferrari": "Ferrari",
    "scuderia ferrari": "Ferrari",
    "scuderia ferrari hp": "Ferrari",
    "red bull": "Red Bull",
    "red bull racing": "Red Bull",
    "oracle red bull racing": "Red Bull",
    "cadillac f1 team": "Cadillac",
    "cadillac": "Cadillac",
}


def _key(name: str) -> str:
    return " ".join(str(name).strip().lower().split())


def clean_team_name(name: str) -> str:
    """Map a source team name to a stable canonical name.

    Unknown names are returned unchanged and logged once, so a new team in a
    future season never crashes the pipeline and is easy to spot.
    """
    raw = str(name)
    key = _key(raw)
    if key in TEAM_ALIASES:
        return TEAM_ALIASES[key]
    log.warning("unknown team name %r - left unchanged (add it to TEAM_ALIASES "
                "if it is a rename)", raw)
    return raw


# ----------------------------------------------------------------- validation
class DataValidationError(ValueError):
    """A row failed a documented sanity rule; message says which and why."""


def validate_field_size(n_rows: int, expected: int, where: str) -> None:
    """Rows per race should equal the grid size (20 for 2023-25, 22 for 2026)."""
    if n_rows == 0:
        raise DataValidationError(f"{where}: no rows at all")
    if n_rows > expected:
        raise DataValidationError(
            f"{where}: {n_rows} rows exceeds the {expected}-car grid"
        )
    if n_rows < expected:
        # not fatal: a driver can be absent from a results table
        log.warning("%s: %d rows (expected %d) - absent driver(s), "
                    "missing-data handling will apply", where, n_rows, expected)


def validate_positions(positions: list[int], expected: int, where: str,
                       *, allow_ties: bool = False) -> None:
    """Positions must start at 1 and stay within the grid size.

    Spec 5: 'qualifying positions must be 1..22'.

    ``allow_ties=False`` (used for ranks we derive ourselves) additionally
    demands a contiguous 1..n block with no duplicates. ``allow_ties=True``
    (used for FastF1's official Position column) downgrades duplicates and
    gaps to warnings: we verified that column really does contain ties - e.g.
    2023 R10 reports Position 15.0 for BOTH PER and BOT - so treating a tie
    as fatal would throw away an otherwise usable race.
    """
    if not positions:
        raise DataValidationError(f"{where}: no positions to validate")
    seen = sorted(positions)
    if seen[0] < 1:
        raise DataValidationError(
            f"{where}: lowest position is {seen[0]}, expected >= 1"
        )
    if seen[-1] > expected:
        raise DataValidationError(
            f"{where}: highest position {seen[-1]} exceeds grid size {expected}"
        )
    duplicates = sorted({p for p in seen if seen.count(p) > 1})
    gaps = sorted(set(range(1, seen[-1] + 1)) - set(seen))
    if duplicates or gaps:
        detail = f"duplicates={duplicates} gaps={gaps}"
        if allow_ties:
            log.warning("%s: ties/gaps in source positions (%s) - tolerated, "
                        "using derived rank instead", where, detail)
        else:
            raise DataValidationError(f"{where}: bad positions ({detail})")


def derive_rank(bests: dict[str, float | None]) -> dict[str, int | None]:
    """Rank drivers by best lap time, 1 = fastest.

    Returns {driver: rank}. Drivers with no time get None.

    Why we derive instead of trusting the source Position column: it contains
    duplicate values (2023 R10 gives Position 15.0 to both PER and BOT), which
    would break any model that treats grid/qualifying position as a clean
    1..n sequence. Ranking by time is unambiguous, and in F1 the classification
    is in practice the ordering of best laps anyway (Q1 eliminees always have
    the slowest best laps).
    """
    timed = {d: t for d, t in bests.items() if t is not None}
    # sort by time, then by driver name for a deterministic tie-break
    order = sorted(timed.items(), key=lambda kv: (kv[1], kv[0]))
    ranks: dict[str, int | None] = {d: None for d in bests}
    for i, (driver, _t) in enumerate(order, start=1):
        ranks[driver] = i
    return ranks


def validate_practice_row(position: int | None, lap_count: int, where: str) -> None:
    """Spec 5: 'practice position must be 1..22 and lap count >= 0'."""
    if lap_count < 0:
        raise DataValidationError(f"{where}: lap_count {lap_count} is negative")
    if position is not None and not 1 <= position <= 22:
        raise DataValidationError(
            f"{where}: practice position {position} outside 1..22"
        )


def validate_gap_percent(gap: float | None, cap: float, where: str) -> float | None:
    """Cap an outlying gap (Appendix A capped practice gap at ~10%)."""
    if gap is None:
        return None
    if gap < 0:
        raise DataValidationError(f"{where}: negative gap {gap}% (impossible)")
    if gap > cap:
        log.warning("%s: gap %.2f%% above cap %.1f%% - clipping", where, gap, cap)
        return cap
    return gap
