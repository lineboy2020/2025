"""
缠论分析技能 - 同花顺数据接口模块
提供从同花顺获取数据并进行缠论分析的功能
"""

import sys
from pathlib import Path
import json

# 添加同花顺数据获取路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'ths-data-fetcher' / 'scripts'))

from unified_ths_downloader import UnifiedTHSDownloader
import pandas as pd


class ChanlunTHSDataInterface:
    """缠论分析 - 同花顺数据接口"""
    
    def __init__(self):
        self.downloader = None
        self.access_token = None
        self._load_config()
    
    def _load_config(self):
        """从配置文件加载同花顺配置"""
        try:
            # 优先从同花顺技能配置读取
            ths_config_path = Path('/root/.openclaw/workspace/skills/ths-data-fetcher/scripts/config.json')
            if ths_config_path.exists():
                with open(ths_config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    self.access_token = config.get('data_skills', {}).get('ths_http', {}).get('access_token')
                    if self.access_token:
                        print(f"✅ 已从同花顺配置读取 Token: {self.access_token[:20]}...")
                        return
            
            # 备用：从本技能配置读取
            local_config = Path(__file__).parent.parent / 'config.json'
            if local_config.exists():
                with open(local_config, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    self.access_token = config.get('ths_data', {}).get('access_token')
                    if self.access_token:
                        print(f"✅ 已从本地配置读取 Token: {self.access_token[:20]}...")
                        return
                        
        except Exception as e:
            print(f"⚠️ 读取配置失败: {e}")
        
        # 使用备用token
        self.access_token = "72a6f6c407b2d433353cdbfa46c8571c152fa724.signs_Njc0Nzc1OTU4"
        print(f"⚠️ 使用备用 Token")
    
    def __enter__(self):
        """上下文管理器入口"""
        self.downloader = UnifiedTHSDownloader(use_http=True)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        if self.downloader:
            self.downloader.__exit__(exc_type, exc_val, exc_tb)
    
    def get_stock_data(self, stock_code, start_date=None, end_date=None, period='1d'):
        """
        获取股票数据用于缠论分析
        
        Args:
            stock_code: 股票代码，如 '000001.SZ'
            start_date: 开始日期，如 '2024-01-01'
            end_date: 结束日期，如 '2024-12-31'
            period: 周期，'1d'日线, '1m'分钟线
            
        Returns:
            DataFrame: 包含OHLCV数据的DataFrame
        """
        try:
            if period == '1d':
                # 获取日线数据
                result = self.downloader.download_history_data(
                    stock_codes=[stock_code],
                    start_date=start_date or '2024-01-01',
                    end_date=end_date or pd.Timestamp.now().strftime('%Y-%m-%d')
                )
            elif period == '1m':
                # 获取分钟线数据
                result = self.downloader.download_hf_data(
                    stock_codes=[stock_code],
                    start_time=f"{start_date or '2024-01-01'} 09:30:00",
                    end_time=f"{end_date or pd.Timestamp.now().strftime('%Y-%m-%d')} 15:00:00"
                )
            else:
                raise ValueError(f"不支持的周期: {period}")
            
            if stock_code in result:
                df = result[stock_code]
                # 标准化列名
                column_mapping = {
                    'tradeDate': 'date',
                    'tradeTime': 'time',
                    'open': 'open',
                    'high': 'high',
                    'low': 'low',
                    'close': 'close',
                    'latest': 'close',
                    'volume': 'volume',
                    'amount': 'amount'
                }
                df = df.rename(columns=column_mapping)
                print(f"✅ 获取 {stock_code} 数据成功: {len(df)} 条")
                return df
            else:
                print(f"⚠️ 未获取到 {stock_code} 的数据")
                return None
                
        except Exception as e:
            print(f"❌ 获取数据失败: {e}")
            return None
    
    def analyze_stock(self, stock_code, start_date=None, end_date=None):
        """
        对股票进行缠论分析
        
        Args:
            stock_code: 股票代码
            start_date: 开始日期
            end_date: 结束日期
            
        Returns:
            dict: 缠论分析结果
        """
        from core_module import calculate_fractals, calculate_bi, calculate_zhongshu, detect_buy_points
        
        # 获取数据
        df = self.get_stock_data(stock_code, start_date, end_date)
        if df is None or df.empty:
            return None
        
        # 执行缠论分析
        print(f"🔍 开始缠论分析: {stock_code}")
        
        # 1. 计算分型
        df_fractals = calculate_fractals(df)
        print(f"✅ 分型计算完成")
        
        # 2. 计算笔
        bi_list = calculate_bi(df_fractals)
        print(f"✅ 笔识别完成: {len(bi_list)} 笔")
        
        # 3. 计算中枢
        zhongshu_list = calculate_zhongshu(bi_list)
        print(f"✅ 中枢识别完成: {len(zhongshu_list)} 个中枢")
        
        # 4. 识别买点
        buy_points = detect_buy_points(df_fractals, bi_list, zhongshu_list)
        print(f"✅ 买点识别完成: {len(buy_points)} 个买点")
        
        return {
            'stock_code': stock_code,
            'data': df_fractals,
            'bi_list': bi_list,
            'zhongshu_list': zhongshu_list,
            'buy_points': buy_points
        }


if __name__ == '__main__':
    # 测试代码
    with ChanlunTHSDataInterface() as interface:
        # 获取平安银行数据并分析
        result = interface.analyze_stock('000001.SZ', start_date='2024-01-01', end_date='2024-03-01')
        if result:
            print("\n📊 分析结果:")
            print(f"股票: {result['stock_code']}")
            print(f"笔数: {len(result['bi_list'])}")
            print(f"中枢数: {len(result['zhongshu_list'])}")
            print(f"买点: {result['buy_points']}")
