import sys
sys.path.insert(0, r'C:\Users\outbnx_\Documents\F1 PROJECTS')
from f1pred import db, features, model

con = db.connect(r'C:\Users\outbnx_\Documents\F1 PROJECTS\f1.db')
df = features.build_features(con)
con.close()

print('=== FULL DATASET ===')
print('Total rows:', len(df))
print('Unique races:', df['race_idx'].nunique())
races = sorted(df['race_idx'].unique())
print('Race idx range:', races[0], 'to', races[-1])

# Check how many races have all finite finishes
for r in races:
    race_df = df[df['race_idx'] == r]
    finite = race_df['finish'].notna().all()
    if not finite:
        print('Race {} ({}-{}): NOT all finite, NaN count={}'.format(
            r, int(race_df['year'].iloc[0]), int(race_df['round'].iloc[0]),
            race_df['finish'].isna().sum()
        ))

# Validation folds
min_train = 20
val_races = [r for r in races if r > min_train]
print('\nValidation races (race_idx > {}): {}'.format(min_train, len(val_races)))

# Check which validation races have all finite finishes
val_finite = 0
val_not_finite = 0
for r in val_races:
    race_df = df[df['race_idx'] == r]
    if race_df['finish'].notna().all():
        val_finite += 1
    else:
        val_not_finite += 1
        print('Validation race {} ({}-{}): NOT all finite, NaN count={}'.format(
            r, int(race_df['year'].iloc[0]), int(race_df['round'].iloc[0]),
            race_df['finish'].isna().sum()
        ))

print('Validation races with all finite finishes:', val_finite)
print('Validation races with some NaN finishes:', val_not_finite)
print('Total validation races:', len(val_races))

# Total validation rows
val_rows = df[df['race_idx'].isin(val_races)]
print('Total validation rows:', len(val_rows))
val_rows_finite = val_rows[val_rows['finish'].notna()]
print('Validation rows with finite finish:', len(val_rows_finite))