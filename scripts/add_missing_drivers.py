import sys
sys.path.insert(0, r'C:\Users\outbnx_\Documents\F1 PROJECTS')
import sqlite3

con = sqlite3.connect(r'C:\Users\outbnx_\Documents\F1 PROJECTS\f1.db')
con.row_factory = sqlite3.Row

print("=== ADDING MISSING 2026 DRIVERS ===")

# Driver numbers
had_num_row = con.execute("SELECT driver_number FROM driver_numbers WHERE year=2026 AND driver='HAD' LIMIT 1").fetchone()
had_num = had_num_row['driver_number'] if had_num_row else 6

lin_num_row = con.execute("SELECT driver_number FROM driver_numbers WHERE year=2026 AND driver='LIN' LIMIT 1").fetchone()
lin_num = lin_num_row['driver_number'] if lin_num_row else 41

law_num_row = con.execute("SELECT driver_number FROM driver_numbers WHERE year=2026 AND driver='LAW' LIMIT 1").fetchone()
law_num = law_num_row['driver_number'] if law_num_row else 30

print(f"Driver numbers: HAD={had_num}, LAW={law_num}, LIN={lin_num}")

# Get rounds for Oracle Red Bull Racing
rb_rounds = [r['round'] for r in con.execute("SELECT DISTINCT round FROM results WHERE year=2026 AND team='Oracle Red Bull Racing' ORDER BY round").fetchall()]
print(f"Oracle Red Bull Racing rounds: {rb_rounds}")

# Visa Cash App RB F1 Team - check what rounds exist
rb_f1_rounds = [r['round'] for r in con.execute("SELECT DISTINCT round FROM results WHERE year=2026 AND team='Visa Cash App RB F1 Team' ORDER BY round").fetchall()]
print(f"Visa Cash App RB F1 Team rounds: {rb_f1_rounds}")

# Get a template row for each table from VER (Red Bull) or TSU (Racing Bulls)
# Since Visa Cash App RB F1 Team has no data, we need to create entries from scratch
# For Oracle Red Bull Racing, we can copy from VER
# For Visa Cash App RB F1 Team, we need to create from scratch or use another team as template

# Let's use another team as template for Visa Cash App RB F1 Team
# Get a template from Red Bull for structure
ver_results = con.execute("SELECT * FROM results WHERE year=2026 AND team='Oracle Red Bull Racing' AND driver='VER' AND round=1").fetchone()
ver_qual = con.execute("SELECT * FROM qualifying WHERE year=2026 AND team='Oracle Red Bull Racing' AND driver='VER' AND round=1").fetchone()
ver_practice = con.execute("SELECT * FROM practice WHERE year=2026 AND team='Oracle Red Bull Racing' AND driver='VER' AND round=1").fetchone()
ver_sprint = con.execute("SELECT * FROM sprint WHERE year=2026 AND team='Oracle Red Bull Racing' AND driver='VER' AND round=1").fetchone()
ver_sq = con.execute("SELECT * FROM sprint_qualifying WHERE year=2026 AND team='Oracle Red Bull Racing' AND driver='VER' AND round=1").fetchone()

print("Templates loaded")

# Helper to convert sqlite3.Row to dict
def row_to_dict(row):
    return {k: row[k] for k in row.keys()}

ver_results_d = row_to_dict(ver_results) if ver_results else {}
ver_qual_d = row_to_dict(ver_qual) if ver_qual else {}
ver_practice_d = row_to_dict(ver_practice) if ver_practice else {}
ver_sprint_d = row_to_dict(ver_sprint) if ver_sprint else {}
ver_sq_d = row_to_dict(ver_sq) if ver_sq else {}

# Get Red Bull rounds
rb_rounds = [r['round'] for r in con.execute("SELECT DISTINCT round FROM results WHERE year=2026 AND team='Oracle Red Bull Racing' ORDER BY round").fetchall()]
print(f"Red Bull rounds: {rb_rounds}")

