"""
市场情绪指标计算器
功能：计算涨跌家数/涨停跌停家数/情绪分等市场情绪指标
数据来源：
    1. 同花顺问财接口（THS_WCQuery）- 优先使用，查询"A股,日期,涨幅"
    2. data\archive\history_d\2025.parquet - 本地备用
输出：data\index\qingxu.parquet
"""

import math
import sys
import time
from pathlib import Path
from typing import Optional, List, Tuple
from datetime import datetime, timedelta

import pandas as pd
import duckdb

def resolve_project_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "config.json").exists() and (parent / "data").exists():
            return parent
    return current.parents[4]


REPO_ROOT = resolve_project_root()
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "data" / "src"))

# 尝试导入同花顺SDK
try:
    import iFinDPy
    from unified_ths_downloader import UnifiedTHSDownloader
    IFIND_AVAILABLE = True
except ImportError:
    IFIND_AVAILABLE = False
    iFinDPy = None
    UnifiedTHSDownloader = None


# 涨停/跌停阈值（参考 compute_market_breadth_from_local_csv.py）
RATIO_LIMIT_THRESHOLDS = (19.9, 9.9)  # 区分20%板和10%板
RATIO_TOLERANCE = 0.2  # 容差（百分比点）


def is_limit_up(change_ratio: float) -> bool:
    """
    判断是否为涨停
    
    Args:
        change_ratio: 涨跌幅（百分比）
    
    Returns:
        bool: 是否为涨停
    """
    if math.isnan(change_ratio):
        return False
    
    for threshold in RATIO_LIMIT_THRESHOLDS:
        if change_ratio >= threshold - RATIO_TOLERANCE:
            return True
    
    return False


def is_limit_down(change_ratio: float) -> bool:
    """
    判断是否为跌停
    
    Args:
        change_ratio: 涨跌幅（百分比）
    
    Returns:
        bool: 是否为跌停
    """
    if math.isnan(change_ratio):
        return False
    
    for threshold in RATIO_LIMIT_THRESHOLDS:
        if change_ratio <= -(threshold - RATIO_TOLERANCE):
            return True
    
    return False


def is_limit_up_20pct(change_ratio: float) -> bool:
    """判断是否为20%板涨停"""
    if math.isnan(change_ratio):
        return False
    return change_ratio >= 19.9 - RATIO_TOLERANCE


def is_limit_down_20pct(change_ratio: float) -> bool:
    """判断是否为20%板跌停"""
    if math.isnan(change_ratio):
        return False
    return change_ratio <= -(19.9 - RATIO_TOLERANCE)


def is_limit_up_10pct(change_ratio: float) -> bool:
    """判断是否为10%板涨停（非20%板）"""
    if math.isnan(change_ratio):
        return False
    # 10%板涨停：>= 9.7 且 < 19.7
    return 9.9 - RATIO_TOLERANCE <= change_ratio < 19.9 - RATIO_TOLERANCE


def is_limit_down_10pct(change_ratio: float) -> bool:
    """判断是否为10%板跌停（非20%板）"""
    if math.isnan(change_ratio):
        return False
    # 10%板跌停：<= -9.7 且 > -19.7
    return -(9.9 - RATIO_TOLERANCE) >= change_ratio > -(19.9 - RATIO_TOLERANCE)


def is_explosion_10pct(row: pd.Series) -> bool:
    """
    判断是否为10%板炸板（涨停后打开）
    
    炸板条件：
    1. 最高价达到10%涨停价（前收盘价 × 1.1）
    2. 收盘价低于涨停价
    
    Args:
        row: 股票日线数据行，需包含 preClose, high, close 字段
    
    Returns:
        bool: 是否为10%板炸板
    """
    pre_close = row.get('preClose', None)
    high = row.get('high', None)
    close = row.get('close', None)
    
    if pd.isna(pre_close) or pd.isna(high) or pd.isna(close) or pre_close <= 0:
        return False
    
    # 计算10%涨停价（保留2位小数）
    limit_price_10pct = round(pre_close * 1.1, 2)
    
    # 判断：最高价达到涨停价，但收盘价低于涨停价
    return high >= limit_price_10pct and close < limit_price_10pct


def is_explosion_20pct(row: pd.Series) -> bool:
    """
    判断是否为20%板炸板（涨停后打开）
    
    炸板条件：
    1. 最高价达到20%涨停价（前收盘价 × 1.2）
    2. 收盘价低于涨停价
    
    Args:
        row: 股票日线数据行，需包含 preClose, high, close 字段
    
    Returns:
        bool: 是否为20%板炸板
    """
    pre_close = row.get('preClose', None)
    high = row.get('high', None)
    close = row.get('close', None)
    
    if pd.isna(pre_close) or pd.isna(high) or pd.isna(close) or pre_close <= 0:
        return False
    
    # 计算20%涨停价（保留2位小数）
    limit_price_20pct = round(pre_close * 1.2, 2)
    
    # 判断：最高价达到涨停价，但收盘价低于涨停价
    return high >= limit_price_20pct and close < limit_price_20pct


