import sqlite3

con = sqlite3.connect('file:f1.db?mode=ro', uri=True)
con.row_factory = sqlite3.Row

print('=== SCHEMA ===')
for row in con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
    t = row[0]
    print(f'--- {t} ---')
    for c in con.execute(f'PRAGMA table_info({t})'):
        print(f'  {c[1]} {c[2]}' + (' NOT NULL' if c[3] else '') + (' PK' if c[5] else ''))
    cnt = con.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
    print(f'  rows: {cnt}')
    print()

# Additional queries
print('=== SEASONS ===')
for row in con.execute("SELECT year, COUNT(DISTINCT round) as races FROM results GROUP BY year ORDER BY year"):
    print(f'  {row[0]}: {row[1]} races')

print()
print('=== DRIVERS PER RACE ===')
for row in con.execute("SELECT year, round, COUNT(*) as n FROM results GROUP BY year, round ORDER BY year, round"):
    print(f'  {row[0]} R{row[1]}: {row[2]} drivers')

print()
print('=== FORECASTS ===')
for row in con.execute("SELECT year, round, mode, COUNT(*) as n, MIN(created_at), MAX(created_at) FROM forecasts GROUP BY year, round, mode ORDER BY year, round"):
    print(f'  {row[0]} R{row[1]} {row[2]}: {row[3]} rows, created {row[4]} to {row[5]}')

print()
print('=== FETCH LOG ===')
for row in con.execute("SELECT year, round, step, nrows, run_at FROM fetch_log ORDER BY year, round, step"):
    print(f'  {row[0]} R{row[1]} {row[2]}: {row[3]} rows at {row[4]}')

print()
print('=== WEATHER ===')
for row in con.execute("SELECT year, round, temp_c, humidity_pct, rain_mm, wind_kmh, source FROM weather ORDER BY year, round"):
    print(f'  {row[0]} R{row[1]}: {row[2]}°C {row[3]}% {row[4]}mm {row[5]}km/h ({row[6]})')

con.close()