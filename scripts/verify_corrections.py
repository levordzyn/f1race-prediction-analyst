"""Verify delta MAE and winner hit integer counts."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
from f1pred import db, features, model
from f1pred.xgboost_model import walk_forward_xgboost
from f1pred.lightgbm_model import walk_forward_lightgbm, LIGHTGBM_MSE_PARAMS, LIGHTGBM_L1_PARAMS, MONOTONE_CONSTRAINTS

con = db.connect()
df = features.build_features(con)
con.close()

ridge_results = model.walk_forward(df, features.ALL_FEATURES, min_train=20)
xgb_results = walk_forward_xgboost(df, features.ALL_FEATURES, min_train_races=20, shuffle=False, monotone_constraints=[1,1,1,1,1,1,-1,1,1,1,1,-1])
lgb_results = walk_forward_lightgbm(df, features.ALL_FEATURES, min_train_races=20, shuffle=False, monotone_constraints=MONOTONE_CONSTRAINTS, params=LIGHTGBM_MSE_PARAMS)

ridge_preds = ridge_results['preds']
ridge_preds['residual'] = ridge_preds['pred'] - ridge_preds['finish']

xgb_preds = xgb_results['predictions']
lgb_preds = lgb_results['predictions']

# Per-race MAE
ridge_race_mae = ridge_preds.groupby('race_idx')['residual'].apply(lambda x: np.mean(np.abs(x))).reset_index()
ridge_race_mae.columns = ['race_idx', 'mae_ridge']

xgb_race_mae = xgb_preds.groupby('race_idx')['residual'].apply(lambda x: np.mean(np.abs(x))).reset_index()
xgb_race_mae.columns = ['race_idx', 'mae_xgb']

lgb_race_mae = lgb_preds.groupby('race_idx')['residual'].apply(lambda x: np.mean(np.abs(x))).reset_index()
lgb_race_mae.columns = ['race_idx', 'mae_lgb']

merged_xgb = ridge_race_mae.merge(xgb_race_mae, on='race_idx', how='inner')
merged_lgb = ridge_race_mae.merge(lgb_race_mae, on='race_idx', how='inner')

# Delta of means (weighted by driver count)
delta_of_means_xgb = xgb_results['mae'] - ridge_results['mae']
delta_of_means_lgb = lgb_results['mae'] - ridge_results['mae']

# Mean of per-race deltas (unweighted)
mean_of_deltas_xgb = (merged_xgb['mae_xgb'] - merged_xgb['mae_ridge']).mean()
mean_of_deltas_lgb = (merged_lgb['mae_lgb'] - merged_lgb['mae_ridge']).mean()

print('DELTA MAE XGB vs Ridge:')
print('  Ridge MAE: {:.4f}'.format(ridge_results['mae']))
print('  XGB MAE: {:.4f}'.format(xgb_results['mae']))
print('  Delta (of means):     {:+.4f}'.format(delta_of_means_xgb))
print('  Mean (of per-race deltas): {:+.4f}'.format(mean_of_deltas_xgb))
print()

print('DELTA MAE LGB C2 vs Ridge:')
print('  LGB MAE: {:.4f}'.format(lgb_results['mae']))
print('  Delta (of means):     {:+.4f}'.format(delta_of_means_lgb))
print('  Mean (of per-race deltas): {:+.4f}'.format(mean_of_deltas_lgb))
print()

# Winner hit integer counts
def get_winner_hit_counts(preds):
    wins = 0
    total = 0
    for race_idx, group in preds.groupby('race_idx'):
        pred_vals = group['pred'].values
        act_vals = group['finish'].values
        if np.unique(pred_vals).size < 2:
            continue
        win = int(np.argmin(pred_vals) == np.argmin(act_vals))
        wins += win
        total += 1
    return wins, total

ridge_wins, ridge_total = get_winner_hit_counts(ridge_preds)
xgb_wins, xgb_total = get_winner_hit_counts(xgb_preds)
lgb_wins, lgb_total = get_winner_hit_counts(lgb_preds)

print('WINNER HIT INTEGER COUNTS:')
print('  Ridge: {}/{} = {:.2f}%'.format(ridge_wins, ridge_total, ridge_wins/ridge_total*100))
print('  XGB:   {}/{} = {:.2f}%'.format(xgb_wins, xgb_total, xgb_wins/xgb_total*100))
print('  LGB C2: {}/{} = {:.2f}%'.format(lgb_wins, lgb_total, lgb_wins/lgb_total*100))
print()

# Podium hit
def get_podium_hit(preds):
    hits = 0
    total = 0
    for race_idx, group in preds.groupby('race_idx'):
        pred_vals = group['pred'].values
        act_vals = group['finish'].values
        if np.unique(pred_vals).size < 2:
            continue
        k = 3
        pred_top = set(np.argsort(pred_vals)[:k])
        act_top = set(np.argsort(act_vals)[:k])
        hits += len(pred_top & act_top)
        total += k
    return hits, total

ridge_pod_hits, ridge_pod_total = get_podium_hit(ridge_preds)
xgb_pod_hits, xgb_pod_total = get_podium_hit(xgb_preds)
lgb_pod_hits, lgb_pod_total = get_podium_hit(lgb_preds)

print('PODIUM HIT INTEGER COUNTS:')
print('  Ridge: {}/{} = {:.2f}%'.format(ridge_pod_hits, ridge_pod_total, ridge_pod_hits/ridge_pod_total*100))
print('  XGB:   {}/{} = {:.2f}%'.format(xgb_pod_hits, xgb_pod_total, xgb_pod_hits/xgb_pod_total*100))
print('  LGB C2: {}/{} = {:.2f}%'.format(lgb_pod_hits, lgb_pod_total, lgb_pod_hits/lgb_pod_total*100))