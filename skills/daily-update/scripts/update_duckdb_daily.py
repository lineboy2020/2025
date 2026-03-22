#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
DuckDB 每日增量更新脚本
======================

每日盘后运行，自动增量更新两个 DuckDB 数据库:
  - kline_eod.duckdb:      日线 + 资金流向
  - kline_intraday.duckdb: 1m + 5m + 30m (股票 + ETF)

依赖:
  - 需要先运行数据下载脚本更新原始数据:
    1. python data/src/qmt_xt.py --all           # 股票分钟数据
    2. python data/src/ETF_xt.py --incremental   # ETF分钟数据
    3. python data/src/unified_ths_downloader.py # 日线+资金流向

用法:
  python data/src/update_duckdb_daily.py              # 更新全部
  python data/src/update_duckdb_daily.py --eod        # 仅更新盘后库，用这个
  python data/src/update_duckdb_daily.py --intraday   # 仅更新盘中库
  python data/src/update_duckdb_daily.py --stats      # 仅显示统计信息

调度建议:
  Windows 任务计划程序 / Linux cron:
    每日 16:30 执行: python data/src/update_duckdb_daily.py
"""

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

# 项目路径
def resolve_project_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "config.json").exists() and (parent / "data").exists():
            return parent
    return current.parents[4]


PROJECT_ROOT = resolve_project_root()
sys.path.insert(0, str(PROJECT_ROOT))

import duckdb
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

try:
    from unified_ths_downloader import UnifiedTHSDownloader
except Exception:
    from .unified_ths_downloader import UnifiedTHSDownloader

DATA_ROOT = PROJECT_ROOT / "data"
DB_DIR = DATA_ROOT / "db"
EOD_DB_PATH = DB_DIR / "kline_eod.duckdb"
INTRADAY_DB_PATH = DB_DIR / "kline_intraday.duckdb"
LIMIT_UP_DB_PATH = DB_DIR / "limit_up.duckdb"

try:
    from data.db.build_duckdb import build_intraday
except Exception:
    build_intraday = None


def log(msg: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def load_runtime_config():
    defaults = {
        "use_ths_direct": True,
    }
    config_paths = [
        PROJECT_ROOT / ".trae" / "skills" / "openclaw-daily-update" / "config.json",
        PROJECT_ROOT / "config.json",
    ]
    for path in config_paths:
        if not path.exists():
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            section = data.get("daily_update", {})
            merged = defaults.copy()
            if isinstance(section, dict):
                merged.update({
                    "use_ths_direct": section.get("use_ths_direct", merged["use_ths_direct"]),
                })
            return merged
        except Exception:
            continue
    return defaults


def _first_existing_column(df: pd.DataFrame, candidates):
    for c in candidates:
        if c in df.columns:
            return c
    return None


def _normalize_daily_df(df: pd.DataFrame):
    if df is None or df.empty:
        return pd.DataFrame(columns=[
            "symbol", "trade_date", "open", "high", "low", "close",
            "pre_close", "volume", "amount", "change_ratio", "float_capital",
        ])
    work = df.copy()
    rename_map = {
        "stock_code": "symbol",
        "tradeDate": "trade_date",
        "changeRatio": "change_ratio",
        "preClose": "pre_close",
        "floatCapitalOfAShares": "float_capital",
    }
    work = work.rename(columns={k: v for k, v in rename_map.items() if k in work.columns})
    if "tradeTime" in work.columns and "trade_date" not in work.columns:
        work["trade_date"] = work["tradeTime"]
    if "trade_date" not in work.columns:
        return pd.DataFrame(columns=[
            "symbol", "trade_date", "open", "high", "low", "close",
            "pre_close", "volume", "amount", "change_ratio", "float_capital",
        ])
    work["trade_date"] = pd.to_datetime(work["trade_date"]).dt.date
    cols = [
        "symbol", "trade_date", "open", "high", "low", "close",
        "pre_close", "volume", "amount", "change_ratio", "float_capital",
    ]
    for c in cols:
        if c not in work.columns:
            work[c] = None
    work = work[cols].dropna(subset=["symbol", "trade_date"])
    work = work.drop_duplicates(subset=["symbol", "trade_date"], keep="last")
    return work


def _normalize_capital_flow_df(df: pd.DataFrame, trade_date: str):
    if df is None or df.empty:
        return pd.DataFrame(columns=["symbol", "trade_date", "name", "main_net_inflow"])
    work = df.copy()
    code_col = _first_existing_column(work, ["symbol", "stock_code", "thscode", "代码", "股票代码"])
    name_col = _first_existing_column(work, ["name", "stock_name", "股票简称", "简称"])
    inflow_col = _first_existing_column(
        work,
        ["main_net_inflow", "主力净流入", "主力净额", "主力资金净流入", "主力净流入额"],
    )
    if inflow_col is None:
        dynamic_candidates = [
            c for c in work.columns
            if any(k in str(c) for k in ["主力资金流向", "主力净流入", "主力资金净流入", "主力净额"])
        ]
        if dynamic_candidates:
            inflow_col = dynamic_candidates[0]
    if code_col is None:
        return pd.DataFrame(columns=["symbol", "trade_date", "name", "main_net_inflow"])
    normalized = pd.DataFrame()
    normalized["symbol"] = work[code_col].astype(str)
    normalized["trade_date"] = pd.to_datetime(trade_date).date()
    normalized["name"] = work[name_col].astype(str) if name_col else None
    normalized["main_net_inflow"] = pd.to_numeric(work[inflow_col], errors="coerce") if inflow_col else None
    normalized = normalized.dropna(subset=["symbol"]).drop_duplicates(subset=["symbol", "trade_date"], keep="last")
    return normalized


def _normalize_limit_up_df(df: pd.DataFrame, trade_date: str):
    if df is None or df.empty:
        return pd.DataFrame(columns=["trade_date", "stock_code", "stock_name", "is_limit_up"])
    work = df.copy()
    code_col = _first_existing_column(work, ["stock_code", "symbol", "thscode", "股票代码", "代码"])
    name_col = _first_existing_column(work, ["stock_name", "name", "股票简称", "简称"])
    if code_col is None:
        return pd.DataFrame(columns=["trade_date", "stock_code", "stock_name", "is_limit_up"])
    normalized = pd.DataFrame(index=work.index.copy())
    normalized["trade_date"] = str(pd.to_datetime(trade_date).date())
    normalized["stock_code"] = work[code_col].astype(str).values
    normalized["stock_name"] = work[name_col].astype(str).values if name_col else ""
    normalized["is_limit_up"] = 1
    normalized = normalized.dropna(subset=["stock_code"]).drop_duplicates(subset=["trade_date", "stock_code"], keep="last")
    return normalized.reset_index(drop=True)


def _align_to_table(conn: duckdb.DuckDBPyConnection, table_name: str, df: pd.DataFrame) -> pd.DataFrame:
    table_info = conn.execute(f"PRAGMA table_info('{table_name}')").fetchall()
    table_cols = [row[1] for row in table_info]
    aligned = df.copy()
    for col in table_cols:
        if col not in aligned.columns:
            aligned[col] = None
    return aligned[table_cols]


def _load_symbols(conn: duckdb.DuckDBPyConnection):
    try:
        rows = conn.execute("SELECT DISTINCT symbol FROM stock_basic WHERE symbol IS NOT NULL").fetchall()
        symbols = [r[0] for r in rows if r and r[0]]
        if symbols:
            return symbols
    except Exception:
        pass
    try:
        rows = conn.execute("SELECT DISTINCT symbol FROM market_daily WHERE symbol IS NOT NULL").fetchall()
        return [r[0] for r in rows if r and r[0]]
    except Exception:
        return []


def update_eod_from_ths(downloader=None):
    """更新日线和资金流向数据
    
    Args:
        downloader: UnifiedTHSDownloader实例，如果为None则创建新实例
    """
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(EOD_DB_PATH))
    
    # 如果没有传入downloader，创建新实例
    close_downloader = False
    if downloader is None:
        downloader = UnifiedTHSDownloader(use_http=False)
        close_downloader = True
    
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS market_daily (
                symbol      VARCHAR,
                trade_date  DATE,
                open        DOUBLE,
                high        DOUBLE,
                low         DOUBLE,
                close       DOUBLE,
                pre_close   DOUBLE,
                volume      DOUBLE,
                amount      DOUBLE,
                change_ratio DOUBLE,
                float_capital DOUBLE
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS capital_flow (
                symbol          VARCHAR,
                trade_date      DATE,
                name            VARCHAR,
                main_net_inflow DOUBLE
            )
        """)
        latest_day = conn.execute("SELECT MAX(trade_date) FROM market_daily").fetchone()[0]
        if latest_day:
            start_date = (latest_day + timedelta(days=1)).strftime("%Y-%m-%d")
        else:
            start_date = datetime.now().strftime("%Y-%m-%d")
        end_date = datetime.now().strftime("%Y-%m-%d")
        symbols = _load_symbols(conn)
        if symbols and start_date <= end_date:
            raw_data = downloader.download_history_data(symbols, start_date, end_date)
            daily_frames = []
            for symbol, df in raw_data.items():
                if df is None or df.empty:
                    continue
                one = df.copy()
                if "stock_code" not in one.columns:
                    one["stock_code"] = symbol
                daily_frames.append(one)
            if daily_frames:
                daily_df = _normalize_daily_df(pd.concat(daily_frames, ignore_index=True))
                if not daily_df.empty:
                    min_day = daily_df["trade_date"].min()
                    max_day = daily_df["trade_date"].max()
                    conn.execute("DELETE FROM market_daily WHERE trade_date BETWEEN ? AND ?", [min_day, max_day])
                    conn.execute("INSERT INTO market_daily SELECT * FROM daily_df")
                    log(f"同花顺日线增量写入: {len(daily_df):,} 行")
            archive_loaded = update_capital_flow_from_zijin_archive(conn, end_date)
            if not archive_loaded:
                flow_df = _normalize_capital_flow_df(downloader.download_wc_data(f"{end_date},主力净流入,A股"), end_date)
                if not flow_df.empty:
                    conn.execute("DELETE FROM capital_flow WHERE trade_date = ?", [pd.to_datetime(end_date).date()])
                    conn.execute("INSERT INTO capital_flow SELECT * FROM flow_df")
                    log(f"同花顺资金流增量写入(问财降级): {len(flow_df):,} 行")
    finally:
        conn.close()
        if close_downloader:
            downloader.logout()


