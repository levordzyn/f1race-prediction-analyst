import sys
sys.path.insert(0, r'C:\Users\outbnx_\Documents\F1 PROJECTS')
import sqlite3

con = sqlite3.connect(r'C:\Users\outbnx_\Documents\F1 PROJECTS\f1.db')
con.row_factory = sqlite3.Row

print("=== ADDING HAD TO RACING BULLS 2026 ===")

# Check current Racing Bulls drivers in 2026
for table in ['results', 'qualifying', 'practice', 'sprint', 'sprint_qualifying']:
    drivers = con.execute("""
        SELECT DISTINCT driver FROM """ + table + """ 
        WHERE year=2026 AND team='Racing Bulls'
    """).fetchall()
    print(f'{table}: {[d["driver"] for d in drivers]}')

# Get HAD's driver_number
had_num_row = con.execute("""
    SELECT driver_number FROM driver_numbers 
    WHERE year=2026 AND driver='HAD'
    LIMIT 1
""").fetchone()
had_num = had_num_row['driver_number'] if had_num_row else 11
print(f"\nHAD driver_number: {had_num}")

# Check what rounds TSU exists in for each table
for table in ['results', 'qualifying', 'practice', 'sprint', 'sprint_qualifying']:
    ts_rounds = con.execute("""
        SELECT DISTINCT round FROM """ + table + """ 
        WHERE year=2026 AND team='Racing Bulls' AND driver='TSU'
        ORDER BY round
    """).fetchall()
    if ts_rounds:
        print(f'{table}: TSU in rounds {[r["round"] for r in ts_rounds]}')

# Table schemas for inserts
table_cols = {
    'results': ['year', 'round', 'event', 'driver', 'team', 'grid', 'finish'],
    'qualifying': ['year', 'round', 'driver', 'driver_number', 'team', 'q_position', 'q_position_official', 'q1_s', 'q2_s', 'q3_s', 'best_q_s', 'gap_to_pole_pct', 'has_qualifying_time'],
    'practice': ['year', 'round', 'driver', 'driver_number', 'team', 'n_sessions', 'best_practice_s', 'practice_rank', 'laps_completed', 'pit_out_laps', 'gap_to_best_pct', 'has_practice_lap'],
    'sprint': ['year', 'round', 'driver', 'driver_number', 'team', 'sprint_position', 'sprint_status', 'sprint_grid', 'sprint_points', 'has_sprint_result'],
    'sprint_qualifying': ['year', 'round', 'driver', 'driver_number', 'team', 'best_sq_s', 'sq_rank', 'laps', 'gap_to_best_pct', 'has_sq_lap'],
}

# For each table, add HAD for rounds where TSU exists
for table in ['results', 'qualifying', 'practice', 'sprint', 'sprint_qualifying']:
    ts_rounds = con.execute("""
        SELECT DISTINCT round FROM """ + table + """ 
        WHERE year=2026 AND team='Racing Bulls' AND driver='TSU'
        ORDER BY round
    """).fetchall()
    
    if not ts_rounds:
        continue
        
    print(f'\n{table}: TSU in rounds {[r["round"] for r in ts_rounds]}')
    
    # Get TSU's data for first round as template
    first_round = ts_rounds[0]['round']
    ts_data = con.execute("""
        SELECT * FROM """ + table + """ 
        WHERE year=2026 AND team='Racing Bulls' AND driver='TSU' AND round=?
    """, (first_round,)).fetchone()
    
    if not ts_data:
        print(f'  No TSU data found for {table} round {first_round}')
        continue
    
    # For each round where TSU exists, add HAD if not present
    for r in ts_rounds:
        round_num = r['round']
        
        # Check if HAD already exists for this round
        existing = con.execute("""
            SELECT 1 FROM """ + table + """ 
            WHERE year=2026 AND team='Racing Bulls' AND driver='HAD' AND round=?
        """, (round_num,)).fetchone()
        
        if existing:
            print(f'  HAD already exists in {table} round {round_num}')
            continue
        
        # Get TSU's data for this specific round
        ts_round_data = con.execute("""
            SELECT * FROM """ + table + """ 
            WHERE year=2026 AND team='Racing Bulls' AND driver='TSU' AND round=?
        """, (round_num,)).fetchone()
        
        if not ts_round_data:
            print(f'  No TSU data for {table} round {round_num}')
            continue
        
        # Build HAD insert values based on TSU's data
        cols = table_cols[table]
        vals = []
        for col in cols:
            if col == 'driver':
                vals.append('HAD')
            elif col == 'driver_number':
                vals.append(had_num)
            elif col == 'team':
                vals.append('Racing Bulls')
            elif col == 'year':
                vals.append(2026)
            elif col == 'round':
                vals.append(round_num)
            else:
                # Copy from TSU's data
                vals.append(ts_round_data[col])
        
        placeholders = ','.join(['?'] * len(cols))
        insert_sql = 'INSERT OR REPLACE INTO ' + table + ' (' + ','.join(cols) + ') VALUES (' + placeholders + ')'
        
        try:
            con.execute(insert_sql, vals)
            print(f'  Added HAD to {table} round {round_num}')
        except Exception as e:
            print(f'  ERROR adding HAD to {table} round {round_num}: {e}')

con.commit()

# Verify
print("\n=== VERIFICATION ===")
for table in ['results', 'qualifying', 'practice']:
    drivers = con.execute("""
        SELECT DISTINCT driver FROM """ + table + """ 
        WHERE year=2026 AND team='Racing Bulls'
        ORDER BY driver
    """).fetchall()
    print(f'{table}: {[d["driver"] for d in drivers]}')

con.close()
import datetime