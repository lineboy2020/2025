#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from analyzer import summarize_results
from data_gateway import DataGateway
from notifier import build_summary_lines, print_console, write_markdown
from strategy_logic import evaluate_demo_signal

ROOT = Path(__file__).resolve().parent
DEFAULT_REPORTS_DIR = '/root/.openclaw/workspace/skills/trend_eod_screener/reports'


def calc_capital_imbalance(snapshot: pd.DataFrame):
    if snapshot.empty or 'amount' not in snapshot.columns:
        return None
    head_amt = float(pd.to_numeric(snapshot.head(min(30, len(snapshot)))['amount'], errors='coerce').fillna(0).sum())
    tail_amt = float(pd.to_numeric(snapshot.tail(min(30, len(snapshot)))['amount'], errors='coerce').fillna(0).sum())
    denom = head_amt + tail_amt
    return round((tail_amt - head_amt) / denom, 4) if denom > 0 else None


def main():
    parser = argparse.ArgumentParser(description='实时运行入口（模板）')
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
    realtime_map = gateway.get_realtime(symbols)

    results = []
    meta = {}
    for candidate in candidates:
        symbol = candidate['symbol']
        realtime = realtime_map.get(symbol, pd.DataFrame())
        if realtime.empty:
            continue
        snapshot = gateway.get_snapshot(symbol, args.date)
        row = realtime.iloc[-1]
        candidate.setdefault('trade_plan', {})
        candidate['trade_plan'].setdefault('buy_price_ref', float(row['preClose']) if 'preClose' in row else float(row['latest']))
        current_price = float(row['latest']) if 'latest' in row else None
        high_price = float(row['high']) if 'high' in row else current_price
        low_price = float(row['low']) if 'low' in row else current_price
        capital_imbalance = calc_capital_imbalance(snapshot)
        results.append(evaluate_demo_signal(candidate, current_price=current_price, high_price=high_price, low_price=low_price, capital_imbalance=capital_imbalance))
        meta[symbol] = {'realtime_rows': len(realtime), 'snapshot_rows': len(snapshot)}

    summary = summarize_results(results)
    lines = build_summary_lines(results)
    print_console(lines)
    write_markdown(str(ROOT / 'demo_live_report.md'), f'实时策略报告 {args.date}', lines)
    print(json.dumps({'date': args.date, 'candidate_count': len(candidates), 'evaluated_count': len(results), 'meta': meta, 'summary': summary}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