def is_suspended_stock(row: pd.Series, prev_row: Optional[pd.Series] = None) -> bool:
    """
    判断股票是否停牌
    停牌特征：数据与前一日完全一样（价格、成交量等）
    
    Args:
        row: 当前行数据
        prev_row: 前一行数据（同一股票的前一日数据）
    
    Returns:
        bool: 是否停牌
    """
    if prev_row is None:
        return False
    
    # 检查关键字段是否完全一致
    key_fields = ['preClose', 'open', 'high', 'low', 'close', 'volume', 'amount']
    
    for field in key_fields:
        if field in row.index and field in prev_row.index:
            if pd.isna(row[field]) or pd.isna(prev_row[field]):
                continue
            if row[field] != prev_row[field]:
                return False
    
    # 如果所有关键字段都一致，可能是停牌
    return True


def calc_market_emotion(df: pd.DataFrame, 
                       date_col: str = 'tradeDate',
                       change_col: str = 'changeRatio',
                       stock_col: str = 'stock_code') -> pd.DataFrame:
    """
    计算市场情绪指标
    
    Args:
        df: 市场数据DataFrame，必须包含以下列：
            - tradeDate: 交易日期
            - stock_code: 股票代码
            - changeRatio: 涨跌幅（百分比）
            - preClose, open, high, low, close, volume, amount: 价格和成交量数据
        date_col: 日期列名，默认'tradeDate'
        change_col: 涨跌幅列名，默认'changeRatio'
        stock_col: 股票代码列名，默认'stock_code'
    
    Returns:
        pd.DataFrame: 包含市场情绪指标的DataFrame，列包括：
            - tradeDate: 交易日期
            - rise_count: 上涨家数
            - fall_count: 下跌家数
            - limit_up_count: 涨停家数（总计）
            - limit_down_count: 跌停家数（总计）
            - limit_up_20pct: 20%板涨停家数
            - limit_down_20pct: 20%板跌停家数
            - limit_up_10pct: 10%板涨停家数
            - limit_down_10pct: 10%板跌停家数
            - explosion_count: 炸板家数（总计，涨停后打开）
            - explosion_10pct: 10%板炸板家数
            - explosion_20pct: 20%板炸板家数
            - explosion_rate: 炸板率（炸板数 / 涨停数）
            - total_count: 总股票数（排除停牌）
            - rise_ratio: 上涨比例
            - fall_ratio: 下跌比例
    """
    if df.empty:
        return pd.DataFrame()
    
    # 数据清洗：确保必要的列存在
    required_cols = [date_col, stock_col, change_col, 'preClose', 'open', 'high', 'low', 'close', 'volume', 'amount']
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        raise ValueError(f"缺少必要的列: {missing_cols}")
    
    # 复制数据，避免修改原DataFrame
    df = df.copy()
    
    # 确保日期列为字符串或日期类型
    if not pd.api.types.is_datetime64_any_dtype(df[date_col]):
        df[date_col] = pd.to_datetime(df[date_col])
    
    # 按股票代码和日期排序，便于判断停牌
    df = df.sort_values([stock_col, date_col]).reset_index(drop=True)
    
    # 标记停牌股票
    df['is_suspended'] = False
    for idx in range(1, len(df)):
        if df.loc[idx, stock_col] == df.loc[idx - 1, stock_col]:
            # 同一股票的前一日数据
            prev_row = df.loc[idx - 1]
            curr_row = df.loc[idx]
            if is_suspended_stock(curr_row, prev_row):
                df.loc[idx, 'is_suspended'] = True
    
    # 过滤停牌股票
    df = df[~df['is_suspended']].copy()
    
    # 确保涨跌幅列有效
    df[change_col] = pd.to_numeric(df[change_col], errors='coerce')
    
    # 过滤无效数据
    df = df[
        df[change_col].notna() & 
        df['preClose'].notna() & 
        (df['preClose'] > 0)
    ].copy()
    
    if df.empty:
        return pd.DataFrame()
    
    # 按日期分组计算
    results = []
    
    for trade_date, group in df.groupby(date_col):
        # 计算涨跌家数
        rise_count = (group[change_col] > 0).sum()
        fall_count = (group[change_col] < 0).sum()
        total_count = len(group)
        
        # 计算涨停跌停家数（总计）
        limit_up_count = group[change_col].apply(is_limit_up).sum()
        limit_down_count = group[change_col].apply(is_limit_down).sum()
        
        # 区分20%板和10%板
        limit_up_20pct = group[change_col].apply(is_limit_up_20pct).sum()
        limit_down_20pct = group[change_col].apply(is_limit_down_20pct).sum()
        limit_up_10pct = group[change_col].apply(is_limit_up_10pct).sum()
        limit_down_10pct = group[change_col].apply(is_limit_down_10pct).sum()
        
        # 计算炸板家数（从日线数据判断）
        explosion_10pct = group.apply(is_explosion_10pct, axis=1).sum()
        explosion_20pct = group.apply(is_explosion_20pct, axis=1).sum()
        explosion_count = explosion_10pct + explosion_20pct
        
        # 计算炸板率（炸板数 / 涨停数）
        explosion_rate = explosion_count / limit_up_count if limit_up_count > 0 else 0.0
        
        # 计算比例
        rise_ratio = rise_count / total_count if total_count > 0 else 0.0
        fall_ratio = fall_count / total_count if total_count > 0 else 0.0
        
        results.append({
            'tradeDate': trade_date if isinstance(trade_date, str) else trade_date.strftime('%Y-%m-%d'),
            'rise_count': int(rise_count),
            'fall_count': int(fall_count),
            'limit_up_count': int(limit_up_count),
            'limit_down_count': int(limit_down_count),
            'limit_up_20pct': int(limit_up_20pct),
            'limit_down_20pct': int(limit_down_20pct),
            'limit_up_10pct': int(limit_up_10pct),
            'limit_down_10pct': int(limit_down_10pct),
            'explosion_count': int(explosion_count),
            'explosion_10pct': int(explosion_10pct),
            'explosion_20pct': int(explosion_20pct),
            'explosion_rate': round(explosion_rate, 4),
            'total_count': int(total_count),
            'rise_ratio': round(rise_ratio, 4),
            'fall_ratio': round(fall_ratio, 4),
        })
    
    result_df = pd.DataFrame(results)
    
    # 按日期排序
    if not result_df.empty:
        result_df = result_df.sort_values('tradeDate').reset_index(drop=True)
    
    return result_df


