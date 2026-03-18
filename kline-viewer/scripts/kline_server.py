"""
K线展示服务 - 核心模块

提供 FastAPI 服务，从 DuckDB 读取K线数据并计算缠论指标
"""
import os
import json
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta

from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
import duckdb
import pandas as pd
import numpy as np
import pyarrow.parquet as pq

# 获取技能根目录
SKILL_ROOT = Path(__file__).parent.parent
PROJECT_ROOT = SKILL_ROOT.parent.parent.parent

# 创建 FastAPI 应用
app = FastAPI(
    title="K线展示服务",
    description="支持缠论指标可视化的K线展示服务",
    version="1.0.0"
)

# 挂载静态文件目录
static_dir = SKILL_ROOT / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# 挂载 Lightweight Charts JS (从主项目复制或使用 CDN)
main_static_dir = PROJECT_ROOT / "static"


def load_config() -> Dict[str, Any]:
    """加载配置文件"""
    config_path = SKILL_ROOT / "config.json"
    if config_path.exists():
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def get_data_db_dir() -> Path:
    return PROJECT_ROOT / "data" / "db"


def get_data_source_path(name: str) -> Path:
    db_dir = get_data_db_dir()
    mapping = {
        'qingxu': db_dir / 'qingxu.parquet',
        'zhishu': db_dir / 'zhishu.parquet',
        'limit_up': db_dir / 'limit_up.parquet',
        'longhubang': db_dir / 'longhubang.parquet',
    }
    if name not in mapping:
        raise KeyError(name)
    return mapping[name]


def _infer_date_column(columns: List[str]) -> Optional[str]:
    for col in ['tradeDate', 'trade_date', 'date', 'time']:
        if col in columns:
            return col
    return None


def _safe_value(v):
    if pd.isna(v):
        return None
    if isinstance(v, (pd.Timestamp, datetime)):
        return v.strftime('%Y-%m-%d')
    if hasattr(v, 'item'):
        try:
            return v.item()
        except Exception:
            pass
    return v


def _frame_preview(df: pd.DataFrame, limit: int = 200) -> List[Dict[str, Any]]:
    if df.empty:
        return []
    preview = df.head(limit).copy()
    for col in preview.columns:
        if pd.api.types.is_datetime64_any_dtype(preview[col]):
            preview[col] = preview[col].dt.strftime('%Y-%m-%d')
        elif preview[col].dtype == 'object':
            preview[col] = preview[col].apply(lambda x: x.strftime('%Y-%m-%d') if hasattr(x, 'strftime') else x)
    preview = preview.replace({np.nan: None})
    return [{k: _safe_value(v) for k, v in row.items()} for row in preview.to_dict('records')]


def build_dataset_summary(name: str, limit: int = 200) -> Dict[str, Any]:
    path = get_data_source_path(name)
    if not path.exists():
        return {
            'success': False,
            'dataset': name,
            'error': f'数据文件不存在: {path}'
        }

    df = pd.read_parquet(path)
    columns = list(df.columns)
    date_col = _infer_date_column(columns)
    latest_date = None
    latest_rows = len(df)
    latest_preview_df = df.copy()

    if date_col and not df.empty:
        date_series = pd.to_datetime(df[date_col], errors='coerce')
        valid = date_series.notna()
        if valid.any():
            latest_ts = date_series[valid].max()
            latest_date = latest_ts.strftime('%Y-%m-%d')
            latest_mask = date_series.dt.strftime('%Y-%m-%d') == latest_date
            latest_preview_df = df.loc[latest_mask].copy()
            latest_rows = len(latest_preview_df)

    null_counts = {col: int(df[col].isna().sum()) for col in columns}
    sample_rows = _frame_preview(latest_preview_df if latest_date else df, limit=limit)

    return {
        'success': True,
        'dataset': name,
        'path': str(path),
        'row_count': int(len(df)),
        'columns': columns,
        'date_column': date_col,
        'latest_date': latest_date,
        'latest_row_count': int(latest_rows),
        'null_counts': null_counts,
        'sample_rows': sample_rows,
    }


