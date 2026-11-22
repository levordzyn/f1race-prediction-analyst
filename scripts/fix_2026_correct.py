import sys
sys.path.insert(0, r'C:\Users\outbnx_\Documents\F1 PROJECTS')
import sqlite3
import datetime
import shutil

con = sqlite3.connect(r'C:\Users\outbnx_\Documents\F1 PROJECTS\f1.db')
con.row_factory = sqlite3.Row

print("=== BACKING UP DATABASE ===")
backup_name = 'f1_backup_before_correct_2026_' + datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + '.db'
shutil.copy2(r'C:\Users\outbnx_\Documents\F1 PROJECTS\f1.db', 
             r'C:\Users\outbnx_\Documents\F1 PROJECTS\\' + backup_name)
print('Backup created: ' + backup_name)

print("\n=== CORRECTING 2026 DATA TO ACTUAL 2026 LINEUPS ===")

# ============================================================
# CORRECT 2026 LINEUPS (per user):
# - Red Bull Racing: VER + HAD (Verstappen + Hadjar)
# - Racing Bulls: LAW + LIN (Lawson + Lindblad)  
# - Haas: BEA + CAM (Bearman + Camara)
# - Team names: Official 2026 F1 names
# ============================================================

# Tables with team column
tables_with_team = ['results', 'qualifying', 'practice', 'sprint', 'sprint_qualifying', 'forecasts']

# ============================================================
# 1. RESTORE OFFICIAL 2026 TEAM NAMES (not shortened)
# ============================================================
print("\n=== RESTORING OFFICIAL 2026 TEAM NAMES ===")

team_name_fixes = {
    'Alpine': 'BWT Alpine F1 Team',
    'Sauber': 'Stake F1 Team Kick Sauber',  # or 'Kick Sauber' - 2026 name
    'Audi': 'Audi',  # Audi doesn't race in 2026, Sauber does
    'Cadillac': 'Cadillac Formula 1 Team',
    'Racing Bulls': 'Visa Cash App RB F1 Team',
    'Red Bull': 'Oracle Red Bull Racing',
    'Haas': 'Haas F1 Team',
    'Mercedes': 'Mercedes-AMG Petronas F1 Team',
    'Ferrari': 'Scuderia Ferrari HP',
    'McLaren': 'McLaren Formula 1 Team',
    'Aston Martin': 'Aston Martin Aramco F1 Team',
    'Williams': 'Williams Racing',
    'RB F1 Team': 'Visa Cash App RB F1 Team',
    'Alpine F1 Team': 'BWT Alpine F1 Team',
    'Alfa Romeo': 'Stake F1 Team Kick Sauber',  # old name
    'AlphaTauri': 'Visa Cash App RB F1 Team',  # old name
}

# Actually, let me check what the current DB has first
print("\n=== Current team names in 2026 ===")
for table in ['results', 'qualifying', 'practice', 'sprint', 'sprint_qualifying']:
    teams = con.execute("SELECT DISTINCT team FROM " + table + " WHERE year=2026").fetchall()
    for t in teams:
        print('  ' + table + ': ' + t['team'])

con.close()
import datetime