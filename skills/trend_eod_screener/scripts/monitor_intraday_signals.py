#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
盘中监控器原型：读取 live candidates，结合同花顺实时/快照数据做盘中信号预警。

当前目标：
1. 读取 live_candidates.json
2. 尝试获取 realtime / snapshot 数据
3. 判断 +3 / +5 / +8 / -7 触发状态
4. 结合快照粗略评估主力资金强弱
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import numpy as np

ROOT = Path('/root/.openclaw/workspace')
REPORT_DIR = ROOT / 'skills/trend_eod_screener/reports'

sys.path.insert(0, str(ROOT / 'skills' / 'ths-data-fetcher' / 'scripts'))
sys.path.insert(0, str(ROOT / 'skills' / 'main-force-intent' / 'scripts'))
sys.path.insert(0, str(ROOT / 'data' / 'src'))


def load_candidates(path: str) -> Dict:
    return json.loads(Path(path).read_text(encoding='utf-8'))


def load_ths_downloader():
    try:
        from unified_ths_downloader import UnifiedTHSDownloader
        return UnifiedTHSDownloader(auto_login=True, use_http=True)
    except Exception:
        return None


def get_realtime_quotes(codes: List[str]) -> pd.DataFrame:
    downloader = load_ths_downloader()
    if downloader is None:
        return pd.DataFrame()
    try:
        results = downloader.download_realtime_data(stock_codes=codes)
        if isinstance(results, dict):
            frames = []
            for code, df in results.items():
                if df is not None and not df.empty:
                    tmp = df.copy()
                    tmp['symbol'] = code
                    frames.append(tmp)
            if frames:
                return pd.concat(frames, ignore_index=True)
        elif isinstance(results, pd.DataFrame):
            return results
    except Exception:
        return pd.DataFrame()
    return pd.DataFrame()


def get_hf_summary(symbol: str, trade_date: str) -> Dict:
    downloader = load_ths_downloader()
    if downloader is None:
        return {}
    try:
        indicators = 'open;high;low;close;avgPrice;volume;amount;buyVolume;sellVolume'
        results = downloader.download_hf_data(
            stock_codes=[symbol],
            start_time=f'{trade_date} 09:30:00',
            end_time=f'{trade_date} 15:00:00',
            indicators=indicators,
        )
        df = results.get(symbol)
        if df is None or df.empty:
            return {}
        buy = pd.to_numeric(df['buyVolume'], errors='coerce').fillna(0) if 'buyVolume' in df.columns else pd.Series(dtype=float)
        sell = pd.to_numeric(df['sellVolume'], errors='coerce').fillna(0) if 'sellVolume' in df.columns else pd.Series(dtype=float)
        vol = pd.to_numeric(df['volume'], errors='coerce').fillna(0) if 'volume' in df.columns else pd.Series(dtype=float)
        amt = pd.to_numeric(df['amount'], errors='coerce').fillna(0) if 'amount' in df.columns else pd.Series(dtype=float)
        buy_sum = float(buy.sum()) if not buy.empty else 0.0
        sell_sum = float(sell.sum()) if not sell.empty else 0.0
        denom = buy_sum + sell_sum
        imbalance = round((buy_sum - sell_sum) / denom, 4) if denom > 0 else None
        return {
            'hf_rows': int(len(df)),
            'hf_buy_volume_sum': buy_sum,
            'hf_sell_volume_sum': sell_sum,
            'hf_volume_sum': float(vol.sum()) if not vol.empty else None,
            'hf_amount_sum': float(amt.sum()) if not amt.empty else None,
            'hf_buy_sell_imbalance': imbalance,
            'hf_direction_source': 'buyVolume_sellVolume' if denom > 0 else 'unavailable',
        }
    except Exception:
        return {}


