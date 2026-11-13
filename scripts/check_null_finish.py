import sys, sqlite3
sys.path.insert(0, r'C:\Users\outbnx_\Documents\F1 PROJECTS')
import pandas as pd
con = sqlite3.connect(r'C:\Users\outbnx_\AppData\Local\Temp\opencode\test_debug.db')
con.row_factory = sqlite3.Row

# Find rows with NULL finish
null_finish = pd.read_sql_query('SELECT year, round, driver, finish FROM results WHERE finish IS NULL', con)
print('NULL finish rows:')
print(null_finish)
print()

# Check if these are DNS or something
for _, row in null_finish.iterrows():
    status = con.execute('SELECT status FROM race_status WHERE year=? AND round=? AND driver=?', (row['year'], row['round'], row['driver'])).fetchone()
    print(f'  {row["driver"]} {row["year"]} R{row["round"]}: finish={row["finish"]}, status={status["status"] if status else "NULL"}')