import sys
sys.path.insert(0, r'C:\Users\outbnx_\Documents\F1 PROJECTS')
from f1pred import db, features, model

con = db.connect(r'C:\Users\outbnx_\Documents\F1 PROJECTS\f1.db')
df = features.build_features(con)
con.close()

# Run walk-forward for Ridge on full features
wf = model.walk_forward(df, model.ALL_FEATURES)
print('Ridge walk-forward results:')
print('  n_races:', wf['n_races'])
print('  n_rows:', wf['n_rows'])
print('  mae:', wf['mae'])
print('  rho:', wf['rho'])
print('  winner_hit:', wf['winner_hit'])
print('  podium_hit:', wf['podium_hit'])
print('  winner_hit count:', int(wf['winner_hit'] * wf['n_races']), '/', wf['n_races'])
print('  podium_hit count:', int(wf['podium_hit'] * wf['n_rows'] / 3 * 3), '/', wf['n_rows'])

# Check per-race winner hits
per_race = wf['per_race']
print('\nPer-race winner hits:')
print(per_race[['year', 'round', 'winner_hit']].to_string(index=False))

# Count actual winner hits
winner_hits = per_race['winner_hit'].sum()
print('\nTotal winner hits:', winner_hits, 'out of', len(per_race), 'races')

# Also run for legacy (2023-2026)
df_legacy = df[df['year'] >= 2023].copy()
wf_legacy = model.walk_forward(df_legacy, model.ALL_FEATURES)
print('\n=== LEGACY 2023-2026 ===')
print('  n_races:', wf_legacy['n_races'])
print('  n_rows:', wf_legacy['n_rows'])
print('  mae:', wf_legacy['mae'])
print('  rho:', wf_legacy['rho'])
print('  winner_hit:', wf_legacy['winner_hit'])
print('  podium_hit:', wf_legacy['podium_hit'])
print('  winner_hit count:', int(wf_legacy['winner_hit'] * wf_legacy['n_races']), '/', wf_legacy['n_races'])