def classify_capital_state(snapshot_summary: Dict, hf_summary: Dict | None = None) -> str:
    hf_summary = hf_summary or {}
    hf_imbalance = hf_summary.get('hf_buy_sell_imbalance')
    hf_buy = hf_summary.get('hf_buy_volume_sum') or 0
    hf_sell = hf_summary.get('hf_sell_volume_sum') or 0
    if hf_imbalance is not None and (hf_buy + hf_sell) > 0:
        hf_buy_ratio = hf_buy / (hf_buy + hf_sell)
        hf_sell_ratio = hf_sell / (hf_buy + hf_sell)
        if hf_imbalance >= 0.20 and hf_buy_ratio >= 0.58:
            return 'strong_strengthening'
        if hf_imbalance >= 0.08 and hf_buy_ratio >= 0.53:
            return 'strengthening'
        if hf_imbalance <= -0.20 and hf_sell_ratio >= 0.58:
            return 'strong_weakening'
        if hf_imbalance <= -0.08 and hf_sell_ratio >= 0.53:
            return 'weakening'
        return 'neutral'

    imbalance = snapshot_summary.get('buy_sell_imbalance')
    buy_amt = snapshot_summary.get('buy_amount_sum') or 0
    sell_amt = snapshot_summary.get('sell_amount_sum') or 0
    tail_amt = snapshot_summary.get('snapshot_amt_tail_sum')
    head_amt = snapshot_summary.get('snapshot_amt_head_sum')
    amt_sum = snapshot_summary.get('snapshot_amount_sum') or 0

    directional_total = buy_amt + sell_amt
    if directional_total > 0:
        buy_ratio = buy_amt / directional_total
        sell_ratio = sell_amt / directional_total
        if imbalance is not None:
            if imbalance >= 0.25 and buy_ratio >= 0.6:
                return 'strong_strengthening'
            if imbalance >= 0.10 and buy_ratio >= 0.55:
                return 'strengthening'
            if imbalance <= -0.25 and sell_ratio >= 0.6:
                return 'strong_weakening'
            if imbalance <= -0.10 and sell_ratio >= 0.55:
                return 'weakening'
            return 'neutral'

    if tail_amt is not None and head_amt is not None:
        if head_amt <= 1e-6 and tail_amt > max(1e6, amt_sum * 0.01):
            return 'strengthening'
        if head_amt > 0 and tail_amt > head_amt * 1.5:
            return 'strengthening'
        if head_amt > 0 and tail_amt < head_amt * 0.7:
            return 'weakening'
        return 'neutral'

    return 'unknown'


def build_intraday_summary(result: Dict) -> str:
    state = result.get('strategy_state', 'unknown')
    price = result.get('current_price')
    ret = result.get('current_return_pct')
    action = result.get('suggested_action')
    capital = result.get('capital_state')
    hf = result.get('hf_summary', {}) or {}
    ss = result.get('snapshot_summary', {}) or {}
    direction_source = hf.get('hf_direction_source') or ss.get('direction_source', 'unknown')
    if direction_source == 'buyVolume_sellVolume':
        capital = f"{capital}(HF)"
    elif direction_source == 'unavailable':
        capital = f"{capital}(方向缺失)"
    return f"{result.get('symbol')} {result.get('name')} | 状态={state} | 现价={price} | 收益={ret}% | 资金={capital} | 动作={action}"


def summarize_snapshot_df(df: pd.DataFrame) -> Dict:
    if df is None or df.empty:
        return {}
    amt_col = 'amount' if 'amount' in df.columns else ('amt' if 'amt' in df.columns else None)
    vol_col = 'volume' if 'volume' in df.columns else ('vol' if 'vol' in df.columns else None)
    price_col = None
    for c in ['latest', 'price', 'lastPrice', 'close', '成交价']:
        if c in df.columns:
            price_col = c
            break
    dir_col = None
    for c in ['dealDirection', 'direction', 'bsFlag', '买卖方向']:
        if c in df.columns:
            dir_col = c
            break
    buy_cols = [c for c in df.columns if 'buy' in str(c).lower() or 'bid' in str(c).lower()]
    sell_cols = [c for c in df.columns if 'sell' in str(c).lower() or 'ask' in str(c).lower()]
    summary = {
        'snapshot_rows': int(len(df)),
        'snapshot_amount_sum': float(pd.to_numeric(df[amt_col], errors='coerce').fillna(0).sum()) if amt_col else None,
        'snapshot_volume_sum': float(pd.to_numeric(df[vol_col], errors='coerce').fillna(0).sum()) if vol_col else None,
        'snapshot_price_last': float(pd.to_numeric(df[price_col], errors='coerce').dropna().iloc[-1]) if price_col and not pd.to_numeric(df[price_col], errors='coerce').dropna().empty else None,
        'buy_cols_detected': buy_cols[:5],
        'sell_cols_detected': sell_cols[:5],
    }
    if amt_col and len(df) >= 20:
        tail = df.tail(min(30, len(df))).copy()
        head = df.head(min(30, len(df))).copy()
        summary['snapshot_amt_tail_sum'] = float(pd.to_numeric(tail[amt_col], errors='coerce').fillna(0).sum())
        summary['snapshot_amt_head_sum'] = float(pd.to_numeric(head[amt_col], errors='coerce').fillna(0).sum())
    if dir_col and amt_col:
        ds = pd.to_numeric(df[dir_col], errors='coerce')
        amt = pd.to_numeric(df[amt_col], errors='coerce').fillna(0)
        summary['direction_nonnull_count'] = int(ds.notna().sum())
        buy_mask = ds.isin([5])
        sell_mask = ds.isin([1])
        neutral_mask = ds.isin([15])
        summary['buy_amount_sum'] = float(amt[buy_mask].sum())
        summary['sell_amount_sum'] = float(amt[sell_mask].sum())
        summary['neutral_amount_sum'] = float(amt[neutral_mask].sum())
        denom = float(amt[buy_mask].sum() + amt[sell_mask].sum())
        summary['buy_sell_imbalance'] = round((float(amt[buy_mask].sum()) - float(amt[sell_mask].sum())) / denom, 4) if denom > 0 else None
        summary['direction_source'] = 'dealDirection' if int(ds.notna().sum()) > 0 else 'unavailable'
    return summary


