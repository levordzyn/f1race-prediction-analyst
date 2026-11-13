import sqlite3
import pandas as pd
import sys
sys.path.insert(0, r'C:\Users\outbnx_\Documents\F1 PROJECTS')
from f1pred import features, db

con = db.connect(r'C:\Users\outbnx_\Documents\F1 PROJECTS\f1.db')
df = features.build_features(con)
con.close()

print('Total rows:', len(df))
print('Unique races:', df['race_idx'].nunique())
print('Race idx range:', df['race_idx'].min(), 'to', df['race_idx'].max())
print('Seasons:', sorted(df['year'].unique()))

# Race distribution
race_counts = df.groupby(['year', 'round']).size().reset_index(name='count')
print('\nRaces per season:')
for yr in sorted(df['year'].unique()):
    rc = race_counts[race_counts['year'] == yr]
    print('  {}: {} races, {} rows, {}-{} cars'.format(yr, len(rc), rc['count'].sum(), rc['count'].min(), rc['count'].max()))

# Validation folds with MIN_TRAIN_RACES=20
min_train = 20
races_sorted = sorted(df['race_idx'].unique())
val_races = [r for r in races_sorted if r > min_train]
print('\nTotal races:', len(races_sorted))
print('Validation folds (race_idx > {}): {}'.format(min_train, len(val_races)))
print('Validation race_idx range:', val_races[0], 'to', val_races[-1])

# Out-of-fold rows
val_rows = df[df['race_idx'].isin(val_races)]
print('Out-of-fold driver-starts:', len(val_rows))

# Check for NaN finishes in validation
nan_finish = val_rows['finish'].isna().sum()
print('NaN finishes in validation:', nan_finish)
print('Valid validation rows:', len(val_rows) - nan_finish)

# Also check 2023-2026 subset (the "89 races" legacy)
df_legacy = df[df['year'] >= 2023].copy()
print('\n=== LEGACY 2023-2026 ===')
print('Total rows:', len(df_legacy))
print('Unique races:', df_legacy['race_idx'].nunique())
races_legacy = sorted(df_legacy['race_idx'].unique())
val_legacy = [r for r in races_legacy if r > min_train]
print('Validation folds (legacy):', len(val_legacy))
val_rows_legacy = df_legacy[df_legacy['race_idx'].isin(val_legacy)]
print('Out-of-fold driver-starts (legacy):', len(val_rows_legacy))
nan_legacy = val_rows_legacy['finish'].isna().sum()
print('Valid validation rows (legacy):', len(val_rows_legacy) - nan_legacy)
PYEOF