def get_db_path() -> str:
    """获取数据库路径"""
    # 优先使用环境变量
    if os.getenv("KLINE_DB_PATH"):
        return os.getenv("KLINE_DB_PATH")
    
    # 其次使用配置文件
    config = load_config()
    db_path = config.get("database", {}).get("path")
    if db_path:
        if not os.path.isabs(db_path):
            db_path = str(PROJECT_ROOT / db_path)
        return db_path
    
    # 默认路径
    return str(PROJECT_ROOT / "data" / "db" / "kline_eod.duckdb")


class KlineServer:
    """K线数据服务"""
    
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or get_db_path()
        self._conn = None
    
    def _get_connection(self) -> duckdb.DuckDBPyConnection:
        """获取数据库连接"""
        if self._conn is None:
            self._conn = duckdb.connect(self.db_path, read_only=True)
        return self._conn
    
    def close(self):
        """关闭连接"""
        if self._conn:
            self._conn.close()
            self._conn = None
    
    def get_kline(self, symbol: str, period: str = "daily", limit: int = 250, 
                   start_date: Optional[str] = None) -> List[Dict]:
        """
        获取K线数据
        
        优先从 DuckDB 获取，如果数据不足则从 feather 文件补充
        
        Args:
            symbol: 股票代码，如 '000001.SZ'
            period: 周期，支持 'daily', 'weekly', 'monthly'
            limit: 返回条数，默认250（约1年交易日）
            start_date: 起始日期，如 '2025-01-01'（可选，不指定则取最近limit条）
        
        Returns:
            K线数据列表
        """
        # 标准化股票代码
        symbol = self._normalize_symbol(symbol)
        
        # 首先尝试从 DuckDB 获取
        data = self._get_kline_from_duckdb(symbol, period, limit, start_date)
        
        # 如果数据不足，尝试从 feather 文件获取
        if len(data) < limit:
            feather_data = self._get_kline_from_feather(symbol, period, limit, start_date)
            if len(feather_data) > len(data):
                data = feather_data
        
        return data
    
    def _get_kline_from_feather(self, symbol: str, period: str, limit: int, 
                                 start_date: Optional[str] = None) -> List[Dict]:
        """从 feather 文件获取K线数据"""
        feather_path = PROJECT_ROOT / "data" / "archive" / "stock" / f"{symbol}.feather"
        
        if not feather_path.exists():
            return []
        
        try:
            df = pd.read_feather(feather_path)
            
            # 标准化列名
            column_map = {
                'tradeDate': 'time',
                'trade_date': 'time',
            }
            df = df.rename(columns=column_map)
            
            # 确保 time 列是字符串格式
            if 'time' in df.columns:
                df['time'] = pd.to_datetime(df['time']).dt.strftime('%Y-%m-%d')
            
            # 只保留日线数据（Interval == 86400000 或者不存在）
            if 'Interval' in df.columns:
                df = df[df['Interval'] == 86400000]
            
            # 日期过滤
            if start_date:
                df = df[df['time'] >= start_date]
            
            # 按时间排序
            df = df.sort_values('time', ascending=False)
            
            # 限制条数
            df = df.head(limit)
            
            # 按时间升序排列返回
            df = df.sort_values('time')
            
            # 选择需要的列
            result_cols = ['time', 'open', 'high', 'low', 'close', 'volume']
            if 'amount' in df.columns:
                result_cols.append('amount')
            df = df[[c for c in result_cols if c in df.columns]]
            
            # 处理 NaN
            df = df.fillna(0)
            
            return df.to_dict('records')
            
        except Exception as e:
            print(f"从 feather 读取数据失败: {e}")
            return []
    
    def _get_kline_from_duckdb(self, symbol: str, period: str, limit: int, 
                                start_date: Optional[str] = None) -> List[Dict]:
        """从 DuckDB 获取K线数据"""
        conn = self._get_connection()
        
        # 构建查询条件
        date_filter = "AND trade_date >= ?" if start_date else ""
        params = [symbol, start_date, limit] if start_date else [symbol, limit]
        
        if period == 'weekly':
            # 周线聚合
            query = f"""
            SELECT 
                DATE_TRUNC('week', trade_date) as time,
                FIRST(open ORDER BY trade_date) as open,
                MAX(high) as high,
                MIN(low) as low,
                LAST(close ORDER BY trade_date) as close,
                SUM(volume) as volume,
                SUM(amount) as amount
            FROM market_daily
            WHERE symbol = ? {date_filter}
            GROUP BY DATE_TRUNC('week', trade_date)
            ORDER BY time DESC
            LIMIT ?
            """
        elif period == 'monthly':
            # 月线聚合
            query = f"""
            SELECT 
                DATE_TRUNC('month', trade_date) as time,
                FIRST(open ORDER BY trade_date) as open,
                MAX(high) as high,
                MIN(low) as low,
                LAST(close ORDER BY trade_date) as close,
                SUM(volume) as volume,
                SUM(amount) as amount
            FROM market_daily
            WHERE symbol = ? {date_filter}
            GROUP BY DATE_TRUNC('month', trade_date)
            ORDER BY time DESC
            LIMIT ?
            """
        else:
            # 日线 - 直接取最近 limit 条
            query = f"""
            SELECT 
                trade_date as time,
                open,
                high,
                low,
                close,
                volume,
                amount
            FROM market_daily
            WHERE symbol = ? {date_filter}
            ORDER BY trade_date DESC
            LIMIT ?
            """
        
        try:
            df = conn.execute(query, params).fetchdf()
            
            if df.empty:
                return []
            
            # 按时间升序排列
            df = df.sort_values('time')
            
            # 转换时间格式
            df['time'] = df['time'].apply(lambda x: x.strftime('%Y-%m-%d') if hasattr(x, 'strftime') else str(x)[:10])
            
            # 处理 NaN
            df = df.fillna(0)
            
            # 转换为字典列表
            return df.to_dict('records')
        
        except Exception as e:
            print(f"查询K线数据失败: {e}")
            return []
    
    def get_capital_flow(self, symbol: str, start_date: Optional[str] = None, limit: int = 250) -> List[Dict]:
        """
        获取资金流向数据
        
        Args:
            symbol: 股票代码
            start_date: 起始日期（可选）
            limit: 返回条数
        
        Returns:
            资金流向数据列表
        """
        conn = self._get_connection()
        symbol = self._normalize_symbol(symbol)
        
        # 构建查询
        if start_date:
            query = """
            SELECT 
                trade_date as time,
                main_net_inflow
            FROM capital_flow
            WHERE symbol = ? AND trade_date >= ?
            ORDER BY trade_date DESC
            LIMIT ?
            """
            params = [symbol, start_date, limit]
        else:
            query = """
            SELECT 
                trade_date as time,
                main_net_inflow
            FROM capital_flow
            WHERE symbol = ?
            ORDER BY trade_date DESC
            LIMIT ?
            """
            params = [symbol, limit]
        
        try:
            df = conn.execute(query, params).fetchdf()
            
            if df.empty:
                return []
            
            # 按时间升序排列（前端需要）
            df = df.sort_values('time')
            
            df['time'] = df['time'].apply(lambda x: x.strftime('%Y-%m-%d') if hasattr(x, 'strftime') else str(x)[:10])
            df = df.fillna(0)
            
            return df.to_dict('records')
        
        except Exception as e:
            print(f"查询资金流向失败: {e}")
            return []
    
    def get_kline_with_chanlun(self, symbol: str, period: str = "daily", limit: int = 250,
                                start_date: Optional[str] = None, with_flow: bool = True) -> Dict[str, Any]:
        """
        获取K线数据并计算缠论指标
        
        Args:
            symbol: 股票代码
            period: 周期
            limit: 返回条数
            start_date: 起始日期
            with_flow: 是否包含资金流向
        
        Returns:
            包含K线数据和缠论指标的字典
        """
        # 获取K线数据
        kline_data = self.get_kline(symbol, period, limit, start_date)
        
        # 获取资金流向
        capital_flow = []
        if with_flow and period == 'daily':
            capital_flow = self.get_capital_flow(symbol, start_date, limit)
        
        if not kline_data:
            return {
                "success": False,
                "data": [],
                "bi": [],
                "zhongshu": [],
                "buy_points": [],
                "sell_points": [],
                "current_state": None,
                "capital_flow": []
            }
        
        # 计算缠论指标
        from scripts.chanlun_calculator import ChanlunCalculator
        calculator = ChanlunCalculator()
        
        bi_list, zhongshu_list, buy_points, sell_points, current_state, kline_with_fractal = calculator.calculate(kline_data)
        
        return {
            "success": True,
            "data": kline_with_fractal,  # 返回带分型信息的K线数据
            "bi": bi_list,
            "zhongshu": zhongshu_list,
            "buy_points": buy_points,
            "sell_points": sell_points,
            "current_state": current_state,
            "capital_flow": capital_flow
        }
    
    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        """标准化股票代码"""
        symbol = symbol.strip().upper()
        
        # 已经是标准格式
        if '.' in symbol:
            return symbol
        
        # 处理 sh000001 / sz399001 格式
        if symbol.startswith('SH') and len(symbol) >= 8:
            return f"{symbol[2:]}.SH"
        if symbol.startswith('SZ') and len(symbol) >= 8:
            return f"{symbol[2:]}.SZ"
        
        # 处理 6 位代码
        if symbol.isdigit() and len(symbol) == 6:
            if symbol.startswith(('6', '9')):
                return f"{symbol}.SH"
            elif symbol.startswith(('0', '3')):
                return f"{symbol}.SZ"
            elif symbol.startswith(('8', '4')):
                return f"{symbol}.BJ"
        
        return symbol