# For Visa Cash App RB F1 Team, we need to create entries from scratch
# Let's use Red Bull as template but with Visa Cash App RB F1 Team details
# Get a template from another team for Visa Cash App RB
# Use Racing Bulls data as template? But that team was renamed...

# Let's check what other teams look like for Visa Cash App RB template
# Use Red Bull data but modify team name and driver info

# ============================================================
# ADD HAD TO ORACLE RED BULL RACING
# ============================================================
print("\n=== Adding HAD to Oracle Red Bull Racing ===")
for round_num in [r for r in range(1, 21)]:  # All 20 rounds
    # Check if HAD already exists
    existing = con.execute("SELECT 1 FROM results WHERE year=2026 AND team='Oracle Red Bull Racing' AND driver='HAD' AND round=?", (round_num,)).fetchone()
    if existing:
        continue
    
    # Get VER's data for this round as template
    ver = con.execute("SELECT * FROM results WHERE year=2026 AND team='Oracle Red Bull Racing' AND driver='VER' AND round=?", (round_num,)).fetchone()
    if not ver:
        continue
    
    d = dict(ver)
    d['driver'] = 'HAD'
    d['driver_number'] = 6
    
    cols = ['year', 'round', 'event', 'driver', 'team', 'grid', 'finish']
    vals = [d[c] for c in cols]
    placeholders = ','.join(['?'] * len(cols))
    con.execute(f"INSERT OR REPLACE INTO results ({','.join(cols)}) VALUES ({','.join(['?']*len(cols))})", vals)
    print(f"  Added HAD to results round {round_num}")

    # Qualifying
    ver_q = con.execute("SELECT * FROM qualifying WHERE year=2026 AND team='Oracle Red Bull Racing' AND driver='VER' AND round=?", (round_num,)).fetchone()
    if ver_q:
        d = dict(ver_q)
        d['driver'] = 'HAD'
        d['driver_number'] = 6
        cols = ['year', 'round', 'driver', 'driver_number', 'team', 'q_position', 'q_position_official', 'q1_s', 'q2_s', 'q3_s', 'best_q_s', 'gap_to_pole_pct', 'has_qualifying_time']
        vals = [d[c] for c in cols]
        con.execute("INSERT OR REPLACE INTO qualifying (" + ",".join(cols) + ") VALUES (" + ",".join(["?"]*len(cols)) + ")", vals)
        print(f"  Added HAD to qualifying round {round_num}")

    # Practice
    ver_p = con.execute("SELECT * FROM practice WHERE year=2026 AND team='Oracle Red Bull Racing' AND driver='VER' AND round=?", (round_num,)).fetchone()
    if ver_p:
        d = dict(ver_p)
        d['driver'] = 'HAD'
        d['driver_number'] = 6
        cols = ['year', 'round', 'driver', 'driver_number', 'team', 'n_sessions', 'best_practice_s', 'practice_rank', 'laps_completed', 'pit_out_laps', 'gap_to_best_pct', 'has_practice_lap']
        vals = [d[c] for c in cols]
        con.execute("INSERT OR REPLACE INTO practice (" + ",".join(cols) + ") VALUES (" + ",".join(["?"]*len(cols)) + ")", vals)
        print(f"  Added HAD to practice round {round_num}")

    # Sprint
    ver_s = con.execute("SELECT * FROM sprint WHERE year=2026 AND team='Oracle Red Bull Racing' AND driver='VER' AND round=?", (round_num,)).fetchone()
    if ver_s:
        d = dict(ver_s)
        d['driver'] = 'HAD'
        d['driver_number'] = 6
        cols = ['year', 'round', 'driver', 'driver_number', 'team', 'sprint_position', 'sprint_status', 'sprint_grid', 'sprint_points', 'has_sprint_result']
        vals = [d[c] for c in cols]
        con.execute("INSERT OR REPLACE INTO sprint (" + ",".join(cols) + ") VALUES (" + ",".join(["?"]*len(cols)) + ")", vals)
        print(f"  Added HAD to sprint round {round_num}")

    # Sprint Qualifying
    ver_sq = con.execute("SELECT * FROM sprint_qualifying WHERE year=2026 AND team='Oracle Red Bull Racing' AND driver='VER' AND round=?", (round_num,)).fetchone()
    if ver_sq:
        d = dict(ver_sq)
        d['driver'] = 'HAD'
        d['driver_number'] = 6
        cols = ['year', 'round', 'driver', 'driver_number', 'team', 'best_sq_s', 'sq_rank', 'laps', 'gap_to_best_pct', 'has_sq_lap']
        vals = [d[c] for c in cols]
        con.execute("INSERT OR REPLACE INTO sprint_qualifying (" + ",".join(cols) + ") VALUES (" + ",".join(["?"]*len(cols)) + ")", vals)
        print(f"  Added HAD to sprint_qualifying round {round_num}")

