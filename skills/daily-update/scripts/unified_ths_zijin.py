"""
同花顺SDK统一资金数据下载模块
专注于下载DDE大单净额数据，支持增量更新

【脚本定位】
- 本脚本用于落地资金流向原始分区数据（archive/zijin）。
- DuckDB 日常更新链路中的资金增量当前优先由 `archive/zijin` 分区数据回写 `capital_flow`；问财直连仅作为降级路径。
- 本脚本建议用于历史补采、回溯重建和字段核对。

【使用说明】
1. 功能：
   - 批量下载所有股票的DDE大单净额数据
   - 自动增量更新，跳过已存在的日期
   - 数据存储为Parquet格式，按日分区

2. 运行方式：
   # 默认运行（检查最近一个交易日的数据）
   python /root/.openclaw/workspace/skills/daily-update/scripts/unified_ths_zijin.py

   # 指定日期范围
   python /root/.openclaw/workspace/skills/daily-update/scripts/unified_ths_zijin.py --start 2025-01-01 --end 2025-01-31

3. 输出数据：
   - 路径：data/archive/zijin/trade_date=YYYY-MM-DD/data.parquet
   - 字段：
     * stock_code: 股票代码 (如 000001.SZ)
     * stock_name: 股票名称
     * dde_large_order_net_amount: DDE大单净额 (浮点数)
"""

import os
import sys
import time
import logging
import argparse
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

def resolve_project_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "config.json").exists() and (parent / "data").exists():
            return parent
    return current.parents[4]


project_root = resolve_project_root()
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from unified_ths_downloader import UnifiedTHSDownloader
except Exception:
    from .unified_ths_downloader import UnifiedTHSDownloader

# 导入路径配置
try:
    from data_path_config import DataPathConfig
    PATH_CONFIG_AVAILABLE = True
except ImportError:
    PATH_CONFIG_AVAILABLE = False
    DataPathConfig = None

