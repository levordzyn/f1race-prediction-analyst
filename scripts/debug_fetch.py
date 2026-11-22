import sys
sys.path.insert(0, r'C:\Users\outbnx_\Documents\F1 PROJECTS')
import sqlite3
from f1pred import fetch

con = sqlite3.connect(r'C:\Users\outbnx_\Documents\F1 PROJECTS\f1.db')
con.row_factory = sqlite3.Row

# Check what fetch_upcoming does for R21
print("=== Testing fetch_upcoming for R21 ===")
from f1pred import fetch as fetch_module
con2 = sqlite3.connect(r'C:\Users\outbnx_\Documents\F1 PROJECTS\f1.db')
con2.row_factory = sqlite3.Row

# Check if R21 is considered "already-raced"
already = con.execute(
    "SELECT COUNT(*) FROM results WHERE year=? AND round=?", (2026, 21)).fetchone()[0]
print(f"Results count for 2026 R21: {already}")

# Check what fetch_upcoming would do
# It checks if results already exist
already_done = con.execute(
    "SELECT COUNT(*) FROM results WHERE year=? AND round=?", (2026, 21)).fetchone()[0]
print(f"Already done (results count): {already_done}")

# Check what the schedule says about R21
import fastf1
fastf1.Cache.enable_cache(r'C:\Users\outbnx_\Documents\F1 PROJECTS\f1_cache')
sched = fastf1.get_event_schedule(2026, include_testing=False)
hit = sched[sched["RoundNumber"] == 21]
if not hit.empty:
    ev = hit.iloc[0]
    print(f"\nEvent: {ev['EventName']}")
    print(f"EventDate: {ev['EventDate']}")
    print(f"EventFormat: {ev['EventFormat']}")
    for i in range(1, 6):
        name = ev.get(f"Session{i}", "")
        date = ev.get(f"Session{i}DateUtc", "")
        print(f"  Session{i}: {name} - {date}")

# Check what the current fetch logic does
# fetch_upcoming checks if results exist, if not, it fetches practice/qualifying
# But fetch_race is only called for races that have already happened (EventDate in past)

# Let's check the event date
from datetime import datetime, timezone
now = datetime.now(timezone.utc)
print(f"\nCurrent UTC time: {now}")

# Check event date
event_date = ev['EventDate']
if hasattr(event_date, 'tzinfo') and event_date.tzinfo is not None:
    event_date = event_date.tz_convert('UTC').tz_localize(None)
print(f"Event date (naive): {event_date}")
print(f"Is event in past? {event_date < now}")

con.close()