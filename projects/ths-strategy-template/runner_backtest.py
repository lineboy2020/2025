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


def main():
    parser = argparse.ArgumentParser(description='历史回测入口（模板）')
    parser.add_argument('--date', required=True)
    args = parser.parse_args()

    gateway = DataGateway()
    end_date = datetime.strptime(args.date, '%Y-%m-%d').date()
    start_date = (end_date - timedelta(days=30)).isoformat()
    history = gateway.get_history(['000001.SZ'], start_date, end_date.isoformat())['000001.SZ']
    if history.empty:
        raise SystemExit('未获取到历史数据')

    last_row = history.iloc[-1]
    sample_candidate = {
        'symbol': '000001.SZ',
        'name': '示例股票',
        'trade_plan': {'buy_price_ref': float(last_row['pre_close']) if 'pre_close' in last_row else float(last_row['close'])}
    }
    result = evaluate_demo_signal(
        sample_candidate,
        current_price=float(last_row['close']),
        high_price=float(last_row['high']),
        low_price=float(last_row['low']),
        capital_imbalance=None,
    )
    summary = summarize_results([result])
    print(json.dumps({'date': args.date, 'history_rows': len(history), 'result': result, 'summary': summary}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
