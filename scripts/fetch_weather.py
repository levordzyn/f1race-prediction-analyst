"""Phase 6b step 2: fetch OBSERVED race-day weather for every race.

WHY THIS SHAPE
  * One request per race (89 of them), each asking for the race date at that
    circuit's coordinates. The provider was verified with a real sample in
    scripts/probe_weather_provider.py BEFORE this file existed, so the four
    daily keys used here - temperature_2m_mean, relative_humidity_2m_mean,
    rain_sum, wind_speed_10m_max - are known to exist rather than guessed.
  * `CIRCUIT_COORDS` is hand-entered because the database holds no
    coordinates at all (proved in probe_weather_provider.py). The one place
    where a name alone would have been WRONG is overridden explicitly:
    "Spanish Grand Prix" is Barcelona for 2023-2025 but the Madring in
    Madrid from 2026, and "Barcelona Grand Prix" (2026 R7) is Barcelona.
    Keying on the event name would have silently given 2026 R14 the wrong
    city's weather.
  * Responses are disk-cached under cache/weather/ so a re-run does not
    spend provider quota.
  * Writes use explicit column names (positional INSERT ... VALUES is banned
    in this project).

Run:
  python scripts/fetch_weather.py --dry-run   # venue table, no network
  python scripts/fetch_weather.py             # fetch + write
  python scripts/fetch_weather.py --force     # ignore the cache
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from f1pred import db  # noqa: E402

CACHE_DIR = Path(__file__).resolve().parents[1] / "cache" / "weather"
SOURCE = "open-meteo archive-api.open-meteo.com (v1/archive), observed daily"

# The four daily keys, each verified against a real response in
# scripts/probe_weather_provider.py (HTTP 200, units printed).
DAILY = "temperature_2m_mean,relative_humidity_2m_mean,rain_sum,wind_speed_10m_max"
NEEDED = ["temperature_2m_mean", "relative_humidity_2m_mean",
          "rain_sum", "wind_speed_10m_max"]

# event name -> (latitude, longitude)
CIRCUIT_COORDS: dict[str, tuple[float, float]] = {
    "Abu Dhabi Grand Prix":        (24.4675, 54.6031),   # Yas Marina
    "Australian Grand Prix":       (-37.8497, 144.9680),  # Albert Park
    "Austrian Grand Prix":         (47.2194, 14.7647),    # Red Bull Ring
    "Azerbaijan Grand Prix":       (40.3725, 49.8533),    # Baku City
    "Bahrain Grand Prix":          (26.0325, 50.5106),    # Sakhir
    "Barcelona Grand Prix":        (41.5700, 2.2611),     # Catalunya
    "Belgian Grand Prix":          (50.4372, 5.9714),     # Spa
    "British Grand Prix":          (52.0786, -1.0169),    # Silverstone
    "Canadian Grand Prix":         (45.5006, -73.5228),   # Gilles Villeneuve
    "Chinese Grand Prix":          (31.3389, 121.2200),   # Shanghai
    "Dutch Grand Prix":            (52.3888, 4.5409),     # Zandvoort
    "Emilia Romagna Grand Prix":   (44.3439, 11.7167),    # Imola
    "Hungarian Grand Prix":        (47.5830, 19.2511),    # Hungaroring
    "Italian Grand Prix":          (45.6159, 9.2817),     # Monza
    "Japanese Grand Prix":         (34.8431, 136.5410),   # Suzuka
    "Las Vegas Grand Prix":        (36.1147, -115.1728),  # Strip circuit
    "Mexico City Grand Prix":      (19.4042, -99.0907),   # Hermanos Rodriguez
    "Miami Grand Prix":            (25.9581, -80.2389),   # Miami Autodrome
    "Monaco Grand Prix":           (43.7347, 7.4206),     # Monte Carlo
    "Qatar Grand Prix":            (25.4900, 51.4542),    # Losail
    "Saudi Arabian Grand Prix":    (21.6320, 39.1044),    # Jeddah
    "Singapore Grand Prix":        (1.2914, 103.8640),    # Marina Bay
    "Spanish Grand Prix":          (41.5700, 2.2611),     # Catalunya, 2023-25
    "São Paulo Grand Prix":        (-23.7036, -46.6997),  # Interlagos
    "United States Grand Prix":    (30.1328, -97.6411),   # COTA, Austin
}

# Where the name alone would be wrong. Resolved by checking the 2026 calendar
# rather than assuming: from 2026 the Spanish Grand Prix moved to the Madring
# in Madrid and Barcelona kept its own race, named the Barcelona Grand Prix.
VENUE_OVERRIDE: dict[tuple[str, int], tuple[float, float]] = {
    ("Spanish Grand Prix", 2026): (40.4117, -3.6914),   # Madring, IFEMA Madrid
}


def rule(t: str = "") -> None:
    print("=" * 78)
    if t:
        print(t)
        print("=" * 78)


def venue(event: str, year: int) -> tuple[float, float]:
    key = (event, year)
    if key in VENUE_OVERRIDE:
        return VENUE_OVERRIDE[key]
    if event not in CIRCUIT_COORDS:
        raise KeyError(
            f"no coordinates for {event!r} ({year}). Add it to "
            f"CIRCUIT_COORDS rather than letting a guess through - wrong "
            f"coordinates mean weather from the wrong city.")
    return CIRCUIT_COORDS[event]


def fetch_one(lat: float, lon: float, day: str, path: Path,
              force: bool) -> dict:
    """Return one cached-or-fetched daily response for a single date."""
    if path.exists() and not force:
        return json.loads(path.read_text(encoding="utf-8"))
    url = ("https://archive-api.open-meteo.com/v1/archive"
           f"?latitude={lat}&longitude={lon}"
           f"&start_date={day}&end_date={day}"
           f"&daily={DAILY}&timezone=auto")
    last: Exception | None = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(url,
                                         headers={"User-Agent": "f1-pred/1.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            break
        except (urllib.error.URLError, urllib.error.HTTPError,
                TimeoutError) as exc:
            last = exc
            time.sleep(1.5 * (attempt + 1))
    else:
        raise RuntimeError(f"3 attempts failed for {day} @ {lat},{lon}: {last}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return data


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true",
                    help="print the venue table and fetch nothing")
    ap.add_argument("--force", action="store_true",
                    help="ignore cache/weather and re-fetch")
    args = ap.parse_args()

    con = db.connect()
    con.row_factory = None
    rows = con.execute(
        "SELECT year, round, event, event_date FROM sessions "
        "ORDER BY year, round").fetchall()

    rule("[1] VENUE TABLE - every race, and the coordinates it will use")
    print(f"  {'year':<5} {'R':<3} {'event':<28} {'date':<11} "
          f"{'lat':>9} {'lon':>10}  source")
    print(f"  {'-'*5} {'-'*3} {'-'*28} {'-'*11} {'-'*9} {'-'*10}  {'-'*10}")
    unknown = []
    used_override = []
    plan = []
    for year, rnd, event, day in rows:
        try:
            lat, lon = venue(event, year)
        except KeyError as exc:
            unknown.append(str(exc))
            continue
        if (event, year) in VENUE_OVERRIDE:
            src = "OVERRIDE"
            used_override.append(f"{event} {year}")
        else:
            src = "name"
        plan.append((year, rnd, event, day, lat, lon))
        print(f"  {year:<5} {rnd:<3} {event:<28} {day:<11} "
              f"{lat:>9.4f} {lon:>10.4f}  {src}")

    if unknown:
        print()
        for u in unknown:
            print(f"  MISSING COORDINATES: {u}")
        con.close()
        return 1

    print()
    print(f"  {len(plan)} races, {len(CIRCUIT_COORDS)} circuits, "
          f"{len(used_override)} name-override(s): "
          f"{', '.join(used_override) or 'none'}")
    print(f"  -> 'Spanish Grand Prix' is Barcelona in 2023-2025 and the")
    print(f"     Madring in 2026; keying on the name alone would have used")
    print(f"     Catalunya's weather for a Madrid race.")

    if args.dry_run:
        rule("DRY RUN - nothing fetched, nothing written")
        con.close()
        return 0

    # ---------------------------------------------------------- [2] fetch
    rule("[2] FETCHING RACE-DAY WEATHER")
    con.execute("""
        CREATE TABLE IF NOT EXISTS weather (
            year INTEGER, round INTEGER, event_date TEXT,
            lat REAL, lon REAL,
            temp_c REAL, humidity_pct REAL, rain_mm REAL, wind_kmh REAL,
            source TEXT,
            PRIMARY KEY (year, round)
        )""")
    con.commit()

    problems: list[str] = []
    written = 0
    for i, (year, rnd, event, day, lat, lon) in enumerate(plan, 1):
        data = fetch_one(lat, lon, day,
                         CACHE_DIR / f"{year}_R{rnd}.json", args.force)
        if "error" in data or "daily" not in data:
            problems.append(f"{year} R{rnd} {event}: provider said "
                            f"{json.dumps(data)[:160]}")
            continue
        daily = data["daily"]
        missing_keys = [k for k in NEEDED if k not in daily]
        if missing_keys:
            problems.append(f"{year} R{rnd} {event}: response lacks "
                            f"{missing_keys}")
            continue
        if day not in daily["time"]:
            problems.append(f"{year} R{rnd} {event}: {day} not in the "
                            f"returned time axis")
            continue
        at = daily["time"].index(day)
        vals = [daily[k][at] for k in NEEDED]
        if any(v is None for v in vals):
            problems.append(f"{year} R{rnd} {event}: null values {vals} - "
                            f"refusing to write a silent placeholder")
            continue
        con.execute(
            "INSERT OR REPLACE INTO weather "
            "(year, round, event_date, lat, lon, "
            " temp_c, humidity_pct, rain_mm, wind_kmh, source) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (year, rnd, day, lat, lon,
             vals[0], vals[1], vals[2], vals[3], SOURCE))
        written += 1
        if i % 20 == 0:
            print(f"  ... {i}/{len(plan)}")
    con.commit()

    print(f"  rows written: {written} of {len(plan)}")

    # ------------------------------------------------------- [3] verify
    rule("[3] VERIFY WHAT LANDED IN THE DATABASE")
    got = con.execute("SELECT COUNT(*) FROM weather").fetchone()[0]
    nulls = con.execute(
        "SELECT COUNT(*) FROM weather WHERE temp_c IS NULL OR "
        "humidity_pct IS NULL OR rain_mm IS NULL OR wind_kmh IS NULL"
    ).fetchone()[0]
    dates = con.execute(
        "SELECT COUNT(*) FROM weather w JOIN sessions s "
        "ON w.year=s.year AND w.round=s.round "
        "WHERE w.event_date <> s.event_date").fetchone()[0]
    print(f"  weather rows                      : {got}")
    print(f"  rows with a NULL quantity         : {nulls}")
    print(f"  rows whose date differs from sessions.event_date : {dates}")
    print()
    print(f"  {'year':<5} {'R':<3} {'temp C':>8} {'humid %':>8} "
          f"{'rain mm':>8} {'wind km/h':>10}")
    print(f"  {'-'*5} {'-'*3} {'-'*8} {'-'*8} {'-'*8} {'-'*10}")
    for r in con.execute(
            "SELECT year, round, temp_c, humidity_pct, rain_mm, wind_kmh "
            "FROM weather ORDER BY year, round LIMIT 8"):
        print(f"  {r[0]:<5} {r[1]:<3} {r[2]:>8.1f} {r[3]:>8.1f} "
              f"{r[4]:>8.2f} {r[5]:>10.1f}")
    print("  ...")
    for r in con.execute(
            "SELECT year, round, temp_c, humidity_pct, rain_mm, wind_kmh "
            "FROM weather ORDER BY year DESC, round DESC LIMIT 4"):
        print(f"  {r[0]:<5} {r[1]:<3} {r[2]:>8.1f} {r[3]:>8.1f} "
              f"{r[4]:>8.2f} {r[5]:>10.1f}")
    print()
    wet = con.execute("SELECT COUNT(*) FROM weather WHERE rain_mm > 0"
                      ).fetchone()[0]
    print(f"  race days with any rain           : {wet} of {got}")
    con.close()

    rule("RESULT")
    if problems:
        print(f"  {len(problems)} problem(s):")
        for p in problems:
            print(f"    - {p}")
        return 1
    if written != len(plan):
        print(f"  WROTE {written} OF {len(plan)} - incomplete")
        return 1
    print(f"  all {written} races have complete observed race-day weather")
    return 0


if __name__ == "__main__":
    sys.exit(main())
