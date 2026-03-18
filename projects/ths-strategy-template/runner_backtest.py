#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from analyzer import summarize_results
from strategy_logic import evaluate_demo_signal

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description='历史回测入口（模板）')
    parser.add_argument('--date', required=True)
    args = parser.parse_args()

    sample_candidate = {
        'symbol': '000001.SZ',
        'name': '示例股票',
        'trade_plan': {'buy_price_ref': 10.0}
    }
    result = evaluate_demo_signal(sample_candidate, current_price=10.35, high_price=10.55, low_price=9.95, capital_imbalance=0.12)
    summary = summarize_results([result])
    print(json.dumps({'date': args.date, 'result': result, 'summary': summary}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
