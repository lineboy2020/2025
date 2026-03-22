#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
按月分段回补涨停历史数据。

作用：
1. 调用 get_zhangting.py / DailyZhangTingCollector 获取指定时间段涨停快照
2. 保存到 skills/data/snapshots/limit_up/year=YYYY/date=YYYY-MM-DD.parquet
3. 汇总生成 data/db/limit_up.parquet
4. 同步回 data/db/limit_up.duckdb
"""

from __future__ import annotations
from pathlib import Path
from datetime import datetime, timedelta
import argparse
import pandas as pd
import duckdb
import sys

WORKSPACE = Path('/root/.openclaw/workspace')
SNAPSHOT_DIR = WORKSPACE / 'skills' / 'data' / 'snapshots' / 'limit_up'
PARQUET_PATH = WORKSPACE / 'data' / 'db' / 'limit_up.parquet'
DUCKDB_PATH = WORKSPACE / 'data' / 'db' / 'limit_up.duckdb'

sys.path.insert(0, str(WORKSPACE / 'skills' / 'daily-update' / 'scripts'))
from get_zhangting import DailyZhangTingCollector  # noqa


def month_ranges(start_date: str, end_date: str):
    start = datetime.strptime(start_date, '%Y-%m-%d').date().replace(day=1)
    end = datetime.strptime(end_date, '%Y-%m-%d').date()
    cur = start
    while cur <= end:
        next_month = (cur.replace(day=28) + timedelta(days=4)).replace(day=1)
        month_end = min(end, next_month - timedelta(days=1))
        yield cur, month_end
        cur = next_month


def collect_range(start_date: str, end_date: str, force: bool = False):
    collector = DailyZhangTingCollector()
    start = datetime.strptime(start_date, '%Y-%m-%d').date()
    end = datetime.strptime(end_date, '%Y-%m-%d').date()
    day = start
    ok = 0
    while day <= end:
        out = SNAPSHOT_DIR / f'year={day.year}' / f'date={day.isoformat()}.parquet'
        if out.exists() and not force:
            day += timedelta(days=1)
            continue
        try:
            res = collector.collect_day(datetime.combine(day, datetime.min.time()), force=force)
            if res.get('status') == 'success':
                ok += 1
        except Exception as e:
            print(f'[WARN] {day} collect failed: {e}')
        day += timedelta(days=1)
    return ok


def rebuild_limit_up_parquet():
    files = sorted(SNAPSHOT_DIR.glob('year=*/date=*.parquet'))
    dfs = []
    for f in files:
        try:
            dfs.append(pd.read_parquet(f))
        except Exception as e:
            print(f'[WARN] read snapshot failed {f}: {e}')
    if not dfs:
        raise RuntimeError('no snapshot parquet files found')
    df = pd.concat(dfs, ignore_index=True)
    if 'trade_date' in df.columns:
        df['trade_date'] = pd.to_datetime(df['trade_date']).dt.strftime('%Y-%m-%d')
    if {'trade_date', 'stock_code'}.issubset(df.columns):
        df = df.drop_duplicates(subset=['trade_date', 'stock_code'], keep='last')
    df = df.sort_values(['trade_date', 'stock_code'])
    PARQUET_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(PARQUET_PATH, index=False)
    return df


def sync_duckdb_from_parquet(df: pd.DataFrame):
    con = duckdb.connect(str(DUCKDB_PATH))
    try:
        con.execute('DROP TABLE IF EXISTS limit_up')
        con.register('limit_df', df)
        con.execute('CREATE TABLE limit_up AS SELECT * FROM limit_df')
        con.unregister('limit_df')
        return con.execute('SELECT MIN(trade_date), MAX(trade_date), COUNT(*), COUNT(DISTINCT trade_date) FROM limit_up').fetchone()
    finally:
        con.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--start-date', required=True)
    ap.add_argument('--end-date', required=True)
    ap.add_argument('--force', action='store_true')
    args = ap.parse_args()

    total_ok = 0
    for s, e in month_ranges(args.start_date, args.end_date):
        print(f'== collecting {s} ~ {e} ==')
        total_ok += collect_range(s.isoformat(), e.isoformat(), force=args.force)
    df = rebuild_limit_up_parquet()
    summary = sync_duckdb_from_parquet(df)
    print({
        'snapshot_days_collected': total_ok,
        'rows': len(df),
        'min_trade_date': str(summary[0]),
        'max_trade_date': str(summary[1]),
        'distinct_days': int(summary[3]),
    })


if __name__ == '__main__':
    main()
