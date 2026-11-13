import sqlite3
con = sqlite3.connect('f1.db')
# Delete practice step for 2018 so it gets re-fetched
con.execute('DELETE FROM fetch_log WHERE year=2018 AND step="practice"')
con.execute('DELETE FROM practice WHERE year=2018')
con.commit()
print('Cleared 2018 practice data and fetch_log')
con.close()