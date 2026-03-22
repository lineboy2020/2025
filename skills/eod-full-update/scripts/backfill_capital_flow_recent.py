#!/usr/bin/env python3
from pathlib import Path
import duckdb
import pandas as pd

ROOT = Path('/root/.openclaw/workspace')
DB = ROOT / 'data' / 'db' / 'kline_eod.duckdb'
ZIJIN = ROOT / 'data' / 'archive' / 'zijin'
DATES = ['2026-03-17','2026-03-18','2026-03-19','2026-03-20']

con = duckdb.connect(str(DB))
try:
    con.execute("""
        CREATE TABLE IF NOT EXISTS capital_flow (
            symbol VARCHAR,
            trade_date DATE,
            name VARCHAR,
            main_net_inflow DOUBLE
        )
    """)
    total = 0
    for d in DATES:
        p = ZIJIN / f'trade_date={d}' / 'data.parquet'
        if not p.exists():
            print('missing', d, p)
            continue
        df = pd.read_parquet(p)
        work = pd.DataFrame({
            'symbol': df['stock_code'].astype(str),
            'trade_date': pd.to_datetime(d).date(),
            'name': df['stock_name'].astype(str),
            'main_net_inflow': pd.to_numeric(df['dde_large_order_net_amount'], errors='coerce'),
        }).drop_duplicates(['symbol','trade_date'], keep='last')
        con.execute('DELETE FROM capital_flow WHERE trade_date = ?', [pd.to_datetime(d).date()])
        con.register('tmp_cf', work)
        con.execute('INSERT INTO capital_flow SELECT * FROM tmp_cf')
        con.unregister('tmp_cf')
        total += len(work)
        print('loaded', d, len(work))
    print('summary', con.execute("SELECT MIN(trade_date), MAX(trade_date), COUNT(*), COUNT(DISTINCT symbol), COUNT(DISTINCT trade_date) FROM capital_flow").fetchone())
    print('recent', con.execute("SELECT trade_date, COUNT(*) FROM capital_flow GROUP BY 1 ORDER BY 1 DESC LIMIT 10").fetchall())
finally:
    con.close()
