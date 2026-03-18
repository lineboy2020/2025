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
from market_regime_adapter import classify_regime
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


def build_history_candidates(gateway: DataGateway, trade_date: str, overrides: Dict | None = None) -> List[Dict]:
    names = load_universe(gateway)
    symbols = list(names.keys())
    history_map = gateway.get_history(symbols, trade_date, trade_date)
    results = []
    cfg = dict(gateway.config['strategy'])
    if overrides:
        cfg.update({k: v for k, v in overrides.items() if v is not None})
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
    results = sorted(results, key=lambda x: x['score'], reverse=True)[: cfg['max_candidates']]
    return results


def compute_market_regime(gateway: DataGateway, trade_date: str, overrides: Dict | None = None) -> Dict:
    names = load_universe(gateway)
    symbols = list(names.keys())
    history_map = gateway.get_history(symbols, trade_date, trade_date)
    gains = []
    strong_count = 0
    weak_count = 0
    for symbol in symbols:
        df = history_map.get(symbol)
        if df is None or df.empty:
            continue
        row = df.iloc[-1]
        if 'open' not in row or 'close' not in row:
            continue
        o = float(row['open'])
        c = float(row['close'])
        if o <= 0:
            continue
        g = (c / o - 1) * 100
        gains.append(g)
        if g >= 4:
            strong_count += 1
        if g <= -3:
            weak_count += 1
    total = len(gains)
    avg_gain = round(sum(gains) / total, 4) if total else 0.0
    strong_ratio = round(strong_count / total, 4) if total else 0.0
    weak_ratio = round(weak_count / total, 4) if total else 0.0
    regime_cfg = {
        'regime_min_avg_gain_pct': 0.5,
        'regime_min_strong_ratio': 0.08,
        'regime_max_weak_ratio': 0.12,
    }
    if overrides:
        regime_cfg.update({k: v for k, v in overrides.items() if v is not None})
    return {
        'total': total,
        'avg_gain_pct': avg_gain,
        'strong_ratio': strong_ratio,
        'weak_ratio': weak_ratio,
        'thresholds': regime_cfg,
        'risk_on': avg_gain >= regime_cfg['regime_min_avg_gain_pct'] and strong_ratio >= regime_cfg['regime_min_strong_ratio'] and weak_ratio <= regime_cfg['regime_max_weak_ratio'],
    }


