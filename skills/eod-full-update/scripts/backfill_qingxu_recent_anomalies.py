#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import sys

import pandas as pd

WORKSPACE_ROOT = Path('/root/.openclaw/workspace')
sys.path.insert(0, str(WORKSPACE_ROOT / 'skills' / 'daily-update' / 'scripts'))

from qingxu import update_market_emotion

QINGXU_PATH = WORKSPACE_ROOT / 'data' / 'db' / 'qingxu.parquet'
ANOMALY_START = '2026-03-01'
CHECK_COLS = ['limit_up_20pct', 'limit_down_20pct', 'explosion_count', 'explosion_10pct', 'explosion_20pct']


def find_anomaly_dates() -> list[str]:
    df = pd.read_parquet(QINGXU_PATH)
    df['tradeDate'] = df['tradeDate'].astype(str)
    mask = (df['tradeDate'] >= ANOMALY_START) & (
        (df['explosion_count'] == 0) |
        (df['limit_up_20pct'] == 0)
    )
    dates = sorted(df.loc[mask, 'tradeDate'].unique().tolist())
    return dates


def main():
    dates = find_anomaly_dates()
    print(json.dumps({'anomaly_dates': dates}, ensure_ascii=False, indent=2))
    if not dates:
        return
    result_df = update_market_emotion(
        WORKSPACE_ROOT,
        incremental=False,
        use_wencai=True,
        dates_to_fetch=dates,
    )
    repaired = result_df[result_df['tradeDate'].astype(str).isin(dates)][['tradeDate'] + CHECK_COLS]
    print(repaired.sort_values('tradeDate').to_string(index=False))


if __name__ == '__main__':
    main()
