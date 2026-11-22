import sys
sys.path.insert(0, r'C:\Users\outbnx_\Documents\F1 PROJECTS')
import sqlite3
import datetime
import shutil

con = sqlite3.connect(r'C:\Users\outbnx_\Documents\F1 PROJECTS\f1.db')
con.row_factory = sqlite3.Row

print("=== BACKING UP DATABASE ===")
backup_name = 'f1_backup_before_r21_fix_' + datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + '.db'
shutil.copy2(r'C:\Users\outbnx_\Documents\F1 PROJECTS\f1.db', 
             r'C:\Users\outbnx_\Documents\F1 PROJECTS\\' + backup_name)
print('Backup created: ' + backup_name)

print("\n=== REMOVING INCOMPLETE R21 RESULTS ===")
# Delete the incomplete R21 results (only 2 drivers)
for table in ['results', 'qualifying', 'practice', 'sprint', 'sprint_qualifying', 'race_status', 'driver_numbers']:
    result = con.execute("DELETE FROM " + table + " WHERE year=2026 AND round=21")
    if result.rowcount > 0:
        print('  Deleted ' + str(result.rowcount) + ' rows from ' + table)

# Also clean up sessions for R21
result = con.execute("DELETE FROM sessions WHERE year=2026 AND round=21")
if result.rowcount > 0:
    print('  Deleted ' + str(result.rowcount) + ' rows from sessions')

# Clean up fetch_log for R21
result = con.execute("DELETE FROM fetch_log WHERE year=2026 AND round=21")
if result.rowcount > 0:
    print('  Deleted ' + str(result.rowcount) + ' rows from fetch_log')

# Clean up forecasts for R21
result = con.execute("DELETE FROM forecasts WHERE year=2026 AND round=21")
if result.rowcount > 0:
    print('  Deleted ' + str(result.rowcount) + ' rows from forecasts')

con.commit()

print("\n=== VERIFICATION AFTER CLEANUP ===")
for table in ['results', 'qualifying', 'practice', 'sessions', 'fetch_log', 'forecasts']:
    count = con.execute("SELECT COUNT(*) FROM " + table + " WHERE year=2026 AND round=21").fetchone()[0]
    print(f'  {table}: {count} rows')

con.close()
import datetime
import shutil