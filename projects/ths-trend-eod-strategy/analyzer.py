#!/usr/bin/env python3
from __future__ import annotations

from typing import Dict, List


def summarize_results(results: List[Dict]) -> Dict:
    total = len(results)
    tp = sum(1 for r in results if 'tp' in r.get('strategy_state', ''))
    sl = sum(1 for r in results if r.get('strategy_state') == 'stoploss_triggered')
    weakening = sum(1 for r in results if r.get('strategy_state') == 'capital_weakening')
    avg_return = round(sum((r.get('current_return_pct') or 0) for r in results) / total, 4) if total else 0.0
    return {
        'total': total,
        'tp_count': tp,
        'stoploss_count': sl,
        'weakening_count': weakening,
        'avg_return_pct': avg_return,
    }


def summarize_backtest_results(results: List[Dict]) -> Dict:
    total = len(results)
    if total == 0:
        return {
            'total': 0,
            'win_count': 0,
            'stoploss_count': 0,
            'avg_return_pct': 0.0,
            'tp_hit_count': 0,
        }
    win_count = sum(1 for r in results if (r.get('exit_return_pct') or 0) > 0)
    stoploss_count = sum(1 for r in results if r.get('exit_reason') == 'stop_loss')
    tp_hit_count = sum(1 for r in results if str(r.get('exit_reason', '')).startswith('take_profit'))
    avg_return = round(sum((r.get('exit_return_pct') or 0) for r in results) / total, 4)
    return {
        'total': total,
        'win_count': win_count,
        'stoploss_count': stoploss_count,
        'avg_return_pct': avg_return,
        'tp_hit_count': tp_hit_count,
    }


def lightweight_grid_hint() -> Dict:
    return {
        'supported': True,
        'note': '当前模板仅预留轻量网格调参扩展位，可后续接入参数遍历与绩效比较。'
    }
