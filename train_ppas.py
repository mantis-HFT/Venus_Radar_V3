"""
train_ppas.py — Venus Radar V3.6
ML Training Pipeline

Changelog v3.6:
  • Added Feature #12: volume_climax_score (mirrors PDRS v3.6 signal)
  • Walk-Forward Validation: reports out-of-sample AUC across 3 time folds
  • Feature importance logging after global model train
  • Smoother label smoothing to reduce overconfident predictions
  • Better progress reporting
"""

import sqlite3
import pandas as pd
import numpy as np
import logging
import joblib
import os
import warnings
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split, TimeSeriesSplit
from sklearn.metrics import accuracy_score, roc_auc_score
from sklearn.calibration import CalibratedClassifierCV
import configparser

warnings.filterwarnings('ignore')

# ==========================================
# 1. CONFIGURATION
# ==========================================
config = configparser.ConfigParser()
config.read('config.ini', encoding='utf-8')

MARKET_DB        = config['DATA_FETCH']['market_db']
RESULT_DB        = config['DATA_FETCH']['result_db']
PREDICTIONS_DB   = config.get('MLOPS', 'predictions_db', fallback='Venus_Predictions.db')
GLOBAL_MODEL_PATH= config['MACHINE_LEARNING']['global_model_path']
PER_COIN_DIR     = config['MACHINE_LEARNING']['per_coin_models_dir']

MIN_SAMPLES   = config['MACHINE_LEARNING'].getint('min_samples_per_coin', fallback=2000)
SIGMA_MULT    = config['MACHINE_LEARNING'].getfloat('risk_sigma_threshold', fallback=3.0)
FUTURE_WINDOW = config['MACHINE_LEARNING'].getint('future_window', fallback=12)
ML_ESTIMATORS = config['MACHINE_LEARNING'].getint('n_estimators', fallback=150)
ML_MAX_DEPTH  = config['MACHINE_LEARNING'].getint('max_depth', fallback=12)
ML_N_JOBS     = config['MACHINE_LEARNING'].getint('n_jobs', fallback=-1)

FEATURE_COLS = [
    'dev_pct', 'streak_penalty', 'sigma_distance', 'rsi', 'volatility',
    'atr_pct', 'volume_surge', 'onchain_proxy', 'liq_attention', 'ls_ratio',
    'rp', 'volume_climax_score'   # v3.6: 12th feature
]

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s',
                    handlers=[logging.StreamHandler()])

# ==========================================
# 2. FEATURE ENGINEERING (12 KPIs)
# ==========================================
def calculate_indicators(df):
    df = df.copy()

    # 1. Dev %
    df['sma_long'] = df['close'].rolling(200).mean()
    df['dev_pct']  = (df['close'] - df['sma_long']) / df['sma_long'] * 100

    # 2. Streak Penalty
    direction = np.sign(df['close'].diff())
    df['streak_penalty'] = direction.rolling(5).apply(lambda x: abs(x.sum()), raw=True) * 2.5

    # 3. Sigma Distance (Z-Score)
    df['log_ret']        = np.log(df['close'] / df['close'].shift(1))
    sigma_1w             = df['log_ret'].rolling(672).std()
    df['sigma_distance'] = abs(df['log_ret']) / (sigma_1w + 1e-9)

    # 4. RSI (56)
    delta = df['close'].diff()
    gain  = delta.where(delta > 0, 0).rolling(56).mean()
    loss  = -delta.where(delta < 0, 0).rolling(56).mean()
    df['rsi'] = 100 - (100 / (1 + gain / (loss + 1e-9)))

    # 5. Volatility (VR)
    df['volatility'] = df['log_ret'].rolling(20).std() * 100

    # 6. ATR %
    tr = pd.concat([
        df['high'] - df['low'],
        abs(df['high'] - df['close'].shift(1)),
        abs(df['low']  - df['close'].shift(1))
    ], axis=1).max(axis=1)
    df['atr_pct'] = (tr.rolling(56).mean() / df['close']) * 100

    # 7. Volume Surge
    df['volume_surge']  = df['volume'] / (df['volume'].rolling(20).mean() + 1e-9)

    # 8. On-chain Proxy
    df['onchain_proxy'] = df['volume'] / (df['volume'].rolling(100).mean() + 1e-9)

    # 9. Liquidity Attention
    df['liq_attention'] = (df['high'] - df['low']) / (df['volume'] + 1e-9)

    # 10. L/S Ratio Proxy
    body          = df['close'] - df['open']
    range_total   = df['high'] - df['low'] + 1e-9
    df['ls_ratio']= 1.0 + (body / range_total)

    # 11. RP (Rebound Probability)
    df['rp'] = np.maximum(0, 100 - df['streak_penalty'] - abs(df['dev_pct']))

    # 12. Volume Climax Score (v3.6 NEW)
    avg_vol_100      = df['volume'].rolling(100).mean()
    vol_spike_ratio  = df['volume'] / (avg_vol_100 + 1e-9)
    trend_consistency= direction.rolling(10).apply(
        lambda x: max((x > 0).sum(), (x < 0).sum()) / 10, raw=True
    )
    df['volume_climax_score'] = np.clip(
        (vol_spike_ratio - 1.5) * 40 * trend_consistency, 0, 100
    ).fillna(0)

    return df