# 创建全局服务实例
_server: Optional[KlineServer] = None


def get_server() -> KlineServer:
    """获取服务实例"""
    global _server
    if _server is None:
        _server = KlineServer()
    return _server


# ============ API 路由 ============

@app.get("/")
async def root():
    """根路径重定向到K线页面"""
    return FileResponse(str(SKILL_ROOT / "static" / "kline.html"))


@app.get("/api/kline/{symbol}")
async def api_get_kline(
    symbol: str,
    period: str = Query(default="daily", description="周期: daily/weekly/monthly"),
    limit: int = Query(default=250, ge=10, le=1000, description="返回条数，默认250约1年"),
    with_chanlun: bool = Query(default=True, description="是否计算缠论指标"),
    with_flow: bool = Query(default=True, description="是否包含资金流向"),
    start_date: Optional[str] = Query(default=None, description="起始日期，如 2025-01-01")
):
    """
    获取K线数据
    
    - **symbol**: 股票代码，如 000001.SZ 或 sh000001
    - **period**: 周期，支持 daily/weekly/monthly
    - **limit**: 返回条数，默认250（约1年）
    - **with_chanlun**: 是否计算缠论指标
    - **with_flow**: 是否包含资金流向
    - **start_date**: 起始日期
    """
    try:
        server = get_server()
        
        if with_chanlun:
            result = server.get_kline_with_chanlun(symbol, period, limit, start_date, with_flow)
        else:
            kline_data = server.get_kline(symbol, period, limit, start_date)
            capital_flow = server.get_capital_flow(symbol, start_date) if with_flow and period == 'daily' else []
            result = {
                "success": len(kline_data) > 0,
                "data": kline_data,
                "bi": [],
                "capital_flow": capital_flow,
                "zhongshu": [],
                "buy_points": [],
                "sell_points": [],
                "current_state": None
            }
        
        return JSONResponse(content=result)
    
    except Exception as e:
        return JSONResponse(
            content={"success": False, "error": str(e), "data": []},
            status_code=500
        )


