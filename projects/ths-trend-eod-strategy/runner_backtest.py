#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List

import duckdb

from analyzer import summarize_backtest_results
from data_gateway import DataGateway
from strategy_logic import evaluate_tail_candidate

ROOT = Path(__file__).resolve().parent


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


def load_universe(gateway: DataGateway) -> Dict[str, str]:
    con = duckdb.connect(gateway.duckdb_path, read_only=True)
    stock_basic = con.execute("select symbol, name from stock_basic where symbol like '%.SH' or symbol like '%.SZ' limit 300").df()
    con.close()
    return dict(zip(stock_basic['symbol'], stock_basic['name']))


def build_history_candidates(gateway: DataGateway, trade_date: str) -> List[Dict]:
    names = load_universe(gateway)
    symbols = list(names.keys())
    history_map = gateway.get_history(symbols, trade_date, trade_date)
    results = []
    cfg = gateway.config['strategy']
    for symbol in symbols:
        df = history_map.get(symbol)
        if df is None or df.empty:
            continue
        row = df.iloc[-1]
        amount = float(row['amount']) if 'amount' in row else None
        candidate = evaluate_tail_candidate(
            symbol=symbol,
            name=names.get(symbol, symbol),
            current_price=float(row['close']) if 'close' in row else None,
            open_price=float(row['open']) if 'open' in row else None,
            high_price=float(row['high']) if 'high' in row else None,
            low_price=float(row['low']) if 'low' in row else None,
            amount=amount,
        )
        if candidate is None:
            continue
        if amount is not None and amount < cfg['min_turnover_amount']:
            continue
        gain = candidate['intraday_gain_pct']
        if gain is not None and (gain < cfg['min_intraday_gain_pct'] or gain > cfg['max_intraday_gain_pct']):
            continue
        if candidate['tail_strength'] < cfg['tail_strength_threshold']:
            continue
        results.append(candidate)
    results = sorted(results, key=lambda x: x['score'], reverse=True)[: gateway.config['strategy']['max_candidates']]
    return results


def run_single_date(gateway: DataGateway, trade_date: str) -> Dict:
    candidates = build_history_candidates(gateway, trade_date)
    if not candidates:
        return {
            'date': trade_date,
            'candidate_count': 0,
            'evaluated_count': 0,
            'summary': summarize_backtest_results([]),
            'results': [],
        }
    buy_date = datetime.strptime(trade_date, '%Y-%m-%d').date()
    end_date = (buy_date + timedelta(days=3)).isoformat()
    history_map = gateway.get_history([c['symbol'] for c in candidates], trade_date, end_date)
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
    return {
        'date': trade_date,
        'candidate_count': len(candidates),
        'evaluated_count': len(results),
        'summary': summarize_backtest_results(results),
        'results': results,
    }


def aggregate_runs(runs: List[Dict]) -> Dict:
    all_results = []
    for r in runs:
        all_results.extend(r.get('results', []))
    total_days = len(runs)
    traded_days = sum(1 for r in runs if r.get('evaluated_count', 0) > 0)
    positive_days = sum(1 for r in runs if (r.get('summary') or {}).get('avg_return_pct', 0) > 0)
    base = summarize_backtest_results(all_results)
    base.update({
        'total_days': total_days,
        'traded_days': traded_days,
        'positive_days': positive_days,
        'day_win_rate': round(positive_days / traded_days, 4) if traded_days else 0.0,
    })
    return base


def main():
    parser = argparse.ArgumentParser(description='趋势尾盘历史回测入口')
    parser.add_argument('--date', default='')
    parser.add_argument('--candidate-file', default='')
    parser.add_argument('--batch-start', default='')
    parser.add_argument('--batch-end', default='')
    args = parser.parse_args()

    gateway = DataGateway()

    if args.batch_start and args.batch_end:
        con = duckdb.connect(gateway.duckdb_path, read_only=True)
        trading_days = con.execute(
            "select distinct trade_date from market_daily where trade_date >= ? and trade_date <= ? order by trade_date",
            [args.batch_start, args.batch_end]
        ).df()['trade_date'].astype(str).tolist()
        con.close()
        runs = [run_single_date(gateway, d) for d in trading_days[:-1]]
        print(json.dumps({
            'batch_start': args.batch_start,
            'batch_end': args.batch_end,
            'run_count': len(runs),
            'aggregate': aggregate_runs(runs),
            'runs': runs,
        }, ensure_ascii=False, indent=2))
        return

    if args.candidate_file:
        path = Path(args.candidate_file)
        if not path.exists():
            raise SystemExit(f'候选文件不存在: {args.candidate_file}')
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
        return

    if args.date:
        print(json.dumps(run_single_date(gateway, args.date), ensure_ascii=False, indent=2))
        return

    raise SystemExit('请提供 --date 或 --batch-start/--batch-end')


if __name__ == '__main__':
    main()
