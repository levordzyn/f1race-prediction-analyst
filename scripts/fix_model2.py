import re

with open(r'C:\Users\outbnx_\Documents\F1 PROJECTS\f1pred\model.py', 'r') as f:
    content = f.read()

old = '''def _predict(train: pd.DataFrame, test: pd.DataFrame, cols: list[str],
             rng: np.random.Generator | None) -> tuple[np.ndarray, np.ndarray | None]:
    """Fit on `train` (scaler inside the fold) and predict `test`.

    `rng` not None => training labels are shuffled first. That is the sanity
    check: the features stay put and only the target is scrambled, so a
    pipeline with any leakage would still look fine while this collapses.
    """
    ytr = train[TARGET].to_numpy(dtype=float)
    if rng is not None:
        rng.shuffle(ytr)

    if not cols:
        # Intercept-only reference: always predicts the training mean.
        return np.full(len(test), ytr.mean()), None

    scaler = StandardScaler().fit(train[cols])      # TRAIN statistics only
    model = Ridge(alpha=RIDGE_ALPHA).fit(scaler.transform(train[cols]), ytr)
    return model.predict(scaler.transform(test[cols])), model.coef_.copy()'''

new = '''def _predict(train: pd.DataFrame, test: pd.DataFrame, cols: list[str],
              rng: np.random.Generator | None) -> tuple[np.ndarray, np.ndarray | None]:
    """Fit on `train` (scaler inside the fold) and predict `test`.

    `rng` not None => training labels are shuffled first. That is the sanity
    check: the features stay put and only the target is scrambled, so a
    pipeline with any leakage would still look fine while this collapses.
    """
    # Filter out rows with NaN finish (DNS drivers) from training data
    train_finite = train[np.isfinite(train[TARGET])]
    ytr = train_finite[TARGET].to_numpy(dtype=float)
    if rng is not None:
        rng.shuffle(ytr)

    if not cols:
        # Intercept-only reference: always predicts the training mean.
        return np.full(len(test), ytr.mean()), None

    scaler = StandardScaler().fit(train_finite[cols])      # TRAIN statistics only
    model = Ridge(alpha=RIDGE_ALPHA).fit(scaler.transform(train_finite[cols]), ytr)
    return model.predict(scaler.transform(test[cols])), model.coef_.copy()'''

if old in content:
    content = content.replace(old, new)
    with open(r'C:\Users\outbnx_\Documents\F1 PROJECTS\f1pred\model.py', 'w') as f:
        f.write(content)
    print('Replacement done')
else:
    print('Old string not found')
    # Show context around _predict
    idx = content.find('def _predict')
    if idx >= 0:
        print('Found at:', idx)
        print(content[idx:idx+600])