class WencaiDataFetcher:
    """
    同花顺问财数据获取器
    使用THS_WCQuery接口获取A股涨跌数据
    """
    
    def __init__(self, username: Optional[str] = None, password: Optional[str] = None):
        """初始化"""
        self._sdk_client = None
        self.username = username
        self.password = password
        self._logged_in = False
    
    def _ensure_login(self) -> bool:
        """确保SDK已登录"""
        if not IFIND_AVAILABLE:
            print("[ERROR] 同花顺SDK不可用")
            return False
        
        if self._logged_in:
            return True
        
        try:
            # 尝试从UnifiedTHSDownloader获取登录
            if UnifiedTHSDownloader is not None:
                self._sdk_client = UnifiedTHSDownloader(
                    username=self.username,
                    password=self.password,
                    auto_login=True
                )
                self._logged_in = True
                return True
            else:
                # 直接登录
                result = iFinDPy.THS_iFinDLogin(self.username or "", self.password or "")
                if result == 0 or result == -201:  # 0=成功, -201=已登录
                    self._logged_in = True
                    return True
                print(f"[ERROR] SDK登录失败: {result}")
                return False
        except Exception as e:
            print(f"[ERROR] SDK登录异常: {e}")
            return False
    
    def fetch_daily_data(self, date_str: str) -> Optional[pd.DataFrame]:
        """
        通过问财获取指定日期的A股涨跌数据
        
        查询关键字: "A股,{date},涨幅"
        
        Args:
            date_str: 日期，格式 YYYY-MM-DD
            
        Returns:
            DataFrame: 包含涨跌幅的股票数据
        """
        if not self._ensure_login():
            return None
        
        # 构建查询关键字
        keyword = f"A股,{date_str},涨幅"
        print(f"[INFO] 问财查询: {keyword}")
        
        try:
            result = iFinDPy.THS_WCQuery(keyword, "stock")
            df = self._parse_result(result)
            
            if df is not None and not df.empty:
                # 标准化列名
                df = self._standardize_columns(df, date_str)
                print(f"[INFO] 获取到 {len(df)} 只股票数据")
                return df
            else:
                print(f"[WARN] {date_str} 无数据")
                return None
                
        except Exception as e:
            print(f"[ERROR] 问财查询失败: {e}")
            return None
    
    def _parse_result(self, result) -> Optional[pd.DataFrame]:
        """解析问财返回结果"""
        if result is None:
            return None
        
        # 检查错误码
        if hasattr(result, 'errorcode') and result.errorcode != 0:
            error_msg = getattr(result, 'errmsg', f'错误码: {result.errorcode}')
            print(f"[ERROR] 问财返回错误: {error_msg}")
            return None
        
        # 提取数据
        data = getattr(result, 'data', result)
        
        if isinstance(data, pd.DataFrame):
            return data.copy()
        
        if isinstance(data, dict):
            if 'tables' in data and data['tables']:
                return pd.DataFrame(data['tables'][0]['table'])
            return pd.DataFrame(data)
        
        if isinstance(data, list):
            return pd.DataFrame(data)
        
        return None
    
    def _standardize_columns(self, df: pd.DataFrame, date_str: str) -> pd.DataFrame:
        """标准化列名"""
        # 列名映射
        column_mapping = {
            'thscode': 'stock_code',
            'THSCODE': 'stock_code',
            'code': 'stock_code',
            '股票代码': 'stock_code',
            'stock_name': 'stock_name',
            '股票简称': 'stock_name',
            '股票名称': 'stock_name',
        }
        
        # 查找涨幅列（可能带日期后缀）
        date_short = date_str.replace('-', '')
        for col in df.columns:
            col_str = str(col)
            if '涨跌幅' in col_str or '涨幅' in col_str:
                column_mapping[col] = 'changeRatio'
            elif '收盘' in col_str or 'close' in col_str.lower():
                column_mapping[col] = 'close'
            elif '开盘' in col_str or 'open' in col_str.lower():
                column_mapping[col] = 'open'
            elif '最高' in col_str or 'high' in col_str.lower():
                column_mapping[col] = 'high'
            elif '最低' in col_str or 'low' in col_str.lower():
                column_mapping[col] = 'low'
            elif '前收' in col_str or 'preclose' in col_str.lower():
                column_mapping[col] = 'preClose'
            elif '成交量' in col_str or 'volume' in col_str.lower():
                column_mapping[col] = 'volume'
            elif '成交额' in col_str or 'amount' in col_str.lower():
                column_mapping[col] = 'amount'
        
        # 应用映射
        for old_col, new_col in column_mapping.items():
            if old_col in df.columns and new_col not in df.columns:
                df = df.rename(columns={old_col: new_col})
        
        # 添加日期列
        df['tradeDate'] = date_str
        
        return df
    
    def fetch_explosion_data(self, date_str: str) -> int:
        """
        通过问财获取指定日期的炸板数量
        
        查询关键字: "{date},炸板"
        
        Args:
            date_str: 日期，格式 YYYY-MM-DD
            
        Returns:
            int: 炸板数量
        """
        if not self._ensure_login():
            return 0
        
        # 构建查询关键字
        keyword = f"{date_str},炸板"
        print(f"[INFO] 问财查询炸板: {keyword}")
        
        try:
            result = iFinDPy.THS_WCQuery(keyword, "stock")
            df = self._parse_result(result)
            
            if df is not None and not df.empty:
                count = len(df)
                print(f"[INFO] 炸板数量: {count}")
                return count
            else:
                print(f"[WARN] {date_str} 无炸板数据")
                return 0
                
        except Exception as e:
            print(f"[ERROR] 问财查询炸板失败: {e}")
            return 0
    
    def logout(self):
        """登出"""
        if self._sdk_client is not None:
            try:
                self._sdk_client.logout()
            except Exception:
                pass
        self._logged_in = False


