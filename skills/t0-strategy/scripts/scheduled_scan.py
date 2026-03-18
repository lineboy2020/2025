#!/usr/bin/env python3
"""
T0策略定时扫描任务
在交易时段自动运行，检测信号并发送通知
"""

import os
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime, time, timedelta

# 添加路径
skill_dir = Path(__file__).parent.parent
sys.path.insert(0, str(skill_dir))
sys.path.insert(0, str(skill_dir.parent / 'ths-data-fetcher' / 'scripts'))

# 加载环境变量
env_file = skill_dir / '.env'
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ.setdefault(key, value)

from t0_strategy import T0StrategyEngine
from data_fetcher import T0DataFetcher as THSDataFetcher
from instant_notifier import T0InstantNotifier

class T0ScheduledScanner:
    """T0策略定时扫描器"""

    def __init__(self, trade_date=None, ignore_market_hours=False):
        self.engine = T0StrategyEngine()
        self.fetcher = THSDataFetcher()
        self.notifier = T0InstantNotifier()
        self.trade_date = trade_date or datetime.now().strftime('%Y-%m-%d')
        self.ignore_market_hours = ignore_market_hours or (trade_date is not None)
        self.notify_enabled = (trade_date is None)

        # 加载标的池
        self.watchlist = self._load_watchlist()

    def _load_watchlist(self):
        """加载监控股票列表"""
        config_file = skill_dir / 'config.json'
        if config_file.exists():
            with open(config_file) as f:
                config = json.load(f)
                return config.get('watchlist', {}).get('stocks', [])
        return ['000001.SZ', '600000.SH']  # 默认标的

    def is_trading_hours(self):
        """检查是否在交易时段"""
        if self.ignore_market_hours:
            return True
        now = datetime.now().time()

        # 上午 9:30 - 11:30
        morning_start = time(9, 30)
        morning_end = time(11, 30)

        # 下午 13:00 - 14:30 (T0策略建议14:30前平仓)
        afternoon_start = time(13, 0)
        afternoon_end = time(14, 30)

        return (
            (morning_start <= now <= morning_end) or
            (afternoon_start <= now <= afternoon_end)
        )

    def scan_stock(self, stock_code):
        """扫描单只股票"""
        try:
            print(f"🔍 扫描 {stock_code}...")

            # 获取日线数据：先看近60天，不够则自动补拉近1年
            trade_dt = datetime.strptime(self.trade_date, '%Y-%m-%d')
            end_date = self.trade_date
            start_date = (trade_dt - timedelta(days=60)).strftime('%Y-%m-%d')
            daily_data_result = self.fetcher.get_history_data(stock_code, start_date=start_date, end_date=end_date)
            if not daily_data_result or stock_code not in daily_data_result:
                print(f"  ⚠️ 无法获取日线数据")
                return []
            daily_data = daily_data_result[stock_code]
            if daily_data is None or daily_data.empty:
                print(f"  ⚠️ 日线数据为空")
                return []

            if len(daily_data) < self.engine.ma_long + 1:
                year_start = (trade_dt - timedelta(days=365)).strftime('%Y-%m-%d')
                print(f"  ↻ 日线样本不足({len(daily_data)}条)，自动补拉近1年历史...")
                daily_data_result = self.fetcher.get_history_data(stock_code, start_date=year_start, end_date=end_date, use_cache=True, write_cache=True)
                daily_data = daily_data_result.get(stock_code)
                if daily_data is None or daily_data.empty or len(daily_data) < self.engine.ma_long + 1:
                    print(f"  ⚠️ 历史数据仍不足: {0 if daily_data is None else len(daily_data)}条")
                    return []

            # 获取指定交易日分钟数据
            intraday_data = self.fetcher.get_minute_kline(stock_code, trade_date=self.trade_date)

            # 生成信号（自动触发通知）
            signals = self.engine.generate_all_signals(
                stock_code,
                daily_data,
                intraday_data,
                notify=self.notify_enabled
            )

            if signals:
                print(f"  ✅ 发现 {len(signals)} 个信号")
            else:
                print(f"  📭 无信号")

            return signals

        except Exception as e:
            print(f"  ❌ 扫描失败: {e}")
            return []

    def run_scan(self):
        """执行扫描"""
        print(f"\n{'='*60}")
        print(f"T0策略定时扫描 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"目标交易日: {self.trade_date}")
        print(f"通知开关: {'开启' if self.notify_enabled else '关闭(历史回放模式)'}")
        print(f"{'='*60}")

        # 检查交易时段
        if not self.is_trading_hours():
            print("⏰ 当前非交易时段，跳过扫描")
            print("交易时段: 09:30-11:30, 13:00-14:30")
            return 0

        total_signals = 0

        for stock in self.watchlist:
            signals = self.scan_stock(stock)
            total_signals += len(signals)

        print(f"\n{'='*60}")
        print(f"扫描完成: {len(self.watchlist)} 只股票，共 {total_signals} 个信号")
        print(f"{'='*60}\n")

        return total_signals


def main():
    """主入口"""
    parser = argparse.ArgumentParser(description='T0策略定时扫描')
    parser.add_argument('--date', type=str, help='指定交易日(YYYY-MM-DD)，用于历史回放测试')
    parser.add_argument('--ignore-market-hours', action='store_true', help='忽略交易时段限制')
    args = parser.parse_args()

    scanner = T0ScheduledScanner(trade_date=args.date, ignore_market_hours=args.ignore_market_hours)
    scanner.run_scan()


if __name__ == "__main__":
    main()
