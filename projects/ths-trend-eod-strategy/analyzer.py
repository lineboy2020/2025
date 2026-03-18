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


def lightweight_grid_hint() -> Dict:
    return {
        'supported': True,
        'note': '当前模板仅预留轻量网格调参扩展位，可后续接入参数遍历与绩效比较。'
    }
