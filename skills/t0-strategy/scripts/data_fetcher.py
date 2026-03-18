"""
T0策略数据获取模块 - 支持同花顺HTTP接口和akshare备用数据源
"""

import os
import sys
import json
import logging
import requests
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Union
import pandas as pd
import duckdb

# 尝试导入iFinDPy SDK
try:
    import iFinDPy
    IFIND_AVAILABLE = True
except ImportError:
    IFIND_AVAILABLE = False
    iFinDPy = None

# 尝试导入akshare作为备用数据源
try:
    import akshare as ak
    AKSHARE_AVAILABLE = True
except ImportError:
    AKSHARE_AVAILABLE = False
    ak = None


class T0DataFetcher:
    """
    T0策略数据获取器
    
    数据源优先级：
    1. 同花顺HTTP接口（THS_HQ/THS_SS）- 需要access_token
    2. akshare备用数据源 - 无需配置，开箱即用
    """
    
    # API配置
    HTTP_BASE_URL = "https://quantapi.51ifind.com/api/v1"
    
    # 标准字段映射
    FIELD_MAPPING = {
        'thscode': 'stock_code',
        'time': 'tradeTime',
        'tradeDate': 'tradeDate',
        'tradeTime': 'tradeTime',
        'preClose': 'preClose',
        'open': 'open',
        'high': 'high',
        'low': 'low',
        'close': 'close',
        'latest': 'latest',
        'volume': 'volume',
        'amount': 'amount',
        'changeRatio': 'changeRatio',
        'turnoverRatio': 'turnoverRatio',
        'floatCapitalOfAShares': 'floatCapitalOfAShares',
    }
    
    def __init__(self, use_http: bool = True, verbose: bool = False, use_akshare_fallback: bool = True):
        """
        初始化数据获取器
        
        Args:
            use_http: 是否使用HTTP接口（True）或SDK（False）
            verbose: 是否显示详细日志
            use_akshare_fallback: 当THS不可用时是否使用akshare作为备用
        """
        self.use_http = use_http
        self.verbose = verbose
        self.use_akshare_fallback = use_akshare_fallback
        self.access_token = None
        self.token_expire_time = None
        self.http_token = None
        self.http_enabled = False
        self.akshare_enabled = AKSHARE_AVAILABLE and use_akshare_fallback
        self.skill_dir = Path(__file__).parent.parent
        self.workspace_root = self.skill_dir.parent.parent
        self.cache_db_path = self.workspace_root / 'data' / 'db' / 't0_strategy.duckdb'
        
        # 配置日志
        self.logger = logging.getLogger('T0DataFetcher')
        if verbose:
            logging.basicConfig(level=logging.INFO)
        
        # 加载配置
        self.config = self._load_config()
        
        # 加载环境变量和项目配置
        self._load_env()
        
        # 检查数据源可用性
        self._check_data_sources()
    
    def _check_data_sources(self):
        """检查数据源可用性"""
        if self.http_enabled:
            self.logger.info("✅ 同花顺HTTP数据源可用")
        elif IFIND_AVAILABLE:
            self.logger.info("✅ 同花顺SDK数据源可用")
        elif self.akshare_enabled:
            self.logger.info("✅ akshare备用数据源可用")
        else:
            self.logger.warning("❌ 无可用的数据源")
    
    def _load_config(self) -> Dict:
        """加载配置文件"""
        config_path = self.skill_dir / 'config.json'
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    
    def _load_env(self):
        """加载环境变量和项目配置"""
        # 项目根目录 (skills/t0-strategy -> skills -> workspace)
        project_root = self.skill_dir.parent.parent
        
        # 尝试从项目根目录加载.env
        env_path = project_root / '.env'
        if env_path.exists():
            with open(env_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        os.environ.setdefault(key.strip(), value.strip())
        
        # 从项目根目录config.json读取配置
        root_config_path = project_root / 'config.json'
        if root_config_path.exists():
            try:
                with open(root_config_path, 'r', encoding='utf-8') as f:
                    root_config = json.load(f)
                    
                    # 读取同花顺HTTP配置
                    ths_http = root_config.get('data_skills', {}).get('ths_http', {})
                    if ths_http.get('enabled'):
                        self.http_token = ths_http.get('access_token', '')
                        self.http_enabled = bool(self.http_token)
                        self.logger.info(f"从项目配置加载THS_HTTP: enabled={self.http_enabled}")
                    
                    # 读取同花顺SDK配置
                    ths_sdk = root_config.get('ths_sdk', {})
                    self.username = ths_sdk.get('username', '')
                    self.password = ths_sdk.get('password', '')
                    
            except Exception as e:
                self.logger.warning(f"读取项目配置失败: {e}")
        
        # 环境变量覆盖
        self.refresh_token = os.getenv('THS_REFRESH_TOKEN', '')
        if os.getenv('THS_USERNAME'):
            self.username = os.getenv('THS_USERNAME')
        if os.getenv('THS_PASSWORD'):
            self.password = os.getenv('THS_PASSWORD')
    
    def _normalize_stock_code(self, code: str) -> str:
        """标准化股票代码"""
        code = code.strip().upper()
        
        # 已经是标准格式
        if '.' in code:
            return code
        
        # 根据代码前缀判断市场
        if code.startswith(('6', '9')):
            return f"{code}.SH"
        elif code.startswith(('0', '3', '2')):
            return f"{code}.SZ"
        elif code.startswith(('4', '8')):
            return f"{code}.BJ"
        
        return code
    
    def _get_access_token(self) -> Optional[str]:
        """获取访问令牌"""
        # 1. 优先使用项目配置中的已签名token
        if self.http_enabled and self.http_token:
            self.logger.info("使用项目配置的access_token")
            return self.http_token
        
        # 2. 检查缓存的动态令牌是否有效
        if self.access_token and self.token_expire_time:
            if datetime.now() < self.token_expire_time:
                return self.access_token
        
        # 3. 使用refresh_token获取新令牌
        if not self.refresh_token:
            self.logger.warning("未配置THS_REFRESH_TOKEN，且无项目配置的access_token")
            return None
        
        try:
            url = f"{self.HTTP_BASE_URL}/get_access_token"
            payload = {"refresh_token": self.refresh_token}
            
            response = requests.post(url, json=payload, timeout=30)
            result = response.json()
            
            if result.get('errorcode') == 0:
                self.access_token = result.get('data', {}).get('access_token')
                self.token_expire_time = datetime.now() + timedelta(hours=1, minutes=50)
                self.logger.info("获取access_token成功")
                return self.access_token
            else:
                self.logger.error(f"获取access_token失败: {result.get('errmsg')}")
                return None
                
        except Exception as e:
            self.logger.error(f"获取access_token异常: {e}")
            return None
    
    def _http_post(self, endpoint: str, payload: Dict) -> Dict:
        """发送HTTP POST请求"""
        token = self._get_access_token()
        if not token:
            raise ValueError("无法获取access_token")
        
        url = f"{self.HTTP_BASE_URL}/{endpoint}"
        headers = {
            "Content-Type": "application/json",
            "access_token": token
        }
        
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        
        if response.status_code == 401:
            self.logger.error(f"HTTP 401 Unauthorized. Token前10位: {token[:10]}...")
            raise ValueError("Token无效或已过期")
        
        response.raise_for_status()
        result = response.json()
        
        if result.get('errorcode', 0) != 0:
            raise RuntimeError(f"THS API错误: {result.get('errmsg')} (code: {result.get('errorcode')})")
        
        return result
    
    def _result_to_dataframe(self, result: Dict) -> pd.DataFrame:
        """将API结果转换为DataFrame"""
        if not result:
            return pd.DataFrame()
        
        if 'tables' in result:
            tables = result.get('tables', [])
            if tables:
                table_item = tables[0]
                thscode = table_item.get('thscode', '')
                time_list = table_item.get('time', [])
                
                if 'table' in table_item:
                    table_data = table_item['table'].copy()
                    if time_list:
                        table_data['time'] = time_list
                    df = pd.DataFrame(table_data)
                    if thscode and 'stock_code' not in df.columns:
                        df['stock_code'] = thscode
                    return df
                
                if time_list:
                    df_data = {}
                    for key, value in table_item.items():
                        if isinstance(value, list):
                            df_data[key] = value
                    
                    df = pd.DataFrame(df_data)
                    if thscode and 'stock_code' not in df.columns:
                        df['stock_code'] = thscode
                    return df
        
        if hasattr(result, 'data'):
            return pd.DataFrame(result.data)
        
        return pd.DataFrame()
    
    def _standardize_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """标准化DataFrame列名"""
        rename_map = {}
        for old_name, new_name in self.FIELD_MAPPING.items():
            if old_name in df.columns:
                rename_map[old_name] = new_name
        
        if rename_map:
            df = df.rename(columns=rename_map)
        
        numeric_cols = ['open', 'high', 'low', 'close', 'latest', 'preClose', 
                        'volume', 'amount', 'changeRatio', 'turnoverRatio']
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        return df
    
    # ==================== akshare 备用数据源 ====================
    
    def _get_history_akshare(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """使用akshare获取历史数据"""
        if not AKSHARE_AVAILABLE:
            raise ImportError("akshare未安装，无法使用备用数据源")
        
        # 转换日期格式
        start_date_fmt = start_date.replace('-', '')
        end_date_fmt = end_date.replace('-', '')
        
        # 解析股票代码
        code = stock_code.split('.')[0]
        market = "sh" if ".SH" in stock_code else "sz"
        
        try:
            # 使用akshare获取历史行情
            df = ak.stock_zh_a_hist(symbol=code, period="daily", 
                                     start_date=start_date_fmt, end_date=end_date_fmt,
                                     adjust="qfq")
            
            if df.empty:
                return pd.DataFrame()
            
            # 标准化列名
            df = df.rename(columns={
                '日期': 'tradeDate',
                '开盘': 'open',
                '收盘': 'close',
                '最高': 'high',
                '最低': 'low',
                '成交量': 'volume',
                '成交额': 'amount',
                '振幅': 'amplitude',
                '涨跌幅': 'changeRatio',
                '涨跌额': 'change',
                '换手率': 'turnoverRatio'
            })
            
            # 添加股票代码
            df['stock_code'] = stock_code
            
            # 计算preClose
            df['preClose'] = df['close'].shift(1)
            
            # 转换日期格式
            df['tradeDate'] = pd.to_datetime(df['tradeDate']).dt.strftime('%Y-%m-%d')
            
            return df
            
        except Exception as e:
            self.logger.error(f"akshare获取历史数据失败 {stock_code}: {e}")
            return pd.DataFrame()
    
    def _get_minute_akshare(self, stock_code: str, trade_date: str, period: str = "5") -> pd.DataFrame:
        """使用akshare获取分钟K线数据"""
        if not AKSHARE_AVAILABLE:
            raise ImportError("akshare未安装，无法使用备用数据源")
        
        code = stock_code.split('.')[0]
        start_date = trade_date.replace('-', '')
        end_date = start_date
        
        try:
            # 使用akshare获取分钟数据
            # 注意：akshare的分钟数据可能需要特定接口
            df = ak.stock_zh_a_hist_min_em(symbol=code, period=period,
                                            start_date=start_date, end_date=end_date,
                                            adjust="qfq")
            
            if df.empty:
                return pd.DataFrame()
            
            # 标准化列名
            df = df.rename(columns={
                '时间': 'tradeTime',
                '开盘': 'open',
                '收盘': 'close',
                '最高': 'high',
                '最低': 'low',
                '成交量': 'volume',
                '成交额': 'amount'
            })
            
            # 提取日期和时间
            df['tradeDate'] = df['tradeTime'].str[:10]
            df['tradeTime'] = df['tradeTime'].str[11:19]
            df['stock_code'] = stock_code
            
            return df
            
        except Exception as e:
            self.logger.error(f"akshare获取分钟数据失败 {stock_code}: {e}")
            return pd.DataFrame()
    
    def _get_realtime_akshare(self, stock_codes: List[str]) -> Dict[str, pd.DataFrame]:
        """使用akshare获取实时数据"""
        if not AKSHARE_AVAILABLE:
            raise ImportError("akshare未安装，无法使用备用数据源")
        
        results = {}
        
        for code in stock_codes:
            try:
                symbol = code.split('.')[0]
                # 获取实时行情
                df = ak.stock_zh_a_spot_em()
                stock_row = df[df['代码'] == symbol]
                
                if stock_row.empty:
                    continue
                
                # 转换为标准格式
                row = stock_row.iloc[0]
                data = {
                    'stock_code': [code],
                    'tradeDate': [datetime.now().strftime('%Y-%m-%d')],
                    'tradeTime': [datetime.now().strftime('%H:%M:%S')],
                    'open': [row['今开']],
                    'high': [row['最高']],
                    'low': [row['最低']],
                    'latest': [row['最新价']],
                    'close': [row['最新价']],
                    'preClose': [row['昨收']],
                    'volume': [row['成交量']],
                    'amount': [row['成交额']],
                    'changeRatio': [row['涨跌幅']]
                }
                
                results[code] = pd.DataFrame(data)
                
            except Exception as e:
                self.logger.error(f"akshare获取实时数据失败 {code}: {e}")
        
        return results
    
    # ==================== 主接口 ====================
    
    def _ensure_history_cache_table(self):
        self.cache_db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = duckdb.connect(str(self.cache_db_path))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS history_daily (
                stock_code VARCHAR,
                trade_date DATE,
                preClose DOUBLE,
                open DOUBLE,
                high DOUBLE,
                low DOUBLE,
                close DOUBLE,
                changeRatio DOUBLE,
                volume DOUBLE,
                amount DOUBLE,
                floatCapitalOfAShares DOUBLE
            )
        """)
        conn.close()

    def _normalize_history_df_for_cache(self, stock_code: str, df: pd.DataFrame) -> pd.DataFrame:
        work = df.copy()
        if 'tradeTime' in work.columns:
            work['trade_date'] = pd.to_datetime(work['tradeTime']).dt.date
        elif 'tradeDate' in work.columns:
            work['trade_date'] = pd.to_datetime(work['tradeDate']).dt.date
        elif 'time' in work.columns:
            work['trade_date'] = pd.to_datetime(work['time']).dt.date
        else:
            raise RuntimeError('history df missing tradeTime/tradeDate/time')
        work['stock_code'] = stock_code
        cols = ['stock_code','trade_date','preClose','open','high','low','close','changeRatio','volume','amount','floatCapitalOfAShares']
        for c in cols:
            if c not in work.columns:
                work[c] = None
        return work[cols].drop_duplicates(['stock_code','trade_date'], keep='last')

    def _write_history_cache(self, results: Dict[str, pd.DataFrame]):
        if not results:
            return
        self._ensure_history_cache_table()
        conn = duckdb.connect(str(self.cache_db_path))
        try:
            for stock_code, df in results.items():
                if df is None or df.empty:
                    continue
                cache_df = self._normalize_history_df_for_cache(stock_code, df)
                conn.register('cache_df_view', cache_df)
                conn.execute("DELETE FROM history_daily WHERE stock_code = ? AND trade_date IN (SELECT trade_date FROM cache_df_view)", [stock_code])
                conn.execute("INSERT INTO history_daily SELECT * FROM cache_df_view")
            conn.close()
        except Exception:
            conn.close()
            raise

    def _read_history_cache(self, codes: List[str], start_date: str, end_date: str) -> Dict[str, pd.DataFrame]:
        if not self.cache_db_path.exists():
            return {}
        conn = duckdb.connect(str(self.cache_db_path), read_only=True)
        try:
            placeholders = ','.join(['?'] * len(codes))
            sql = f"SELECT * FROM history_daily WHERE stock_code IN ({placeholders}) AND trade_date BETWEEN ? AND ? ORDER BY stock_code, trade_date"
            rows = conn.execute(sql, codes + [start_date, end_date]).fetchdf()
        finally:
            conn.close()
        results = {}
        if rows.empty:
            return results
        for code, group in rows.groupby('stock_code'):
            out = group.copy()
            out['tradeTime'] = out['trade_date'].astype(str)
            results[code] = out.reset_index(drop=True)
        return results

    def get_history_data(self, 
                          stock_codes: Union[str, List[str]],
                          start_date: str,
                          end_date: str,
                          indicators: str = None,
                          use_cache: bool = True,
                          write_cache: bool = True) -> Dict[str, pd.DataFrame]:
        """
        获取历史行情数据
        优先读本地缓存，缺失时再拉取并回写缓存。
        """
        codes = [stock_codes] if isinstance(stock_codes, str) else stock_codes
        codes = [self._normalize_stock_code(c) for c in codes]

        if use_cache:
            cached = self._read_history_cache(codes, start_date, end_date)
            if len(cached) == len(codes) and all(df is not None and not df.empty for df in cached.values()):
                return cached
        else:
            cached = {}

        results = {}

        if self.http_enabled or self.refresh_token:
            try:
                results = self._get_history_ths(codes, start_date, end_date, indicators)
            except Exception as e:
                self.logger.warning(f"THS获取历史数据失败，尝试akshare: {e}")

        if (not results or len(results) < len(codes)) and self.akshare_enabled:
            missing = [c for c in codes if c not in results or results[c] is None or results[c].empty]
            for code in missing:
                df = self._get_history_akshare(code, start_date, end_date)
                if not df.empty:
                    results[code] = df
                    self.logger.info(f"akshare获取历史数据成功: {code}")

        merged = dict(cached)
        merged.update(results)
        if write_cache and results:
            self._write_history_cache(results)
        return merged
    
    def _get_history_ths(self, codes: List[str], start_date: str, end_date: str, 
                         indicators: str = None) -> Dict[str, pd.DataFrame]:
        """使用THS获取历史数据"""
        if indicators is None:
            indicators = self.config.get('data', {}).get(
                'history_indicators',
                "preClose,open,high,low,close,changeRatio,volume,amount"
            )
        
        results = {}
        codes_str = ','.join(codes)
        payload = {
            "codes": codes_str,
            "indicators": indicators,
            "startdate": start_date,
            "enddate": end_date,
            "period": "D",
            "adjust": "1"
        }
        
        result = self._http_post("cmd_history_quotation", payload)
        df = self._result_to_dataframe(result)
        
        if not df.empty:
            df = self._standardize_dataframe(df)
            
            if 'stock_code' in df.columns:
                for code, group_df in df.groupby('stock_code'):
                    results[code] = group_df.copy().reset_index(drop=True)
            else:
                if len(codes) == 1:
                    df['stock_code'] = codes[0]
                    results[codes[0]] = df
        
        return results
    
    def get_snapshot_data(self,
                           stock_codes: Union[str, List[str]],
                           trade_date: str,
                           start_time: str = "09:15:00",
                           end_time: str = "15:15:00",
                           indicators: str = None) -> Dict[str, pd.DataFrame]:
        """获取日内快照数据"""
        codes = [stock_codes] if isinstance(stock_codes, str) else stock_codes
        codes = [self._normalize_stock_code(c) for c in codes]
        
        results = {}
        
        # 尝试使用THS接口
        if self.http_enabled or self.refresh_token:
            try:
                results = self._get_snapshot_ths(codes, trade_date, start_time, end_time, indicators)
                if results:
                    return results
            except Exception as e:
                self.logger.warning(f"THS获取快照数据失败，尝试akshare: {e}")
        
        # 使用akshare备用数据源
        if self.akshare_enabled:
            for code in codes:
                df = self._get_minute_akshare(code, trade_date, period="5")
                if not df.empty:
                    results[code] = df
                    self.logger.info(f"akshare获取分钟数据成功: {code}")
        
        return results
    
    def _get_snapshot_ths(self, codes: List[str], trade_date: str, 
                          start_time: str, end_time: str, indicators: str) -> Dict[str, pd.DataFrame]:
        """使用THS获取快照数据"""
        results = {}
        
        for code in codes:
            try:
                starttime = f"{trade_date} {start_time}"
                endtime = f"{trade_date} {end_time}"
                
                payload = {
                    "codes": code,
                    "indicators": "open,high,low,close,volume,amount",
                    "starttime": starttime,
                    "endtime": endtime
                }
                
                result = self._http_post("high_frequency", payload)
                df = self._result_to_dataframe(result)
                
                if not df.empty:
                    df = self._standardize_dataframe(df)
                    if 'stock_code' not in df.columns:
                        df['stock_code'] = code
                    results[code] = df
                    self.logger.info(f"HTTP获取分钟数据成功: {code}, {len(df)}条")
                    
            except Exception as e:
                self.logger.error(f"HTTP获取分钟数据失败 {code}: {e}")
        
        return results
    
    def get_realtime_data(self,
                           stock_codes: Union[str, List[str]],
                           indicators: str = None) -> Dict[str, pd.DataFrame]:
        """获取实时行情数据"""
        codes = [stock_codes] if isinstance(stock_codes, str) else stock_codes
        codes = [self._normalize_stock_code(c) for c in codes]
        
        results = {}
        
        # 尝试使用THS接口
        if self.http_enabled or self.refresh_token:
            try:
                results = self._get_realtime_ths(codes, indicators)
                if results:
                    return results
            except Exception as e:
                self.logger.warning(f"THS获取实时数据失败，尝试akshare: {e}")
        
        # 使用akshare备用数据源
        if self.akshare_enabled:
            results = self._get_realtime_akshare(codes)
        
        return results
    
    def _get_realtime_ths(self, codes: List[str], indicators: str = None) -> Dict[str, pd.DataFrame]:
        """使用THS获取实时数据"""
        if indicators is None:
            indicators = "tradeDate,tradeTime,preClose,open,high,low,latest,volume,amount,changeRatio"
        
        results = {}
        codes_str = ','.join(codes)
        payload = {
            "codes": codes_str,
            "indicators": indicators
        }
        
        result = self._http_post("real_time_quotation", payload)
        df = self._result_to_dataframe(result)
        
        if not df.empty:
            df = self._standardize_dataframe(df)
            
            if 'stock_code' in df.columns:
                for code, group_df in df.groupby('stock_code'):
                    results[code] = group_df.copy().reset_index(drop=True)
            else:
                if len(codes) == 1:
                    df['stock_code'] = codes[0]
                    results[codes[0]] = df
        
        return results
    
    def get_minute_kline(self,
                          stock_code: str,
                          trade_date: str,
                          period: str = "5") -> pd.DataFrame:
        """获取分钟K线数据"""
        code = self._normalize_stock_code(stock_code)
        
        # 优先使用THS
        if self.http_enabled or self.refresh_token:
            try:
                indicators = "tradeDate;tradeTime;open;high;low;close;volume;amount"
                results = self._get_snapshot_ths([code], trade_date, "09:30:00", "15:00:00", indicators)
                
                if code in results:
                    df = results[code]
                    if period != "1" and 'tradeTime' in df.columns:
                        df = self._resample_kline(df, int(period))
                    return df
            except Exception as e:
                self.logger.warning(f"THS获取分钟K线失败，尝试akshare: {e}")
        
        # 使用akshare
        if self.akshare_enabled:
            return self._get_minute_akshare(code, trade_date, period)
        
        return pd.DataFrame()
    
    def _resample_kline(self, df: pd.DataFrame, period: int) -> pd.DataFrame:
        """重采样K线数据"""
        if df.empty or 'tradeTime' not in df.columns:
            return df
        
        df = df.copy()
        if 'tradeDate' in df.columns:
            df['datetime'] = pd.to_datetime(df['tradeDate'].astype(str) + ' ' + df['tradeTime'])
        else:
            df['datetime'] = pd.to_datetime(df['tradeTime'])
        
        df = df.set_index('datetime')
        
        agg_dict = {
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum',
            'amount': 'sum'
        }
        
        agg_dict = {k: v for k, v in agg_dict.items() if k in df.columns}
        
        resampled = df.resample(f'{period}min').agg(agg_dict)
        resampled = resampled.dropna()
        resampled = resampled.reset_index()
        
        return resampled


if __name__ == "__main__":
    # 测试代码
    fetcher = T0DataFetcher(use_http=True, verbose=True, use_akshare_fallback=True)
    
    # 测试获取历史数据
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    
    print(f"测试获取历史数据: 000001.SZ {start_date} ~ {end_date}")
    history_data = fetcher.get_history_data("000001.SZ", start_date, end_date)
    
    if history_data:
        for code, df in history_data.items():
            print(f"\n{code} 历史数据:")
            print(df.head())
    else:
        print("未获取到数据")
    
    # 测试获取实时数据
    print("\n测试获取实时数据: 000001.SZ")
    realtime_data = fetcher.get_realtime_data("000001.SZ")
    
    if realtime_data:
        for code, df in realtime_data.items():
            print(f"\n{code} 实时数据:")
            print(df)
    else:
        print("未获取到实时数据")
