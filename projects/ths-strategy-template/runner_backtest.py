#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path

from analyzer import summarize_results
from data_gateway import DataGateway
from strategy_logic import evaluate_demo_signal

ROOT = Path(__file__).resolve().parent
DEFAULT_REPORTS_DIR = '/root/.openclaw/workspace/skills/trend_eod_screener/reports'


def main():
    parser = argparse.ArgumentParser(description='历史回测入口（模板）')
    parser.add_argument('--date', required=True)
    parser.add_argument('--candidate-file', default='')
    args = parser.parse_args()

    gateway = DataGateway()
    if args.candidate_file:
        pool = gateway.load_candidate_pool(args.candidate_file)
    else:
        pool = gateway.resolve_latest_candidate_pool(DEFAULT_REPORTS_DIR)

    candidates = pool.get('candidates', [])
    if not candidates:
        raise SystemExit('未获取到候选池')

    symbols = [c['symbol'] for c in candidates]
    end_date = datetime.strptime(args.date, '%Y-%m-%d').date()
    start_date = (end_date - timedelta(days=30)).isoformat()
    history_map = gateway.get_history(symbols, start_date, end_date.isoformat())

    results = []
    history_rows = {}
    for candidate in candidates:
        symbol = candidate['symbol']
        history = history_map.get(symbol)
        if history is None or history.empty:
            continue
        history_rows[symbol] = len(history)
        last_row = history.iloc[-1]
        candidate.setdefault('trade_plan', {})
        candidate['trade_plan'].setdefault('buy_price_ref', float(last_row['pre_close']) if 'pre_close' in last_row else float(last_row['close']))
        results.append(evaluate_demo_signal(
            candidate,
            current_price=float(last_row['close']),
            high_price=float(last_row['high']),
            low_price=float(last_row['low']),
            capital_imbalance=None,
        ))

    summary = summarize_results(results)
    print(json.dumps({'date': args.date, 'candidate_count': len(candidates), 'evaluated_count': len(results), 'history_rows': history_rows, 'summary': summary, 'results': results}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
