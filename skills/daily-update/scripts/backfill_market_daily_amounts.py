#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import math
import json
import argparse
from pathlib import Path
from datetime import datetime
import duckdb
import pandas as pd

ROOT = Path('/root/.openclaw/workspace')
SCRIPT_DIR = ROOT / 'skills' / 'daily-update' / 'scripts'
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from unified_ths_downloader import UnifiedTHSDownloader

DB_PATH = ROOT / 'data' / 'db' / 'kline_eod.duckdb'
START_DATE = '20250301'
END_DATE = '20260317'
DELETE_START = '2025-03-01'
DELETE_END = '2026-03-17'
BATCH_SIZE = 520
STATE_PATH = ROOT / 'skills' / 'daily-update' / 'logs' / 'backfill_market_daily_amounts.state.json'


def log(msg: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def load_state():
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding='utf-8'))
        except Exception:
            return {}
    return {}


def save_state(state):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')


def normalize_market_df(df: pd.DataFrame) -> pd.DataFrame:
    work = df.copy()
    rename_map = {
        'stock_code': 'symbol', 'thscode': 'symbol', '股票代码': 'symbol', '代码': 'symbol',
        'open': 'open', 'high': 'high', 'low': 'low', 'close': 'close',
        'preclose': 'pre_close', 'preClose': 'pre_close', 'pre_close': 'pre_close',
        'volume': 'volume', '成交量': 'volume',
        'amount': 'amount', '成交额': 'amount',
        'changeratio': 'change_ratio', 'changeRatio': 'change_ratio', 'change_ratio': 'change_ratio',
        'time': 'trade_date', 'tradeDate': 'trade_date', 'trade_date': 'trade_date',
        'floatcapitalofashares': 'float_capital', 'floatCapitalOfAShares': 'float_capital'
    }
    work = work.rename(columns={k: v for k, v in rename_map.items() if k in work.columns})
    if 'trade_date' not in work.columns:
        raise RuntimeError(f'no trade_date in columns: {list(work.columns)}')
    work['trade_date'] = pd.to_datetime(work['trade_date']).dt.date
    cols = ['symbol','trade_date','open','high','low','close','pre_close','volume','amount','change_ratio','float_capital']
    for c in cols:
        if c not in work.columns:
            work[c] = None
    out = work[cols].dropna(subset=['symbol','trade_date']).drop_duplicates(['symbol','trade_date'], keep='last')
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--start-batch', type=int, default=None)
    parser.add_argument('--end-batch', type=int, default=None)
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args()

    con = duckdb.connect(str(DB_PATH))
    rows = con.execute("select distinct symbol from market_daily where symbol is not null order by symbol").fetchall()
    symbols = [r[0] for r in rows]
    total = len(symbols)
    total_batches = math.ceil(total / BATCH_SIZE)
    state = load_state()

    start_batch = 1
    if args.resume and state.get('last_completed_batch'):
        start_batch = int(state['last_completed_batch']) + 1
    if args.start_batch:
        start_batch = args.start_batch
    end_batch = args.end_batch or total_batches

    log(f'total symbols={total}, total_batches={total_batches}, run={start_batch}..{end_batch}')

    downloader = UnifiedTHSDownloader(use_http=False)
    try:
        for batch_no in range(start_batch, min(end_batch, total_batches) + 1):
            i = (batch_no - 1) * BATCH_SIZE
            batch = symbols[i:i+BATCH_SIZE]
            if not batch:
                break
            state.update({
                'status': 'running',
                'current_batch': batch_no,
                'batch_start_symbol': batch[0],
                'batch_end_symbol': batch[-1],
                'updated_at': datetime.now().isoformat(),
            })
            save_state(state)
            log(f'batch {batch_no}/{total_batches} start: {batch[0]} .. {batch[-1]} ({len(batch)})')
            try:
                res = downloader.download_history_data(batch, START_DATE, END_DATE)
            except Exception as e:
                log(f'batch {batch_no} download failed: {e}')
                state.update({'status': 'failed', 'failed_batch': batch_no, 'error': str(e), 'updated_at': datetime.now().isoformat()})
                save_state(state)
                raise

            frames = []
            ok_codes = 0
            for code in batch:
                df = res.get(code)
                if df is None or df.empty:
                    continue
                try:
                    norm = normalize_market_df(df)
                    if not norm.empty:
                        frames.append(norm)
                        ok_codes += 1
                except Exception as e:
                    log(f'normalize failed {code}: {e}')
            if not frames:
                log(f'batch {batch_no} no valid frames')
                state.update({'last_completed_batch': batch_no, 'updated_at': datetime.now().isoformat()})
                save_state(state)
                continue

            merged = pd.concat(frames, ignore_index=True)
            batch_codes = merged['symbol'].dropna().unique().tolist()
            con.execute(
                f"DELETE FROM market_daily WHERE symbol IN ({','.join(['?']*len(batch_codes))}) AND trade_date BETWEEN ? AND ?",
                batch_codes + [DELETE_START, DELETE_END]
            )
            con.register('batch_view', merged)
            con.execute("""
                INSERT INTO market_daily (
                    symbol, trade_date, open, high, low, close,
                    pre_close, volume, amount, change_ratio, float_capital
                )
                SELECT symbol, trade_date, open, high, low, close,
                       pre_close, volume, amount, change_ratio, float_capital
                FROM batch_view
            """)
            state.update({
                'status': 'running',
                'last_completed_batch': batch_no,
                'last_ok_codes': ok_codes,
                'last_rows': int(len(merged)),
                'updated_at': datetime.now().isoformat(),
            })
            save_state(state)
            log(f'batch {batch_no} done: ok_codes={ok_codes}, rows={len(merged)}')

        state.update({'status': 'finished', 'updated_at': datetime.now().isoformat()})
        save_state(state)
        log('backfill finished')
    finally:
        try:
            downloader.logout()
        except Exception:
            pass
        con.close()


if __name__ == '__main__':
    main()