def fetch_data_via_wencai(dates: List[str], fetch_explosion: bool = True) -> Tuple[pd.DataFrame, dict]:
    """
    通过问财接口获取多个日期的数据
    
    Args:
        dates: 日期列表，格式 ['YYYY-MM-DD', ...]
        fetch_explosion: 是否同时获取炸板数据
        
    Returns:
        Tuple[DataFrame, dict]: (合并后的股票数据, 炸板数据字典{日期: 数量})
    """
    if not IFIND_AVAILABLE:
        print("[WARN] 同花顺SDK不可用，无法使用问财接口")
        return pd.DataFrame(), {}
    
    fetcher = WencaiDataFetcher()
    all_data = []
    explosion_data = {}
    
    try:
        for date_str in dates:
            print(f"\n[INFO] 获取 {date_str} 数据...")
            df = fetcher.fetch_daily_data(date_str)
            
            if df is not None and not df.empty:
                all_data.append(df)
                
                # 获取炸板数据
                if fetch_explosion:
                    time.sleep(0.5)  # 避免API限制
                    explosion_count = fetcher.fetch_explosion_data(date_str)
                    explosion_data[date_str] = explosion_count
            
            # 添加延迟避免API限制
            time.sleep(1)
        
        if all_data:
            result = pd.concat(all_data, ignore_index=True)
            print(f"\n[INFO] 总共获取 {len(result)} 条记录，{len(all_data)} 个交易日")
            return result, explosion_data
        
        return pd.DataFrame(), explosion_data
        
    finally:
        fetcher.logout()