def update_capital_flow_from_zijin_archive(conn, trade_date: str):
    archive_path = PROJECT_ROOT / 'data' / 'archive' / 'zijin' / f'trade_date={trade_date}' / 'data.parquet'
    if not archive_path.exists():
        return False
    df = pd.read_parquet(archive_path)
    if df is None or df.empty:
        return False
    work = pd.DataFrame({
        'symbol': df['stock_code'].astype(str),
        'trade_date': pd.to_datetime(trade_date).date(),
        'name': df['stock_name'].astype(str),
        'main_net_inflow': pd.to_numeric(df['dde_large_order_net_amount'], errors='coerce'),
    }).drop_duplicates(['symbol', 'trade_date'], keep='last')
    conn.execute("DELETE FROM capital_flow WHERE trade_date = ?", [pd.to_datetime(trade_date).date()])
    conn.register('flow_df', work)
    conn.execute("INSERT INTO capital_flow SELECT * FROM flow_df")
    conn.unregister('flow_df')
    log(f"资金流从 archive/zijin 增量写入: {len(work):,} 行")
    return True


def update_limit_up_from_ths(downloader=None):
    """更新涨停数据
    
    Args:
        downloader: UnifiedTHSDownloader实例，如果为None则创建新实例
    """
    DB_DIR.mkdir(parents=True, exist_ok=True)
    trade_date = datetime.now().strftime("%Y-%m-%d")
    conn = duckdb.connect(str(LIMIT_UP_DB_PATH))
    
    # 如果没有传入downloader，创建新实例
    close_downloader = False
    if downloader is None:
        downloader = UnifiedTHSDownloader(use_http=False)
        close_downloader = True
    
    try:
        raw_df = downloader.download_wc_data(f"{trade_date},涨停")
        limit_df = _normalize_limit_up_df(raw_df, trade_date)
        if limit_df.empty:
            log("同花顺未返回涨停数据，跳过写入")
            return
        if not conn.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_name='limit_up'").fetchone()[0]:
            conn.execute("CREATE TABLE limit_up AS SELECT * FROM limit_df LIMIT 0")
        write_df = _align_to_table(conn, "limit_up", limit_df)
        conn.execute("DELETE FROM limit_up WHERE trade_date = ?", [pd.to_datetime(trade_date).date()])
        conn.execute("INSERT INTO limit_up SELECT * FROM write_df")
        log(f"同花顺涨停增量写入: {len(write_df):,} 行")
    finally:
        conn.close()
        if close_downloader:
            downloader.logout()


