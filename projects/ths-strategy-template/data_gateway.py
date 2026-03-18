#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

import pandas as pd

ROOT = Path(__file__).resolve().parent
CONFIG = json.loads((ROOT / 'config.json').read_text(encoding='utf-8'))


class DataGateway:
    """统一数据入口：历史/实时/高频/候选池。"""

    def __init__(self):
        self.config = CONFIG

    def get_history(self, symbols: List[str], start_date: str, end_date: str) -> Dict[str, pd.DataFrame]:
        """历史数据统一入口。
        默认约定：先本地 DuckDB，缺失再回补。
        当前模板阶段只返回空壳，等待具体项目接入。
        """
        return {s: pd.DataFrame() for s in symbols}

    def get_realtime(self, symbols: List[str]) -> Dict[str, pd.DataFrame]:
        """实时行情统一入口。
        默认约定：盘中仅允许 HTTP。
        """
        return {s: pd.DataFrame() for s in symbols}

    def get_snapshot(self, symbol: str, trade_date: str) -> pd.DataFrame:
        """分钟/快照统一入口，默认 HTTP。"""
        return pd.DataFrame()

    def get_hf(self, symbol: str, trade_date: str) -> pd.DataFrame:
        """高频数据统一入口，默认 HTTP。"""
        return pd.DataFrame()

    def load_candidate_pool(self, path: str) -> Dict:
        return json.loads(Path(path).read_text(encoding='utf-8'))