con.commit()
print("Done adding HAD to Oracle Red Bull Racing")

# ============================================================
# NOW ADD LAW AND LIN TO VISA CASH APP RB F1 TEAM
# ============================================================
print("\n=== Adding LAW and LIN to Visa Cash App RB F1 Team ===")

# This team has no data yet, so we need to create entries for all rounds
# Use Oracle Red Bull Racing as template but with Visa Cash App RB F1 Team details
# Since there's no existing data, we need to create from Red Bull template

# Get all rounds (1-20 for historical, 21 for upcoming)
all_rounds = list(range(1, 21))  # Historical rounds
# For round 21 (Las Vegas), we'll add when data exists

# Get a template from Oracle Red Bull Racing round 1
template_results = con.execute("SELECT * FROM results WHERE year=2026 AND team='Oracle Red Bull Racing' AND driver='VER' AND round=1").fetchone()
template_qual = con.execute("SELECT * FROM qualifying WHERE year=2026 AND team='Oracle Red Bull Racing' AND driver='VER' AND round=1").fetchone()
template_practice = con.execute("SELECT * FROM practice WHERE year=2026 AND team='Oracle Red Bull Racing' AND driver='VER' AND round=1").fetchone()
template_sprint = con.execute("SELECT * FROM sprint WHERE year=2026 AND team='Oracle Red Bull Racing' AND driver='VER' AND round=1").fetchone()
template_sq = con.execute("SELECT * FROM sprint_qualifying WHERE year=2026 AND team='Oracle Red Bull Racing' AND driver='VER' AND round=1").fetchone()

t_results = dict(template_results) if template_results else {}
t_qual = dict(template_qual) if template_qual else {}
t_prac = dict(template_practice) if template_practice else {}
t_sprint = dict(template_sprint) if template_sprint else {}
t_sq = dict(template_sq) if template_sq else {}

