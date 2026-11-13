content = open(r'C:\Users\outbnx_\Documents\F1 PROJECTS\scripts\run_phase7a_linear_diagnostics.py', 'r', encoding='utf-8').read()

old = """# Fit Ridge on train
        # Filter out rows with NaN in target
        train_mask = y_train.notna()
        test_mask = y_test.notna()
        if not train_mask.any() or not test_mask.any():
            continue

        X_train_clean = X_train[train_mask]
        y_train_clean = y_train[train_mask]
        X_test_clean = X_test[test_mask]
        y_test_clean = y_test[test_mask]

        # Fit Ridge on train
        scaler = StandardScaler().fit(X_train)
        X_train_scaled = scaler.transform(X_train_clean)
        X_test_scaled = scaler.transform(X_test_clean)

        ridge = Ridge(alpha=1.0).fit(X_train_scaled, y_train_clean)
        y_pred = ridge.predict(X_test_scaled)

        # Residuals
        residuals = y_pred - y_test_clean.values
        test_residuals = pd.DataFrame({
            "year": test["year"].values,
            "round": test["round"].values,
            "driver": test["driver"].values,
            "race_idx": test["race_idx"].values,
            "pred": y_pred,
            "finish": y_test.values,
            "residual": residuals,
        })
        for feat in features.ALL_FEATURES:
            test_residuals[f"feat_{feat}"] = X_test[feat].values"""

new = """# Fit Ridge on train
        # Filter out rows with NaN in target
        train_mask = y_train.notna()
        test_mask = y_test.notna()
        if not train_mask.any() or not test_mask.any():
            continue

        X_train_clean = X_train.loc[train_mask]
        y_train_clean = y_train.loc[train_mask]
        X_test_clean = X_test.loc[test_mask]
        y_test_clean = y_test.loc[test_mask]

        # Fit Ridge on train
        scaler = StandardScaler().fit(X_train_clean)
        X_train_scaled = scaler.transform(X_train_clean)
        X_test_scaled = scaler.transform(X_test_clean)

        ridge = Ridge(alpha=1.0).fit(X_train_scaled, y_train_clean)
        y_pred = ridge.predict(X_test_scaled)

        # Residuals
        residuals = y_pred - y_test_clean.values
        test_residuals = pd.DataFrame({
            "year": test.loc[test_mask, "year"].values,
            "round": test.loc[test_mask, "round"].values,
            "driver": test.loc[test_mask, "driver"].values,
            "race_idx": test.loc[test_mask, "race_idx"].values,
            "pred": y_pred,
            "finish": y_test_clean.values,
            "residual": residuals,
        })
        for feat in features.ALL_FEATURES:
            test_residuals[f"feat_{feat}"] = X_test.loc[test_mask, feat].values"""

if old in content:
    content = content.replace(old, new)
    with open(r'C:\Users\outbnx_\Documents\F1 PROJECTS\scripts\run_phase7a_linear_diagnostics.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Replacement done')
else:
    print('Old string not found')
    idx = content.find('Fit Ridge on train')
    if idx >= 0:
        print('Found at:', idx)
        print(content[idx:idx+800])