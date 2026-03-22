#!/usr/bin/env python3
"""
针对指定股票列表，按“趋势尾盘选股”逻辑做单票回测。

逻辑：
1. 对每只股票逐日检查是否出现策略买点：
   - 过去10日存在大阳线（实体涨幅>=8%，成交量>=20日均量2倍，收盘在20日均线上）
   - 当前日期距离最近大阳线 2~7 天
   - 当前成交量 <= 大阳线成交量的60%
   - 当前收盘价 >= 大阳线最低价
2. 若命中，则在当日收盘买入，下一交易日开盘卖出
3. 同一股票不重叠持仓
4. 默认每个标的独立以 10 万元资金全仓回测，输出每只股票近一区间收益
"""

import os
import sys
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd

ths_skill_dir = Path("/root/.openclaw/workspace/skills/ths-data-fetcher")
sys.path.insert(0, str(ths_skill_dir / "sdk"))

env_file = ths_skill_dir / ".env"
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            if '=' in line and not line.startswith('#'):
                key, value = line.strip().split('=', 1)
                os.environ[key] = value


COMMISSION_RATE = 0.0003
MIN_COMMISSION = 5
STAMP_TAX = 0.001


def normalize_symbol(symbol: str) -> str:
    s = symbol.strip().upper()
    if s.endswith('.SH') or s.endswith('.SZ'):
        return s
    if s.startswith('6'):
        return f"{s}.SH"
    return f"{s}.SZ"


def calc_commission(amount: float, is_sell: bool = False) -> float:
    commission = max(amount * COMMISSION_RATE, MIN_COMMISSION)
    if is_sell:
        commission += amount * STAMP_TAX
    return commission


class THSClient:
    def __init__(self):
        self.ifindpy = None
        self.login()

    def login(self):
        import iFinDPy
        username = os.environ.get('THS_SDK_USERNAME', 'hss130')
        password = os.environ.get('THS_SDK_PASSWORD', '335d9e')
        result = iFinDPy.THS_iFinDLogin(username, password)
        if result != 0:
            raise RuntimeError(f"同花顺SDK登录失败: {result}")
        self.ifindpy = iFinDPy

    def logout(self):
        if self.ifindpy:
            self.ifindpy.THS_iFinDLogout()

    def get_history(self, code: str, start_date: str, end_date: str) -> pd.DataFrame:
        indicators = 'close,open,high,low,volume,amount,changeRatio'
        jsonparam = '{"period":"D","rptcategory":"1"}'
        result = self.ifindpy.THS_HQ(code, indicators, jsonparam, start_date, end_date)
        if not result or result.errorcode != 0:
            return pd.DataFrame()
        df = result.data.copy()
        df['time'] = pd.to_datetime(df['time'])
        df = df.sort_values('time').reset_index(drop=True)
        return df


def find_signals(df: pd.DataFrame, start_date: str, end_date: str) -> List[Dict]:
    if df.empty or len(df) < 10:
        return []

    data = df.copy()
    data['body_change'] = (data['close'] - data['open']) / data['open'] * 100
    data['volume_ma20'] = data['volume'].rolling(20, min_periods=5).mean()
    data['close_ma20'] = data['close'].rolling(20, min_periods=5).mean()
    data['date'] = data['time'].dt.strftime('%Y-%m-%d')

    start_dt = pd.to_datetime(start_date)
    end_dt = pd.to_datetime(end_date)
    signals: List[Dict] = []

    for i in range(len(data) - 1):
        row = data.iloc[i]
        trade_dt = row['time']
        if trade_dt < start_dt or trade_dt > end_dt:
            continue

        lookback = data.iloc[max(0, i - 10): i + 1].copy()
        if len(lookback) < 5:
            continue

        big_yang = lookback[
            (lookback['body_change'] >= 8) &
            (lookback['volume'] >= lookback['volume_ma20'] * 2) &
            (lookback['close'] > lookback['close_ma20'])
        ]
        if big_yang.empty:
            continue

        last_big = big_yang.iloc[-1]
        adjustment_days = (trade_dt - last_big['time']).days
        if adjustment_days < 2 or adjustment_days > 7:
            continue

        shrink_ratio = row['volume'] / last_big['volume'] if last_big['volume'] > 0 else 1
        if shrink_ratio > 0.6:
            continue

        if row['close'] < last_big['low']:
            continue

        next_row = data.iloc[i + 1]
        signals.append({
            'buy_date': row['date'],
            'buy_price': float(row['close']),
            'sell_date': next_row['time'].strftime('%Y-%m-%d'),
            'sell_price': float(next_row['open']),
            'big_yang_date': last_big['time'].strftime('%Y-%m-%d'),
            'adjustment_days': int(adjustment_days),
            'shrink_ratio': float(shrink_ratio),
            'buy_change': float(row['changeRatio']) if pd.notna(row['changeRatio']) else None,
        })
    return signals


