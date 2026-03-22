#!/usr/bin/env python3
from pathlib import Path
import duckdb

root = Path('/root/.openclaw/workspace/data/db')
parquet_path = root / 'limit_up.parquet'
duckdb_path = root / 'limit_up.duckdb'

con = duckdb.connect(str(duckdb_path))
try:
    if not parquet_path.exists():
        raise SystemExit(f'missing parquet: {parquet_path}')
    exists = con.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_name='limit_up'").fetchone()[0] > 0
    if exists:
        schema = con.execute("PRAGMA table_info('limit_up')").fetchall()
        cols = [(r[1], r[2]) for r in schema]
        src_cols = con.execute(f"DESCRIBE SELECT * FROM read_parquet('{str(parquet_path)}')").fetchall()
        src_names = {r[0] for r in src_cols}
        select_parts = []
        for name, typ in cols:
            if name in src_names:
                if name == 'trade_date':
                    select_parts.append(f"CAST(trade_date AS VARCHAR) AS \"{name}\"")
                else:
                    select_parts.append(f"CAST(\"{name}\" AS {typ}) AS \"{name}\"")
            else:
                select_parts.append(f"CAST(NULL AS {typ}) AS \"{name}\"")
        sql = ', '.join(select_parts)
        con.execute('BEGIN TRANSACTION')
        con.execute('DELETE FROM limit_up')
        con.execute(f"INSERT INTO limit_up SELECT {sql} FROM read_parquet('{str(parquet_path)}')")
        con.execute('COMMIT')
    else:
        con.execute(f"CREATE TABLE limit_up AS SELECT * FROM read_parquet('{str(parquet_path)}')")
    print(con.execute("SELECT MIN(trade_date), MAX(trade_date), COUNT(*), COUNT(DISTINCT trade_date) FROM limit_up").fetchone())
finally:
    con.close()