@app.get("/api/symbols")
async def api_list_symbols(
    search: str = Query(default="", description="搜索关键词"),
    limit: int = Query(default=50, ge=1, le=200, description="返回条数")
):
    """
    搜索股票代码
    
    - **search**: 代码或名称关键词
    - **limit**: 返回条数
    """
    try:
        server = get_server()
        conn = server._get_connection()
        
        if search:
            query = """
            SELECT DISTINCT symbol
            FROM market_daily
            WHERE symbol LIKE ?
            ORDER BY symbol
            LIMIT ?
            """
            df = conn.execute(query, [f"%{search.upper()}%", limit]).fetchdf()
        else:
            query = """
            SELECT DISTINCT symbol
            FROM market_daily
            ORDER BY symbol
            LIMIT ?
            """
            df = conn.execute(query, [limit]).fetchdf()
        
        return JSONResponse(content={
            "success": True,
            "symbols": df['symbol'].tolist()
        })
    
    except Exception as e:
        return JSONResponse(
            content={"success": False, "error": str(e), "symbols": []},
            status_code=500
        )


@app.get("/api/health")
async def api_health():
    """健康检查"""
    try:
        server = get_server()
        conn = server._get_connection()
        result = conn.execute("SELECT COUNT(*) as cnt FROM market_daily").fetchone()
        return JSONResponse(content={
            "status": "healthy",
            "database": server.db_path,
            "records": result[0]
        })
    except Exception as e:
        return JSONResponse(
            content={"status": "unhealthy", "error": str(e)},
            status_code=500
        )