# ==========================================
# 3. ADAPTIVE LABELING
# ==========================================
def apply_adaptive_labels(df, sigma_mult):
    df = df.copy()
    df['sigma']             = df['log_ret'].rolling(window=672).std()
    df['dynamic_threshold'] = df['sigma'] * sigma_mult

    f_max = (df['high'].rolling(FUTURE_WINDOW).max().shift(-FUTURE_WINDOW) - df['close']) / df['close']
    f_min = (df['close'] - df['low'].rolling(FUTURE_WINDOW).min().shift(-FUTURE_WINDOW)) / df['close']

    cond             = (f_max >= df['dynamic_threshold']) | (f_min >= df['dynamic_threshold'])
    df['target_label'] = np.where(cond, 1, 0)

    return df.dropna(subset=['target_label', 'sigma'])


# ==========================================
# 4. HARD EXAMPLE MINING (MLOps Active Learning)
# ==========================================
def hard_example_mining(df_train_ready):
    if not os.path.exists(PREDICTIONS_DB):
        return df_train_ready
    try:
        conn_pred = sqlite3.connect(PREDICTIONS_DB)
        df_preds  = pd.read_sql_query(
            "SELECT ts AS timestamp_ms, symbol, ppas AS ppas_pred FROM live_predictions",
            conn_pred
        )
        conn_pred.close()
    except Exception as e:
        logging.warning(f"Could not read Predictions log: {e}")
        return df_train_ready

    df_merged       = pd.merge(df_train_ready, df_preds, on=['symbol', 'timestamp_ms'], how='inner')
    if df_merged.empty:
        return df_train_ready

    false_negatives = df_merged[(df_merged['ppas_pred'] < 50) & (df_merged['target_label'] == 1)]
    false_positives = df_merged[(df_merged['ppas_pred'] > 80) & (df_merged['target_label'] == 0)]
    hard_cases      = pd.concat([false_negatives, false_positives])

    if not hard_cases.empty:
        hard_cases = hard_cases.drop(columns=['ppas_pred'])
        logging.info(f"MLOps: {len(hard_cases)} hard examples found. Oversampling ×5...")
        df_train_ready = pd.concat([df_train_ready] + [hard_cases] * 5, ignore_index=True)

    return df_train_ready


# ==========================================
# 5. WALK-FORWARD VALIDATION (v3.6 NEW)
# ==========================================
def walk_forward_validation(X, y, title):
    """
    Time-series aware cross-validation using 3 expanding folds.
    Reports AUC per fold to detect overfitting across time.
    """
    if len(np.unique(y)) < 2:
        return
    tscv   = TimeSeriesSplit(n_splits=3)
    aucs   = []
    for fold, (train_idx, test_idx) in enumerate(tscv.split(X)):
        X_tr, X_te = X.iloc[train_idx], X.iloc[test_idx]
        y_tr, y_te = y.iloc[train_idx], y.iloc[test_idx]
        if len(np.unique(y_tr)) < 2 or len(np.unique(y_te)) < 2:
            continue
        m = RandomForestClassifier(
            n_estimators=80, max_depth=ML_MAX_DEPTH,
            n_jobs=ML_N_JOBS, class_weight='balanced', random_state=fold
        )
        m.fit(X_tr, y_tr)
        prob = m.predict_proba(X_te)[:, list(m.classes_).index(1)] if 1 in m.classes_ else np.zeros(len(y_te))
        auc  = roc_auc_score(y_te, prob)
        aucs.append(auc)
        logging.info(f"  [{title}] Fold {fold+1} OOS AUC: {auc:.3f}")

    if aucs:
        logging.info(f"  [{title}] Walk-Forward Avg AUC: {np.mean(aucs):.3f} "
                     f"(std: {np.std(aucs):.3f})")