def show_stats():
    """显示数据库统计信息"""
    log("=" * 60)
    log("DuckDB 数据库状态")
    log("=" * 60)

    # 盘后库
    if EOD_DB_PATH.exists():
        conn = duckdb.connect(str(EOD_DB_PATH), read_only=True)
        try:
            log(f"\n[kline_eod.duckdb] {EOD_DB_PATH.stat().st_size / 1024 / 1024:.1f} MB")
            
            # market_daily
            try:
                result = conn.execute("""
                    SELECT 
                        COUNT(*) as rows,
                        COUNT(DISTINCT symbol) as symbols,
                        MIN(trade_date) as min_date,
                        MAX(trade_date) as max_date
                    FROM market_daily
                """).fetchone()
                log(f"  market_daily: {result[0]:,} rows | {result[1]} symbols | {result[2]} ~ {result[3]}")
            except:
                log("  market_daily: (不存在)")

            # capital_flow
            try:
                result = conn.execute("""
                    SELECT 
                        COUNT(*) as rows,
                        COUNT(DISTINCT trade_date) as days,
                        MAX(trade_date) as latest
                    FROM capital_flow
                """).fetchone()
                log(f"  capital_flow: {result[0]:,} rows | {result[1]} 天 | 最新: {result[2]}")
            except:
                log("  capital_flow: (不存在)")

            # stock_basic
            try:
                cnt = conn.execute("SELECT COUNT(*) FROM stock_basic").fetchone()[0]
                log(f"  stock_basic:  {cnt:,} 只股票")
            except:
                log("  stock_basic:  (不存在)")
                
        finally:
            conn.close()
    else:
        log(f"\n[kline_eod.duckdb] 不存在")

    if LIMIT_UP_DB_PATH.exists():
        conn = duckdb.connect(str(LIMIT_UP_DB_PATH), read_only=True)
        try:
            log(f"\n[limit_up.duckdb] {LIMIT_UP_DB_PATH.stat().st_size / 1024 / 1024:.1f} MB")
            try:
                result = conn.execute("""
                    SELECT
                        COUNT(*) as rows,
                        COUNT(DISTINCT trade_date) as days,
                        MAX(trade_date) as latest
                    FROM limit_up
                """).fetchone()
                log(f"  limit_up: {result[0]:,} rows | {result[1]} 天 | 最新: {result[2]}")
            except Exception:
                log("  limit_up: (不存在)")
        finally:
            conn.close()
    else:
        log(f"\n[limit_up.duckdb] 不存在")

    # 盘中库
    if INTRADAY_DB_PATH.exists():
        conn = duckdb.connect(str(INTRADAY_DB_PATH), read_only=True)
        try:
            log(f"\n[kline_intraday.duckdb] {INTRADAY_DB_PATH.stat().st_size / 1024 / 1024:.1f} MB")
            
            for table in ["stock_1m", "stock_5m", "stock_30m", "etf_1m", "etf_5m", "etf_30m"]:
                try:
                    result = conn.execute(f"""
                        SELECT 
                            COUNT(*) as rows,
                            COUNT(DISTINCT symbol) as symbols,
                            MAX(timestamp) as latest
                        FROM {table}
                    """).fetchone()
                    log(f"  {table:12}: {result[0]:>12,} rows | {result[1]:>4} symbols | {result[2]}")
                except:
                    log(f"  {table:12}: (不存在)")
                    
        finally:
            conn.close()
    else:
        log(f"\n[kline_intraday.duckdb] 不存在")

    log("")


