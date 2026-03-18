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


def infer_trend_from_history(history_df, ma_window: int = 20) -> int:
    if history_df is None or history_df.empty or len(history_df) < ma_window:
        return 0
    ma = history_df['close'].rolling(ma_window).mean().iloc[-1]
    close = float(history_df.iloc[-1]['close'])
    return 1 if close > ma else -1


def evaluate_etf_t0_signal(candidate: Dict,
                           current_price: Optional[float],
                           high_price: Optional[float],
                           low_price: Optional[float],
                           open_price: Optional[float],
                           capital_imbalance: Optional[float],
                           trend_d: int = 0,
                           trend_30: int = 0) -> Dict:
    buy_ref = float(candidate['trade_plan']['buy_price_ref'])
    capital_state = classify_capital_state(capital_imbalance)
    current_return = round((current_price / buy_ref - 1) * 100, 2) if current_price and buy_ref else None

    action = 'hold_watch'
    state = 'intraday_monitoring'

    is_dip_buy = current_price is not None and open_price is not None and current_price < open_price * (1 - 0.005)
    is_rally_sell = current_price is not None and open_price is not None and current_price > open_price * (1 + 0.005)
    hit_stop = low_price is not None and low_price <= buy_ref * (1 - 0.01)
    hit_tp1 = high_price is not None and high_price >= buy_ref * (1 + 0.01)
    hit_tp2 = high_price is not None and high_price >= buy_ref * (1 + 0.02)

    if hit_tp2:
        action, state = 'take_profit_final', 'tp2_triggered'
    elif hit_tp1:
        action, state = 'take_profit_partial', 'tp1_triggered'
    elif hit_stop:
        action, state = 'stop_loss', 'stoploss_triggered'
    elif is_dip_buy and (trend_d >= 0 or trend_30 >= 0):
        action, state = 'buy_on_dip', 'dip_buy_ready'
    elif is_rally_sell:
        action, state = 'sell_on_rebound', 'rebound_sell_ready'
    elif capital_state == 'weakening' and current_return is not None and current_return < 0.5:
        action, state = 'reduce_or_watch', 'capital_weakening'

    return {
        'symbol': candidate['symbol'],
        'name': candidate['name'],
        'strategy_state': state,
        'current_price': current_price,
        'open_price': open_price,
        'current_return_pct': current_return,
        'capital_state': capital_state,
        'trend_d': trend_d,
        'trend_30': trend_30,
        'suggested_action': action,
    }
