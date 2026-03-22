#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score
from xgboost import XGBClassifier

ROOT = Path('/root/.openclaw/workspace')
SKILL = ROOT / 'skills' / 'index-nextday-forecast'
EMOTION = ROOT / 'data' / 'index' / 'emotion_features.parquet'
ZHISHU = ROOT / 'data' / 'db' / 'zhishu.parquet'
OUT = SKILL / 'reports'
OUT.mkdir(parents=True, exist_ok=True)

FEATURE_COLUMNS = [
    'sh_change_pct','sh_amplitude','sh_ma5_deviation','sh_ma10_deviation','sh_ma20_deviation',
    'limit_up_count','limit_down_count','rise_count','fall_count','rise_fall_ratio','emotion_score',
    'first_board_count','continuous_board_count','explosion_rate','fractal_type','bi_direction',
    'days_since_bottom_fractal','days_since_top_fractal','limit_up_trend_3d','limit_up_trend_5d',
    'market_strength','volatility_5d'
]


def load_frame():
    emo = pd.read_parquet(EMOTION)
    emo['tradeDate'] = pd.to_datetime(emo['tradeDate'])
    zh = pd.read_parquet(ZHISHU)
    if 'tradeDate' in zh.columns:
        zh['tradeDate'] = pd.to_datetime(zh['tradeDate'])
    elif 'time' in zh.columns:
        zh['tradeDate'] = pd.to_datetime(zh['time'])
    if 'index_code' in zh.columns:
        zh = zh[zh['index_code'].astype(str).str.contains('000001', na=False)].copy()
    zh = zh.sort_values('tradeDate').drop_duplicates('tradeDate', keep='last')
    zh['sh_change_pct_real'] = pd.to_numeric(zh['changeRatio'], errors='coerce')
    if 'changeRatio' in zh.columns and 'sh_change_pct' not in zh.columns:
        zh['sh_change_pct'] = pd.to_numeric(zh['changeRatio'], errors='coerce')
    if 'high' in zh.columns and 'low' in zh.columns and 'preClose' in zh.columns:
        zh['sh_amplitude'] = (pd.to_numeric(zh['high'], errors='coerce') - pd.to_numeric(zh['low'], errors='coerce')) / pd.to_numeric(zh['preClose'], errors='coerce').replace(0, np.nan) * 100
    keep = ['tradeDate'] + [c for c in ['sh_change_pct','sh_amplitude','sh_change_pct_real'] if c in zh.columns]
    zh = zh[keep]
    df = emo.merge(zh, on='tradeDate', how='left')
    for c in FEATURE_COLUMNS:
        if c not in df.columns:
            df[c] = 0
    df = df.sort_values('tradeDate').reset_index(drop=True)
    df['next_sh_change_pct'] = df['sh_change_pct_real'].shift(-1)
    df['target_up'] = (df['next_sh_change_pct'] > 0).astype(int)
    return df.iloc[:-1].copy()


def fit_predict(train_df, test_df):
    X_train = train_df[FEATURE_COLUMNS].fillna(0)
    y_train = train_df['target_up']
    X_test = test_df[FEATURE_COLUMNS].fillna(0)
    y_test = test_df['target_up']
    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s = scaler.transform(X_test)
    model = XGBClassifier(
        n_estimators=200, max_depth=4, learning_rate=0.05,
        subsample=0.9, colsample_bytree=0.9,
        objective='binary:logistic', eval_metric='logloss', random_state=42
    )
    model.fit(X_train_s, y_train)
    pred = model.predict(X_test_s)
    prob = model.predict_proba(X_test_s)[:, 1]
    return pred, prob, y_test.values


def main():
    df = load_frame()
    n = len(df)
    windows = []
    # expanding windows: 60/10, 70/10, 80/10
    for train_ratio in [0.6, 0.7, 0.8]:
        train_end = int(n * train_ratio)
        test_end = min(n, train_end + max(20, int(n * 0.1)))
        if test_end - train_end < 5:
            continue
        train_df = df.iloc[:train_end].copy()
        test_df = df.iloc[train_end:test_end].copy()
        pred, prob, y_true = fit_predict(train_df, test_df)
        acc = float(accuracy_score(y_true, pred))
        base_down = np.zeros(len(y_true), dtype=int)
        base_acc = float(accuracy_score(y_true, base_down))
        windows.append({
            'train_ratio': train_ratio,
            'train_count': int(len(train_df)),
            'test_count': int(len(test_df)),
            'test_up_ratio': float(test_df['target_up'].mean()),
            'accuracy': acc,
            'always_down_acc': base_acc,
            'delta_vs_always_down': acc - base_acc,
            'test_range': [str(test_df['tradeDate'].min())[:10], str(test_df['tradeDate'].max())[:10]],
        })
    summary = {
        'sample_count': int(n),
        'windows': windows,
        'avg_accuracy': float(np.mean([w['accuracy'] for w in windows])) if windows else None,
        'avg_delta_vs_always_down': float(np.mean([w['delta_vs_always_down'] for w in windows])) if windows else None,
    }
    out = OUT / 'rolling_backtest_summary.json'
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
