#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from analyzer import summarize_results
from notifier import build_summary_lines, print_console, write_markdown
from strategy_logic import evaluate_demo_signal

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description='实时运行入口（模板）')
    parser.add_argument('--date', required=True)
    args = parser.parse_args()

    sample_candidate = {
        'symbol': '000001.SZ',
        'name': '示例股票',
        'trade_plan': {'buy_price_ref': 10.0}
    }
    result = evaluate_demo_signal(sample_candidate, current_price=10.22, high_price=10.32, low_price=10.01, capital_imbalance=0.09)
    summary = summarize_results([result])
    lines = build_summary_lines([result])
    print_console(lines)
    write_markdown(str(ROOT / 'demo_live_report.md'), f'实时策略报告 {args.date}', lines)
    print(json.dumps({'date': args.date, 'summary': summary}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
