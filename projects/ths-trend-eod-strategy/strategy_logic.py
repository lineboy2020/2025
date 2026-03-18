#!/usr/bin/env python3
from __future__ import annotations

from typing import Dict, Optional


def classify_tail_strength(day_open: float, current_price: float, day_high: float, day_low: float) -> float:
    if day_high <= day_low:
        return 0.0
    return round((current_price - day_low) / (day_high - day_low), 4)


def build_trade_plan(price: float) -> Dict:
    return {
        'buy_window': '14:30-14:50',
        'buy_price_ref': round(price, 2),
        'stop_loss_price': round(price * 0.93, 2),
        'take_profit_plan': [
            {'target_pct': 3.0, 'price': round(price * 1.03, 2), 'sell_ratio': 0.35},
            {'target_pct': 5.0, 'price': round(price * 1.05, 2), 'sell_ratio': 0.35},
            {'target_pct': 8.0, 'price': round(price * 1.08, 2), 'sell_ratio': 0.30}
        ],
        'fallback': '若次日未触发止盈止损，尾盘择机清仓'
    }


def evaluate_tail_candidate(symbol: str,
                            name: str,
                            current_price: Optional[float],
                            open_price: Optional[float],
                            high_price: Optional[float],
                            low_price: Optional[float],
                            amount: Optional[float]) -> Optional[Dict]:
    if current_price is None or open_price is None or high_price is None or low_price is None:
        return None
    intraday_gain_pct = round((current_price / open_price - 1) * 100, 2) if open_price else None
    tail_strength = classify_tail_strength(open_price, current_price, high_price, low_price)

    risk_tags = []
    if intraday_gain_pct is not None and intraday_gain_pct > 7:
        risk_tags.append('涨幅过大谨慎追高')
    if tail_strength < 0.2:
        risk_tags.append('尾盘承接偏弱')

    score = 0.0
    score += max(min((intraday_gain_pct or 0) * 8, 40), -20)
    score += tail_strength * 40
    score += max(min((amount or 0) / 1e8, 20), 0)

    return {
        'symbol': symbol,
        'name': name,
        'score': round(score, 2),
        'intraday_gain_pct': intraday_gain_pct,
        'tail_strength': tail_strength,
        'amount': amount,
        'risk_tags': risk_tags,
        'trade_plan': build_trade_plan(current_price),
        'strategy_state': 'tail_candidate_ready'
    }
