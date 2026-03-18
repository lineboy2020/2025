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


def main():
    parser = argparse.ArgumentParser(description='实时运行入口（模板）')
    parser.add_argument('--date', required=True)
    args = parser.parse_args()

    gateway = DataGateway()
    symbol = '000001.SZ'
    realtime = gateway.get_realtime([symbol]).get(symbol, pd.DataFrame())
    snapshot = gateway.get_snapshot(symbol, args.date)
    if realtime.empty:
        raise SystemExit('未获取到实时数据')

    row = realtime.iloc[-1]
    sample_candidate = {
        'symbol': symbol,
        'name': '示例股票',
        'trade_plan': {'buy_price_ref': float(row['preClose']) if 'preClose' in row else float(row['latest'])}
    }
    current_price = float(row['latest']) if 'latest' in row else None
    high_price = float(row['high']) if 'high' in row else current_price
    low_price = float(row['low']) if 'low' in row else current_price
    capital_imbalance = None
    if not snapshot.empty and 'amount' in snapshot.columns:
        head_amt = float(pd.to_numeric(snapshot.head(min(30, len(snapshot)))['amount'], errors='coerce').fillna(0).sum())
        tail_amt = float(pd.to_numeric(snapshot.tail(min(30, len(snapshot)))['amount'], errors='coerce').fillna(0).sum())
        denom = head_amt + tail_amt
        capital_imbalance = round((tail_amt - head_amt) / denom, 4) if denom > 0 else None

    result = evaluate_demo_signal(sample_candidate, current_price=current_price, high_price=high_price, low_price=low_price, capital_imbalance=capital_imbalance)
    summary = summarize_results([result])
    lines = build_summary_lines([result])
    print_console(lines)
    write_markdown(str(ROOT / 'demo_live_report.md'), f'实时策略报告 {args.date}', lines)
    print(json.dumps({'date': args.date, 'realtime_rows': len(realtime), 'snapshot_rows': len(snapshot), 'summary': summary}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