def get_snapshot_summary(symbol: str, trade_date: str) -> Dict:
    downloader = load_ths_downloader()
    if downloader is None:
        return {}
    try:
        indicators = 'open;high;low;close;volume;amount'
        results = downloader.download_hf_data(
            stock_codes=[symbol],
            start_time=f'{trade_date} 09:30:00',
            end_time=f'{trade_date} 15:00:00',
            indicators=indicators,
        )
        df = results.get(symbol)
        return summarize_snapshot_df(df) if df is not None else {}
    except Exception:
        return {}


def detect_price_fields(row: pd.Series) -> Dict[str, Optional[float]]:
    mapping = {}
    candidates = {
        'current_price': ['latest', 'last', 'price', '现价', 'close'],
        'high_price': ['high', '最高'],
        'low_price': ['low', '最低'],
        'open_price': ['open', '今开'],
    }
    for key, cols in candidates.items():
        val = None
        for c in cols:
            if c in row.index:
                try:
                    raw = pd.to_numeric(pd.Series([row[c]]), errors='coerce').iloc[0]
                    if pd.notna(raw):
                        val = float(raw)
                        break
                except Exception:
                    pass
        mapping[key] = val
    return mapping


def price_hit(level_price: Optional[float], threshold_price: float, tolerance: float = 0.001) -> bool:
    if level_price is None:
        return False
    return level_price >= threshold_price * (1 - tolerance)


def price_stop(level_price: Optional[float], threshold_price: float, tolerance: float = 0.001) -> bool:
    if level_price is None:
        return False
    return level_price <= threshold_price * (1 + tolerance)


def eval_alerts(candidate: Dict, realtime_row: Optional[pd.Series], snapshot_summary: Dict, hf_summary: Dict | None = None) -> Dict:
    buy = float(candidate['trade_plan']['buy_price_ref'])
    tp3 = buy * 1.03
    tp5 = buy * 1.05
    tp8 = buy * 1.08
    sl7 = buy * 0.93

    current_price = high_price = low_price = None
    if realtime_row is not None:
        prices = detect_price_fields(realtime_row)
        current_price = prices['current_price']
        high_price = prices['high_price']
        low_price = prices['low_price']

    if current_price is None and snapshot_summary.get('snapshot_price_last') is not None:
        current_price = snapshot_summary.get('snapshot_price_last')
    if high_price is None:
        high_price = current_price
    if low_price is None:
        low_price = current_price

    current_return = round((current_price / buy - 1) * 100, 2) if current_price else None
    hit_tp3 = price_hit(high_price, tp3)
    hit_tp5 = price_hit(high_price, tp5)
    hit_tp8 = price_hit(high_price, tp8)
    hit_sl7 = price_stop(low_price, sl7)

    capital_state = classify_capital_state(snapshot_summary, hf_summary)

    alert_level = 'normal'
    action = 'hold_watch'
    strategy_state = 'intraday_monitoring'
    if hit_tp8:
        action = 'take_profit_final'
        strategy_state = 'tp8_triggered'
        alert_level = 'critical'
    elif hit_tp5:
        action = 'take_profit_partial_2'
        strategy_state = 'tp5_triggered'
        alert_level = 'high'
    elif hit_tp3:
        action = 'take_profit_partial_1'
        strategy_state = 'tp3_triggered'
        alert_level = 'medium'
    elif hit_sl7:
        action = 'stop_loss'
        strategy_state = 'stoploss_triggered'
        alert_level = 'critical'
    elif capital_state in ('strong_weakening', 'weakening') and current_return is not None and current_return < 1:
        action = 'reduce_or_watch'
        strategy_state = 'capital_weakening'
        alert_level = 'high' if capital_state == 'strong_weakening' else 'medium'
    elif capital_state in ('strong_strengthening', 'strengthening') and current_return is not None and current_return > 0:
        action = 'hold_or_trail'
        strategy_state = 'capital_strengthening'
        alert_level = 'medium' if capital_state == 'strong_strengthening' else 'low'

    result = {
        'symbol': candidate['symbol'],
        'name': candidate['name'],
        'signal_mode': candidate.get('signal_mode'),
        'strategy_state': strategy_state,
        'current_price': current_price,
        'current_return_pct': current_return,
        'high_price_seen': high_price,
        'low_price_seen': low_price,
        'hit_tp3': hit_tp3,
        'hit_tp5': hit_tp5,
        'hit_tp8': hit_tp8,
        'hit_sl7': hit_sl7,
        'capital_state': capital_state,
        'alert_level': alert_level,
        'suggested_action': action,
        'snapshot_summary': snapshot_summary,
        'hf_summary': hf_summary or {},
    }
    result['summary_text'] = build_intraday_summary(result)
    return result