def run_update(
    eod_only: bool = False,
    intraday_only: bool = False,
    use_ths_direct: bool = True,
):
    """执行增量更新"""
    log("=" * 60)
    log(f"DuckDB 每日增量更新 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log("=" * 60)

    import time
    t_start = time.time()

    result = {'success': True, 'error': '', 'eod_success': None, 'intraday_success': None}

    # 更新盘后库
    if not intraday_only:
        log("\n>>> 更新盘后库 (日线 + 资金流向 + 涨停)...")
        try:
            if use_ths_direct:
                # 创建统一的downloader实例，确保所有查询在同一个SDK会话中
                downloader = UnifiedTHSDownloader(use_http=False)
                try:
                    update_eod_from_ths(downloader)
                    update_limit_up_from_ths(downloader)
                finally:
                    downloader.logout()
            else:
                raise RuntimeError('当前仅支持同花顺直连更新，请使用 --from-ths 或配置 use_ths_direct=true')
            log("盘后库更新完成")
            result['eod_success'] = True
        except Exception as e:
            result['success'] = False
            result['eod_success'] = False
            result['error'] = str(e)
            log(f"盘后库更新失败: {e}")

    # 更新盘中库
    if not eod_only:
        log("\n>>> 更新盘中库 (1m + 5m + 30m)...")
        if build_intraday is None:
            log("盘中库更新模块不可用，已跳过")
            result['intraday_success'] = None
        else:
            try:
                build_intraday(rebuild=False)
                log("盘中库更新完成")
                result['intraday_success'] = True
            except Exception as e:
                result['success'] = False
                result['intraday_success'] = False
                if not result['error']:
                    result['error'] = str(e)
                log(f"盘中库更新失败: {e}")

    elapsed = time.time() - t_start
    log(f"\n>>> 全部完成! 耗时 {elapsed:.1f}s")

    # 显示最终统计
    show_stats()
    return result


def main():
    parser = argparse.ArgumentParser(
        description="DuckDB 每日增量更新",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python update_duckdb_daily.py              # 更新全部
  python update_duckdb_daily.py --eod        # 仅更新盘后库  
  python update_duckdb_daily.py --intraday   # 仅更新盘中库
  python update_duckdb_daily.py --stats      # 仅显示统计
        """
    )
    parser.add_argument("--eod", action="store_true", help="仅更新盘后库 (kline_eod.duckdb)")
    parser.add_argument("--intraday", action="store_true", help="仅更新盘中库 (kline_intraday.duckdb)")
    parser.add_argument("--stats", action="store_true", help="仅显示统计信息")
    parser.add_argument("--from-ths", action="store_true", help="优先使用同花顺直连增量更新盘后库")
    
    args = parser.parse_args()
    runtime_cfg = load_runtime_config()
    use_ths_direct = runtime_cfg["use_ths_direct"]
    if args.from_ths:
        use_ths_direct = True

    if args.stats:
        show_stats()
    else:
        run_update(
            eod_only=args.eod,
            intraday_only=args.intraday,
            use_ths_direct=use_ths_direct,
        )


if __name__ == "__main__":
    main()
