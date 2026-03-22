#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import pickle
import argparse
from pathlib import Path
import pandas as pd
import numpy as np

ROOT = Path('/root/.openclaw/workspace')
SKILL = ROOT / 'skills' / 'index-nextday-forecast'
MODEL = SKILL / 'models' / 'index_nextday_xgb.pkl'
EMOTION = ROOT / 'data' / 'index' / 'emotion_features.parquet'
ZHISHU = ROOT / 'data' / 'db' / 'zhishu.parquet'

EMOTION_LABELS = {0:'冰点期',1:'启动期',2:'发酵期',3:'高潮期',4:'退潮期'}


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
    if 'changeRatio' in zh.columns and 'sh_change_pct' not in zh.columns:
        zh['sh_change_pct'] = pd.to_numeric(zh['changeRatio'], errors='coerce')
    if 'high' in zh.columns and 'low' in zh.columns and 'preClose' in zh.columns:
        zh['sh_amplitude'] = (pd.to_numeric(zh['high'], errors='coerce') - pd.to_numeric(zh['low'], errors='coerce')) / pd.to_numeric(zh['preClose'], errors='coerce').replace(0, np.nan) * 100
    keep = ['tradeDate'] + [c for c in ['sh_change_pct','sh_amplitude'] if c in zh.columns]
    zh = zh[keep]
    return emo.merge(zh, on='tradeDate', how='left').sort_values('tradeDate').reset_index(drop=True)


def explain(row, up_prob):
    reasons = []
    if row.get('emotion_label', -1) in [2,3]:
        reasons.append('情绪周期偏强')
    elif row.get('emotion_label', -1) in [0,4]:
        reasons.append('情绪周期偏弱')
    if row.get('fractal_type', 0) == 1:
        reasons.append('存在底分型信号')
    elif row.get('fractal_type', 0) == -1:
        reasons.append('存在顶分型信号')
    if row.get('bi_direction', 0) == 1:
        reasons.append('笔方向向上')
    elif row.get('bi_direction', 0) == -1:
        reasons.append('笔方向向下')
    if row.get('sh_change_pct', 0) > 0:
        reasons.append('指数当日收涨')
    else:
        reasons.append('指数当日收跌或走弱')
    direction = '看涨' if up_prob >= 0.5 else '看跌'
    return direction, reasons[:4]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--date', default=None)
    args = ap.parse_args()

    with open(MODEL, 'rb') as f:
        bundle = pickle.load(f)
    df = load_frame()
    if args.date:
        row = df[df['tradeDate'] == pd.to_datetime(args.date)].tail(1)
    else:
        row = df.tail(1)
    if row.empty:
        raise SystemExit('no data for target date')
    for c in bundle['feature_columns']:
        if c not in row.columns:
            row[c] = 0
    X = row[bundle['feature_columns']].fillna(0)
    Xs = bundle['scaler'].transform(X)
    up_prob = float(bundle['model'].predict_proba(Xs)[0][1])
    down_prob = 1 - up_prob
    r = row.iloc[0]
    direction, reasons = explain(r, up_prob)
    print(json.dumps({
        'date': str(r['tradeDate'])[:10],
        'predict_next_day': direction,
        'up_probability': round(up_prob, 4),
        'down_probability': round(down_prob, 4),
        'emotion_cycle': EMOTION_LABELS.get(int(r.get('emotion_label', -1)), '未知') if pd.notna(r.get('emotion_label', np.nan)) else '未知',
        'fractal_type': int(r.get('fractal_type', 0)) if pd.notna(r.get('fractal_type', np.nan)) else 0,
        'bi_direction': int(r.get('bi_direction', 0)) if pd.notna(r.get('bi_direction', np.nan)) else 0,
        'reasons': reasons,
        'sh_change_pct': round(float(r.get('sh_change_pct', 0)), 4),
        'emotion_score': round(float(r.get('emotion_score', 0)), 2),
    }, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
