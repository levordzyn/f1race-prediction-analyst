import sys
sys.path.insert(0, r'C:\Users\outbnx_\Documents\F1 PROJECTS')
import sqlite3

con = sqlite3.connect(r'C:\Users\outbnx_\Documents\F1 PROJECTS\f1.db')
con.row_factory = sqlite3.Row

print('=== 2026 All teams and drivers (results) ===')
teams = con.execute("""
    SELECT team, GROUP_CONCAT(DISTINCT driver) as drivers, COUNT(DISTINCT driver) as cnt
    FROM results 
    WHERE year=2026
    GROUP BY team
    ORDER BY team
""").fetchall()
for r in teams:
    print(f'  {r["team"]}: {r["drivers"]} ({r["cnt"]} drivers)')

print('\n=== 2026 All teams and drivers (practice) ===')
teams_p = con.execute("""
    SELECT team, GROUP_CONCAT(DISTINCT driver) as drivers, COUNT(DISTINCT driver) as cnt
    FROM practice 
    WHERE year=2026
    GROUP BY team
    ORDER BY team
""").fetchall()
for r in teams_p:
    print(f'  {r["team"]}: {r["drivers"]} ({r["cnt"]} drivers)')

print('\n=== 2026 All teams and drivers (qualifying) ===')
teams_q = con.execute("""
    SELECT team, GROUP_CONCAT(DISTINCT driver) as drivers, COUNT(DISTINCT driver) as cnt
    FROM qualifying 
    WHERE year=2026
    GROUP BY team
    ORDER BY team
""").fetchall()
for r in teams_q:
    print(f'  {r["team"]}: {r["drivers"]} ({r["cnt"]} drivers)')

con.close()