def run_symbol_backtest(df: pd.DataFrame, start_date: str, end_date: str, initial_capital: float) -> Dict:
    cash = initial_capital
    signals = find_signals(df, start_date, end_date)
    trades = []
    wins = 0
    losses = 0
    equity_curve = [initial_capital]
    total_profit = 0.0
    total_loss = 0.0

    for s in signals:
        buy_price = s['buy_price']
        sell_price = s['sell_price']
        shares = int(cash / buy_price / 100) * 100
        if shares < 100:
            continue

        buy_amount = shares * buy_price
        buy_commission = calc_commission(buy_amount, is_sell=False)
        total_buy_cost = buy_amount + buy_commission
        if total_buy_cost > cash:
            shares = int((cash - MIN_COMMISSION) / buy_price / 100) * 100
            if shares < 100:
                continue
            buy_amount = shares * buy_price
            buy_commission = calc_commission(buy_amount, is_sell=False)
            total_buy_cost = buy_amount + buy_commission
            if total_buy_cost > cash:
                continue

        cash -= total_buy_cost
        sell_amount = shares * sell_price
        sell_commission = calc_commission(sell_amount, is_sell=True)
        net_sell = sell_amount - sell_commission
        cash += net_sell

        pnl = net_sell - buy_amount - buy_commission
        ret = pnl / total_buy_cost * 100 if total_buy_cost else 0
        if pnl > 0:
            wins += 1
            total_profit += pnl
        else:
            losses += 1
            total_loss += abs(pnl)

        trades.append({
            **s,
            'shares': shares,
            'buy_amount': round(buy_amount, 2),
            'sell_amount': round(sell_amount, 2),
            'pnl': round(pnl, 2),
            'trade_return_pct': round(ret, 2),
            'equity_after_trade': round(cash, 2),
        })
        equity_curve.append(cash)

    total_return = (cash - initial_capital) / initial_capital * 100
    total_trades = wins + losses
    win_rate = wins / total_trades * 100 if total_trades else 0.0
    pl_ratio = total_profit / total_loss if total_loss > 0 else None

    max_value = equity_curve[0]
    max_drawdown = 0.0
    for v in equity_curve:
        if v > max_value:
            max_value = v
        dd = (max_value - v) / max_value * 100 if max_value else 0.0
        max_drawdown = max(max_drawdown, dd)

    days = max((pd.to_datetime(end_date) - pd.to_datetime(start_date)).days, 1)
    annualized = ((cash / initial_capital) ** (365 / days) - 1) * 100 if cash > 0 else -100.0

    return {
        'initial_capital': round(initial_capital, 2),
        'final_capital': round(cash, 2),
        'total_return_pct': round(total_return, 2),
        'annualized_return_pct': round(annualized, 2),
        'trade_count': total_trades,
        'win_rate_pct': round(win_rate, 2),
        'pl_ratio': round(pl_ratio, 2) if pl_ratio is not None else None,
        'max_drawdown_pct': round(max_drawdown, 2),
        'trades': trades,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--symbols', required=True, help='逗号分隔，如 600900,000158')
    parser.add_argument('--start-date', required=True)
    parser.add_argument('--end-date', required=True)
    parser.add_argument('--initial-capital', type=float, default=100000)
    args = parser.parse_args()

    symbols = [normalize_symbol(x) for x in args.symbols.split(',') if x.strip()]
    client = THSClient()

    try:
        fetch_start = (pd.to_datetime(args.start_date) - pd.Timedelta(days=40)).strftime('%Y-%m-%d')
        results = {}
        for symbol in symbols:
            df = client.get_history(symbol, fetch_start, args.end_date)
            if df.empty:
                results[symbol] = {'error': 'no_data'}
                continue
            results[symbol] = run_symbol_backtest(df, args.start_date, args.end_date, args.initial_capital)
        print(pd.Series(results).to_json(force_ascii=False))
    finally:
        client.logout()


if __name__ == '__main__':
    main()