# ============ 选股 API ============

@app.get("/data-check")
async def data_check_page():
    return FileResponse(str(SKILL_ROOT / "static" / "data_check.html"))


@app.get("/api/data-check/datasets")
async def api_data_check_datasets():
    datasets = [
        {"key": "qingxu", "label": "市场情绪 qingxu.parquet"},
        {"key": "zhishu", "label": "指数 zhishu.parquet"},
        {"key": "limit_up", "label": "涨停 limit_up.parquet"},
        {"key": "longhubang", "label": "龙虎榜 longhubang.parquet"},
    ]
    return JSONResponse(content={"success": True, "datasets": datasets})


@app.get("/api/data-check/summary/{dataset}")
async def api_data_check_summary(dataset: str, limit: int = Query(200, ge=1, le=1000)):
    try:
        summary = build_dataset_summary(dataset, limit=limit)
        status_code = 200 if summary.get('success') else 404
        return JSONResponse(content=summary, status_code=status_code)
    except KeyError:
        return JSONResponse(content={"success": False, "error": f"未知数据集: {dataset}"}, status_code=404)
    except Exception as e:
        return JSONResponse(content={"success": False, "error": str(e)}, status_code=500)


@app.get("/api/data-check/all")
async def api_data_check_all(limit: int = Query(100, ge=1, le=500)):
    datasets = ['qingxu', 'zhishu', 'limit_up', 'longhubang']
    result = []
    for name in datasets:
        try:
            result.append(build_dataset_summary(name, limit=limit))
        except Exception as e:
            result.append({"success": False, "dataset": name, "error": str(e)})
    return JSONResponse(content={"success": True, "items": result})


@app.get("/api/screener/dates")
async def api_screener_dates():
    """
    获取所有可用的扫描日期
    """
    try:
        from scripts.stock_screener import list_scan_results
        
        results = list_scan_results()
        dates = [r['date'] for r in results]
        
        return JSONResponse(content={
            "success": True,
            "dates": dates,
            "count": len(dates)
        })
        
    except Exception as e:
        return JSONResponse(
            content={"success": False, "error": str(e), "dates": []},
            status_code=500
        )


@app.get("/api/screener/data/{date}")
async def api_screener_data(date: str):
    """
    获取指定日期的扫描结果
    
    - **date**: 日期，如 2026-03-08
    """
    try:
        output_dir = SKILL_ROOT / "output"
        json_file = output_dir / f"scan_{date}.json"
        
        if not json_file.exists():
            return JSONResponse(content={
                "success": False,
                "error": f"未找到 {date} 的扫描结果"
            })
        
        import json
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        return JSONResponse(content={
            "success": True,
            "data": data
        })
        
    except Exception as e:
        return JSONResponse(
            content={"success": False, "error": str(e)},
            status_code=500
        )


@app.get("/api/screener/latest")
async def api_screener_latest():
    """
    获取最新的扫描结果
    """
    try:
        from scripts.stock_screener import list_scan_results
        
        results = list_scan_results()
        
        if not results:
            return JSONResponse(content={
                "success": False,
                "error": "暂无扫描结果，请先运行: python stock_screener.py scan"
            })
        
        # 加载最新的
        latest = results[0]
        json_file = latest['path']
        
        import json
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        return JSONResponse(content={
            "success": True,
            "data": data
        })
        
    except Exception as e:
        return JSONResponse(
            content={"success": False, "error": str(e)},
            status_code=500
        )


# ============ 应用工厂 ============

def create_app(db_path: Optional[str] = None) -> FastAPI:
    """创建应用实例"""
    global _server
    if db_path:
        os.environ["KLINE_DB_PATH"] = db_path
        _server = KlineServer(db_path)
    return app
