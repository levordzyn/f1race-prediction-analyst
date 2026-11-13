import sqlite3
import sys
sys.path.insert(0, r'C:\Users\outbnx_\Documents\F1 PROJECTS')
from f1pred import db, features

con = db.connect(r'C:\Users\outbnx_\Documents\F1 PROJECTS\f1.db')
con.row_factory = sqlite3.Row

print('=== GRID POSITION ANALYSIS ===')

# Check qualifying vs results grid match rate
print('\n1. Qualifying vs Results Grid Match Rate:')
match = con.execute('''
    SELECT 
        COUNT(*) as total,
        SUM(CASE WHEN q.q_position = r.grid THEN 1 ELSE 0 END) as matches,
        SUM(CASE WHEN q.q_position != r.grid THEN 1 ELSE 0 END) as mismatches
    FROM qualifying q
    JOIN results r ON q.year=r.year AND q.round=r.round AND q.driver=r.driver
    WHERE r.grid IS NOT NULL AND q.q_position IS NOT NULL
''').fetchone()
print(f'  Total: {match["total"]}, Matches: {match["matches"]}, Mismatches: {match["mismatches"]}')
print(f'  Match rate: {match["matches"]/match["total"]*100:.1f}%')

# Check by year
print('\n2. Match Rate by Year:')
by_year = con.execute('''
    SELECT 
        r.year,
        COUNT(*) as total,
        SUM(CASE WHEN q.q_position = r.grid THEN 1 ELSE 0 END) as matches,
        SUM(CASE WHEN q.q_position != r.grid THEN 1 ELSE 0 END) as mismatches
    FROM qualifying q
    JOIN results r ON q.year=r.year AND q.round=r.round AND q.driver=r.driver
    WHERE r.grid IS NOT NULL AND q.q_position IS NOT NULL
    GROUP BY r.year
    ORDER BY r.year
''').fetchall()
for r in by_year:
    print(f'  {r[0]}: {r[1]} total, {r[2]} matches, {r[3]} mismatches ({r[2]/r[1]*100:.1f}% match)')

# Check grid position distribution
print('\n3. Results Grid Position Distribution:')
grid_dist = con.execute('''
    SELECT grid, COUNT(*) as cnt
    FROM results
    WHERE grid IS NOT NULL
    GROUP BY grid
    ORDER BY grid
''').fetchall()
for r in grid_dist[:30]:
    print(f'  Grid {r[0]}: {r[1]}')

# Check for -1, 0, NULL grids
print('\n4. Anomalous Grid Values:')
anomalies = con.execute('''
    SELECT grid, COUNT(*) as cnt
    FROM results
    WHERE grid IS NULL OR grid <= 0
    GROUP BY grid
    ORDER BY grid
''').fetchall()
for r in anomalies:
    print(f'  Grid {r[0]}: {r[1]}')

# Check pit-lane starts (grid = field_n + 1)
print('\n5. Pit-lane / Back-of-grid Starts (grid = field_n + 1):')
pit_lane = con.execute('''
    SELECT r.year, r.round, r.driver, r.grid, 
           (SELECT COUNT(*) FROM results r2 WHERE r2.year=r.year AND r2.round=r.round) as field_n
    FROM results r
    WHERE r.grid = (SELECT COUNT(*) FROM results r2 WHERE r2.year=r.year AND r2.round=r.round) + 1
''').fetchall()
for r in pit_lane[:20]:
    print(f'  {r[0]} R{r[1]} {r[3]}: grid={r[2]}, field_n={r[4]}')

# Check qualifying position anomalies
print('\n6. Qualifying Position Anomalies:')
qual_anom = con.execute('''
    SELECT q_position, COUNT(*) as cnt
    FROM qualifying
    WHERE q_position IS NOT NULL
    GROUP BY q_position
    ORDER BY q_position
''').fetchall()
for r in qual_anom[:30]:
    print(f'  Q-Pos {r[0]}: {r[1]}')

# Check for ties in qualifying
print('\n7. Qualifying Ties (same position, same race):')
ties = con.execute('''
    SELECT year, round, q_position, COUNT(*) as cnt
    FROM qualifying
    WHERE q_position IS NOT NULL
    GROUP BY year, round, q_position
    HAVING COUNT(*) > 1
    ORDER BY year, round
''').fetchall()
for r in ties:
    print(f'  {r[0]} R{r[1]}: Q-Pos {r[2]} has {r[3]} drivers')

# Check sprint grid
print('\n8. Sprint Grid Availability:')
sprint_grid = con.execute('''
    SELECT 
        COUNT(*) as total,
        SUM(CASE WHEN sprint_grid IS NOT NULL AND sprint_grid > 0 THEN 1 ELSE 0 END) as has_grid,
        SUM(CASE WHEN sprint_grid IS NULL OR sprint_grid <= 0 THEN 1 ELSE 0 END) as no_grid
    FROM sprint
    WHERE has_sprint_result = 1
''').fetchone()
print(f'  Total sprint results: {sprint_grid[0]}')
print(f'  Has valid grid: {sprint_grid[1]}')
print(f'  No grid: {sprint_grid[2]}')

con.close()