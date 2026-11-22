import sys
sys.path.insert(0, r'C:\Users\outbnx_\Documents\F1 PROJECTS')
import sqlite3

con = sqlite3.connect(r'C:\Users\outbnx_\Documents\F1 PROJECTS\f1.db')
con.row_factory = sqlite3.Row

# Check R21 qualifying drivers
print('=== R21 QUALIFYING DRIVERS ===')
q = con.execute('SELECT driver, team, q_position FROM qualifying WHERE year=2026 AND round=21 ORDER BY q_position').fetchall()
for r in q:
    print('  {} - {} - P{}'.format(r['driver'], r['team'], r['q_position']))

print('\n=== R21 PRACTICE DRIVERS ===')
p = con.execute('SELECT driver, team, practice_rank FROM practice WHERE year=2026 AND round=21 ORDER BY practice_rank').fetchall()
for r in p:
    print('  {} - {} - P{}'.format(r['driver'], r['team'], r['practice_rank']))

print('\n=== R21 RESULTS ===')
r = con.execute('SELECT driver, team, grid, finish FROM results WHERE year=2026 AND round=21').fetchall()
for r in r:
    print('  {} - {} - Grid:{} Finish:{}'.format(r['driver'], r['team'], r['grid'], r['finish']))

# Check all 2026 drivers
print('\n=== ALL 2026 TEAMS/DRIVERS IN RESULTS ===')
teams = con.execute('''
    SELECT team, GROUP_CONCAT(DISTINCT driver) as drivers, COUNT(DISTINCT driver) as cnt
    FROM results WHERE year=2026
    GROUP BY team ORDER BY team
''').fetchall()
for r in teams:
    print('  {}: {} ({})'.format(r['team'], r['drivers'], r['cnt']))

con.close()