#!/usr/bin/env python3
from __future__ import annotations

from typing import Dict, Optional


def classify_capital_state(imbalance: Optional[float]) -> str:
    if imbalance is None:
        return 'unknown'
    if imbalance >= 0.08:
        return 'strengthening'
    if imbalance <= -0.08:
        return 'weakening'
    return 'neutral'


def evaluate_demo_signal(candidate: Dict, current_price: Optional[float], high_price: Optional[float], low_price: Optional[float], capital_imbalance: Optional[float]) -> Dict:
    buy = float(candidate['trade_plan']['buy_price_ref'])
    tp3 = buy * 1.03
    tp5 = buy * 1.05
    tp8 = buy * 1.08
    sl7 = buy * 0.93

    capital_state = classify_capital_state(capital_imbalance)
    current_return = round((current_price / buy - 1) * 100, 2) if current_price else None

    action = 'hold_watch'
    state = 'intraday_monitoring'
    if high_price and high_price >= tp8:
        action, state = 'take_profit_final', 'tp8_triggered'
    elif high_price and high_price >= tp5:
        action, state = 'take_profit_partial_2', 'tp5_triggered'
    elif high_price and high_price >= tp3:
        action, state = 'take_profit_partial_1', 'tp3_triggered'
    elif low_price and low_price <= sl7:
        action, state = 'stop_loss', 'stoploss_triggered'
    elif capital_state == 'weakening' and current_return is not None and current_return < 1:
        action, state = 'reduce_or_watch', 'capital_weakening'

    return {
        'symbol': candidate['symbol'],
        'name': candidate['name'],
        'strategy_state': state,
        'current_price': current_price,
        'current_return_pct': current_return,
        'capital_state': capital_state,
        'suggested_action': action,
    }
