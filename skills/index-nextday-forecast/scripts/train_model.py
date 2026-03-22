#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import pickle
from pathlib import Path
from datetime import datetime

import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score, classification_report
from xgboost import XGBClassifier

ROOT = Path('/root/.openclaw/workspace')
SKILL = ROOT / 'skills' / 'index-nextday-forecast'
MODELS = SKILL / 'models'
MODELS.mkdir(parents=True, exist_ok=True)

ZHISHU = ROOT / 'data' / 'db' / 'zhishu.parquet'
QINGXU = ROOT / 'data' / 'db' / 'qingxu.parquet'
EMOTION = ROOT / 'data' / 'index' / 'emotion_features.parquet'

FEATURE_COLUMNS = [
    'sh_change_pct','sh_amplitude','sh_ma5_deviation','sh_ma10_deviation','sh_ma20_deviation',
    'limit_up_count','limit_down_count','rise_count','fall_count','rise_fall_ratio','emotion_score',
    'first_board_count','continuous_board_count','explosion_rate','fractal_type','bi_direction',
    'days_since_bottom_fractal','days_since_top_fractal','limit_up_trend_3d','limit_up_trend_5d',
    'market_strength','volatility_5d'
]


def load_feature_frame():
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
    if 'changeRatio' in zh.columns and 'sh_change_pct' not in zh.columns:
        zh['sh_change_pct'] = pd.to_numeric(zh['changeRatio'], errors='coerce')
    if 'high' in zh.columns and 'low' in zh.columns and 'preClose' in zh.columns:
        zh['sh_amplitude'] = (pd.to_numeric(zh['high'], errors='coerce') - pd.to_numeric(zh['low'], errors='coerce')) / pd.to_numeric(zh['preClose'], errors='coerce').replace(0, np.nan) * 100
    keep = ['tradeDate'] + [c for c in ['sh_change_pct','sh_amplitude'] if c in zh.columns]
    zh = zh[keep]

    df = emo.merge(zh, on='tradeDate', how='left')
    for c in FEATURE_COLUMNS:
        if c not in df.columns:
            df[c] = 0
    df = df.sort_values('tradeDate').reset_index(drop=True)
    df['next_sh_change_pct'] = df['sh_change_pct'].shift(-1)
    df['target_up'] = (df['next_sh_change_pct'] > 0).astype(int)
    df = df.iloc[:-1].copy()
    return df


def main():
    df = load_feature_frame()
    X = df[FEATURE_COLUMNS].fillna(0)
    y = df['target_up']

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    model = XGBClassifier(
        n_estimators=200,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.9,
        colsample_bytree=0.9,
        objective='binary:logistic',
        eval_metric='logloss',
        random_state=42,
    )
    model.fit(X_train_scaled, y_train)
    pred = model.predict(X_test_scaled)
    acc = accuracy_score(y_test, pred)
    report = classification_report(y_test, pred, output_dict=True)

    with open(MODELS / 'index_nextday_xgb.pkl', 'wb') as f:
        pickle.dump({
            'model': model,
            'scaler': scaler,
            'feature_columns': FEATURE_COLUMNS,
            'train_time': datetime.now().isoformat(),
            'version': '1.0.0',
            'target': 'next_day_up_down',
        }, f)

    meta = {
        'train_time': datetime.now().isoformat(),
        'version': '1.0.0',
        'sample_count': int(len(df)),
        'accuracy': float(acc),
        'target_positive_ratio': float(y.mean()),
        'feature_count': len(FEATURE_COLUMNS),
        'classification_report': report,
    }
    (MODELS / 'model_meta.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
    (MODELS / 'feature_columns.json').write_text(json.dumps(FEATURE_COLUMNS, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'ok': True, 'sample_count': len(df), 'accuracy': acc, 'model_path': str(MODELS / 'index_nextday_xgb.pkl')}, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
