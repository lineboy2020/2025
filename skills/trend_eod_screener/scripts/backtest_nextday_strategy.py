#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
trend_eod_screener 研究版回测脚本

目标：
1. 基于本地 DuckDB 生成候选股票
2. 引入市场情绪闸门与简化主力意图评分
3. 评估次日触达 +3/+5/+8 和 -7 止损概率
4. 分 trend / leader 两种模式输出摘要

说明：
- 当前版本优先保证可回测、可解释、可扩展
- 分钟级 14:55 数据暂不可得，研究版用当日收盘价近似尾盘买入价
- 主力意图先使用 DuckDB 可得因子做“轻量代理评分”，后续再对接 main-force-intent 全量分析
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import duckdb
import numpy as np
import pandas as pd

SKILL_DIR = Path(__file__).resolve().parents[1]
CONFIG_PATH = SKILL_DIR / 'config.v2.json'


@dataclass
class Candidate:
    trade_date: str
    symbol: str
    name: str
    mode: str
    score: float
    emotion_name: str
    topic_strength: float
    trend_score: float
    capital_score: float
    limitup_score: float
    intent_proxy_score: float
    close: float
    next_open: float
    next_high: float
    next_low: float
    next_close: float
    hit_tp3: int
    hit_tp5: int
    hit_tp8: int
    hit_sl7: int
    next_close_positive: int


