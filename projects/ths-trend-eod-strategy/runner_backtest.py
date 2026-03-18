#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path

from analyzer import summarize_backtest_results
from data_gateway import DataGateway

ROOT = Path(__file__).resolve().parent
LIVE_REPORT = ROOT / 'tail_candidates_2026-03-18.md'


def decide_exit(buy_price: float, next_high: float, next_low: float, next_close: float):
    tp1 = buy_price * 1.03
    tp2 = buy_price * 1.05
    tp3 = buy_price * 1.08
    sl = buy_price * 0.93
    if next_low <= sl:
        return 'stop_loss', round((sl / buy_price - 1) * 100, 2)
    if next_high >= tp3:
        return 'take_profit_8', 8.0
    if next_high >= tp2:
        return 'take_profit_5', 5.0
    if next_high >= tp1:
        return 'take_profit_3', 3.0
    return 'close_next_day', round((next_close / buy_price - 1) * 100, 2)


def main():
    parser = argparse.ArgumentParser(description='趋势尾盘历史回测入口')
    parser.add_argument('--date', required=True)
    parser.add_argument('--candidate-file', default='')
    args = parser.parse_args()

    gateway = DataGateway()
    candidate_file = args.candidate_file or str(ROOT / f'tail_candidates_{args.date}.json')
    path = Path(candidate_file)
    if not path.exists():
        raise SystemExit(f'候选文件不存在: {candidate_file}')
    payload = json.loads(path.read_text(encoding='utf-8'))
    candidates = payload.get('candidates', [])
    if not candidates:
        raise SystemExit('候选文件为空')

    buy_date = datetime.strptime(args.date, '%Y-%m-%d').date()
    end_date = (buy_date + timedelta(days=3)).isoformat()
    history_map = gateway.get_history([c['symbol'] for c in candidates], args.date, end_date)

    results = []
    for c in candidates:
        history = history_map.get(c['symbol'])
        if history is None or len(history) < 2:
            continue
        buy_row = history.iloc[0]
        next_row = history.iloc[1]
        buy_price = float(c['trade_plan']['buy_price_ref'])
        exit_reason, exit_return_pct = decide_exit(
            buy_price,
            float(next_row['high']),
            float(next_row['low']),
            float(next_row['close'])
        )
        results.append({
            'symbol': c['symbol'],
            'name': c.get('name', c['symbol']),
            'buy_date': str(buy_row['trade_date']),
            'sell_date': str(next_row['trade_date']),
            'buy_price': buy_price,
            'next_open': float(next_row['open']),
            'next_high': float(next_row['high']),
            'next_low': float(next_row['low']),
            'next_close': float(next_row['close']),
            'exit_reason': exit_reason,
            'exit_return_pct': exit_return_pct,
        })

    summary = summarize_backtest_results(results)
    print(json.dumps({'date': args.date, 'candidate_count': len(candidates), 'evaluated_count': len(results), 'summary': summary, 'results': results}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
