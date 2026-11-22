import sys
sys.path.insert(0, r'C:\Users\outbnx_\Documents\F1 PROJECTS')
import sqlite3

con = sqlite3.connect(r'C:\Users\outbnx_\Documents\F1 PROJECTS\f1.db')
con.row_factory = sqlite3.Row

print('=== FINAL 2026 LINEUP VERIFICATION ===')
for table in ['results', 'qualifying', 'practice']:
    print('\n--- ' + table + ' 2026 ---')
    teams = con.execute('''
        SELECT team, GROUP_CONCAT(DISTINCT driver) as drivers, COUNT(DISTINCT driver) as cnt
        FROM {} WHERE year=2026 GROUP BY team ORDER BY team
    '''.format(table)).fetchall()
    for r in teams:
        status = 'OK' if r['cnt'] == 2 else 'CHECK'
        print('  ' + r['team'] + ': ' + r['drivers'] + ' (' + str(r['cnt']) + ' drivers) ' + status)

con.close()