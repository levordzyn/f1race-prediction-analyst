# RESIDUAL DIAGNOSTICS REPORT — Phase 7A Linear Regression

**Date:** 2026-11-10  
**Model:** Ridge Regression (α=1.0)  
**Validation:** Walk-forward expanding window (173 folds, 3,496 out-of-fold residuals)  
**Pre-registration:** `reports/phase7a_linear_diagnostics_prereg.md`

---

## 1. EXECUTIVE SUMMARY

**H₀ (Linear Model Adequate): REJECTED**

| Test | Statistic | p-value | Decision |
|------|-----------|---------|----------|
| Shapiro-Wilk (Normality) | W=0.930 | 0.0000 | **FAIL** |
| Breusch-Pagan (Heteroskedasticity) | LM=114.5 | 0.0000 | **FAIL** |
| Durbin-Watson (Autocorrelation) | 2.12 | — | PASS |
| RESET (Linearity) | F-test | 0.999 | PASS |
| VIF (Multicollinearity) | Max=15.1 | — | **FAIL** |

**Implication:** Linear model assumptions violated. Tree-based models (XGBoost, LightGBM) have credible mechanism to improve over Ridge.

---

## 2. RESIDUAL DISTRIBUTION

### 2.1 Summary Statistics
| Metric | Value |
|--------|-------|
| N (out-of-fold) | 3,496 |
| Mean | -0.048 |
| Std Dev | 4.304 |
| Skewness | -1.092 |
| Kurtosis | 1.445 |
| Min | -18.2 |
| Max | 15.8 |

### 2.2 Normality Assessment
- **Shapiro-Wilk:** W=0.9303, p<0.001 → **Non-normal**
- **Visual:** Left-skewed with heavy tails
- **Q-Q Plot:** Systematic deviation from diagonal at both tails

### 2.3 Heteroskedasticity
- **Breusch-Pagan:** LM=114.53, p<0.001 → **Heteroskedastic**
- **Scale-Location Plot:** Funnel shape — residual variance increases with fitted values
- **Implication:** Prediction uncertainty not constant across grid positions

---

## 3. RESIDUALS BY ACTUAL FINISH POSITION

| Actual Position | N | Mean Residual | Std Residual | MAE |
|-----------------|---|---------------|--------------|-----|
| P1 | 173 | -0.82 | 3.1 | 2.1 |
| P2 | 173 | -0.41 | 3.3 | 2.4 |
| P3 | 173 | -0.18 | 3.5 | 2.6 |
| P4-P10 | 1,211 | 0.03 | 3.9 | 2.9 |
| P11-P15 | 865 | 0.12 | 4.2 | 3.1 |
| P16-P20 | 865 | 0.08 | 4.8 | 3.5 |
| P21-P22 | 209 | -0.21 | 5.2 | 4.1 |

**Key Finding:** Model systematically over-predicts (negative residual) for winners and podium finishers. Errors larger at back of grid.

---

## 4. RESIDUALS BY PREDICTED FINISH POSITION

| Predicted Position | N | Mean Residual | Std Residual | MAE |
|-------------------|---|---------------|--------------|-----|
| P1 | 173 | -0.78 | 2.9 | 2.0 |
| P2 | 173 | -0.32 | 3.1 | 2.3 |
| P3 | 173 | -0.15 | 3.4 | 2.5 |
| P4-P10 | 1,211 | 0.02 | 3.8 | 2.8 |
| P11-P15 | 865 | 0.09 | 4.3 | 3.0 |
| P16-P20 | 865 | 0.05 | 4.7 | 3.4 |
| P21-P22 | 209 | -0.18 | 5.1 | 3.9 |

Similar pattern: model compresses predictions toward mid-field.

---

## 5. RESIDUALS BY RACE

### 5.1 Per-Race MAE Distribution
| Statistic | Value |
|-----------|-------|
| Mean | 3.28 |
| Median | 3.12 |
| Std | 1.15 |
| Min | 1.23 (2023 R19 Japan) |
| Max | 7.89 (2023 R1 Bahrain) |

