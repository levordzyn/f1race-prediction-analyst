import sys
sys.path.insert(0, r'C:\Users\outbnx_\Documents\F1 PROJECTS')
import sqlite3
import datetime
import shutil

con = sqlite3.connect(r'C:\Users\outbnx_\Documents\F1 PROJECTS\f1.db')
con.row_factory = sqlite3.Row

print("=== BACKING UP DATABASE ===")
backup_name = 'f1_backup_before_official_2026_' + datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + '.db'
shutil.copy2(r'C:\Users\outbnx_\Documents\F1 PROJECTS\f1.db', 
             r'C:\Users\outbnx_\Documents\F1 PROJECTS\\' + backup_name)
print('Backup created: ' + backup_name)

print("\n=== SETTING CORRECT 2026 LINEUPS & OFFICIAL TEAM NAMES ===")

# Tables with team column
tables_with_team = ['results', 'qualifying', 'practice', 'sprint', 'sprint_qualifying', 'forecasts']

# ============================================================
# OFFICIAL 2026 F1 TEAM NAMES
# ============================================================
official_team_names = {
    'Red Bull': 'Oracle Red Bull Racing',
    'Racing Bulls': 'Visa Cash App RB F1 Team',
    'Haas': 'Haas F1 Team',
    'Sauber': 'Stake F1 Team Kick Sauber',
    'Alpine': 'BWT Alpine F1 Team',
    'Red Bull': 'Oracle Red Bull Racing',
    'Racing Bulls': 'Visa Cash App RB F1 Team',
    'Haas': 'Haas F1 Team',
    'Alpine': 'BWT Alpine F1 Team',
    'Sauber': 'Stake F1 Team Kick Sauber',
    'Audi': 'Audi',  # Not in 2026
    'Cadillac': 'Cadillac Formula 1 Team',
    'Williams': 'Williams Racing',
    'Aston Martin': 'Aston Martin Aramco F1 Team',
    'Mercedes': 'Mercedes-AMG Petronas F1 Team',
    'Ferrari': 'Scuderia Ferrari HP',
    'McLaren': 'McLaren Formula 1 Team',
    'Alpine F1 Team': 'BWT Alpine F1 Team',
    'RB F1 Team': 'Visa Cash App RB F1 Team',
    'Red Bull Racing': 'Oracle Red Bull Racing',
    'Haas F1 Team': 'Haas F1 Team',
    'Cadillac F1 Team': 'Cadillac Formula 1 Team',
    'Alpine F1 Team': 'BWT Alpine F1 Team',
    'RB F1 Team': 'Visa Cash App RB F1 Team',
}

# First, fix any remaining shortened names to official names
print("\n=== STANDARDIZING TO OFFICIAL 2026 TEAM NAMES ===")
tables_with_team_and_year = ['results', 'qualifying', 'practice', 'sprint', 'sprint_qualifying', 'forecasts']

for table in ['results', 'qualifying', 'practice', 'sprint', 'sprint_qualifying', 'forecasts']:
    rows = con.execute("SELECT DISTINCT team FROM " + table + " WHERE year=2026").fetchall()
    for row in rows:
        raw = row['team']
        if raw in official_team_names:
            official = official_team_names[raw]
            if raw != official:
                con.execute("UPDATE " + table + " SET team=? WHERE year=2026 AND team=?", (official, raw))
                print('  Fixed ' + table + ': "' + raw + '" -> "' + official + '"')

con.commit()

# ============================================================
# CORRECT 2026 DRIVER LINEUPS
# ============================================================
print("\n=== SETTING CORRECT 2026 DRIVER LINEUPS ===")

# Correct 2026 lineups per user:
# Oracle Red Bull Racing: VER + HAD (Verstappen + Hadjar)
# Visa Cash App RB F1 Team: LAW + LIN (Lawson + Lindblad)  
# Haas F1 Team: BEA + CAM (Bearman + Camara)
# BWT Alpine F1 Team: COL + GAS
# Stake F1 Team Kick Sauber: BOR + HUL
# Cadillac Formula 1 Team: BOT + PER
# Williams Racing: ALB + SAI
# Aston Martin Aramco F1 Team: ALO + STR
# Mercedes-AMG Petronas F1 Team: ANT + RUS
# Scuderia Ferrari HP: HAM + LEC
# McLaren Formula 1 Team: NOR + PIA
# Visa Cash App RB F1 Team: LAW + LIN

correct_lineups = {
    'Oracle Red Bull Racing': ['VER', 'HAD'],
    'Visa Cash App RB F1 Team': ['LAW', 'LIN'],
    'Haas F1 Team': ['BEA', 'CAM'],
    'BWT Alpine F1 Team': ['COL', 'GAS'],
    'Stake F1 Team Kick Sauber': ['BOR', 'HUL'],
    'Cadillac Formula 1 Team': ['BOT', 'PER'],
    'Williams Racing': ['ALB', 'SAI'],
    'Aston Martin Aramco F1 Team': ['ALO', 'STR'],
    'Mercedes-AMG Petronas F1 Team': ['ANT', 'RUS'],
    'Scuderia Ferrari HP': ['HAM', 'LEC'],
    'McLaren Formula 1 Team': ['NOR', 'PIA'],
}

tables_with_team = ['results', 'qualifying', 'practice', 'sprint', 'sprint_qualifying']

print("\n=== FIXING DRIVER LINEUPS ===")

for team_name, correct_drivers in correct_lineups.items():
    print('\n--- ' + team_name + ' ---')
    print('  Correct drivers: ' + ', '.join(correct_drivers))
    
    for table in ['results', 'qualifying', 'practice', 'sprint', 'sprint_qualifying']:
        # Get current drivers for this team
        current = con.execute("""
            SELECT DISTINCT driver FROM """ + table + """ 
            WHERE year=2026 AND team=?
        """, (team_name,)).fetchall()
        current_drivers = [d['driver'] for d in current]
        
        # Find drivers to remove (in current but not in correct)
        to_remove = [d for d in current_drivers if d not in correct_drivers]
        for driver in to_remove:
            result = con.execute("DELETE FROM " + table + " WHERE year=2026 AND team=? AND driver=?", (team_name, driver))
            if result.rowcount > 0:
                print('  Removed ' + driver + ' from ' + table + ' (' + str(result.rowcount) + ' rows)')
        
        # Check if correct drivers are missing
        for driver in correct_drivers:
            exists = con.execute("""
                SELECT 1 FROM """ + table + """ WHERE year=2026 AND team=? AND driver=?
            """, (team_name, driver)).fetchone()
            if not exists:
                print('  MISSING ' + driver + ' in ' + table + ' - would need to add')

con.commit()

# ============================================================
# VERIFICATION
# ============================================================
print("\n=== FINAL VERIFICATION ===")
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
        status = 'OK' if r['cnt'] == 2 else 'CHECK (' + str(r['cnt']) + ')'
        print('  ' + r["team"] + ': ' + r["drivers"] + ' (' + str(r["cnt"]) + ' drivers) ' + status)

con.close()
import datetime