def load_daily_data_from_duckdb(project_root: Path, target_date: str = None) -> pd.DataFrame:
    """优先从 kline_eod.duckdb / market_daily 加载日线数据。"""
    db_path = project_root / "data" / "db" / "kline_eod.duckdb"
    if not db_path.exists():
        return pd.DataFrame()
    con = None
    try:
        con = duckdb.connect(str(db_path), read_only=True)
        sql = """
            SELECT
                symbol AS stock_code,
                trade_date AS tradeDate,
                open,
                high,
                low,
                close,
                pre_close AS preClose,
                volume,
                amount,
                change_ratio AS changeRatio
            FROM market_daily
        """
        params = []
        if target_date:
            sql += " WHERE trade_date = ?"
            params.append(target_date)
        df = con.execute(sql, params).fetchdf()
        if not df.empty:
            df['tradeDate'] = pd.to_datetime(df['tradeDate'])
            df = df.sort_values(['stock_code', 'tradeDate']).reset_index(drop=True)
            if 'preClose' in df.columns:
                df['preClose'] = pd.to_numeric(df['preClose'], errors='coerce')
            else:
                df['preClose'] = pd.NA
            if 'changeRatio' in df.columns:
                df['changeRatio'] = pd.to_numeric(df['changeRatio'], errors='coerce')
            else:
                df['changeRatio'] = pd.NA
            prev_close = df.groupby('stock_code')['close'].shift(1)
            df['preClose'] = df['preClose'].fillna(prev_close)
            valid_mask = df['changeRatio'].isna() & df['preClose'].notna() & (pd.to_numeric(df['preClose'], errors='coerce') > 0)
            df.loc[valid_mask, 'changeRatio'] = (
                (pd.to_numeric(df.loc[valid_mask, 'close'], errors='coerce') /
                 pd.to_numeric(df.loc[valid_mask, 'preClose'], errors='coerce') - 1) * 100
            )
        return df
    except Exception as e:
        print(f"[WARN] 从 DuckDB 加载日线失败: {e}")
        return pd.DataFrame()
    finally:
        if con is not None:
            try:
                con.close()
            except Exception:
                pass


def load_daily_data(project_root: Path, year: int = None, target_date: str = None) -> pd.DataFrame:
    """
    加载日线数据
    优先顺序：
    1. data/archive/history_d/year={year} (分区存储)
    2. data/archive/history_d/{year}.parquet (单文件)
    
    Args:
        project_root: 项目根目录
        year: 年份（默认当前年份）
        target_date: 目标日期（YYYY-MM-DD），如果指定则只加载该日期，否则加载所有日期
    
    Returns:
        DataFrame: 日线数据
    """
    duckdb_df = load_daily_data_from_duckdb(project_root, target_date=target_date)
    if not duckdb_df.empty:
        print(f"[INFO] 从 DuckDB 加载成功，共 {len(duckdb_df)} 条")
        return duckdb_df

    if year is None:
        year = datetime.now().year
    
    all_data_list = []
    
    # 路径定义
    partition_dir = project_root / "data" / "archive" / "history_d" / f"year={year}"
    single_file = project_root / "data" / "archive" / "history_d" / f"{year}.parquet"
    
    print(f"[INFO] 尝试加载本地数据，年份: {year}")
    
    # 1. 尝试加载分区存储
    if partition_dir.exists():
        print(f"[INFO] 发现分区存储: {partition_dir}")
        try:
            # 尝试使用 pyarrow dataset 读取（更高效）
            import pyarrow.parquet as pq
            dataset = pq.ParquetDataset(partition_dir)
            df = dataset.read_pandas().to_pandas()
            all_data_list.append(df)
            print(f"[INFO] 分区数据加载成功，共 {len(df)} 条")
        except Exception as e:
            print(f"[WARN] 分区存储读取失败: {e}，尝试逐个文件读取...")
            # 回退到逐个文件读取
            files = sorted(partition_dir.glob("date=*.parquet"))
            if not files:
                print(f"[WARN] 分区目录下无 parquet 文件")
            
            for date_file in files:
                try:
                    all_data_list.append(pd.read_parquet(date_file))
                except Exception as e:
                    print(f"[WARN] 读取文件失败 {date_file}: {e}")
                    continue
    
    # 2. 如果分区加载失败或不存在，尝试加载单文件
    if not all_data_list and single_file.exists():
        print(f"[INFO] 发现单文件存储: {single_file}")
        try:
            df = pd.read_parquet(single_file)
            all_data_list.append(df)
            print(f"[INFO] 单文件加载成功，共 {len(df)} 条")
        except Exception as e:
            print(f"[ERROR] 读取单文件失败: {e}")

    if not all_data_list:
        print(f"[ERROR] 未找到本地数据文件")
        print(f"  - 检查路径 1: {partition_dir}")
        print(f"  - 检查路径 2: {single_file}")
        return pd.DataFrame()
    
    # 合并数据
    df = pd.concat(all_data_list, ignore_index=True)
    
    # 去重
    if 'stock_code' in df.columns and 'tradeDate' in df.columns:
        before_len = len(df)
        df = df.drop_duplicates(subset=['stock_code', 'tradeDate'], keep='last')
        if len(df) < before_len:
            print(f"[INFO] 去重完成: {before_len} -> {len(df)}")
    
    # 过滤指定日期
    if target_date:
        if 'tradeDate' in df.columns:
            # 确保日期格式一致
            target_dt = pd.to_datetime(target_date).date()
            df['tradeDate'] = pd.to_datetime(df['tradeDate'])
            df = df[df['tradeDate'].dt.date == target_dt].copy()
            print(f"[INFO] 过滤日期 {target_date}: 剩余 {len(df)} 条记录")
        else:
            print("[WARN] 数据中缺少 tradeDate 列，无法过滤日期")
            
    return df