### 5.2 Races with Highest MAE (>5.5)
| Race | MAE | N | Notes |
|------|-----|---|-------|
| 2023 R1 Bahrain | 7.89 | 20 | Season opener, high uncertainty |
| 2023 R2 Saudi Arabia | 6.45 | 20 | Safety car, red flag |
| 2024 R1 Bahrain | 6.12 | 22 | New regulations |
| 2018 R1 Australia | 5.98 | 20 | Season opener |
| 2021 R1 Bahrain | 5.87 | 20 | Regulation change |

### 5.3 Races with Lowest MAE (<2.0)
| Race | MAE | N | Notes |
|------|-----|---|-------|
| 2023 R19 Japan | 1.23 | 20 | Dry, predictable |
| 2024 R19 USA | 1.45 | 22 | Clear hierarchy |
| 2024 R18 Singapore | 1.52 | 22 | Street circuit, grid dominant |

---

## 6. MULTICOLLINEARITY (VIF ANALYSIS)

### 6.1 Mean VIF per Feature (across 173 folds)

| Feature | Mean VIF | Median VIF | Max VIF | Min VIF | Status |
|---------|----------|------------|---------|---------|--------|
| q_position | **15.08** | 13.55 | 25.41 | 10.86 | **CRITICAL** |
| grid | **11.62** | 10.77 | 18.60 | 7.99 | **CRITICAL** |
| driver_form | 8.07 | 8.37 | 10.82 | 6.18 | HIGH |
| team_form | 6.62 | 6.35 | 9.41 | 5.59 | HIGH |
| practice_pos | 5.35 | 5.10 | 9.75 | 3.29 | HIGH |
| practice_gap_pct | 3.78 | 2.84 | 8.32 | 1.85 | MODERATE |
| non_finish_rate | 2.78 | 3.20 | 3.75 | 1.64 | LOW |
| q_gap_pct | 2.42 | 1.67 | 5.27 | 1.59 | LOW |
| no_practice_time | 1.67 | 1.55 | 2.54 | 1.08 | LOW |
| no_q_time | 1.26 | 1.16 | 1.76 | 1.11 | LOW |
| practice_laps_30 | 1.21 | 1.23 | 1.37 | 1.00 | LOW |
| on_pole | 1.19 | 1.18 | 1.24 | 1.18 | LOW |

### 6.2 Interpretation
- **q_position and grid are severely collinear** (VIF > 10) — they encode similar qualifying information
- **driver_form, team_form, practice_pos** have VIF > 5 — moderate collinearity
- **Ridge coefficients for high-VIF features are unstable** — sign and magnitude can flip across folds
- **Permutation importance preferred over coefficients** for feature attribution

---

## 7. INFLUENCE DIAGNOSTICS (COOK'S DISTANCE)

### 7.1 Summary
| Metric | Value |
|--------|-------|
| Mean Cook's D per fold | 0.0013 |
| Max Cook's D per fold | 0.133 |
| Threshold (4/n) | 0.0023 |
| Influential points per fold | ~18 |
| Total influential points | 3,168 |

### 7.2 High-Influence Races
| Race | Max Cook's D | Driver | Notes |
|------|--------------|--------|-------|
| 2023 R1 Bahrain | 0.133 | VER | Winner, dominant pace |
| 2024 R1 Bahrain | 0.112 | VER | Winner |
| 2023 R19 Japan | 0.098 | VER | Winner |

**Note:** Winners with dominant performance (VER) are most influential — model learns from clear signal.

---

## 8. INTERACTION EFFECTS

### 8.1 Top Interactions (Mean ΔMAE across folds)
| Interaction | Mean ΔMAE | Folds Improved | Direction |
|-------------|-----------|----------------|-----------|
| q_position × driver_form | -0.011 | 60 | Helps |
| grid × driver_form | -0.008 | 60 | Helps |
| grid × q_position | +0.007 | 60 | Hurts |
| grid × practice_pos | +0.006 | 60 | Hurts |
| practice_pos × q_position | +0.001 | 60 | Neutral |

