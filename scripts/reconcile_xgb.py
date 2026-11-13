import sys
sys.path.insert(0, r'C:\Users\outbnx_\Documents\F1 PROJECTS')
from f1pred import db, features
from f1pred.xgboost_model import walk_forward_xgboost, XGBOOST_PARAMS, MONOTONE_CONSTRAINTS, MIN_TRAIN_RACES

con = db.connect(r'C:\Users\outbnx_\Documents\F1 PROJECTS\f1.db')
df = features.build_features(con)
con.close()

# Run XGBoost walk-forward
xgb_results = walk_forward_xgboost(
    df,
    features.ALL_FEATURES,
    min_train_races=MIN_TRAIN_RACES,
    shuffle=False,
    monotone_constraints=MONOTONE_CONSTRAINTS,
)

xgb_preds = xgb_results["predictions"]
xgb_mae = xgb_results["mae"]
xgb_spearman = xgb_results["spearman"]
xgb_podium = xgb_results["podium_hit"]
xgb_winner = xgb_results["winner_hit"]

print('XGBoost walk-forward results:')
print('  MAE:', xgb_mae)
print('  Spearman:', xgb_spearman)
print('  Podium hit:', xgb_podium)
print('  Winner hit:', xgb_winner)

# Per-race hits
def _hits_per_race(pred_vals, act_vals):
    import numpy as np
    if np.unique(pred_vals).size < 2:
        return float("nan"), float("nan")
    win = float(int(np.argmin(pred_vals) == np.argmin(act_vals)))
    k = min(3, act_vals.size)
    pred_top = set(np.argsort(pred_vals)[:k])
    act_top = set(np.argsort(act_vals)[:k])
    return win, len(pred_top & act_top) / k

import numpy as np
per_race_hits = xgb_preds.groupby("race_idx").apply(
    lambda g: _hits_per_race(g["pred"].values, g["finish"].values)
)
winner_hits = per_race_hits.apply(lambda x: x[0]).sum()
podium_hits = per_race_hits.apply(lambda x: x[1]).sum()
n_races_scored = per_race_hits.apply(lambda x: x[0]).notna().sum()

print('  Winner hits:', winner_hits, '/', n_races_scored)
print('  Podium hits:', podium_hits, '/', n_races_scored)

# Also check legacy
df_legacy = df[df['year'] >= 2023].copy()
xgb_results_legacy = walk_forward_xgboost(
    df_legacy,
    features.ALL_FEATURES,
    min_train_races=MIN_TRAIN_RACES,
    shuffle=False,
    monotone_constraints=MONOTONE_CONSTRAINTS,
)
print('\n=== LEGACY 2023-2026 ===')
print('  MAE:', xgb_results_legacy["mae"])
print('  Winner hit:', xgb_results_legacy["winner_hit"])
print('  Podium hit:', xgb_results_legacy["podium_hit"])