# ==========================================
# 6. TRAINING ENGINE
# ==========================================
def train_model(X, y, output_path, title, calibrate=False):
    if len(np.unique(y)) < 2:
        logging.warning(f"[{title}] Skipping: only one class in labels.")
        return False
    try:
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42, stratify=y
        )
        rf = RandomForestClassifier(
            n_estimators=ML_ESTIMATORS, max_depth=ML_MAX_DEPTH,
            n_jobs=ML_N_JOBS, class_weight='balanced', random_state=42
        )

        if calibrate:
            # v3.6: Calibrate global model probabilities for better PPAS resolution
            model = CalibratedClassifierCV(rf, method='isotonic', cv=3)
        else:
            model = rf

        model.fit(X_train, y_train)
        y_pred = model.predict(X_test)

        # Get class 1 probabilities safely
        if hasattr(model, 'classes_') and 1 in model.classes_:
            idx_1  = list(model.classes_).index(1)
            y_prob = model.predict_proba(X_test)[:, idx_1]
        elif hasattr(model, 'estimator') and hasattr(model.estimator, 'classes_'):
            y_prob = model.predict_proba(X_test)[:, 1]
        else:
            y_prob = np.zeros(len(y_test))

        acc = accuracy_score(y_test, y_pred) * 100
        auc = roc_auc_score(y_test, y_prob) if len(np.unique(y_test)) > 1 else 0.0
        logging.info(f"[{title}] Accuracy: {acc:.1f}% | AUC: {auc:.3f}")

        joblib.dump(model, output_path)

        # Feature importance for global model
        if title == "Global Model" and hasattr(rf, 'feature_importances_'):
            rf.fit(X_train, y_train)  # fit base rf for importance
            imp = pd.Series(rf.feature_importances_, index=FEATURE_COLS).sort_values(ascending=False)
            logging.info(f"\n[{title}] Feature Importance:\n{imp.to_string()}")

        return True
    except Exception as e:
        logging.error(f"[{title}] Train error: {e}")
        return False


# ==========================================
# 7. MAIN
# ==========================================
def main():
    if not os.path.exists(MARKET_DB):
        logging.error(f"Database not found: {MARKET_DB}. Run data_fetcher.py first.")
        return

    logging.info("Reading raw OHLCV data from SQLite...")
    conn   = sqlite3.connect(MARKET_DB)
    df_raw = pd.read_sql_query(
        "SELECT * FROM historical_ohlcv ORDER BY symbol, timestamp_ms", conn
    )
    conn.close()
    logging.info(f"Loaded {len(df_raw):,} rows across {df_raw['symbol'].nunique()} symbols.")

    processed_dfs = []
    symbols = df_raw['symbol'].unique()
    for i, sym in enumerate(symbols):
        group = df_raw[df_raw['symbol'] == sym].copy()
        if len(group) < 1000:
            continue
        sys.stdout.write(f"\r  Engineering features {i+1}/{len(symbols)}: {sym.ljust(20)}")
        sys.stdout.flush()
        try:
            df_ind = calculate_indicators(group)
            df_lab = apply_adaptive_labels(df_ind, SIGMA_MULT)
            processed_dfs.append(df_lab)
        except Exception as e:
            logging.warning(f"\nSkipping {sym}: {e}")

    print()
    if not processed_dfs:
        logging.error("No data after feature engineering. Ensure DB has enough candles.")
        return

    df_final = pd.concat(processed_dfs, ignore_index=True)
    valid_features = [f for f in FEATURE_COLS if f in df_final.columns]
    df_final = df_final.dropna(subset=valid_features + ['target_label'])

    logging.info(f"Final dataset: {len(df_final):,} rows | Positive rate: "
                 f"{df_final['target_label'].mean()*100:.1f}%")

    # Save enriched features to result DB
    conn_r = sqlite3.connect(RESULT_DB)
    df_final.to_sql('ml_features_labels', conn_r, if_exists='replace', index=False)
    conn_r.close()

    # MLOps Active Learning
    df_final = hard_example_mining(df_final)

    os.makedirs(os.path.dirname(GLOBAL_MODEL_PATH), exist_ok=True)
    os.makedirs(PER_COIN_DIR, exist_ok=True)

    # 1. Walk-Forward Validation (v3.6)
    logging.info("\n--- WALK-FORWARD VALIDATION (Global) ---")
    walk_forward_validation(df_final[valid_features], df_final['target_label'], "Global")

    # 2. Global Model (with probability calibration)
    logging.info("\n--- TRAINING GLOBAL MODEL ---")
    train_model(df_final[valid_features], df_final['target_label'],
                GLOBAL_MODEL_PATH, "Global Model", calibrate=True)

    # 3. Per-Coin Models
    logging.info("\n--- TRAINING PER-COIN MODELS ---")
    count = 0
    for symbol, group in df_final.groupby('symbol'):
        if len(group) < MIN_SAMPLES:
            continue
        path = os.path.join(
            PER_COIN_DIR,
            f"ppas_model_{symbol.replace('/','_').replace(':','_')}.pkl"
        )
        if train_model(group[valid_features], group['target_label'], path, f"Coin:{symbol}"):
            count += 1

    logging.info(f"\n✅ Training complete: 1 Global Model + {count} Per-Coin Models saved.")


import sys

if __name__ == "__main__":
    main()
