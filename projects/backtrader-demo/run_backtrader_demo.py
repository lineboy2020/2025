# -*- coding: utf-8 -*-
"""最小可跑 Backtrader 回测示例

策略：双均线交叉
- 快线上穿慢线 -> 买入
- 快线下穿慢线 -> 卖出

直接运行：
    python3 run_backtrader_demo.py
"""

from __future__ import annotations

import math
from pathlib import Path

import backtrader as bt
import matplotlib
import pandas as pd

matplotlib.use('Agg')

BASE_DIR = Path(__file__).parent
DATA_PATH = BASE_DIR / 'sample_ohlcv.csv'
PLOT_PATH = BASE_DIR / 'backtrader_demo_plot.png'


class SmaCross(bt.Strategy):
    params = (
        ('fast', 5),
        ('slow', 20),
    )

    def __init__(self):
        self.fast_ma = bt.indicators.SMA(self.data.close, period=self.p.fast)
        self.slow_ma = bt.indicators.SMA(self.data.close, period=self.p.slow)
        self.cross = bt.indicators.CrossOver(self.fast_ma, self.slow_ma)

    def next(self):
        dt = self.datas[0].datetime.date(0)
        if not self.position and self.cross[0] > 0:
            self.buy(size=100)
            print(f'{dt} BUY  close={self.data.close[0]:.2f}')
        elif self.position and self.cross[0] < 0:
            self.close()
            print(f'{dt} SELL close={self.data.close[0]:.2f}')

    def notify_trade(self, trade):
        if trade.isclosed:
            print(f'   Trade PnL: gross={trade.pnl:.2f}, net={trade.pnlcomm:.2f}')


def generate_sample_csv(path: Path, n: int = 240):
    rows = []
    price = 100.0
    for i in range(n):
        date = pd.Timestamp('2024-01-01') + pd.Timedelta(days=i)
        if date.weekday() >= 5:
            continue
        trend = i * 0.08
        wave = math.sin(i / 7) * 3.0 + math.sin(i / 17) * 1.8
        close = 100 + trend + wave
        open_ = price
        high = max(open_, close) + 1.2
        low = min(open_, close) - 1.2
        volume = 100000 + i * 300
        rows.append([date.strftime('%Y-%m-%d'), round(open_, 2), round(high, 2), round(low, 2), round(close, 2), volume])
        price = close

    df = pd.DataFrame(rows, columns=['date', 'open', 'high', 'low', 'close', 'volume'])
    df.to_csv(path, index=False)
    return df


def run_backtest():
    if not DATA_PATH.exists():
        generate_sample_csv(DATA_PATH)

    df = pd.read_csv(DATA_PATH, parse_dates=['date'])
    df = df.set_index('date')

    cerebro = bt.Cerebro()
    cerebro.addstrategy(SmaCross, fast=5, slow=20)

    data = bt.feeds.PandasData(dataname=df)
    cerebro.adddata(data)

    cerebro.broker.setcash(100000.0)
    cerebro.broker.setcommission(commission=0.001)

    cerebro.addanalyzer(bt.analyzers.Returns, _name='returns')
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')

    print(f'初始资金: {cerebro.broker.getvalue():.2f}')
    results = cerebro.run()
    strat = results[0]
    print(f'最终资金: {cerebro.broker.getvalue():.2f}')

    ret = strat.analyzers.returns.get_analysis()
    dd = strat.analyzers.drawdown.get_analysis()
    trades = strat.analyzers.trades.get_analysis()

    print('--- 回测结果 ---')
    print(f"总收益率: {ret.get('rtot', 0):.4f}")
    print(f"年化收益率: {ret.get('rnorm100', 0):.2f}%")
    print(f"最大回撤: {dd.get('max', {}).get('drawdown', 0):.2f}%")
    print(f"总交易次数: {trades.get('total', {}).get('total', 0)}")
    print(f"盈利交易: {trades.get('won', {}).get('total', 0)}")
    print(f"亏损交易: {trades.get('lost', {}).get('total', 0)}")

    print('图表输出已跳过：当前环境缺少 tkinter，回测数值结果不受影响。')
    print(f'示例数据文件: {DATA_PATH}')


if __name__ == '__main__':
    run_backtest()