def calc_emotion_from_wencai(df: pd.DataFrame, explosion_data: dict = None) -> pd.DataFrame:
    """
    从问财数据计算市场情绪指标（简化版，因为问财数据可能缺少部分字段）
    
    Args:
        df: 问财返回的数据，必须包含 tradeDate, changeRatio
        explosion_data: 炸板数据字典 {日期: 炸板数量}，可选
        
    Returns:
        DataFrame: 市场情绪指标
    """
    if df.empty:
        return pd.DataFrame()
    
    # 确保必要列存在
    if 'changeRatio' not in df.columns:
        print("[ERROR] 数据缺少涨跌幅列")
        return pd.DataFrame()
    
    df = df.copy()
    df['tradeDate'] = pd.to_datetime(df['tradeDate'])
    df['changeRatio'] = pd.to_numeric(df['changeRatio'], errors='coerce')
    
    # 过滤无效数据
    df = df[df['changeRatio'].notna()].copy()
    
    explosion_data = explosion_data or {}
    results = []
    
    for trade_date, group in df.groupby('tradeDate'):
        change = group['changeRatio']
        
        # 计算涨跌家数
        rise_count = (change > 0).sum()
        fall_count = (change < 0).sum()
        flat_count = (change == 0).sum()
        total_count = len(group)
        
        # 计算涨停跌停家数
        limit_up_count = change.apply(is_limit_up).sum()
        limit_down_count = change.apply(is_limit_down).sum()
        
        # 区分20%板和10%板
        limit_up_20pct = change.apply(is_limit_up_20pct).sum()
        limit_down_20pct = change.apply(is_limit_down_20pct).sum()
        limit_up_10pct = change.apply(is_limit_up_10pct).sum()
        limit_down_10pct = change.apply(is_limit_down_10pct).sum()
        
        # 获取炸板数据
        date_key = trade_date.strftime('%Y-%m-%d') if hasattr(trade_date, 'strftime') else str(trade_date)[:10]
        explosion_count = explosion_data.get(date_key, 0)
        
        # 如果没有从问财获取到炸板数据，且有价格数据，尝试自行计算
        if explosion_count == 0 and 'high' in group.columns and 'close' in group.columns and 'preClose' in group.columns:
            explosion_10pct = group.apply(is_explosion_10pct, axis=1).sum()
            explosion_20pct = group.apply(is_explosion_20pct, axis=1).sum()
            explosion_count = explosion_10pct + explosion_20pct
        
        # 计算炸板率
        explosion_rate = explosion_count / limit_up_count if limit_up_count > 0 else 0.0
        
        # 计算比例
        rise_ratio = rise_count / total_count if total_count > 0 else 0.0
        fall_ratio = fall_count / total_count if total_count > 0 else 0.0
        
        results.append({
            'tradeDate': date_key,
            'rise_count': int(rise_count),
            'fall_count': int(fall_count),
            'limit_up_count': int(limit_up_count),
            'limit_down_count': int(limit_down_count),
            'limit_up_20pct': int(limit_up_20pct),
            'limit_down_20pct': int(limit_down_20pct),
            'limit_up_10pct': int(limit_up_10pct),
            'limit_down_10pct': int(limit_down_10pct),
            'explosion_count': int(explosion_count),
            'explosion_10pct': 0,  # 问财炸板接口不区分板块
            'explosion_20pct': 0,  # 问财炸板接口不区分板块
            'explosion_rate': round(explosion_rate, 4),
            'total_count': int(total_count),
            'rise_ratio': round(rise_ratio, 4),
            'fall_ratio': round(fall_ratio, 4),
        })
    
    result_df = pd.DataFrame(results)
    if not result_df.empty:
        result_df = result_df.sort_values('tradeDate').reset_index(drop=True)
    
    return result_df