def resolve_prev_candidates_file() -> Path:
    files = sorted(REPORT_DIR.glob('live_candidates_*.json'))
    dated = []
    for f in files:
        stem = f.stem.replace('live_candidates_', '')
        try:
            d = datetime.strptime(stem, '%Y-%m-%d').date()
            dated.append((d, f))
        except Exception:
            continue
    if not dated:
        return REPORT_DIR / 'live_candidates.json'
    dated.sort(key=lambda x: x[0])
    return dated[-1][1]


def main():
    parser = argparse.ArgumentParser(description='盘中监控 live candidates')
    parser.add_argument('--input', type=str, default='')
    parser.add_argument('--json-out', type=str, default=str(REPORT_DIR / 'intraday_monitor.json'))
    parser.add_argument('--md-out', type=str, default=str(REPORT_DIR / 'intraday_monitor.md'))
    parser.add_argument('--current-date', type=str, default='', help='当前监控日期，默认今天')
    args = parser.parse_args()

    input_path = Path(args.input) if args.input else resolve_prev_candidates_file()
    payload = load_candidates(str(input_path))
    candidates = payload.get('candidates', [])
    candidate_trade_date = payload.get('trade_date')
    current_trade_date = args.current_date or datetime.utcnow().strftime('%Y-%m-%d')
    if not candidates:
        result = {'status': 'empty', 'strategy_state': 'no_candidates', 'message': 'no candidates'}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        Path(args.json_out).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        return

    codes = [c['symbol'] for c in candidates]
    realtime_df = get_realtime_quotes(codes)
    results = []
    for c in candidates:
        row = None
        if not realtime_df.empty and 'symbol' in realtime_df.columns:
            m = realtime_df[realtime_df['symbol'] == c['symbol']]
            if not m.empty:
                row = m.iloc[-1]
        snap = get_snapshot_summary(c['symbol'], current_trade_date)
        hf = get_hf_summary(c['symbol'], current_trade_date)
        results.append(eval_alerts(c, row, snap, hf))

    out = {
        'status': 'ok',
        'generated_at': datetime.utcnow().isoformat(),
        'candidate_trade_date': candidate_trade_date,
        'current_trade_date': current_trade_date,
        'strategy': payload.get('strategy'),
        'signal_mode': payload.get('signal_mode'),
        'strategy_state': 'intraday_monitor_generated',
        'details': results,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    Path(args.json_out).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')

    lines = [
        f"# 盘中监控报告 - {current_trade_date}",
        '',
        f"候选日期：{candidate_trade_date}",
        f"监控日期：{current_trade_date}",
        f"策略：{payload.get('strategy')}",
        f"信号类型：{payload.get('signal_mode')}",
        ''
    ]
    for r in results:
        lines.extend([
            f"## {r['symbol']} {r['name']}",
            f"- 摘要：{r.get('summary_text')}",
            f"- 当前价：{r['current_price']}",
            f"- 当前收益：{r['current_return_pct']}%",
            f"- 命中 +3 / +5 / +8：{r['hit_tp3']} / {r['hit_tp5']} / {r['hit_tp8']}",
            f"- 触发 -7：{r['hit_sl7']}",
            f"- 资金状态：{r['capital_state']}",
            f"- 预警级别：{r['alert_level']}",
            f"- 建议动作：{r['suggested_action']}",
            ''
        ])
    Path(args.md_out).write_text('\n'.join(lines), encoding='utf-8')


if __name__ == '__main__':
    main()