class ResearchBacktester:
    def __init__(self, config_path: Path = CONFIG_PATH):
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)
        self.db_dir = Path(self.config['workspace']['db_dir'])
        self.emotion_output_dir = Path(self.config['workspace']['emotion_output_dir'])
        self.kline_db = self.db_dir / 'kline_eod.duckdb'
        self.limit_up_db = self.db_dir / 'limit_up.duckdb'

    def load_emotion_map(self) -> Dict[str, str]:
        emotion_map = {}
        if not self.emotion_output_dir.exists():
            return emotion_map
        for p in sorted(self.emotion_output_dir.glob('*.json')):
            if p.name == 'latest_30days.json':
                continue
            try:
                data = json.loads(p.read_text(encoding='utf-8'))
                emotion_map[data['date']] = data.get('emotion_name', '')
            except Exception:
                pass
        return emotion_map

    def load_base_frame(self, start_date: str) -> pd.DataFrame:
        con = duckdb.connect(str(self.kline_db), read_only=True)
        try:
            sql = f"""
            with base as (
                select
                    md.symbol,
                    sb.name,
                    sb.is_st,
                    sb.concepts,
                    md.trade_date,
                    md.open,
                    md.high,
                    md.low,
                    md.close,
                    coalesce(md.pre_close, lag(md.close) over(partition by md.symbol order by md.trade_date)) as pre_close,
                    md.volume,
                    md.amount,
                    md.change_ratio,
                    md.float_capital,
                    cf.main_net_inflow,
                    lag(md.close, 1) over(partition by md.symbol order by md.trade_date) as prev_close,
                    lag(md.amount, 1) over(partition by md.symbol order by md.trade_date) as prev_amount,
                    avg(md.close) over(partition by md.symbol order by md.trade_date rows between 4 preceding and current row) as ma5,
                    avg(md.close) over(partition by md.symbol order by md.trade_date rows between 9 preceding and current row) as ma10,
                    avg(md.close) over(partition by md.symbol order by md.trade_date rows between 19 preceding and current row) as ma20,
                    avg(md.amount) over(partition by md.symbol order by md.trade_date rows between 19 preceding and current row) as amt_ma20,
                    max(md.high) over(partition by md.symbol order by md.trade_date rows between 19 preceding and current row) as high20,
                    min(md.low) over(partition by md.symbol order by md.trade_date rows between 19 preceding and current row) as low20,
                    lead(md.open, 1) over(partition by md.symbol order by md.trade_date) as next_open,
                    lead(md.high, 1) over(partition by md.symbol order by md.trade_date) as next_high,
                    lead(md.low, 1) over(partition by md.symbol order by md.trade_date) as next_low,
                    lead(md.close, 1) over(partition by md.symbol order by md.trade_date) as next_close
                from market_daily md
                left join stock_basic sb on md.symbol = sb.symbol
                left join capital_flow cf on md.symbol = cf.symbol and md.trade_date = cf.trade_date
                where md.trade_date >= date '{start_date}'
            )
            select * from base
            """
            df = con.execute(sql).fetchdf()
        finally:
            con.close()
        return df

    def load_limitup_frame(self, start_date: str) -> pd.DataFrame:
        con = duckdb.connect(str(self.limit_up_db), read_only=True)
        try:
            sql = f"""
            select
                trade_date,
                stock_code as symbol,
                stock_name,
                concept_tags,
                consecutive_boards,
                is_first_limit_up,
                seal_amount,
                float_market_value,
                turnover_ratio,
                炸板次数 as bomb_count
            from limit_up
            where trade_date >= '{start_date}'
            """
            df = con.execute(sql).fetchdf()
        finally:
            con.close()
        return df

    @staticmethod
    def _normalize(series: pd.Series, floor: float = 0.0, ceil: float = 100.0) -> pd.Series:
        s = series.astype(float).replace([np.inf, -np.inf], np.nan)
        lo = s.quantile(0.05) if len(s.dropna()) else 0
        hi = s.quantile(0.95) if len(s.dropna()) else 1
        if hi <= lo:
            return pd.Series(np.full(len(s), 50.0), index=s.index)
        norm = (s.clip(lo, hi) - lo) / (hi - lo) * 100
        return norm.clip(floor, ceil)

    def build_candidates(self, months: int = 6, top_n: int = 20) -> pd.DataFrame:
        start_date = (datetime.utcnow().date() - timedelta(days=months * 31)).isoformat()
        base = self.load_base_frame(start_date)
        limitups = self.load_limitup_frame(start_date)
        emotion_map = self.load_emotion_map()

        if base.empty:
            return pd.DataFrame()

        base['trade_date'] = pd.to_datetime(base['trade_date'])
        for col in ['next_open', 'next_high', 'next_low', 'next_close', 'pre_close', 'amt_ma20', 'ma5', 'ma10', 'ma20', 'high20', 'low20']:
            if col in base.columns:
                base[col] = pd.to_numeric(base[col], errors='coerce')

        base['is_st_flag'] = base['is_st'].fillna('否').astype(str).str.contains('是')
        base['is_kcb'] = base['symbol'].astype(str).str.startswith('688')
        base['is_bj'] = base['symbol'].astype(str).str.endswith('.BJ')
        base['body_pct'] = np.where(base['open'] > 0, (base['close'] - base['open']) / base['open'] * 100, 0)
        base['amp_pct'] = np.where(base['low'] > 0, (base['high'] - base['low']) / base['low'] * 100, 0)
        base['turnover_ratio_vs20'] = np.where(base['amt_ma20'] > 0, base['amount'] / base['amt_ma20'], 0)
        base['pullback_to_ma20'] = np.where(base['ma20'] > 0, (base['close'] - base['ma20']) / base['ma20'] * 100, 0)
        base['near_high20'] = np.where(base['high20'] > 0, base['close'] / base['high20'], 0)
        base['near_low20'] = np.where(base['low20'] > 0, (base['close'] - base['low20']) / base['low20'] * 100, 0)
        base['capital_score_raw'] = base['main_net_inflow'].fillna(0)
        base['trend_pass'] = ((base['close'] > base['ma20']) & (base['ma5'] >= base['ma10']) & (base['ma10'] >= base['ma20']))
        base['pattern_trend_raw'] = (
            (base['body_pct'].clip(-5, 12) * 2.5)
            + (base['turnover_ratio_vs20'].clip(0, 4) * 10)
            + ((100 - base['pullback_to_ma20'].abs().clip(0, 15) * 6))
        )

        limitups['trade_date'] = pd.to_datetime(limitups['trade_date'])
        topic_daily = (
            limitups.assign(concept_tags=limitups['concept_tags'].fillna(''))
            .assign(topic_count=lambda d: d['concept_tags'].str.count(',') + (d['concept_tags'] != '').astype(int))
            .groupby('trade_date')
            .agg(limitup_count=('symbol', 'count'), avg_boards=('consecutive_boards', 'mean'), avg_topic_count=('topic_count', 'mean'))
            .reset_index()
        )
        merged = base.merge(limitups[['trade_date', 'symbol', 'consecutive_boards', 'is_first_limit_up', 'seal_amount', 'bomb_count', 'concept_tags']], on=['trade_date', 'symbol'], how='left')
        merged = merged.merge(topic_daily, on='trade_date', how='left')
        merged['consecutive_boards'] = merged['consecutive_boards'].fillna(0)
        merged['seal_amount'] = merged['seal_amount'].fillna(0)
        merged['bomb_count'] = merged['bomb_count'].fillna(0)
        merged['limitup_count'] = merged['limitup_count'].fillna(0)
        merged['avg_boards'] = merged['avg_boards'].fillna(0)
        merged['avg_topic_count'] = merged['avg_topic_count'].fillna(0)
        merged['emotion_name'] = merged['trade_date'].dt.strftime('%Y-%m-%d').map(emotion_map).fillna('未知')

        # universe filter
        uni = self.config['universe']
        merged = merged[(merged['amount'] >= uni['min_turnover_amount'])]
        merged = merged[(merged['close'] >= uni['min_close']) & (merged['close'] <= uni['max_close'])]
        merged = merged[(merged['float_capital'].fillna(0) >= uni['min_float_capital']) & (merged['float_capital'].fillna(0) <= uni['max_float_capital'])]
        merged = merged[~merged['is_st_flag']]
        merged = merged[~merged['is_kcb']]
        merged = merged[~merged['is_bj']]
        merged = merged[merged['next_open'].notna() & merged['next_high'].notna() & merged['next_low'].notna() & merged['next_close'].notna()]

        # emotion gate
        block_cycles = set(self.config['filters']['emotion']['block_cycles'])
        merged = merged[~merged['emotion_name'].isin(block_cycles)]

        # scores
        merged['pattern_score'] = self._normalize(merged['pattern_trend_raw'])
        merged['trend_score'] = self._normalize((merged['near_high20'].clip(0.7, 1.05) * 100) + (merged['trend_pass'].astype(int) * 30))
        merged['capital_score'] = self._normalize(merged['capital_score_raw'])
        merged['topic_strength'] = self._normalize(merged['limitup_count'] * 5 + merged['avg_topic_count'] * 15)
        merged['limitup_score'] = self._normalize(merged['consecutive_boards'] * 20 + np.log1p(merged['seal_amount']) - merged['bomb_count'] * 10)

        # simplified intent proxy
        merged['intent_proxy_score'] = self._normalize(
            merged['capital_score_raw'].fillna(0) / 1e7
            + merged['turnover_ratio_vs20'].clip(0, 4) * 10
            + (merged['close'] > merged['ma20']).astype(int) * 20
            - merged['bomb_count'] * 8
        )
        merged['intent_label_proxy'] = np.select(
            [
                merged['intent_proxy_score'] >= 75,
                merged['intent_proxy_score'] >= 60,
                merged['intent_proxy_score'] >= 45,
                merged['intent_proxy_score'] >= 30,
            ],
            ['强势吸筹', '偏多建仓', '多空分歧', '偏空出货'],
            default='出货陷阱'
        )
        allow_labels = set(self.config['filters']['intent']['allow_labels'])
        block_labels = set(self.config['filters']['intent']['block_labels'])
        merged = merged[merged['intent_label_proxy'].isin(allow_labels)]
        merged = merged[~merged['intent_label_proxy'].isin(block_labels)]

        # build two modes
        results = []
        for mode, mode_cfg in self.config['modes'].items():
            if not mode_cfg.get('enabled', False):
                continue
            weights = mode_cfg['weights']
            tmp = merged.copy()
            tmp['mode'] = mode
            tmp['score'] = (
                tmp['pattern_score'] * weights['pattern']
                + tmp['trend_score'] * weights['trend']
                + tmp['capital_score'] * weights['capital']
                + self._normalize(100 - tmp['pullback_to_ma20'].abs().clip(0, 12) * 6) * weights['position']
                + tmp['topic_strength'] * weights['topic']
                + tmp['limitup_score'] * weights['limit_up']
                + tmp['intent_proxy_score'] * weights['intent']
            )
            if mode == 'trend':
                tmp = tmp[(tmp['body_pct'] >= -3) & (tmp['trend_pass']) & (tmp['consecutive_boards'] <= 2)]
            elif mode == 'leader':
                tmp = tmp[(tmp['consecutive_boards'] >= 1) | (tmp['limitup_count'] >= 20)]
            tmp = tmp.sort_values(['trade_date', 'score'], ascending=[True, False])
            tmp['rank'] = tmp.groupby('trade_date')['score'].rank(method='first', ascending=False)
            tmp = tmp[tmp['rank'] <= top_n]
            results.append(tmp)

        if not results:
            return pd.DataFrame()
        final_df = pd.concat(results, ignore_index=True)

        # next-day metrics
        buy_price = final_df['close']
        final_df['hit_tp3'] = (final_df['next_high'] >= buy_price * 1.03).astype(int)
        final_df['hit_tp5'] = (final_df['next_high'] >= buy_price * 1.05).astype(int)
        final_df['hit_tp8'] = (final_df['next_high'] >= buy_price * 1.08).astype(int)
        final_df['hit_sl7'] = (final_df['next_low'] <= buy_price * 0.93).astype(int)
        final_df['next_close_positive'] = (final_df['next_close'] > buy_price).astype(int)
        final_df['next_return_close_pct'] = np.where(buy_price > 0, (final_df['next_close'] - buy_price) / buy_price * 100, 0)
        final_df['next_return_open_pct'] = np.where(buy_price > 0, (final_df['next_open'] - buy_price) / buy_price * 100, 0)
        final_df['next_intraday_max_pct'] = np.where(buy_price > 0, (final_df['next_high'] - buy_price) / buy_price * 100, 0)
        final_df['next_intraday_min_pct'] = np.where(buy_price > 0, (final_df['next_low'] - buy_price) / buy_price * 100, 0)
        return final_df

    def summarize(self, df: pd.DataFrame) -> Dict:
        if df.empty:
            return {'status': 'empty', 'message': 'no candidates'}
        summary = {'status': 'ok', 'generated_at': datetime.utcnow().isoformat(), 'overall': {}, 'by_mode': {}, 'by_emotion': {}}
        summary['overall'] = self._summary_block(df)
        for mode, part in df.groupby('mode'):
            summary['by_mode'][mode] = self._summary_block(part)
        for emo, part in df.groupby('emotion_name'):
            summary['by_emotion'][emo] = self._summary_block(part)
        return summary

    @staticmethod
    def _summary_block(df: pd.DataFrame) -> Dict:
        return {
            'sample_size': int(len(df)),
            'avg_score': round(float(df['score'].mean()), 2),
            'win_close_rate': round(float(df['next_close_positive'].mean() * 100), 2),
            'tp3_rate': round(float(df['hit_tp3'].mean() * 100), 2),
            'tp5_rate': round(float(df['hit_tp5'].mean() * 100), 2),
            'tp8_rate': round(float(df['hit_tp8'].mean() * 100), 2),
            'sl7_rate': round(float(df['hit_sl7'].mean() * 100), 2),
            'avg_next_close_return_pct': round(float(df['next_return_close_pct'].mean()), 2),
            'avg_next_max_return_pct': round(float(df['next_intraday_max_pct'].mean()), 2),
            'avg_next_min_return_pct': round(float(df['next_intraday_min_pct'].mean()), 2),
        }


def main():
    parser = argparse.ArgumentParser(description='trend_eod_screener 研究版回测')
    parser.add_argument('--months', type=int, default=6, help='回测月份数')
    parser.add_argument('--top-n', type=int, default=20, help='每日每模式保留数量')
    parser.add_argument('--json-out', type=str, default='', help='输出摘要 JSON 文件')
    parser.add_argument('--csv-out', type=str, default='', help='输出候选明细 CSV 文件')
    args = parser.parse_args()

    bt = ResearchBacktester()
    df = bt.build_candidates(months=args.months, top_n=args.top_n)
    summary = bt.summarize(df)

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.csv_out and not df.empty:
        Path(args.csv_out).parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(args.csv_out, index=False)
    if args.json_out:
        Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_out).write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