def run_single_date(gateway: DataGateway, trade_date: str, overrides: Dict | None = None) -> Dict:
    if overrides and overrides.get('use_market_emotion_filter'):
        regime = classify_regime(trade_date)
        if regime.get('regime_mode') == 'risk_off':
            return {
                'date': trade_date,
                'candidate_count': 0,
                'evaluated_count': 0,
                'summary': summarize_backtest_results([]),
                'results': [],
                'regime': regime,
                'skipped_by_regime_filter': True,
            }
        emotion_overrides = dict(overrides or {})
        emotion_overrides['max_candidates'] = regime.get('regime_max_candidates', overrides.get('max_candidates', 2))
        candidates = build_history_candidates(gateway, trade_date, overrides=emotion_overrides)
    else:
        regime = compute_market_regime(gateway, trade_date, overrides=overrides)
        if overrides and overrides.get('use_regime_filter') and not regime.get('risk_on'):
            return {
                'date': trade_date,
                'candidate_count': 0,
                'evaluated_count': 0,
                'summary': summarize_backtest_results([]),
                'results': [],
                'regime': regime,
                'skipped_by_regime_filter': True,
            }
        candidates = build_history_candidates(gateway, trade_date, overrides=overrides)
    if not candidates:
        return {
            'date': trade_date,
            'candidate_count': 0,
            'evaluated_count': 0,
            'summary': summarize_backtest_results([]),
            'results': [],
            'regime': regime,
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
        'regime': regime,
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


def score_aggregate(agg: Dict) -> float:
    return round(
        (agg.get('avg_return_pct', 0.0) * 4)
        + (agg.get('day_win_rate', 0.0) * 10)
        + (agg.get('tp_hit_count', 0) * 0.2)
        - (agg.get('stoploss_count', 0) * 0.8),
        4,
    )


def main():
    parser = argparse.ArgumentParser(description='趋势尾盘历史回测入口')
    parser.add_argument('--date', default='')
    parser.add_argument('--candidate-file', default='')
    parser.add_argument('--batch-start', default='')
    parser.add_argument('--batch-end', default='')
    parser.add_argument('--max-intraday-gain-pct', type=float, default=None)
    parser.add_argument('--tail-strength-threshold', type=float, default=None)
    parser.add_argument('--min-turnover-amount', type=float, default=None)
    parser.add_argument('--max-candidates', type=int, default=None)
    parser.add_argument('--scan-grid', action='store_true')
    parser.add_argument('--use-regime-filter', action='store_true')
    parser.add_argument('--use-market-emotion-filter', action='store_true')
    parser.add_argument('--regime-min-avg-gain-pct', type=float, default=None)
    parser.add_argument('--regime-min-strong-ratio', type=float, default=None)
    parser.add_argument('--regime-max-weak-ratio', type=float, default=None)
    parser.add_argument('--scan-regime-grid', action='store_true')
    args = parser.parse_args()

    gateway = DataGateway()
    overrides = {
        'max_intraday_gain_pct': args.max_intraday_gain_pct,
        'tail_strength_threshold': args.tail_strength_threshold,
        'min_turnover_amount': args.min_turnover_amount,
        'max_candidates': args.max_candidates,
        'use_regime_filter': args.use_regime_filter,
        'use_market_emotion_filter': args.use_market_emotion_filter,
        'regime_min_avg_gain_pct': args.regime_min_avg_gain_pct,
        'regime_min_strong_ratio': args.regime_min_strong_ratio,
        'regime_max_weak_ratio': args.regime_max_weak_ratio,
    }

    if args.batch_start and args.batch_end and args.scan_grid:
        con = duckdb.connect(gateway.duckdb_path, read_only=True)
        trading_days = con.execute(
            "select distinct trade_date from market_daily where trade_date >= ? and trade_date <= ? order by trade_date",
            [args.batch_start, args.batch_end]
        ).df()['trade_date'].astype(str).tolist()
        con.close()
        grid = []
        for max_gain in [6.5, 7.0, 8.0]:
            for tail_strength in [0.4, 0.5, 0.6]:
                for min_amount in [2e8, 5e8, 8e8]:
                    for max_candidates in [2, 3]:
                        ov = {
                            'max_intraday_gain_pct': max_gain,
                            'tail_strength_threshold': tail_strength,
                            'min_turnover_amount': min_amount,
                            'max_candidates': max_candidates,
                        }
                        runs = [run_single_date(gateway, d, overrides=ov) for d in trading_days[:-1]]
                        agg = aggregate_runs(runs)
                        grid.append({
                            'params': ov,
                            'aggregate': agg,
                            'score': score_aggregate(agg),
                        })
        grid = sorted(grid, key=lambda x: x['score'], reverse=True)
        print(json.dumps({
            'batch_start': args.batch_start,
            'batch_end': args.batch_end,
            'grid_size': len(grid),
            'top_results': grid[:10],
            'bottom_results': grid[-10:],
        }, ensure_ascii=False, indent=2))
        return

    if args.batch_start and args.batch_end and args.scan_regime_grid:
        con = duckdb.connect(gateway.duckdb_path, read_only=True)
        trading_days = con.execute(
            "select distinct trade_date from market_daily where trade_date >= ? and trade_date <= ? order by trade_date",
            [args.batch_start, args.batch_end]
        ).df()['trade_date'].astype(str).tolist()
        con.close()
        grid = []
        base_params = {
            'max_intraday_gain_pct': 7.0,
            'tail_strength_threshold': 0.5,
            'min_turnover_amount': 5e8,
            'max_candidates': 2,
            'use_regime_filter': True,
        }
        for min_avg in [0.0, 0.1, 0.2, 0.3, 0.5]:
            for min_strong in [0.03, 0.04, 0.05, 0.06, 0.08]:
                for max_weak in [0.10, 0.12, 0.15]:
                    ov = dict(base_params)
                    ov.update({
                        'regime_min_avg_gain_pct': min_avg,
                        'regime_min_strong_ratio': min_strong,
                        'regime_max_weak_ratio': max_weak,
                    })
                    runs = [run_single_date(gateway, d, overrides=ov) for d in trading_days[:-1]]
                    agg = aggregate_runs(runs)
                    grid.append({
                        'params': ov,
                        'aggregate': agg,
                        'score': score_aggregate(agg),
                        'skipped_days': sum(1 for r in runs if r.get('skipped_by_regime_filter')),
                    })
        grid = sorted(grid, key=lambda x: x['score'], reverse=True)
        print(json.dumps({
            'batch_start': args.batch_start,
            'batch_end': args.batch_end,
            'grid_size': len(grid),
            'top_results': grid[:15],
            'bottom_results': grid[-15:],
        }, ensure_ascii=False, indent=2))
        return

    if args.batch_start and args.batch_end:
        con = duckdb.connect(gateway.duckdb_path, read_only=True)
        trading_days = con.execute(
            "select distinct trade_date from market_daily where trade_date >= ? and trade_date <= ? order by trade_date",
            [args.batch_start, args.batch_end]
        ).df()['trade_date'].astype(str).tolist()
        con.close()
        runs = [run_single_date(gateway, d, overrides=overrides) for d in trading_days[:-1]]
        print(json.dumps({
            'batch_start': args.batch_start,
            'batch_end': args.batch_end,
            'run_count': len(runs),
            'overrides': overrides,
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
