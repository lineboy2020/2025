#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

WORKSPACE_ROOT = Path('/root/.openclaw/workspace')
sys.path.insert(0, str(WORKSPACE_ROOT / 'skills' / 'daily-update' / 'scripts'))

from get_zhangting import DailyZhangTingCollector

LIMIT_UP_PATH = WORKSPACE_ROOT / 'data' / 'db' / 'limit_up.parquet'
BACKFILL_DATES = [
    '2026-03-07',
    '2026-03-10',
    '2026-03-11',
    '2026-03-12',
    '2026-03-13',
    '2026-03-17',
    '2026-03-18',
]


def normalize_date_df(collector: DailyZhangTingCollector, date_str: str) -> pd.DataFrame:
    dt = pd.to_datetime(date_str).to_pydatetime()
    raw = collector.fetch_zhangting_data(dt)
    if raw is None or raw.empty:
        return pd.DataFrame()
    std = collector._standardize_data(raw, date_str)
    if std.empty:
        return std
    std = std.drop_duplicates(subset=['trade_date', 'stock_code'], keep='first').copy()
    return std


def main():
    collector = DailyZhangTingCollector()
    try:
        frames = []
        for d in BACKFILL_DATES:
            df = normalize_date_df(collector, d)
            if not df.empty:
                frames.append(df)
        if not frames:
            raise RuntimeError('回补未获取到任何涨停数据')

        new_df = pd.concat(frames, ignore_index=True)
        if LIMIT_UP_PATH.exists():
            try:
                existing = pd.read_parquet(LIMIT_UP_PATH)
                if 'trade_date' in existing.columns:
                    existing['trade_date'] = existing['trade_date'].astype(str)
                    existing = existing[~existing['trade_date'].isin(BACKFILL_DATES)].copy()
                    keep_cols = [c for c in existing.columns if c in new_df.columns]
                    existing = existing[keep_cols] if keep_cols else pd.DataFrame()
                else:
                    existing = pd.DataFrame()
            except Exception:
                existing = pd.DataFrame()
            merged = pd.concat([existing, new_df], ignore_index=True, sort=False)
        else:
            merged = new_df

        merged = merged.drop_duplicates(subset=['trade_date', 'stock_code'], keep='last').sort_values(['trade_date', 'stock_code']).reset_index(drop=True)
        merged.to_parquet(LIMIT_UP_PATH, index=False)

        summary = merged[merged['trade_date'].isin(BACKFILL_DATES)].groupby('trade_date').size().to_dict()
        print(json.dumps({'backfilled_dates': BACKFILL_DATES, 'counts': summary, 'columns': list(merged.columns)}, ensure_ascii=False, indent=2))
    finally:
        try:
            collector.logout()
        except Exception:
            pass


if __name__ == '__main__':
    main()
