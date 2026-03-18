#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from analyzer import summarize_results
from data_gateway import DataGateway
from notifier import build_summary_lines, print_console, write_markdown
from strategy_logic import evaluate_etf_t0_signal, infer_trend_from_history

ROOT = Path(__file__).resolve().parent


def calc_capital_imbalance(snapshot: pd.DataFrame):
    if snapshot.empty or 'amount' not in snapshot.columns:
        return None
    head_amt = float(pd.to_numeric(snapshot.head(min(30, len(snapshot)))['amount'], errors='coerce').fillna(0).sum())
    tail_amt = float(pd.to_numeric(snapshot.tail(min(30, len(snapshot)))['amount'], errors='coerce').fillna(0).sum())
    denom = head_amt + tail_amt
    return round((tail_amt - head_amt) / denom, 4) if denom > 0 else None


def build_default_candidates(symbols):
    return [{'symbol': s, 'name': s, 'trade_plan': {}} for s in symbols]


def main():
    parser = argparse.ArgumentParser(description='ETF T0 实时运行入口')
    parser.add_argument('--date', required=True)
    args = parser.parse_args()

    gateway = DataGateway()
    symbols = gateway.config['strategy']['symbols']
    candidates = build_default_candidates(symbols)

    history_end = datetime.strptime(args.date, '%Y-%m-%d').date()
    history_start = (history_end - timedelta(days=60)).isoformat()
    history_map = gateway.get_history(symbols, history_start, history_end.isoformat())
    realtime_map = gateway.get_realtime(symbols)

    results = []
    meta = {}
    for candidate in candidates:
        symbol = candidate['symbol']
        realtime = realtime_map.get(symbol, pd.DataFrame())
        history = history_map.get(symbol, pd.DataFrame())
        if realtime.empty or history.empty:
            continue
        row = realtime.iloc[-1]
        snapshot = gateway.get_snapshot(symbol, args.date)
        candidate['trade_plan']['buy_price_ref'] = float(row['preClose']) if 'preClose' in row else float(row['latest'])
        trend_d = infer_trend_from_history(history, gateway.config['strategy']['ma_window'])
        result = evaluate_etf_t0_signal(
            candidate,
            current_price=float(row['latest']) if 'latest' in row else None,
            high_price=float(row['high']) if 'high' in row else None,
            low_price=float(row['low']) if 'low' in row else None,
            open_price=float(row['open']) if 'open' in row else None,
            capital_imbalance=calc_capital_imbalance(snapshot),
            trend_d=trend_d,
            trend_30=0,
        )
        results.append(result)
        meta[symbol] = {'realtime_rows': len(realtime), 'snapshot_rows': len(snapshot), 'history_rows': len(history)}

    summary = summarize_results(results)
    lines = build_summary_lines(results)
    print_console(lines)
    write_markdown(str(ROOT / 'demo_live_report.md'), f'ETF T0 实时策略报告 {args.date}', lines)
    print(json.dumps({'date': args.date, 'summary': summary, 'meta': meta, 'results': results}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