def update_market_emotion(project_root: Path, target_date: str = None, incremental: bool = True,
                          use_wencai: bool = True, dates_to_fetch: List[str] = None) -> pd.DataFrame:
    """
    更新市场情绪数据
    
    Args:
        project_root: 项目根目录
        target_date: 目标日期（YYYY-MM-DD），如果指定则只计算该日期
        incremental: 是否增量更新（只计算新增的日期）
        use_wencai: 是否使用问财接口获取数据（默认True）
        dates_to_fetch: 指定要获取的日期列表（优先级最高）
    
    Returns:
        DataFrame: 市场情绪指标数据
    """
    output_file = project_root / "data" / "db" / "qingxu.parquet"
    
    # 如果增量更新且输出文件存在，读取已有数据
    existing_dates = set()
    existing_df = None
    if output_file.exists():
        try:
            existing_df = pd.read_parquet(output_file)
            existing_dates = set(existing_df['tradeDate'].unique())
            print(f"[INFO] 已有数据日期数: {len(existing_dates)}")
        except Exception as e:
            print(f"[WARN] 读取已有数据失败: {e}")
    
    result_df = pd.DataFrame()
    
    # 情况1：指定日期列表（通过问财获取）
    if dates_to_fetch:
        print(f"\n[INFO] 使用问财接口获取指定日期数据: {dates_to_fetch}")
        if use_wencai and IFIND_AVAILABLE:
            df, explosion_data = fetch_data_via_wencai(dates_to_fetch, fetch_explosion=True)
            if not df.empty:
                result_df = calc_emotion_from_wencai(df, explosion_data=explosion_data)
        else:
            print("[WARN] 问财接口不可用")
    
    # 情况2：指定单个日期
    elif target_date:
        print(f"\n[INFO] 获取指定日期数据: {target_date}")
        
        # 优先使用问财
        if use_wencai and IFIND_AVAILABLE:
            df, explosion_data = fetch_data_via_wencai([target_date], fetch_explosion=True)
            if not df.empty:
                result_df = calc_emotion_from_wencai(df, explosion_data=explosion_data)
        
        # 如果问财失败，回退到本地数据
        if result_df.empty:
            print("[INFO] 问财数据为空，尝试本地数据...")
            df = load_daily_data(project_root, target_date=target_date)
            if not df.empty:
                result_df = calc_market_emotion(df)
    
    # 情况3：全量或增量更新（优先本地，失败则尝试问财当天回退）
    else:
        print("\n[INFO] 从本地数据计算...")
        df = load_daily_data(project_root)
        if df.empty:
            print("[WARN] 无本地数据")
            if use_wencai and IFIND_AVAILABLE:
                fallback_date = target_date or datetime.now().strftime('%Y-%m-%d')
                print(f"[INFO] 尝试问财回退获取: {fallback_date}")
                wc_df, explosion_data = fetch_data_via_wencai([fallback_date], fetch_explosion=True)
                if not wc_df.empty:
                    result_df = calc_emotion_from_wencai(wc_df, explosion_data=explosion_data)
                    if not result_df.empty:
                        print(f"[INFO] 问财回退成功: {fallback_date}")
                        # 继续走后续保存逻辑
                        df = pd.DataFrame({'tradeDate': []})
                    else:
                        return pd.DataFrame()
                else:
                    return pd.DataFrame()
            else:
                return pd.DataFrame()
        
        # 增量更新：过滤已有日期
        if incremental and existing_dates:
            df['tradeDate_str'] = pd.to_datetime(df['tradeDate']).dt.strftime('%Y-%m-%d')
            df = df[~df['tradeDate_str'].isin(existing_dates)].copy()
            if df.empty:
                print("[INFO] 所有日期已计算，无需更新")
                return pd.DataFrame()
            print(f"[INFO] 增量更新：需要计算 {df['tradeDate'].nunique()} 个新日期")
        
        if not df.empty:
            print(f"[INFO] 数据形状: {df.shape}")
            df['tradeDate'] = pd.to_datetime(df['tradeDate'])
            print(f"[INFO] 日期范围: {df['tradeDate'].min()} 至 {df['tradeDate'].max()}")
            
            print("\n[INFO] 开始计算市场情绪指标...")
            result_df = calc_market_emotion(df)
    
    if result_df.empty:
        print("[WARN] 计算结果为空")
        return pd.DataFrame()
    
    print(f"\n[INFO] 计算结果:")
    print(result_df.tail(10))
    print(f"\n[INFO] 共计算 {len(result_df)} 个交易日的数据")
    
    # 合并已有数据
    if existing_df is not None and not existing_df.empty:
        try:
            # 确保日期列类型一致（都转换为字符串）
            existing_df['tradeDate'] = existing_df['tradeDate'].astype(str)
            result_df['tradeDate'] = result_df['tradeDate'].astype(str)
            
            # 移除已有日期中与新数据重叠的部分
            existing_df = existing_df[~existing_df['tradeDate'].isin(result_df['tradeDate'])].copy()
            result_df = pd.concat([existing_df, result_df], ignore_index=True)
            result_df = result_df.sort_values('tradeDate').reset_index(drop=True)
            print(f"[INFO] 合并后总数据: {len(result_df)} 个交易日")
        except Exception as e:
            print(f"[WARN] 合并已有数据失败: {e}")
    
    # 保存结果
    output_file.parent.mkdir(parents=True, exist_ok=True)
    print(f"\n[INFO] 保存结果到: {output_file}")
    result_df.to_parquet(output_file, index=False)
    print("[INFO] 保存完成！")
    
    return result_df


