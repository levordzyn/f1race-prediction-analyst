"""Exact numbers verification."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from f1pred import db, features, model
from f1pred.xgboost_model import walk_forward_xgboost
from f1pred.lightgbm_model import walk_forward_lightgbm, LIGHTGBM_MSE_PARAMS, LIGHTGBM_L1_PARAMS, MONOTONE_CONSTRAINTS

con = db.connect()
df = features.build_features(con)
con.close()

ridge_results = model.walk_forward(df, features.ALL_FEATURES, min_train=20)
xgb_results = walk_forward_xgboost(df, features.ALL_FEATURES, min_train_races=20, shuffle=False, monotone_constraints=[1,1,1,1,1,1,-1,1,1,1,1,-1])
lgb_results = walk_forward_lightgbm(df, features.ALL_FEATURES, min_train_races=20, shuffle=False, monotone_constraints=MONOTONE_CONSTRAINTS, params=LIGHTGBM_MSE_PARAMS)
lgb_c1_results = walk_forward_lightgbm(df, features.ALL_FEATURES, min_train_races=20, shuffle=False, monotone_constraints=None, params=LIGHTGBM_L1_PARAMS)

def get_overfit(results):
    if "train_mae_per_fold" in results and "test_mae_per_fold" in results:
        train_mae = sum(results["train_mae_per_fold"]) / len(results["train_mae_per_fold"])
        test_mae = sum(results["test_mae_per_fold"]) / len(results["test_mae_per_fold"])
        return test_mae - train_mae
    return None

print("Ridge:")
print("  MAE: {:.4f}".format(ridge_results["mae"]))
print("  rho: {:.4f}".format(ridge_results["rho"]))
print("  winner_hit: {:.4f}".format(ridge_results["winner_hit"]))
print("  podium_hit: {:.4f}".format(ridge_results["podium_hit"]))
ridge_overfit = get_overfit(ridge_results)
if ridge_overfit is not None:
    print("  overfit: {:.4f}".format(ridge_overfit))
else:
    print("  overfit: N/A (Ridge walk_forward doesn't return train/test per fold)")
print()

print("XGBoost (corrected):")
print("  MAE: {:.4f}".format(xgb_results["mae"]))
print("  rho: {:.4f}".format(xgb_results["spearman"]))
print("  winner_hit: {:.4f}".format(xgb_results["winner_hit"]))
print("  podium_hit: {:.4f}".format(xgb_results["podium_hit"]))
print("  overfit: {:.4f}".format(get_overfit(xgb_results)))
print()

print("LightGBM C2:")
print("  MAE: {:.4f}".format(lgb_results["mae"]))
print("  rho: {:.4f}".format(lgb_results["spearman"]))
print("  winner_hit: {:.4f}".format(lgb_results["winner_hit"]))
print("  podium_hit: {:.4f}".format(lgb_results["podium_hit"]))
print("  overfit: {:.4f}".format(get_overfit(lgb_results)))
print()

print("LightGBM C1 (regression_l1):")
print("  MAE: {:.4f}".format(lgb_c1_results["mae"]))
print("  rho: {:.4f}".format(lgb_c1_results["spearman"]))
print("  winner_hit: {:.4f}".format(lgb_c1_results["winner_hit"]))
print("  podium_hit: {:.4f}".format(lgb_c1_results["podium_hit"]))
print("  overfit: {:.4f}".format(get_overfit(lgb_c1_results)))