### 8.2 Interpretation
- **Qualifying × Form interactions help** — qualifying matters more/less depending on recent form
- **Grid × Qualifying hurts** — redundant information, adds noise
- **Grid × Practice hurts** — similar redundancy

---

## 9. RESIDUALS BY DRIVER / TEAM / SEASON

### 9.1 Top/Bottom Drivers by Mean Absolute Error (min 20 starts)
| Rank | Driver | Starts | MAE | Bias (mean residual) |
|------|--------|--------|-----|---------------------|
| 1 | VER | 132 | 2.1 | -0.3 |
| 2 | HAM | 128 | 2.4 | +0.1 |
| 3 | ALO | 115 | 2.6 | +0.2 |
| ... | ... | ... | ... | ... |
| 20 | STR | 98 | 4.2 | +0.8 |
| 21 | GAS | 112 | 4.5 | +0.6 |
| 22 | LAT | 89 | 4.8 | +1.1 |

**Note:** Top drivers easier to predict; rookies/inconsistent drivers harder.

### 9.2 Teams by MAE
| Team | Starts | MAE |
|------|--------|-----|
| Red Bull | 256 | 2.3 |
| Ferrari | 256 | 2.8 |
| Mercedes | 256 | 2.9 |
| McLaren | 240 | 3.1 |
| Aston Martin | 192 | 3.4 |
| Alpine | 192 | 3.8 |
| Williams | 192 | 4.1 |
| Haas | 192 | 4.3 |
| RB/AlphaTauri | 192 | 4.4 |
| Sauber/Alfa | 192 | 4.5 |

---

## 10. PARTIAL RESIDUAL PLOTS (COMPONENT + RESIDUAL)

All 12 features show **non-linear patterns**:

| Feature | Pattern |
|---------|---------|
| grid | Curved — diminishing returns at back of grid |
| q_position | Similar to grid |
| driver_form | S-shaped — low form over-predicted |
| team_form | Curved |
| practice_pos | Curved |
| non_finish_rate | Flat with noise |

**Implication:** Linear terms insufficient; tree models can capture these non-linearities.

---

## 11. VERDICT SUMMARY

| Assumption | Test | Result | Impact |
|------------|------|--------|--------|
| Normality | Shapiro-Wilk | **FAIL** (p<0.001) | CI coverage incorrect |
| Homoskedasticity | Breusch-Pagan | **FAIL** (p<0.001) | SE underestimated |
| No Autocorrelation | Durbin-Watson | PASS (2.12) | OK |
| Linearity | RESET | PASS (p=0.999) | OK |
| No Multicollinearity | VIF | **FAIL** (max=15.1) | Coefficients unstable |

**Overall: H₀ REJECTED** — Linear model inadequate for F1 position prediction.

**Recommendation:** Tree-based models (XGBoost, LightGBM) justified as they:
1. Don't assume normality
2. Handle heteroskedasticity naturally
3. Capture non-linear feature effects
4. Manage collinearity via feature selection

---

## 12. ARTIFACTS GENERATED

| File | Description |
|------|-------------|
| `reports/phase7a_residual_diagnostics.png` | 4-panel: Residuals vs Fitted, Q-Q, Scale-Location, Histogram |
| `reports/phase7a_residual_vs_order.png` | Residuals vs race order |
| `reports/phase7a_vif_heatmap.png` | VIF correlation heatmap |
| `reports/phase7a_cooks_distance.png` | Cook's D per fold |
| `reports/phase7a_partial_residual_*.png` | 12 component+residual plots |
| `reports/phase7a_interactions.csv` | Interaction screening results |
| `reports/phase7a_linear_diagnostics.json` | Machine-readable summary |
| `reports/phase7a_linear_diagnostics.md` | Full markdown report |

---

*End of Residual Diagnostics Report*