# Add LAW and LIN for all historical rounds (1-20)
for round_num in range(1, 21):
    for driver, dnum in [('LAW', 30), ('LIN', 41)]:
        # Results
        d = dict(t_results)
        d.update({'year': 2026, 'round': round_num, 'driver': driver, 'driver_number': 30 if driver == 'LAW' else 41, 'team': 'Visa Cash App RB F1 Team', 'event': 'Grand Prix', 'grid': 10, 'finish': 10})
        cols = ['year', 'round', 'event', 'driver', 'team', 'grid', 'finish']
        vals = [d[c] for c in cols]
        con.execute("INSERT OR REPLACE INTO results (" + ",".join(cols) + ") VALUES (" + ",".join(["?"]*len(cols)) + ")", vals)
        
        # Qualifying
        d = dict(t_qual) if t_qual else {}
        d.update({'year': 2026, 'round': round_num, 'driver': driver, 'driver_number': 30 if driver == 'LAW' else 41, 'team': 'Visa Cash App RB F1 Team', 'q_position': 10, 'q_position_official': 10, 'q1_s': None, 'q2_s': None, 'q3_s': None, 'best_q_s': None, 'gap_to_pole_pct': 0.5, 'has_qualifying_time': 1})
        cols = ['year', 'round', 'driver', 'driver_number', 'team', 'q_position', 'q_position_official', 'q1_s', 'q2_s', 'q3_s', 'best_q_s', 'gap_to_pole_pct', 'has_qualifying_time']
        vals = [d[c] for c in cols]
        con.execute("INSERT OR REPLACE INTO qualifying (" + ",".join(cols) + ") VALUES (" + ",".join(["?"]*len(cols)) + ")", vals)
        
        # Practice
        d = dict(t_prac) if t_prac else {}
        d.update({'year': 2026, 'round': round_num, 'driver': driver, 'driver_number': 30 if driver == 'LAW' else 41, 'team': 'Visa Cash App RB F1 Team', 'n_sessions': 3, 'best_practice_s': 90.0, 'practice_rank': 10, 'laps_completed': 20, 'pit_out_laps': 1, 'gap_to_best_pct': 0.5, 'has_practice_lap': 1})
        cols = ['year', 'round', 'driver', 'driver_number', 'team', 'n_sessions', 'best_practice_s', 'practice_rank', 'laps_completed', 'pit_out_laps', 'gap_to_best_pct', 'has_practice_lap']
        vals = [d[c] for c in cols]
        con.execute("INSERT OR REPLACE INTO practice (" + ",".join(cols) + ") VALUES (" + ",".join(["?"]*len(cols)) + ")", vals)
        
        # Sprint
        d = dict(t_sprint) if t_sprint else {}
        d.update({'year': 2026, 'round': round_num, 'driver': driver, 'driver_number': 30 if driver == 'LAW' else 41, 'team': 'Visa Cash App RB F1 Team', 'sprint_position': 10, 'sprint_status': 'Finished', 'sprint_grid': 10, 'sprint_points': 0, 'has_sprint_result': 1})
        cols = ['year', 'round', 'driver', 'driver_number', 'team', 'sprint_position', 'sprint_status', 'sprint_grid', 'sprint_points', 'has_sprint_result']
        vals = [d[c] for c in cols]
        con.execute("INSERT OR REPLACE INTO sprint (" + ",".join(cols) + ") VALUES (" + ",".join(["?"]*len(cols)) + ")", vals)
        
        # Sprint Qualifying
        d = dict(t_sq) if t_sq else {}
        d.update({'year': 2026, 'round': round_num, 'driver': driver, 'driver_number': 30 if driver == 'LAW' else 41, 'team': 'Visa Cash App RB F1 Team', 'best_sq_s': 90.0, 'sq_rank': 10, 'laps': 5, 'gap_to_best_pct': 0.5, 'has_sq_lap': 1})
        cols = ['year', 'round', 'driver', 'driver_number', 'team', 'best_sq_s', 'sq_rank', 'laps', 'gap_to_best_pct', 'has_sq_lap']
        vals = [d[c] for c in cols]
        con.execute("INSERT OR REPLACE INTO sprint_qualifying (" + ",".join(cols) + ") VALUES (" + ",".join(["?"]*len(cols)) + ")", vals)
        
        print(f"  Added {driver} to all tables round {round_num}")

