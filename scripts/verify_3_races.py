"""Manual verification of 3 races."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from f1pred import db, features, model
from f1pred.xgboost_model import walk_forward_xgboost

con = db.connect()
df = features.build_features(con)
con.close()

ridge_results = model.walk_forward(df, features.ALL_FEATURES, min_train=20)
ridge_preds = ridge_results['preds']
ridge_preds['residual'] = ridge_preds['pred'] - ridge_preds['finish']

xgb_results = walk_forward_xgboost(
    df, features.ALL_FEATURES, min_train_races=20, shuffle=False, 
    monotone_constraints=[1,1,1,1,1,1,-1,1,1,1,1,-1]
)
xgb_preds = xgb_results['predictions']

import numpy as np

def get_hits(preds, race_idx):
    r = preds[preds['race_idx']==race_idx].sort_values('pred')
    if len(r) == 0:
        return None
    pred_vals = r['pred'].values
    act_vals = r['finish'].values
    win = int(np.argmin(pred_vals) == np.argmin(act_vals))
    k = 3
    pred_top = set(np.argsort(pred_vals)[:k])
    act_top = set(np.argsort(act_vals)[:k])
    pod = len(pred_top & act_top) / k
    return {'win': win, 'pod': pod, 'pred_top3': r.head(3)['driver'].tolist(), 'act_top3': r.nsmallest(3, 'finish')['driver'].tolist()}

# Race indices: 2023 R10 ≈ 150, 2026 R20 ≈ 193, 2024 sprint ≈ 178
sample_races = [150, 178, 193]

print("="*80)
print("MANUAL VERIFICATION: 3 RACE SAMPLES")
print("="*80)

for race_idx in sample_races:
    if race_idx not in ridge_preds['race_idx'].values:
        continue
    r = ridge_preds[ridge_preds['race_idx']==race_idx]
    x = xgb_preds[xgb_preds['race_idx']==race_idx]
    year = int(r['year'].iloc[0])
    round_num = int(r['round'].iloc[0])
    
    ridge_hits = get_hits(ridge_preds, race_idx)
    xgb_hits = get_hits(xgb_preds, race_idx)
    
    if ridge_hits and xgb_hits:
        print(f"Race {year} R{round_num} (race_idx={race_idx}):")
        print(f"  Ridge: win={ridge_hits['win']}, pod={ridge_hits['pod']:.3f}")
        print(f"    pred_top3={ridge_hits['pred_top3']}")
        print(f"    act_top3={ridge_hits['act_top3']}")
        print(f"  XGB:   win={xgb_hits['win']}, pod={xgb_hits['pod']:.3f}")
        print(f"    pred_top3={xgb_hits['pred_top3']}")
        print(f"    act_top3={xgb_hits['act_top3']}")
        
        # Position-by-position (buggy) for XGB
        x_sorted = x.sort_values('pred')
        x_act_sorted = x.sort_values('finish')
        pos_match = sum(1 for i in range(3) if x_sorted.iloc[i]['driver'] == x_act_sorted.iloc[i]['driver'])
        print(f"  XGB position-by-position (BUGGY): {pos_match}/3")
        print()

print("="*80)
print("VERIFICATION COMPLETE")