#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
特征工程模块 - 市场情绪周期分析

构建用于情绪周期识别的特征集：
1. 涨停特征：涨停数、跌停数、涨停率、炸板率等
2. 涨跌家数特征：涨跌比、上涨比例等
3. 上证指数特征：涨跌幅、成交量变化、均线偏离等
4. 技术特征：动量、趋势等
5. 缠论特征：分型类型、笔方向等
"""

import numpy as np
import pandas as pd
from pathlib import Path
from typing import Optional, List, Dict, Tuple
import logging


class EmotionFeatureEngineer:
    """
    情绪周期特征工程器
    
    输入：市场统计数据 + 指数K线数据 + 涨停详情数据
    输出：用于模型训练的特征矩阵
    """
    
    # 特征列定义
    FEATURE_COLUMNS = [
        # === 涨停特征 ===
        'limit_up_count',           # 涨停家数
        'limit_down_count',         # 跌停家数
        'limit_up_ratio',           # 涨停率 (涨停数/总股票数)
        'limit_up_down_ratio',      # 涨跌停比 (涨停/跌停)
        'first_board_count',        # 首板数量
        'continuous_board_count',   # 连板数量
        'explosion_rate',           # 炸板率
        
        # === 涨跌家数特征 ===
        'rise_count',               # 上涨家数
        'fall_count',               # 下跌家数
        'rise_fall_ratio',          # 涨跌比
        'rise_ratio',               # 上涨比例
        'flat_count',               # 平盘家数
        
        # === 上证指数特征 ===
        'sh_close',                 # 上证收盘价
        'sh_change_pct',            # 上证涨跌幅
        'sh_volume_change',         # 上证成交量变化率
        'sh_amount_change',         # 上证成交额变化率
        'sh_amplitude',             # 上证振幅
        'sh_ma5_deviation',         # MA5偏离度
        'sh_ma10_deviation',        # MA10偏离度
        'sh_ma20_deviation',        # MA20偏离度
        
        # === 技术特征 ===
        'limit_up_ma5',             # 涨停数5日均值
        'limit_up_ma10',            # 涨停数10日均值
        'limit_up_ma5_dev',         # 涨停数MA5偏离度
        'limit_up_ma10_dev',        # 涨停数MA10偏离度
        'limit_up_change_1d',       # 涨停数1日变化
        'limit_up_change_3d',       # 涨停数3日变化
        'limit_up_trend_3d',        # 3日涨停趋势（斜率）
        'limit_up_trend_5d',        # 5日涨停趋势（斜率）
        
        # === 动量特征 ===
        'limit_up_momentum_3d',     # 涨停3日动量
        'limit_up_momentum_5d',     # 涨停5日动量
        'rise_momentum_3d',         # 上涨家数3日动量
        'explosion_rate_ma3',       # 炸板率3日均值
        'explosion_trend_3d',       # 炸板率3日趋势
        
        # === 情绪综合特征 ===
        'emotion_score',            # 情绪综合得分
        'market_strength',          # 市场强度
        'volatility_5d',            # 5日波动率
        
        # === 缠论特征 ===
        'fractal_type',             # 分型类型 (0=无, 1=底分型, -1=顶分型)
        'bi_direction',             # 笔方向 (1=向上, -1=向下, 0=无)
        'days_since_bottom_fractal', # 距离最近底分型天数
        'days_since_top_fractal',   # 距离最近顶分型天数
    ]
    
    def __init__(self):
        """初始化特征工程器"""
        self.logger = self._setup_logger()
        self.feature_df = None
        
    def _setup_logger(self) -> logging.Logger:
        """设置日志"""
        logger = logging.getLogger("EmotionFeatureEngineer")
        logger.setLevel(logging.INFO)
        if not logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            ))
            logger.addHandler(handler)
        return logger
    
    def build_features(self,
                       market_stats: pd.DataFrame,
                       index_kline: pd.DataFrame,
                       limit_up_data: pd.DataFrame) -> pd.DataFrame:
        """
        构建完整的特征矩阵
        
        Args:
            market_stats: 市场统计数据（涨跌家数）
            index_kline: 上证指数K线数据
            limit_up_data: 涨停详情数据
            
        Returns:
            DataFrame: 特征矩阵
        """
        self.logger.info("=" * 60)
        self.logger.info("开始构建特征矩阵")
        self.logger.info("=" * 60)
        
        # 1. 处理市场统计数据
        self.logger.info("\n[1/5] 处理市场统计特征...")
        df = self._process_market_stats(market_stats)
        
        # 2. 添加涨停详情特征
        self.logger.info("\n[2/5] 添加涨停详情特征...")
        df = self._add_limit_up_features(df, limit_up_data)
        
        # 3. 添加指数特征
        self.logger.info("\n[3/5] 添加上证指数特征...")
        df = self._add_index_features(df, index_kline)
        
        # 4. 添加技术特征
        self.logger.info("\n[4/5] 计算技术特征...")
        df = self._add_technical_features(df)
        
        # 5. 添加缠论特征
        self.logger.info("\n[5/5] 添加缠论特征...")
        df = self._add_chanlun_features(df, index_kline)
        
        # 填充缺失值
        df = self._fill_missing_values(df)
        
        self.feature_df = df
        
        self.logger.info(f"\n{'=' * 60}")
        self.logger.info(f"特征构建完成:")
        self.logger.info(f"  - 样本数: {len(df)}")
        self.logger.info(f"  - 特征数: {len(df.columns) - 1}")  # 减去日期列
        self.logger.info(f"  - 日期范围: {df['tradeDate'].min()} ~ {df['tradeDate'].max()}")
        self.logger.info(f"{'=' * 60}")
        
        return df
    
    def _process_market_stats(self, market_stats: pd.DataFrame) -> pd.DataFrame:
        """处理市场统计数据"""
        if market_stats.empty:
            self.logger.warning("市场统计数据为空")
            return pd.DataFrame()
        
        df = market_stats.copy()
        
        # 确保日期列格式正确
        if 'tradeDate' in df.columns:
            df['tradeDate'] = pd.to_datetime(df['tradeDate'])
        elif 'date' in df.columns:
            df['tradeDate'] = pd.to_datetime(df['date'])
            
        # 排序
        df = df.sort_values('tradeDate').reset_index(drop=True)
        
        # 基础特征
        if 'rise_count' in df.columns and 'fall_count' in df.columns:
            # 涨跌比
            df['rise_fall_ratio'] = df['rise_count'] / df['fall_count'].replace(0, 1)
            # 上涨比例
            total = df['rise_count'] + df['fall_count']
            df['rise_ratio'] = df['rise_count'] / total.replace(0, 1)
            # 平盘家数（若 total_count 可用则反推，否则记 0）
            if 'total_count' in df.columns:
                df['flat_count'] = (df['total_count'] - df['rise_count'] - df['fall_count']).clip(lower=0)
            else:
                df['flat_count'] = 0
        
        if 'limit_up_count' in df.columns and 'limit_down_count' in df.columns:
            # 涨跌停比
            df['limit_up_down_ratio'] = df['limit_up_count'] / df['limit_down_count'].replace(0, 1)
            
        # 涨停率
        if 'limit_up_count' in df.columns and 'total_count' in df.columns:
            df['limit_up_ratio'] = df['limit_up_count'] / df['total_count'].replace(0, 1)
        
        self.logger.info(f"  ✅ 处理 {len(df)} 条市场统计记录")
        return df
    
    def _add_limit_up_features(self, 
                               df: pd.DataFrame, 
                               limit_up_data: pd.DataFrame) -> pd.DataFrame:
        """添加涨停详情特征"""
        if df.empty or limit_up_data.empty:
            # 添加默认列
            for col in ['first_board_count', 'continuous_board_count', 'explosion_rate']:
                if col not in df.columns:
                    df[col] = 0
            return df
        
        # 确保日期格式一致
        if 'trade_date' in limit_up_data.columns:
            limit_up_data['trade_date'] = pd.to_datetime(limit_up_data['trade_date'])
        
        # 按日期统计
        daily_stats = []
        for date in df['tradeDate'].unique():
            date_str = pd.to_datetime(date).strftime('%Y-%m-%d')
            day_data = limit_up_data[limit_up_data['trade_date'] == date_str]
            
            if day_data.empty:
                daily_stats.append({
                    'tradeDate': date,
                    'first_board_count': 0,
                    'continuous_board_count': 0,
                    'avg_consecutive_boards': 0,
                    'max_consecutive_boards': 0,
                })
                continue
            
            # 首板数量
            first_board = 0
            if 'is_first_limit_up' in day_data.columns:
                first_board = day_data['is_first_limit_up'].sum()
            elif 'consecutive_boards' in day_data.columns:
                first_board = (day_data['consecutive_boards'] == 1).sum()
            
            # 连板数量
            continuous_board = len(day_data) - first_board
            
            # 平均连板高度
            avg_boards = 1
            max_boards = 1
            if 'consecutive_boards' in day_data.columns:
                avg_boards = day_data['consecutive_boards'].mean()
                max_boards = day_data['consecutive_boards'].max()
            
            daily_stats.append({
                'tradeDate': date,
                'first_board_count': first_board,
                'continuous_board_count': continuous_board,
                'avg_consecutive_boards': avg_boards,
                'max_consecutive_boards': max_boards,
            })
        
        if daily_stats:
            stats_df = pd.DataFrame(daily_stats)
            df = df.merge(stats_df, on='tradeDate', how='left')
        
        # 填充默认值
        for col in ['first_board_count', 'continuous_board_count', 'avg_consecutive_boards', 'max_consecutive_boards']:
            if col in df.columns:
                df[col] = df[col].fillna(0)
            else:
                df[col] = 0
        
        self.logger.info(f"  ✅ 添加涨停详情特征完成")
        return df
    
    def _add_index_features(self, 
                            df: pd.DataFrame, 
                            index_kline: pd.DataFrame) -> pd.DataFrame:
        """添加上证指数特征"""
        if df.empty or index_kline.empty:
            # 添加默认列
            index_cols = ['sh_close', 'sh_change_pct', 'sh_volume_change', 
                         'sh_amount_change', 'sh_amplitude', 'sh_ma5_deviation',
                         'sh_ma10_deviation', 'sh_ma20_deviation']
            for col in index_cols:
                if col not in df.columns:
                    df[col] = 0
            return df
        
        # 处理指数数据 - 只使用上证指数
        idx = index_kline.copy()
        
        # 筛选上证指数（000001.SH）
        if 'symbol' in idx.columns:
            idx = idx[idx['symbol'] == '000001.SH'].copy()
        elif 'stock_code' in idx.columns:
            idx = idx[idx['stock_code'] == '000001.SH'].copy()
        
        if idx.empty:
            # 添加默认列
            index_cols = ['sh_close', 'sh_change_pct', 'sh_volume_change', 
                         'sh_amount_change', 'sh_amplitude', 'sh_ma5_deviation',
                         'sh_ma10_deviation', 'sh_ma20_deviation']
            for col in index_cols:
                if col not in df.columns:
                    df[col] = 0
            return df
        
        # 标准化列名（兼容不同数据源）
        column_mapping = {
            'latest': 'close',           # 本地数据
            'changeRatio': 'pct_change', # 本地数据
            'preClose': 'pre_close',     # 本地数据
        }
        for old_col, new_col in column_mapping.items():
            if old_col in idx.columns and new_col not in idx.columns:
                idx[new_col] = idx[old_col]
        
        # 日期列处理
        if 'time' in idx.columns:
            idx['tradeDate'] = pd.to_datetime(idx['time'])
        elif 'tradeDate' in idx.columns:
            idx['tradeDate'] = pd.to_datetime(idx['tradeDate'])
        elif 'date' in idx.columns:
            idx['tradeDate'] = pd.to_datetime(idx['date'])
        
        # 计算指数特征
        idx = idx.sort_values('tradeDate').reset_index(drop=True)
        
        # 收盘价（优先使用 close，其次 latest）
        if 'close' in idx.columns:
            idx['sh_close'] = idx['close']
        elif 'latest' in idx.columns:
            idx['sh_close'] = idx['latest']
        else:
            idx['sh_close'] = 0
        
        # 涨跌幅（优先使用已有的 pct_change/changeRatio，其次计算）
        if 'pct_change' in idx.columns:
            idx['sh_change_pct'] = idx['pct_change']
        elif 'changeRatio' in idx.columns:
            idx['sh_change_pct'] = idx['changeRatio']
        elif 'close' in idx.columns:
            idx['sh_change_pct'] = idx['close'].pct_change() * 100
        else:
            idx['sh_change_pct'] = 0
        
        # 成交量/成交额变化
        if 'volume' in idx.columns:
            idx['sh_volume_change'] = idx['volume'].pct_change()
        else:
            idx['sh_volume_change'] = 0
            
        if 'amount' in idx.columns:
            idx['sh_amount_change'] = idx['amount'].pct_change()
        else:
            idx['sh_amount_change'] = 0
        
        # 振幅
        if 'high' in idx.columns and 'low' in idx.columns:
            pre_close = idx.get('preClose', idx['close'].shift(1))
            idx['sh_amplitude'] = (idx['high'] - idx['low']) / pre_close.replace(0, np.nan) * 100
        else:
            idx['sh_amplitude'] = 0
        
        # 均线偏离度
        if 'close' in idx.columns:
            idx['sh_ma5'] = idx['close'].rolling(5).mean()
            idx['sh_ma10'] = idx['close'].rolling(10).mean()
            idx['sh_ma20'] = idx['close'].rolling(20).mean()
            
            idx['sh_ma5_deviation'] = (idx['close'] - idx['sh_ma5']) / idx['sh_ma5'].replace(0, np.nan) * 100
            idx['sh_ma10_deviation'] = (idx['close'] - idx['sh_ma10']) / idx['sh_ma10'].replace(0, np.nan) * 100
            idx['sh_ma20_deviation'] = (idx['close'] - idx['sh_ma20']) / idx['sh_ma20'].replace(0, np.nan) * 100
        
        # 选择需要的列
        idx_cols = ['tradeDate', 'sh_close', 'sh_change_pct', 'sh_volume_change',
                   'sh_amount_change', 'sh_amplitude', 'sh_ma5_deviation',
                   'sh_ma10_deviation', 'sh_ma20_deviation']
        idx_features = idx[[c for c in idx_cols if c in idx.columns]]
        
        # 合并到主表
        df = df.merge(idx_features, on='tradeDate', how='left')
        
        self.logger.info(f"  ✅ 添加上证指数特征完成")
        return df
    
    def _add_technical_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """添加技术特征（趋势、动量等）"""
        if df.empty:
            return df
        
        # 确保按日期排序
        df = df.sort_values('tradeDate').reset_index(drop=True)
        
        # === 涨停数技术特征 ===
        if 'limit_up_count' in df.columns:
            # 移动平均
            df['limit_up_ma5'] = df['limit_up_count'].rolling(5, min_periods=1).mean()
            df['limit_up_ma10'] = df['limit_up_count'].rolling(10, min_periods=1).mean()
            
            # MA偏离度
            df['limit_up_ma5_dev'] = (df['limit_up_count'] - df['limit_up_ma5']) / df['limit_up_ma5'].replace(0, np.nan)
            df['limit_up_ma10_dev'] = (df['limit_up_count'] - df['limit_up_ma10']) / df['limit_up_ma10'].replace(0, np.nan)
            
            # 变化量
            df['limit_up_change_1d'] = df['limit_up_count'].diff(1)
            df['limit_up_change_3d'] = df['limit_up_count'].diff(3)
            
            # 趋势（线性回归斜率）
            df['limit_up_trend_3d'] = self._calc_rolling_slope(df['limit_up_count'], 3)
            df['limit_up_trend_5d'] = self._calc_rolling_slope(df['limit_up_count'], 5)
            
            # 动量
            df['limit_up_momentum_3d'] = df['limit_up_count'] / df['limit_up_count'].shift(3).replace(0, np.nan) - 1
            df['limit_up_momentum_5d'] = df['limit_up_count'] / df['limit_up_count'].shift(5).replace(0, np.nan) - 1
        
        # === 上涨家数动量 ===
        if 'rise_count' in df.columns:
            df['rise_momentum_3d'] = df['rise_count'] / df['rise_count'].shift(3).replace(0, np.nan) - 1
        
        # === 炸板率特征 ===
        if 'explosion_rate' in df.columns:
            df['explosion_rate_ma3'] = df['explosion_rate'].rolling(3, min_periods=1).mean()
            df['explosion_trend_3d'] = self._calc_rolling_slope(df['explosion_rate'], 3)
        else:
            df['explosion_rate'] = 0
            df['explosion_rate_ma3'] = 0
            df['explosion_trend_3d'] = 0
        
        # === 情绪综合得分 ===
        df['emotion_score'] = self._calc_emotion_score(df)
        
        # === 市场强度 ===
        df['market_strength'] = self._calc_market_strength(df)
        
        # === 波动率 ===
        if 'limit_up_count' in df.columns:
            df['volatility_5d'] = df['limit_up_count'].rolling(5, min_periods=1).std()
        
        self.logger.info(f"  ✅ 添加技术特征完成")
        return df
    
    def _calc_rolling_slope(self, series: pd.Series, window: int) -> pd.Series:
        """计算滚动线性回归斜率"""
        slopes = []
        x = np.arange(window)
        
        for i in range(len(series)):
            if i < window - 1:
                slopes.append(0)
            else:
                y = series.iloc[i-window+1:i+1].values
                if len(y) == window and not np.isnan(y).any():
                    # 简单线性回归斜率
                    slope = np.polyfit(x, y, 1)[0]
                    slopes.append(slope)
                else:
                    slopes.append(0)
        
        return pd.Series(slopes, index=series.index)
    
    def _calc_emotion_score(self, df: pd.DataFrame) -> pd.Series:
        """
        计算情绪综合得分 (0-100)
        
        权重：
        - 涨停数占比: 30%
        - 涨跌比: 25%
        - 涨停趋势: 20%
        - 连板占比: 15%
        - 炸板率(反向): 10%
        """
        scores = pd.Series(index=df.index, dtype=float)
        scores[:] = 50  # 基准分
        
        # 涨停数得分 (归一化到0-100)
        if 'limit_up_count' in df.columns:
            q95 = df['limit_up_count'].quantile(0.95)
            q95 = max(q95, 1)  # 确保不为0
            limit_up_norm = df['limit_up_count'] / q95
            limit_up_score = limit_up_norm.clip(upper=1) * 100
            scores += (limit_up_score - 50) * 0.30
        
        # 涨跌比得分
        if 'rise_fall_ratio' in df.columns:
            ratio_norm = df['rise_fall_ratio'].clip(upper=5) / 5
            ratio_score = ratio_norm * 100
            scores += (ratio_score - 50) * 0.25
        
        # 涨停趋势得分
        if 'limit_up_trend_3d' in df.columns:
            q95_trend = df['limit_up_trend_3d'].abs().quantile(0.95)
            q95_trend = max(q95_trend, 1)  # 确保不为0
            trend_norm = df['limit_up_trend_3d'] / q95_trend
            trend_score = (trend_norm.clip(-1, 1) + 1) / 2 * 100
            scores += (trend_score - 50) * 0.20
        
        # 连板占比得分
        if 'continuous_board_count' in df.columns and 'limit_up_count' in df.columns:
            cont_ratio = df['continuous_board_count'] / df['limit_up_count'].replace(0, 1)
            cont_score = cont_ratio.clip(upper=0.5) / 0.5 * 100
            scores += (cont_score - 50) * 0.15
        
        # 炸板率得分（反向）
        if 'explosion_rate' in df.columns:
            exp_score = (1 - df['explosion_rate'].clip(upper=0.5) / 0.5) * 100
            scores += (exp_score - 50) * 0.10
        
        return scores.clip(0, 100)
    
    def _calc_market_strength(self, df: pd.DataFrame) -> pd.Series:
        """计算市场强度 (-100 ~ +100)"""
        strength = pd.Series(index=df.index, dtype=float)
        strength[:] = 0
        
        # 涨跌比因子
        if 'rise_fall_ratio' in df.columns:
            ratio_factor = (df['rise_fall_ratio'] - 1).clip(-2, 2) / 2 * 50
            strength += ratio_factor
        
        # 涨停/跌停比因子
        if 'limit_up_down_ratio' in df.columns:
            limit_factor = (df['limit_up_down_ratio'] - 1).clip(-5, 5) / 5 * 30
            strength += limit_factor
        
        # 指数涨跌因子
        if 'sh_change_pct' in df.columns:
            idx_factor = df['sh_change_pct'].clip(-5, 5) / 5 * 20
            strength += idx_factor
        
        return strength.clip(-100, 100)
    
    def _add_chanlun_features(self, 
                              df: pd.DataFrame, 
                              index_kline: pd.DataFrame) -> pd.DataFrame:
        """添加缠论特征"""
        # 初始化缠论特征列
        df['fractal_type'] = 0  # 0=无, 1=底分型, -1=顶分型
        df['bi_direction'] = 0  # 1=向上, -1=向下, 0=无
        df['days_since_bottom_fractal'] = 999
        df['days_since_top_fractal'] = 999
        
        if index_kline.empty:
            self.logger.warning("  ⚠️ 指数K线数据为空，跳过缠论特征")
            return df
        
        # 处理分型数据
        if 'fractal' in index_kline.columns:
            idx = index_kline.copy()
            if 'time' in idx.columns:
                idx['tradeDate'] = pd.to_datetime(idx['time'])
            elif 'date' in idx.columns:
                idx['tradeDate'] = pd.to_datetime(idx['date'])
            
            # 映射分型类型
            fractal_map = {'bottom': 1, 'top': -1, 'up': 1, 'down': -1}
            idx['fractal_type'] = idx['fractal'].map(fractal_map).fillna(0).astype(int)
            
            # 合并分型
            if 'tradeDate' in df.columns and 'tradeDate' in idx.columns:
                fractal_df = idx[['tradeDate', 'fractal_type']].drop_duplicates('tradeDate')
                df = df.merge(fractal_df, on='tradeDate', how='left', suffixes=('', '_new'))
                if 'fractal_type_new' in df.columns:
                    df['fractal_type'] = df['fractal_type_new'].fillna(0).astype(int)
                    df.drop('fractal_type_new', axis=1, inplace=True)
        
        # 处理笔方向数据
        if 'bi_direction' in index_kline.columns:
            idx = index_kline.copy()
            if 'time' in idx.columns:
                idx['tradeDate'] = pd.to_datetime(idx['time'])
            
            bi_df = idx[['tradeDate', 'bi_direction']].dropna().drop_duplicates('tradeDate')
            if not bi_df.empty:
                df = df.merge(bi_df, on='tradeDate', how='left', suffixes=('', '_new'))
                if 'bi_direction_new' in df.columns:
                    df['bi_direction'] = df['bi_direction_new'].fillna(0).astype(int)
                    df.drop('bi_direction_new', axis=1, inplace=True)
        
        # 计算距离最近分型的天数
        df = df.sort_values('tradeDate').reset_index(drop=True)
        
        last_bottom_idx = -999
        last_top_idx = -999
        
        for i in range(len(df)):
            if df.loc[i, 'fractal_type'] == 1:  # 底分型
                last_bottom_idx = i
            elif df.loc[i, 'fractal_type'] == -1:  # 顶分型
                last_top_idx = i
            
            if last_bottom_idx >= 0:
                df.loc[i, 'days_since_bottom_fractal'] = i - last_bottom_idx
            if last_top_idx >= 0:
                df.loc[i, 'days_since_top_fractal'] = i - last_top_idx
        
        self.logger.info(f"  ✅ 添加缠论特征完成")
        return df
    
    def _fill_missing_values(self, df: pd.DataFrame) -> pd.DataFrame:
        """填充缺失值"""
        if df.empty:
            return df
        
        # 数值列填充0或前值
        numeric_cols = df.select_dtypes(include=[np.number]).columns
        
        # 比例类特征填充中性值
        ratio_cols = [c for c in numeric_cols if 'ratio' in c.lower() or 'deviation' in c.lower()]
        for col in ratio_cols:
            if col in df.columns:
                df[col] = df[col].fillna(0)
        
        # 其他数值列向前填充后填0
        for col in numeric_cols:
            if col not in ratio_cols:
                df[col] = df[col].ffill().fillna(0)
        
        # 无穷值替换
        df = df.replace([np.inf, -np.inf], 0)
        
        return df
    
    def get_feature_matrix(self, include_date: bool = False) -> Tuple[np.ndarray, List[str]]:
        """
        获取特征矩阵
        
        Args:
            include_date: 是否包含日期列
            
        Returns:
            Tuple: (特征矩阵, 特征列名)
        """
        if self.feature_df is None or self.feature_df.empty:
            raise ValueError("请先调用 build_features 方法构建特征")
        
        # 选择特征列
        feature_cols = [c for c in self.FEATURE_COLUMNS if c in self.feature_df.columns]
        
        if include_date:
            feature_cols = ['tradeDate'] + feature_cols
        
        X = self.feature_df[feature_cols].values
        
        return X, feature_cols
    
    def save_features(self, output_path: Path) -> None:
        """保存特征数据"""
        if self.feature_df is None or self.feature_df.empty:
            raise ValueError("请先调用 build_features 方法构建特征")
        
        self.feature_df.to_parquet(output_path, index=False)
        self.logger.info(f"✅ 特征数据已保存: {output_path}")


def main():
    """测试入口"""
    from data_fetcher import EmotionDataFetcher
    
    # 获取数据
    fetcher = EmotionDataFetcher()
    market_stats, index_kline, limit_up_data = fetcher.fetch_all_data(years=2)
    fetcher.close()
    
    # 构建特征
    engineer = EmotionFeatureEngineer()
    feature_df = engineer.build_features(market_stats, index_kline, limit_up_data)
    
    # 保存特征
    output_path = Path(__file__).parent.parent.parent / "index" / "emotion_features.parquet"
    engineer.save_features(output_path)
    
    # 显示特征信息
    print("\n特征列表:")
    for col in feature_df.columns:
        if col != 'tradeDate':
            print(f"  - {col}")


if __name__ == "__main__":
    main()
