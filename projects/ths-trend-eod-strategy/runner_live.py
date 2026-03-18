#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

import pandas as pd

from data_gateway import DataGateway
from notifier import print_console, write_markdown
from strategy_logic import evaluate_tail_candidate

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description='趋势尾盘实时筛选入口')
    parser.add_argument('--date', required=True)
    parser.add_argument('--json-out', default='')
    parser.add_argument('--history-mode', action='store_true', help='使用历史日线近似回放尾盘筛选')
    args = parser.parse_args()

    gateway = DataGateway()
    # V0 版本先使用 stock_basic 表做 universe，后续可升级成更精确候选宇宙
    import duckdb
    con = duckdb.connect(gateway.duckdb_path, read_only=True)
    stock_basic = con.execute("select symbol, name from stock_basic where symbol like '%.SH' or symbol like '%.SZ' limit 300").df()
    con.close()
    symbols = stock_basic['symbol'].tolist()
    names = dict(zip(stock_basic['symbol'], stock_basic['name']))

    results = []
    if args.history_mode:
        history_map = gateway.get_history(symbols, args.date, args.date)
        for symbol in symbols:
            df = history_map.get(symbol, pd.DataFrame())
            if df.empty:
                continue
            row = df.iloc[-1]
            amount = float(row['amount']) if 'amount' in row and pd.notna(row['amount']) else None
            candidate = evaluate_tail_candidate(
                symbol=symbol,
                name=names.get(symbol, symbol),
                current_price=float(row['close']) if 'close' in row and pd.notna(row['close']) else None,
                open_price=float(row['open']) if 'open' in row and pd.notna(row['open']) else None,
                high_price=float(row['high']) if 'high' in row and pd.notna(row['high']) else None,
                low_price=float(row['low']) if 'low' in row and pd.notna(row['low']) else None,
                amount=amount,
            )
            if candidate is None:
                continue
            if amount is not None and amount < gateway.config['strategy']['min_turnover_amount']:
                continue
            gain = candidate['intraday_gain_pct']
            if gain is not None and (gain < gateway.config['strategy']['min_intraday_gain_pct'] or gain > gateway.config['strategy']['max_intraday_gain_pct']):
                continue
            if candidate['tail_strength'] < gateway.config['strategy']['tail_strength_threshold']:
                continue
            results.append(candidate)
    else:
        realtime_map = gateway.get_realtime(symbols)
        for symbol in symbols:
            df = realtime_map.get(symbol, pd.DataFrame())
            if df.empty:
                continue
            row = df.iloc[-1]
            amount = float(row['amount']) if 'amount' in row and pd.notna(row['amount']) else None
            candidate = evaluate_tail_candidate(
                symbol=symbol,
                name=names.get(symbol, symbol),
                current_price=float(row['latest']) if 'latest' in row and pd.notna(row['latest']) else None,
                open_price=float(row['open']) if 'open' in row and pd.notna(row['open']) else None,
                high_price=float(row['high']) if 'high' in row and pd.notna(row['high']) else None,
                low_price=float(row['low']) if 'low' in row and pd.notna(row['low']) else None,
                amount=amount,
            )
            if candidate is None:
                continue
            if amount is not None and amount < gateway.config['strategy']['min_turnover_amount']:
                continue
            gain = candidate['intraday_gain_pct']
            if gain is not None and (gain < gateway.config['strategy']['min_intraday_gain_pct'] or gain > gateway.config['strategy']['max_intraday_gain_pct']):
                continue
            if candidate['tail_strength'] < gateway.config['strategy']['tail_strength_threshold']:
                continue
            results.append(candidate)

    results = sorted(results, key=lambda x: x['score'], reverse=True)[: gateway.config['strategy']['max_candidates']]
    out = {
        'status': 'ok',
        'generated_at': datetime.utcnow().isoformat(),
        'trade_date': args.date,
        'strategy': gateway.config['strategy']['name'],
        'strategy_state': 'tail_candidates_generated',
        'candidate_count': len(results),
        'candidates': results,
    }
    json_out = args.json_out or str(ROOT / f'tail_candidates_{args.date}.json')
    Path(json_out).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(out, ensure_ascii=False, indent=2))
    lines = [f"- {c['symbol']} {c['name']} | 分数={c['score']} | 日内涨幅={c['intraday_gain_pct']}% | 尾盘强度={c['tail_strength']} | 买入参考={c['trade_plan']['buy_price_ref']}" for c in results]
    print_console(lines)
    write_markdown(str(ROOT / f'tail_candidates_{args.date}.md'), f'趋势尾盘候选 {args.date}', lines)


if __name__ == '__main__':
    main()
