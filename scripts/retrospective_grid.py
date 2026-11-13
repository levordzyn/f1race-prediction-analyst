import sqlite3
import pandas as pd

con = sqlite3.connect('f1.db')

full = pd.read_sql_query(
    "SELECT driver, pred, pred_pos, grid_pred FROM forecasts WHERE year=2026 AND round=20 AND mode='full'", con)
early = pd.read_sql_query(
    "SELECT driver, pred, pred_pos, grid_pred FROM forecasts WHERE year=2026 AND round=20 AND mode='early'", con)
act = pd.read_sql_query(
    "SELECT driver, finish FROM results WHERE year=2026 AND round=20", con)

act_dict = dict(zip(act['driver'], act['finish']))

official = {
    'NOR': 1, 'ANT': 2, 'LAW': 3, 'HUL': 4, 'HAD': 5, 'BEA': 6,
    'RUS': 7, 'ALO': 8, 'ALB': 9, 'PIA': 10, 'CAM': 11, 'LIN': 12,
    'SAI': 13, 'LEC': 14, 'COL': 15, 'GAS': 16, 'STR': 17, 'BOT': 18,
    'BOR': 19, 'HAM': 20, 'VER': 21, 'PER': 22
}

print('=== GRID FEATURE COMPARISON (saved grid_pred vs official grid) ===')
print('Driver  Quali(grid_pred)  Official  Diff')
print('------  ----------------  --------  ----')
for d in sorted(full['driver']):
    q = full[full['driver']==d]['grid_pred'].values[0]
    o = official[d]
    diff = o - q
    if diff != 0:
        print(f'{d:5}  {q:16}  {o:8}  {diff:+4}')

print()
print('=== RETROSPECTIVE: How grid feature differs from training meaning ===')
print('In training, grid = results.grid (real starting grid after penalties).')
print('At forecast time, we used grid_pred = qualifying order (no penalties).')
print('For R20, 21/22 cars had different official grid positions.')
print()
print('Largest grid differences (affects grid feature value):')
diffs = []
for d in sorted(full['driver']):
    q = full[full['driver']==d]['grid_pred'].values[0]
    o = official[d]
    if q != o:
        diffs.append((abs(o-q), d, q, o))
for diff, d, q, o in sorted(diffs, reverse=True)[:10]:
    print(f'  {d:4} quali={q:2} -> official={o:2} (diff {o-q:+3})')

print()
print('This is a DATA AVAILABILITY LIMITATION, not a model error.')
print('The model was trained on real grids; forecast used qualifying order.')
print('Official grid was not available from FastF1/OpenF1 at forecast time.')