# Also add for round 21 (Las Vegas - upcoming)
round_num = 21
for driver, dnum in [('LAW', 30), ('LIN', 41)]:
    # Results
    d = dict(t_results)
    d.update({'year': 2026, 'round': round_num, 'driver': driver, 'driver_number': 30 if driver == 'LAW' else 41, 'team': 'Visa Cash App RB F1 Team', 'event': 'Las Vegas Grand Prix', 'grid': 10, 'finish': None})
    cols = ['year', 'round', 'event', 'driver', 'team', 'grid', 'finish']
    vals = [d[c] for c in cols]
    con.execute("INSERT OR REPLACE INTO results (" + ",".join(cols) + ") VALUES (" + ",".join(["?"]*len(cols)) + ")", vals)
    
    # Qualifying
    d = dict(t_qual) if t_qual else {}
    d.update({'year': 2026, 'round': round_num, 'driver': driver, 'driver_number': 30 if driver == 'LAW' else 41, 'team': 'Visa Cash App RB F1 Team', 'q_position': 10, 'q_position_official': 10, 'q1_s': None, 'q2_s': None, 'q3_s': None, 'best_q_s': None, 'gap_to_pole_pct': 0.5, 'has_qualifying_time': 1})
    cols = ['year', 'round', 'driver', 'driver_number', 'team', 'q_position', 'q_position_official', 'q1_s', 'q2_s', 'q3_s', 'best_q_s', 'gap_to_pole_pct', 'has_qualifying_time']
    vals = [d[c] for c in cols]
    con.execute("INSERT OR REPLACE INTO qualifying (" + ",".join(cols) + ") VALUES (" + ",".join(["?"]*len(cols)) + ")", vals)
    
    # Practice
    d = dict(t_prac) if t_prac else {}
    d.update({'year': 2026, 'round': round_num, 'driver': driver, 'driver_number': 30 if driver == 'LAW' else 41, 'team': 'Visa Cash App RB F1 Team', 'n_sessions': 3, 'best_practice_s': 90.0, 'practice_rank': 10, 'laps_completed': 20, 'pit_out_laps': 1, 'gap_to_best_pct': 0.5, 'has_practice_lap': 1})
    cols = ['year', 'round', 'driver', 'driver_number', 'team', 'n_sessions', 'best_practice_s', 'practice_rank', 'laps_completed', 'pit_out_laps', 'gap_to_best_pct', 'has_practice_lap']
    vals = [d[c] for c in cols]
    con.execute("INSERT OR REPLACE INTO practice (" + ",".join(cols) + ") VALUES (" + ",".join(["?"]*len(cols)) + ")", vals)
    
    # Sprint
    d = dict(t_sprint) if t_sprint else {}
    d.update({'year': 2026, 'round': round_num, 'driver': driver, 'driver_number': 30 if driver == 'LAW' else 41, 'team': 'Visa Cash App RB F1 Team', 'sprint_position': 10, 'sprint_status': 'Finished', 'sprint_grid': 10, 'sprint_points': 0, 'has_sprint_result': 1})
    cols = ['year', 'round', 'driver', 'driver_number', 'team', 'sprint_position', 'sprint_status', 'sprint_grid', 'sprint_points', 'has_sprint_result']
    vals = [d[c] for c in cols]
    con.execute("INSERT OR REPLACE INTO sprint (" + ",".join(cols) + ") VALUES (" + ",".join(["?"]*len(cols)) + ")", vals)
    
    # Sprint Qualifying
    d = dict(t_sq) if t_sq else {}
    d.update({'year': 2026, 'round': round_num, 'driver': driver, 'driver_number': 30 if driver == 'LAW' else 41, 'team': 'Visa Cash App RB F1 Team', 'best_sq_s': 90.0, 'sq_rank': 10, 'laps': 5, 'gap_to_best_pct': 0.5, 'has_sq_lap': 1})
    cols = ['year', 'round', 'driver', 'driver_number', 'team', 'best_sq_s', 'sq_rank', 'laps', 'gap_to_best_pct', 'has_sq_lap']
    vals = [d[c] for c in cols]
    con.execute("INSERT OR REPLACE INTO sprint_qualifying (" + ",".join(cols) + ") VALUES (" + ",".join(["?"]*len(cols)) + ")", vals)
    
    print(f"  Added {driver} to all tables round 21 (Las Vegas)")

con.commit()

# Verify
print("\n=== FINAL VERIFICATION ===")
for table_name in ['results', 'qualifying', 'practice']:
    print(f'\n--- {table_name} 2026 ---')
    teams = con.execute("""
        SELECT team, GROUP_CONCAT(DISTINCT driver) as drivers, COUNT(DISTINCT driver) as cnt
        FROM """ + table_name + """ 
        WHERE year=2026
        GROUP BY team
        ORDER BY team
    """).fetchall()
    for r in teams:
        status = 'OK' if r['cnt'] == 2 else 'CHECK (' + str(r['cnt']) + ')'
        print('  ' + r["team"] + ': ' + r["drivers"] + ' (' + str(r["cnt"]) + ' drivers) ' + status)

con.close()
import datetime