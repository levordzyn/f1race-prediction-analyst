import sys
sys.path.insert(0, r'C:\Users\outbnx_\Documents\F1 PROJECTS')
import sqlite3
import datetime
import shutil

con = sqlite3.connect(r'C:\Users\outbnx_\Documents\F1 PROJECTS\f1.db')
con.row_factory = sqlite3.Row

print("=== BACKING UP DATABASE ===")
backup_name = 'f1_backup_before_2026_fix_' + datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + '.db'
shutil.copy2(r'C:\Users\outbnx_\Documents\F1 PROJECTS\f1.db', 
             r'C:\Users\outbnx_\Documents\F1 PROJECTS\\' + backup_name)
print('Backup created: ' + backup_name)

print("\n=== FIXING 2026 DATA ===")

# ============================================================
# 1. FIX TEAM ALIASES - Use clean_team_name to standardize
# ============================================================
from f1pred.clean import clean_team_name

# Only tables that have BOTH 'team' and 'year' columns
tables_with_team_and_year = ['results', 'qualifying', 'practice', 'sprint', 'sprint_qualifying', 'forecasts']

print("\n=== Raw team names in 2026 ===")
for table in tables_with_team_and_year:
    rows = con.execute("SELECT DISTINCT team FROM " + table + " WHERE year=2026").fetchall()
    for row in rows:
        raw = row['team']
        clean = clean_team_name(raw)
        if raw != clean:
            print('  ' + table + ': "' + raw + '" -> "' + clean + '"')

# Apply team name standardization
for table in tables_with_team_and_year:
    rows = con.execute("SELECT DISTINCT team FROM " + table + " WHERE year=2026").fetchall()
    for row in rows:
        raw = row['team']
        clean = clean_team_name(raw)
        if raw != clean:
            con.execute("UPDATE " + table + " SET team=? WHERE year=2026 AND team=?", (clean, raw))
            print('  Fixed ' + table + ': "' + raw + '" -> "' + clean + '"')

con.commit()

# ============================================================
# 2. FIX HAAS - Remove OCO and HIR, keep only BEA and CAM
# ============================================================
print("\n=== FIXING HAAS ===")
haas_drivers_to_remove = ['OCO', 'HIR']
# Tables that have 'team' column
tables_with_team = ['results', 'qualifying', 'practice', 'sprint', 'sprint_qualifying']
for driver in haas_drivers_to_remove:
    for table in tables_with_team:
        result = con.execute("DELETE FROM " + table + " WHERE year=2026 AND team='Haas' AND driver=?", (driver,))
        if result.rowcount > 0:
            print('  Deleted ' + driver + ' from ' + table + ' (' + str(result.rowcount) + ' rows)')

con.commit()

# ============================================================
# 3. FIX RED BULL / RACING BULLS TEAM NAMES AND DRIVERS
# ============================================================
print("\n=== FIXING RED BULL / RACING BULLS ===")

# Team name standardization already done above
# Now fix driver assignments for 2026

# Correct 2026 lineups:
# Red Bull: VER, LAW
# Racing Bulls: TSU, HAD

# Remove HAD from Red Bull (HAD should be at Racing Bulls)
for table in tables_with_team:
    result = con.execute("DELETE FROM " + table + " WHERE year=2026 AND team='Red Bull' AND driver=?", ('HAD',))
    if result.rowcount > 0:
        print('  Deleted HAD from ' + table + ' (' + str(result.rowcount) + ' rows)')

# Remove LAW from Racing Bulls (LAW is at Red Bull)
for table in tables_with_team:
    result = con.execute("DELETE FROM " + table + " WHERE year=2026 AND team='Racing Bulls' AND driver=?", ('LAW',))
    if result.rowcount > 0:
        print('  Deleted LAW from ' + table + ' (' + str(result.rowcount) + ' rows)')

# Remove LIN from Racing Bulls (if exists)
for table in tables_with_team:
    result = con.execute("DELETE FROM " + table + " WHERE year=2026 AND team='Racing Bulls' AND driver=?", ('LIN',))
    if result.rowcount > 0:
        print('  Deleted LIN from ' + table + ' (' + str(result.rowcount) + ' rows)')

con.commit()

# ============================================================
# 4. VERIFY FINAL STATE
# ============================================================
print("\n=== VERIFICATION AFTER FIXES ===")

for table_name in ['results', 'qualifying', 'practice']:
    print('\n--- ' + table_name + ' 2026 ---')
    teams = con.execute("""
        SELECT team, GROUP_CONCAT(DISTINCT driver) as drivers, COUNT(DISTINCT driver) as cnt
        FROM """ + table_name + """ 
        WHERE year=2026
        GROUP BY team
        ORDER BY team
    """).fetchall()
    for r in teams:
        print('  ' + r["team"] + ': ' + r["drivers"] + ' (' + str(r["cnt"]) + ' drivers)')

con.close()
import datetime