#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
市场情绪模型重训练脚本（基于规则标签重建）

流程：
1. 读取 emotion_features.parquet
2. 用 predictor.py 中的规则逻辑生成 emotion_label
3. 训练 XGBoost 多分类模型
4. 输出新模型资产：
   - models/emotion_cycle_xgb_v3.pkl
   - models/feature_columns.json
   - models/model_meta.json
"""

import json
import pickle
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score, classification_report
from xgboost import XGBClassifier

SKILL_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = SKILL_ROOT.parent.parent
FEATURE_FILE = WORKSPACE_ROOT / 'data' / 'index' / 'emotion_features.parquet'
MODELS_DIR = SKILL_ROOT / 'models'
MODELS_DIR.mkdir(parents=True, exist_ok=True)

FEATURE_COLUMNS = [
    'limit_up_count','limit_down_count','limit_up_ratio','limit_up_down_ratio','first_board_count','continuous_board_count','explosion_rate',
    'rise_count','fall_count','rise_fall_ratio','rise_ratio','flat_count','sh_close','sh_change_pct','sh_volume_change','sh_amount_change',
    'sh_amplitude','sh_ma5_deviation','sh_ma10_deviation','sh_ma20_deviation','limit_up_ma5','limit_up_ma10','limit_up_ma5_dev',
    'limit_up_ma10_dev','limit_up_change_1d','limit_up_change_3d','limit_up_trend_3d','limit_up_trend_5d','limit_up_momentum_3d',
    'limit_up_momentum_5d','rise_momentum_3d','explosion_rate_ma3','explosion_trend_3d','emotion_score','market_strength','volatility_5d',
    'fractal_type','bi_direction','days_since_bottom_fractal','days_since_top_fractal'
]

EMOTION_LABELS = {0:'冰点期',1:'启动期',2:'发酵期',3:'高潮期',4:'退潮期'}


def rule_label(row):
    limit_up = row.get('limit_up_count', 0)
    limit_down = row.get('limit_down_count', 0)
    rise_fall_ratio = row.get('rise_fall_ratio', 1)
    explosion_rate = row.get('explosion_rate', 0)
    limit_up_trend = row.get('limit_up_trend_3d', 0)
    limit_up_ma5 = row.get('limit_up_ma5', limit_up)
    emotion_score = row.get('emotion_score', 50)

    # 冰点期：极弱环境
    if limit_down >= 60:
        return 0
    elif limit_up <= 20 and limit_down >= 15:
        return 0
    elif rise_fall_ratio < 0.25 and limit_down >= 20:
        return 0
    elif emotion_score <= 12 and limit_down >= 20:
        return 0

    # 高潮期：放宽阈值，避免样本过少
    elif limit_up >= 95 and limit_down <= 8 and rise_fall_ratio >= 2.0 and explosion_rate <= 0.30:
        return 3
    elif limit_up >= 80 and limit_down <= 5 and rise_fall_ratio >= 2.5 and explosion_rate <= 0.28 and limit_up_ma5 >= 60:
        return 3
    elif limit_up >= 70 and emotion_score >= 70 and rise_fall_ratio >= 2.0 and limit_up_trend >= 5:
        return 3

    # 退潮期：偏弱但未到冰点
    elif limit_up >= 40 and limit_down >= 25:
        return 4
    elif limit_up >= 60 and rise_fall_ratio < 0.7:
        return 4
    elif limit_down >= 20 and rise_fall_ratio < 0.9:
        return 4
    elif limit_up_trend < -8 and limit_down >= 15:
        return 4
    elif emotion_score < 25 and limit_down >= 12:
        return 4

    # 发酵期：主升扩散
    elif limit_up >= 70 and limit_down <= 12 and rise_fall_ratio >= 1.3 and explosion_rate <= 0.40:
        return 2
    elif limit_up >= 55 and limit_down <= 10 and rise_fall_ratio >= 2.0:
        return 2
    elif limit_up >= 85 and rise_fall_ratio >= 1.1 and emotion_score >= 45:
        return 2

    # 其余归为启动期
    else:
        return 1


def main():
    df = pd.read_parquet(FEATURE_FILE)
    df['tradeDate'] = pd.to_datetime(df['tradeDate'])
    for c in FEATURE_COLUMNS:
        if c not in df.columns:
            df[c] = 0
    df = df.sort_values('tradeDate').reset_index(drop=True)
    df['emotion_label'] = df.apply(rule_label, axis=1)
    X = df[FEATURE_COLUMNS].fillna(0)
    y = df['emotion_label']

    label_counts = y.value_counts()
    use_stratify = None if (label_counts.min() < 2 or len(label_counts) < 2) else y
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=use_stratify
    )

    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    model = XGBClassifier(
        n_estimators=200,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.9,
        colsample_bytree=0.9,
        objective='multi:softprob',
        num_class=5,
        eval_metric='mlogloss',
        random_state=42,
    )
    model.fit(X_train_scaled, y_train)

    pred = model.predict(X_test_scaled)
    acc = accuracy_score(y_test, pred)
    report = classification_report(y_test, pred, output_dict=True)

    with open(MODELS_DIR / 'emotion_cycle_xgb_v3.pkl', 'wb') as f:
        pickle.dump({
            'model': model,
            'scaler': scaler,
            'feature_columns': FEATURE_COLUMNS,
            'emotion_labels': EMOTION_LABELS,
            'train_time': datetime.now().isoformat(),
            'version': '3.0.0-rebuilt',
            'label_source': 'rule_engine_distillation_v3',
        }, f)

    (MODELS_DIR / 'feature_columns.json').write_text(
        json.dumps(FEATURE_COLUMNS, ensure_ascii=False, indent=2), encoding='utf-8'
    )
    meta = {
        'train_time': datetime.now().isoformat(),
        'version': '3.0.0-rebuilt',
        'feature_count': len(FEATURE_COLUMNS),
        'sample_count': int(len(df)),
        'label_distribution': {str(k): int(v) for k,v in y.value_counts().sort_index().items()},
        'accuracy': float(acc),
        'label_source': 'rule_engine_distillation_v3',
        'classification_report': report,
    }
    (MODELS_DIR / 'model_meta.json').write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8'
    )

    print(json.dumps({
        'ok': True,
        'sample_count': len(df),
        'accuracy': acc,
        'label_distribution': meta['label_distribution'],
        'model_path': str(MODELS_DIR / 'emotion_cycle_xgb_v3.pkl'),
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
