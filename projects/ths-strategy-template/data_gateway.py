#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, List

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT.parents[1]
CONFIG = json.loads((ROOT / 'config.json').read_text(encoding='utf-8'))
sys.path.insert(0, str(WORKSPACE / 'skills' / 'ths-data-fetcher' / 'scripts'))


class DataGateway:
    """统一数据入口：历史/实时/高频/候选池。"""

    def __init__(self):
        self.config = CONFIG
        self.duckdb_path = self.config['storage']['duckdb_path']

    def _load_http_downloader(self):
        from unified_ths_downloader import UnifiedTHSDownloader
        return UnifiedTHSDownloader(auto_login=True, use_http=True)

    def get_history(self, symbols: List[str], start_date: str, end_date: str) -> Dict[str, pd.DataFrame]:
        """历史数据统一入口：先本地 DuckDB。"""
        if not symbols:
            return {}
        con = duckdb.connect(self.duckdb_path, read_only=True)
        placeholders = ','.join(['?'] * len(symbols))
        sql = f'''
            select *
            from market_daily
            where symbol in ({placeholders})
              and trade_date >= ?
              and trade_date <= ?
            order by symbol, trade_date
        '''
        params = list(symbols) + [start_date, end_date]
        df = con.execute(sql, params).df()
        con.close()
        results: Dict[str, pd.DataFrame] = {}
        for symbol in symbols:
            sub = df[df['symbol'] == symbol].copy() if not df.empty else pd.DataFrame()
            results[symbol] = sub.reset_index(drop=True)
        return results

    def get_realtime(self, symbols: List[str]) -> Dict[str, pd.DataFrame]:
        """实时行情统一入口：盘中仅允许 HTTP。"""
        if not symbols:
            return {}
        downloader = self._load_http_downloader()
        return downloader.download_realtime_data(stock_codes=symbols)

    def get_snapshot(self, symbol: str, trade_date: str) -> pd.DataFrame:
        """分钟/快照统一入口，默认 HTTP 高频。"""
        downloader = self._load_http_downloader()
        results = downloader.download_hf_data(
            stock_codes=[symbol],
            start_time=f'{trade_date} 09:30:00',
            end_time=f'{trade_date} 15:00:00',
            indicators='open;high;low;close;volume;amount'
        )
        return results.get(symbol, pd.DataFrame())

    def get_hf(self, symbol: str, trade_date: str) -> pd.DataFrame:
        """高频数据统一入口，默认 HTTP。"""
        downloader = self._load_http_downloader()
        results = downloader.download_hf_data(
            stock_codes=[symbol],
            start_time=f'{trade_date} 09:30:00',
            end_time=f'{trade_date} 15:00:00'
        )
        return results.get(symbol, pd.DataFrame())

    def load_candidate_pool(self, path: str) -> Dict:
        return json.loads(Path(path).read_text(encoding='utf-8'))
