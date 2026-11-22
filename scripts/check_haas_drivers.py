import sys
sys.path.insert(0, r'C:\Users\outbnx_\Documents\F1 PROJECTS')
import sqlite3

con = sqlite3.connect(r'C:\Users\outbnx_\Documents\F1 PROJECTS\f1.db')
con.row_factory = sqlite3.Row

# Check 2026 results for Haas drivers
print('=== 2026 Haas drivers in results ===')
haas = con.execute("""
    SELECT DISTINCT driver, team FROM results 
    WHERE year=2026 AND team LIKE '%Haas%'
    ORDER BY round
""").fetchall()
for r in haas:
    print(f'  {r["driver"]} - {r["team"]}')

# Check 2026 practice entries
print('\n=== 2026 Haas drivers in practice ===')
prac = con.execute("""
    SELECT DISTINCT driver, team FROM practice 
    WHERE year=2026 AND team LIKE '%Haas%'
    ORDER BY round
""").fetchall()
for r in prac:
    print(f'  {r["driver"]} - {r["team"]}')

# Check 2026 qualifying entries
print('\n=== 2026 Haas drivers in qualifying ===')
qual = con.execute("""
    SELECT DISTINCT driver, team FROM qualifying 
    WHERE year=2026 AND team LIKE '%Haas%'
    ORDER BY round
""").fetchall()
for r in qual:
    print(f'  {r["driver"]} - {r["team"]}')

# Check 2026 R21 specifically
print('\n=== 2026 R21 entries ===')
r21 = con.execute("""
    SELECT driver, team FROM practice WHERE year=2026 AND round=21
    UNION
    SELECT driver, team FROM qualifying WHERE year=2026 AND round=21
    ORDER BY driver
""").fetchall()
for r in r21:
    print(f'  {r["driver"]} - {r["team"]}')

con.close()