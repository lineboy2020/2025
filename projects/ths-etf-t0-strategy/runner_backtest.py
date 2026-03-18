#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path

from analyzer import summarize_results
from data_gateway import DataGateway
from strategy_logic import evaluate_etf_t0_signal, infer_trend_from_history

ROOT = Path(__file__).resolve().parent


def build_default_candidates(symbols):
    return [{'symbol': s, 'name': s, 'trade_plan': {}} for s in symbols]


def main():
    parser = argparse.ArgumentParser(description='ETF T0 历史回测入口')
    parser.add_argument('--date', required=True)
    args = parser.parse_args()

    gateway = DataGateway()
    symbols = gateway.config['strategy']['symbols']
    candidates = build_default_candidates(symbols)

    end_date = datetime.strptime(args.date, '%Y-%m-%d').date()
    start_date = (end_date - timedelta(days=60)).isoformat()
    history_map = gateway.get_history(symbols, start_date, end_date.isoformat())

    results = []
    rows = {}
    for candidate in candidates:
        symbol = candidate['symbol']
        history = history_map.get(symbol)
        if history is None or history.empty:
            continue
        rows[symbol] = len(history)
        last_row = history.iloc[-1]
        candidate['trade_plan']['buy_price_ref'] = float(last_row['pre_close']) if 'pre_close' in last_row else float(last_row['close'])
        trend_d = infer_trend_from_history(history, gateway.config['strategy']['ma_window'])
        result = evaluate_etf_t0_signal(
            candidate,
            current_price=float(last_row['close']),
            high_price=float(last_row['high']),
            low_price=float(last_row['low']),
            open_price=float(last_row['open']),
            capital_imbalance=None,
            trend_d=trend_d,
            trend_30=0,
        )
        results.append(result)

    summary = summarize_results(results)
    print(json.dumps({'date': args.date, 'history_rows': rows, 'summary': summary, 'results': results}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