class UnifiedTHSZijin(UnifiedTHSDownloader):
    """
    同花顺资金数据下载器
    继承自 UnifiedTHSDownloader，复用登录和日志功能
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 设置数据保存根目录
        if PATH_CONFIG_AVAILABLE:
            self.data_root = Path(DataPathConfig.ARCHIVE_DIR) / "zijin"
        else:
            self.data_root = project_root / "data" / "archive" / "zijin"
            
    def get_trade_dates(self, start_date: str, end_date: str) -> List[str]:
        """
        获取交易日历
        """
        try:
            self._ensure_login()
            # 使用 THS_DateQuery 获取交易日
            # 格式：THS_DateQuery('Exchange','dateType','startDate','endDate')
            # dateType: 101-上交所, 105-深交所
            import iFinDPy
            result = iFinDPy.THS_DateQuery('SSE', 'date', start_date, end_date)
            
            if hasattr(result, 'errorcode') and result.errorcode != 0:
                self.logger.error(f"获取交易日历失败: {result.errmsg}")
                # return []  <-- 注释掉这行，让其进入降级方案
                
            # 解析结果
            # 结果通常是逗号分隔的字符串
            if isinstance(result, str):
                dates = result.split(',')
            elif hasattr(result, 'data'):
                dates = result.data.split(',')
            else:
                dates = []
                
            # 格式化日期 YYYY-MM-DD
            formatted_dates = []
            for d in dates:
                try:
                    # 尝试解析多种格式
                    dt = pd.to_datetime(d)
                    formatted_dates.append(dt.strftime('%Y-%m-%d'))
                except:
                    continue
                    
            return sorted(list(set(formatted_dates)))
            
        except Exception as e:
            self.logger.error(f"获取交易日历异常: {e}")
        
        # 降级方案：使用pandas生成日期范围，跳过周末
        self.logger.warning("使用降级方案生成交易日（仅跳过周末）")
        dates = pd.date_range(start=start_date, end=end_date, freq='B')
        return [d.strftime('%Y-%m-%d') for d in dates]

    def download_daily_zijin(self, trade_date: str, force: bool = False) -> bool:
        """
        下载指定日期的全市场DDE大单净额数据
        
        Args:
            trade_date: 交易日期 YYYY-MM-DD
            force: 是否强制重新下载
        """
        # 检查是否已存在
        save_dir = self.data_root / f"trade_date={trade_date}"
        save_file = save_dir / "data.parquet"
        
        if not force and save_file.exists():
            self.logger.info(f"数据已存在，跳过: {trade_date}")
            return True
            
        try:
            self._ensure_login()
        except Exception as e:
            self.logger.error(f"登录失败，无法下载 {trade_date} 数据: {e}")
            return False

        import iFinDPy
        
        try:
            self.logger.info(f"正在下载 {trade_date} 资金数据...")
            
            # 构造问财查询语句
            # 查询全市场A股在指定日期的大单净额
            query = f"A股, {trade_date}, dde大单净额"
            
            # 调用接口
            # THS_WCQuery(query, 'indicators')
            result = iFinDPy.THS_WCQuery(query, 'stock_code,stock_name,dde_large_order_net_amount')
            
            df = self._result_to_dataframe(result)
            
            if df.empty:
                self.logger.warning(f"{trade_date} 无数据返回")
                return False
                
            # 数据清洗与重命名
            # 问财返回的列名通常带有日期后缀，如 "dde大单净额[20251223]"
            # 我们需要将其标准化为 "dde_large_order_net_amount"
            
            rename_dict = {}
            keep_cols = []
            
            for col in df.columns:
                col_lower = col.lower()
                if 'code' in col_lower or '股票代码' in col:
                    rename_dict[col] = 'stock_code'
                    keep_cols.append('stock_code')
                elif 'name' in col_lower or '股票简称' in col:
                    rename_dict[col] = 'stock_name'
                    keep_cols.append('stock_name')
                elif 'dde' in col_lower or '大单净额' in col:
                    rename_dict[col] = 'dde_large_order_net_amount'
                    keep_cols.append('dde_large_order_net_amount')
            
            # 执行重命名
            df.rename(columns=rename_dict, inplace=True)
            
            # 确保必需字段存在
            if 'stock_code' not in df.columns:
                self.logger.error(f"{trade_date} 数据缺失股票代码列")
                return False
                
            if 'dde_large_order_net_amount' not in df.columns:
                self.logger.error(f"{trade_date} 数据缺失大单净额列")
                return False
            
            # 标准化股票代码
            df['stock_code'] = df['stock_code'].apply(self._normalize_stock_code)
            
            # 转换数值类型
            df['dde_large_order_net_amount'] = pd.to_numeric(df['dde_large_order_net_amount'], errors='coerce')
            
            # 只保留需要的列
            final_cols = ['stock_code', 'stock_name', 'dde_large_order_net_amount']
            # 如果有额外有用的列也可以保留
            df = df[final_cols]
            
            # 保存数据
            save_dir.mkdir(parents=True, exist_ok=True)
            df.to_parquet(save_file, index=False)
            
            self.logger.info(f"✅ 成功保存 {trade_date} 数据，共 {len(df)} 条")
            return True
            
        except Exception as e:
            self.logger.error(f"下载 {trade_date} 数据失败: {e}")
            return False

    def update_zijin_data(self, start_date: str = '2025-01-01', end_date: str = None, force: bool = False):
        """
        批量更新资金数据
        """
        if not end_date:
            end_date = datetime.now().strftime('%Y-%m-%d')
            
        self.logger.info(f"开始更新资金数据: {start_date} -> {end_date}")
        
        # 获取交易日历
        trade_dates = self.get_trade_dates(start_date, end_date)
        
        if not trade_dates:
            self.logger.error("未获取到交易日历")
            # 降级方案
            self.logger.warning("使用降级方案生成交易日（仅跳过周末）")
            dates = pd.date_range(start=start_date, end=end_date, freq='B')
            trade_dates = [d.strftime('%Y-%m-%d') for d in dates]
            
        self.logger.info(f"共获取到 {len(trade_dates)} 个交易日")
        
        success_count = 0
        fail_count = 0
        
        for date in trade_dates:
            # 检查是否是未来日期
            if date > datetime.now().strftime('%Y-%m-%d'):
                continue
                
            if self.download_daily_zijin(date, force):
                success_count += 1
            else:
                fail_count += 1
                
            # 避免请求过于频繁
            time.sleep(0.5)
            
        self.logger.info(f"更新完成: 成功 {success_count}, 失败 {fail_count}")

def main():
    parser = argparse.ArgumentParser(description="同花顺资金数据下载工具")
    parser.add_argument("--start", type=str, help="开始日期 YYYY-MM-DD (不指定则默认检查最近交易日)")
    parser.add_argument("--end", type=str, help="结束日期 YYYY-MM-DD (默认今天)")
    parser.add_argument("--force", action="store_true", help="强制重新下载已存在的数据")
    
    args = parser.parse_args()
    
    # 使用上下文管理器自动处理登录登出
    with UnifiedTHSZijin() as downloader:
        start_date = args.start
        end_date = args.end
        
        # 如果未指定开始日期，启用“智能单日模式”
        if not start_date:
            today = datetime.now().strftime('%Y-%m-%d')
            downloader.logger.info(f"未指定日期范围，正在检测最近交易日 (基准日期: {today})...")
            
            # 尝试获取最近的交易日
            # 我们查询过去10天到今天的交易日，然后取最后一个
            check_start = (datetime.now() - timedelta(days=10)).strftime('%Y-%m-%d')
            trade_dates = downloader.get_trade_dates(check_start, today)
            
            if trade_dates:
                latest_trade_date = trade_dates[-1]
                downloader.logger.info(f"检测到最近交易日: {latest_trade_date}")
                start_date = latest_trade_date
                # 如果也是单日模式，end_date 也设为同一天
                if not end_date:
                    end_date = latest_trade_date
            else:
                downloader.logger.warning("无法获取最近交易日，默认使用今天")
                start_date = today
                if not end_date:
                    end_date = today

        downloader.update_zijin_data(
            start_date=start_date,
            end_date=end_date,
            force=args.force
        )

if __name__ == "__main__":
    main()
