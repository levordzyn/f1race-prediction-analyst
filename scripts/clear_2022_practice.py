import sqlite3
con = sqlite3.connect('f1.db')
con.execute('DELETE FROM fetch_log WHERE year=2022 AND step="practice"')
con.execute('DELETE FROM practice WHERE year=2022')
con.commit()
print('Cleared 2022 practice data and fetch_log')
con.close()