if __name__ == "__main__":
    project_root = REPO_ROOT
    
    # 解析命令行参数
    target_date = None
    incremental = True
    use_wencai = True
    dates_to_fetch = None
    
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        arg = args[i]
        
        if arg == "--date":
            if i + 1 < len(args):
                target_date = args[i + 1]
                i += 2
            else:
                print("[ERROR] --date 参数需要指定日期 (YYYY-MM-DD)")
                sys.exit(1)
        
        elif arg == "--dates":
            # 获取多个日期，逗号分隔
            if i + 1 < len(args):
                dates_to_fetch = [d.strip() for d in args[i + 1].split(',')]
                i += 2
            else:
                print("[ERROR] --dates 参数需要指定日期列表 (YYYY-MM-DD,YYYY-MM-DD)")
                sys.exit(1)
        
        elif arg == "--full":
            incremental = False
            i += 1
        
        elif arg == "--today":
            target_date = datetime.now().strftime('%Y-%m-%d')
            i += 1
        
        elif arg == "--local":
            use_wencai = False
            i += 1
        
        elif arg == "--wencai":
            use_wencai = True
            i += 1
        
        elif arg == "--help" or arg == "-h":
            print("""
市场情绪指标计算器

用法:
    python qingxu.py [选项]

选项:
    --date YYYY-MM-DD     获取指定日期数据
    --dates D1,D2,...     获取多个日期数据（逗号分隔）
    --today               获取今日数据
    --full                全量重新计算（不增量）
    --local               仅使用本地数据（不调用问财）
    --wencai              使用问财接口（默认）
    --help, -h            显示帮助

示例:
    python qingxu.py --dates 2026-01-19,2026-01-20
    python qingxu.py --date 2026-01-20
    python qingxu.py --today
    python qingxu.py --full --local
            """)
            sys.exit(0)
        
        else:
            print(f"[WARN] 未知参数: {arg}")
            i += 1
    
    print("=" * 60)
    print("市场情绪指标计算器")
    print("=" * 60)
    
    if dates_to_fetch:
        print(f"[INFO] 模式: 问财获取多日期")
        print(f"[INFO] 日期列表: {dates_to_fetch}")
    elif target_date:
        print(f"[INFO] 模式: 单日期")
        print(f"[INFO] 目标日期: {target_date}")
    else:
        print(f"[INFO] 模式: {'增量更新' if incremental else '全量计算'}")
    
    print(f"[INFO] 数据源: {'问财优先' if use_wencai else '仅本地'}")
    print("=" * 60)
    
    # 更新市场情绪数据
    result_df = update_market_emotion(
        project_root, 
        target_date=target_date, 
        incremental=incremental,
        use_wencai=use_wencai,
        dates_to_fetch=dates_to_fetch
    )
    
    if result_df.empty:
        print("[WARN] 未生成新数据")
        sys.exit(0)
    
    # 显示最新数据
    print("\n" + "=" * 60)
    print("最新数据:")
    print("=" * 60)
    print(result_df.tail(5).to_string(index=False))
