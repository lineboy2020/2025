#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每日预测与操作建议模块 - 市场情绪周期分析

功能：
1. 每日收盘后读取当日数据
2. 调用训练好的XGBoost模型进行预测
3. 输出情绪周期判断和详细操作建议
4. 支持命令行调用
"""

import os
import sys
import json
import pickle
import logging
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List

import numpy as np
import pandas as pd

# 技能根目录
SKILL_ROOT = Path(__file__).resolve().parents[1]
# 数据目录 - 统一使用主项目数据库
WORKSPACE_ROOT = SKILL_ROOT.parent.parent
DATA_DIR = WORKSPACE_ROOT / "data" / "db"


class EmotionCyclePredictor:
    """
    情绪周期预测器
    
    每日收盘后运行，输出当前情绪周期和操作建议
    """
    
    # 情绪周期标签
    EMOTION_LABELS = {
        0: '冰点期',
        1: '启动期',
        2: '发酵期', 
        3: '高潮期',
        4: '退潮期'
    }
    
    # 详细操作建议
    OPERATION_ADVICE = {
        0: {  # 冰点期
            "周期名称": "冰点期",
            "emoji": "🥶",
            "周期特征": "市场极度悲观，涨停数极少（<30只），跌停数较多，炸板率高，赚钱效应差",
            "仓位建议": "空仓或10%以下试探仓位",
            "操作策略": "低吸首板，关注低位新题材首板、历史低位股",
            "选股方向": [
                "低位首板：流通市值<50亿，前期跌幅>30%",
                "新题材首板：政策驱动、事件催化的新方向",
                "超跌反弹：连续3日跌幅>15%的个股"
            ],
            "关注信号": [
                "涨停数连续2日回升",
                "指数放量阳线",
                "龙头股止跌企稳"
            ],
            "风险提示": "市场情绪极度低迷，追高容易被套，切勿抄底老龙头",
            "止损建议": "首板次日低于成本价5%止损，严格执行"
        },
        1: {  # 启动期
            "周期名称": "启动期",
            "emoji": "🌱",
            "周期特征": "情绪开始回暖，涨停数回升（30-50只），跌停减少，赚钱效应改善",
            "仓位建议": "30%~50%仓位",
            "操作策略": "1进2半路打板，高低切换、补涨",
            "选股方向": [
                "1进2：前日首板涨停，今日竞价强势（高开3%以上）",
                "高低切换：龙头断板后的低位补涨股",
                "板块轮动：资金流出板块的龙头首阴"
            ],
            "关注信号": [
                "连板股开始出现",
                "板块涨停家数>3只",
                "指数站上5日线"
            ],
            "风险提示": "情绪刚启动，可能假突破，控制仓位",
            "止损建议": "2板失败次日集合竞价弱转强失败止损"
        },
        2: {  # 发酵期
            "周期名称": "发酵期",
            "emoji": "🔥",
            "周期特征": "情绪持续升温，涨停数增加（60-90只），连板股活跃，龙头股主升",
            "仓位建议": "50%~70%仓位",
            "操作策略": "持有龙头，加仓主升、接龙头为主",
            "选股方向": [
                "龙头股：连板最高的股票，加仓主升浪",
                "龙头跟随股：同板块2-3板股",
                "龙头首阴：龙头断板首日低吸（成功率高）"
            ],
            "关注信号": [
                "龙头股加速（一字板或T字板）",
                "板块持续扩散",
                "成交额放大"
            ],
            "风险提示": "龙头可能加速赶顶，注意高位分歧",
            "止损建议": "龙头跌破5日线考虑减仓，破10日线清仓"
        },
        3: {  # 高潮期
            "周期名称": "高潮期",
            "emoji": "🚀",
            "周期特征": "情绪达到顶峰，涨停数最多（>100只），连板高度最高，市场亢奋",
            "仓位建议": "70%~100%仓位（根据龙头强度）",
            "操作策略": "重仓龙头，全仓龙头、做妖股",
            "选股方向": [
                "核心龙头：板块空间最高股，只做龙头",
                "妖股博弈：超预期连板股，情绪标杆",
                "龙头加速：一字板加速阶段跟随"
            ],
            "关注信号": [
                "龙头出现加速一字板",
                "跟风股全面开花",
                "市场热度爆棚"
            ],
            "风险提示": "高潮期往往是分歧的开始，注意高位风险，随时准备撤退",
            "止损建议": "龙头炸板当日不封回考虑止盈，次日弱势必须离场"
        },
        4: {  # 退潮期
            "周期名称": "退潮期",
            "emoji": "📉",
            "周期特征": "情绪开始回落，涨停数减少（<40只），跌停增加，连板断板，亏钱效应显现",
            "仓位建议": "10%以下或空仓",
            "操作策略": "空仓避险，等待新周期、切换低位",
            "选股方向": [
                "低位新题材：与前期主线无关的新方向",
                "超跌反抽：大跌后的技术性反弹（快进快出）",
                "避险板块：防御性板块的龙头"
            ],
            "关注信号": [
                "新题材首板开始出现",
                "老龙头企稳",
                "指数缩量止跌"
            ],
            "风险提示": "退潮期做多容易大面，宁可错过不要做错",
            "止损建议": "严格执行止损，不抱有幻想，保住本金最重要"
        }
    }
    
    def __init__(self, 
                 model_dir: Optional[Path] = None,
                 data_dir: Optional[Path] = None,
                 output_dir: Optional[Path] = None):
        """
        初始化预测器
        
        Args:
            model_dir: 模型目录
            data_dir: 数据目录
            output_dir: 输出目录
        """
        self.logger = self._setup_logger()
        
        # 路径配置（支持外部配置）
        self.model_dir = model_dir or SKILL_ROOT / "models"
        self.data_dir = data_dir or DATA_DIR / "index"
        self.output_dir = output_dir or DATA_DIR / "output"
        
        # 确保目录存在
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # 模型和数据
        self.model = None
        self.scaler = None
        self.feature_columns = None
        
        # 加载模型
        self._load_model()
    
    def _setup_logger(self) -> logging.Logger:
        """设置日志"""
        logger = logging.getLogger("EmotionCyclePredictor")
        logger.setLevel(logging.INFO)
        if not logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            ))
            logger.addHandler(handler)
        return logger
    
    def _load_model(self) -> bool:
        """加载模型"""
        model_path = self.model_dir / "emotion_cycle_xgb_v3.pkl"
        if not model_path.exists():
            model_path = self.model_dir / "emotion_cycle_xgb.pkl"
        
        if not model_path.exists():
            self.logger.warning(f"模型文件不存在: {model_path}")
            self.logger.info("将使用规则引擎进行预测")
            return False
        
        try:
            with open(model_path, 'rb') as f:
                model_data = pickle.load(f)
            
            self.model = model_data['model']
            self.scaler = model_data['scaler']
            self.feature_columns = model_data['feature_columns']
            
            self.logger.info(f"✅ 模型加载成功")
            return True
            
        except Exception as e:
            self.logger.error(f"模型加载失败: {e}")
            return False
    
    def predict_today(self, date: Optional[str] = None) -> Dict[str, Any]:
        """
        预测指定日期的情绪周期
        
        Args:
            date: 日期（YYYY-MM-DD），默认今天
            
        Returns:
            Dict: 预测结果和操作建议
        """
        if date is None:
            date = datetime.now().strftime('%Y-%m-%d')
        
        self.logger.info(f"\n{'=' * 60}")
        self.logger.info(f"市场情绪周期预测 - {date}")
        self.logger.info(f"{'=' * 60}")
        
        # 获取特征数据
        feature_df = self._get_feature_data(date)
        
        if feature_df.empty:
            self.logger.warning("无法获取特征数据")
            return self._empty_result(date)
        
        # 获取当日数据
        today_data = feature_df[feature_df['tradeDate'] == pd.to_datetime(date)]
        
        if today_data.empty:
            # 尝试获取最近一个交易日
            today_data = feature_df.iloc[[-1]]
            actual_date = today_data['tradeDate'].iloc[0]
            self.logger.info(f"使用最近交易日数据: {actual_date}")
        
        # 预测
        if self.model is not None:
            prediction = self._predict_with_model(today_data)
        else:
            prediction = self._predict_with_rules(today_data)
        
        # 获取操作建议
        advice = self.OPERATION_ADVICE.get(prediction['emotion_label'], {})
        
        # 组装结果
        result = {
            'date': date,
            'actual_date': str(today_data['tradeDate'].iloc[0])[:10],
            'emotion_label': prediction['emotion_label'],
            'emotion_name': prediction['emotion_name'],
            'confidence': prediction.get('confidence', 0),
            'probabilities': prediction.get('probabilities', {}),
            'market_data': self._extract_market_data(today_data),
            'advice': advice,
            'trend_analysis': self._analyze_trend(feature_df, date)
        }
        
        # 打印结果
        self._print_result(result)
        
        return result
    
    def _get_feature_data(self, date: str) -> pd.DataFrame:
        """获取特征数据 - 从统一数据源读取"""
        # 优先从主项目数据库读取
        feature_file = self.data_dir / "emotion_features.parquet"
        
        if feature_file.exists():
            try:
                df = pd.read_parquet(feature_file)
                df['tradeDate'] = pd.to_datetime(df['tradeDate'])
                self.logger.info(f"✅ 从统一数据源读取特征数据: {feature_file}")
                return df
            except Exception as e:
                self.logger.warning(f"读取统一数据源失败: {e}")
        
        # 回退到技能本地数据
        local_feature_file = SKILL_ROOT / "data" / "index" / "emotion_features.parquet"
        if local_feature_file.exists():
            try:
                df = pd.read_parquet(local_feature_file)
                df['tradeDate'] = pd.to_datetime(df['tradeDate'])
                self.logger.info(f"✅ 从本地读取特征数据: {local_feature_file}")
                return df
            except Exception as e:
                self.logger.warning(f"读取本地特征失败: {e}")
        
        self.logger.warning("特征文件不存在")
        return pd.DataFrame()
    
    def _predict_with_model(self, today_data: pd.DataFrame) -> Dict[str, Any]:
        """使用模型预测"""
        # 准备特征
        available_features = [c for c in self.feature_columns if c in today_data.columns]
        if len(available_features) < len(self.feature_columns):
            missing = set(self.feature_columns) - set(available_features)
            self.logger.warning(f"缺少特征: {missing}")
            # 填充缺失特征为0
            for col in missing:
                today_data = today_data.copy()
                today_data[col] = 0
        
        X = today_data[self.feature_columns].values
        X_scaled = self.scaler.transform(X)
        
        # 预测
        prediction = self.model.predict(X_scaled)[0]
        probabilities = self.model.predict_proba(X_scaled)[0]
        
        return {
            'emotion_label': int(prediction),
            'emotion_name': self.EMOTION_LABELS.get(int(prediction), '未知'),
            'confidence': float(probabilities.max()),
            'probabilities': {
                self.EMOTION_LABELS[i]: float(p) 
                for i, p in enumerate(probabilities)
            }
        }
    
    def _predict_with_rules(self, today_data: pd.DataFrame) -> Dict[str, Any]:
        """使用规则引擎预测（备用方案）"""
        row = today_data.iloc[0]
        
        # 提取关键指标
        limit_up = row.get('limit_up_count', 0)
        limit_down = row.get('limit_down_count', 0)
        rise_fall_ratio = row.get('rise_fall_ratio', 1)
        explosion_rate = row.get('explosion_rate', 0)
        limit_up_trend = row.get('limit_up_trend_3d', 0)
        emotion_score = row.get('emotion_score', 50)
        limit_up_ma5 = row.get('limit_up_ma5', limit_up)
        
        # 规则判断（v2.0）
        # 冰点期
        if limit_down >= 80:
            label = 0
        elif limit_up <= 25 and limit_down >= 20:
            label = 0
        elif rise_fall_ratio < 0.2 and limit_down >= 30:
            label = 0
        # 高潮期
        elif limit_up >= 120 and limit_down <= 10 and rise_fall_ratio >= 3.0 and explosion_rate <= 0.20 and limit_up_ma5 >= 80:
            label = 3
        elif limit_up >= 150 and rise_fall_ratio >= 2.0 and explosion_rate <= 0.25 and limit_up_ma5 >= 100:
            label = 3
        # 退潮期
        elif limit_up >= 50 and limit_down >= 40:
            label = 4
        elif limit_up >= 80 and rise_fall_ratio < 0.6:
            label = 4
        elif limit_down >= 30 and rise_fall_ratio < 0.8:
            label = 4
        elif limit_up_trend < -10 and limit_down >= 20:
            label = 4
        # 发酵期
        elif limit_up >= 80 and limit_down <= 15 and rise_fall_ratio >= 1.5 and explosion_rate <= 0.35:
            label = 2
        elif limit_up >= 100 and limit_down <= 20 and rise_fall_ratio >= 1.2:
            label = 2
        elif limit_up >= 60 and limit_down <= 10 and rise_fall_ratio >= 2.5:
            label = 2
        # 启动期（默认）
        else:
            label = 1
        
        return {
            'emotion_label': label,
            'emotion_name': self.EMOTION_LABELS.get(label, '未知'),
            'confidence': 0.6,  # 规则引擎置信度较低
            'probabilities': {}
        }
    
    def _extract_market_data(self, today_data: pd.DataFrame) -> Dict[str, Any]:
        """提取市场数据"""
        row = today_data.iloc[0]
        
        return {
            '涨停家数': int(row.get('limit_up_count', 0)),
            '跌停家数': int(row.get('limit_down_count', 0)),
            '上涨家数': int(row.get('rise_count', 0)),
            '下跌家数': int(row.get('fall_count', 0)),
            '涨跌比': round(row.get('rise_fall_ratio', 0), 2),
            '炸板率': f"{row.get('explosion_rate', 0) * 100:.1f}%",
            '情绪分数': round(row.get('emotion_score', 0), 1),
            '上证涨跌幅': f"{row.get('sh_change_pct', 0):.2f}%",
            '首板数量': int(row.get('first_board_count', 0)),
            '连板数量': int(row.get('continuous_board_count', 0)),
        }
    
    def _analyze_trend(self, feature_df: pd.DataFrame, date: str) -> Dict[str, Any]:
        """分析趋势"""
        df = feature_df.sort_values('tradeDate')
        
        # 最近5日数据
        recent = df.tail(5)
        
        if len(recent) < 2:
            return {'趋势': '数据不足'}
        
        # 涨停趋势
        limit_up_trend = recent['limit_up_count'].diff().mean() if 'limit_up_count' in recent.columns else 0
        
        # 情绪趋势
        emotion_trend = recent['emotion_score'].diff().mean() if 'emotion_score' in recent.columns else 0
        
        # 判断趋势
        if limit_up_trend > 5:
            trend = "情绪快速升温 ↑↑"
        elif limit_up_trend > 0:
            trend = "情绪温和回暖 ↑"
        elif limit_up_trend > -5:
            trend = "情绪平稳 →"
        elif limit_up_trend > -10:
            trend = "情绪降温 ↓"
        else:
            trend = "情绪快速回落 ↓↓"
        
        return {
            '5日趋势': trend,
            '涨停数变化': f"{limit_up_trend:+.1f}/日",
            '情绪分变化': f"{emotion_trend:+.1f}/日",
            '近5日涨停数': recent['limit_up_count'].tolist() if 'limit_up_count' in recent.columns else []
        }
    
    def _empty_result(self, date: str) -> Dict[str, Any]:
        """返回空结果"""
        return {
            'date': date,
            'emotion_label': -1,
            'emotion_name': '无法判断',
            'confidence': 0,
            'advice': {},
            'error': '无法获取数据'
        }
    
    def _print_result(self, result: Dict[str, Any]) -> None:
        """打印预测结果"""
        advice = result.get('advice', {})
        # Windows控制台可能不支持emoji，使用try-except处理
        try:
            emoji = advice.get('emoji', '')
            header = f"[*] 市场情绪周期判断结果 {emoji}"
            print("\n" + "=" * 60)
            print(header)
        except UnicodeEncodeError:
            print("\n" + "=" * 60)
            print("[*] 市场情绪周期判断结果")
        print("=" * 60)
        
        print(f"\n[日期] 交易日期: {result['actual_date']}")
        print(f"\n[预测] 情绪周期: 【{result['emotion_name']}】")
        print(f"       置信度: {result['confidence']:.1%}")
        
        # 概率分布
        if result.get('probabilities'):
            print(f"\n[概率分布]")
            for name, prob in result['probabilities'].items():
                bar = "#" * int(prob * 20)
                print(f"   {name}: {bar} {prob:.1%}")
        
        # 市场数据
        print(f"\n[市场数据]")
        for key, value in result.get('market_data', {}).items():
            print(f"   {key}: {value}")
        
        # 趋势分析
        trend = result.get('trend_analysis', {})
        if trend:
            print(f"\n[趋势分析]")
            print(f"   {trend.get('5日趋势', '')}")
            print(f"   涨停数变化: {trend.get('涨停数变化', '')}")
        
        # 操作建议
        if advice:
            print(f"\n{'=' * 60}")
            try:
                emoji = advice.get('emoji', '')
                print(f"[操作建议] {emoji}")
            except UnicodeEncodeError:
                print("[操作建议]")
            print("=" * 60)
            print(f"\n[周期] {advice.get('周期名称', '')}")
            print(f"\n[特征] 周期特征:")
            print(f"   {advice.get('周期特征', '')}")
            
            print(f"\n[仓位] 仓位建议: {advice.get('仓位建议', '')}")
            
            print(f"\n[策略] 操作策略: {advice.get('操作策略', '')}")
            
            print(f"\n[选股] 选股方向:")
            for item in advice.get('选股方向', []):
                print(f"   - {item}")
            
            print(f"\n[信号] 关注信号:")
            for item in advice.get('关注信号', []):
                print(f"   - {item}")
            
            print(f"\n[风险] 风险提示:")
            print(f"   {advice.get('风险提示', '')}")
            
            print(f"\n[止损] 止损建议:")
            print(f"   {advice.get('止损建议', '')}")
        
        print("\n" + "=" * 60)
    
    def save_prediction(self, result: Dict[str, Any]) -> Path:
        """保存预测结果到每日文件"""
        # 每日存储目录
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # 获取日期
        date_str = result.get('actual_date', result['date'])
        if isinstance(date_str, str):
            date_str = date_str[:10]  # YYYY-MM-DD
        
        # 构建每日记录
        daily_record = {
            'date': date_str,
            'emotion_label': result['emotion_label'],
            'emotion_name': result['emotion_name'],
            'confidence': result['confidence'],
            'predict_time': datetime.now().isoformat(),
            'market_data': result.get('market_data', {}),
            'advice': result.get('advice', {}),
            'trend_analysis': result.get('trend_analysis', {}),
            'probabilities': result.get('probabilities', {})
        }
        
        # 保存每日JSON文件
        daily_file = self.output_dir / f"{date_str}.json"
        with open(daily_file, 'w', encoding='utf-8') as f:
            json.dump(daily_record, f, ensure_ascii=False, indent=2)
        self.logger.info(f"每日预测已保存: {daily_file}")
        
        return daily_file
    
    def save_recent_days(self, days: int = 30) -> Path:
        """
        生成并保存最近N日的情绪周期数据
        
        Args:
            days: 天数，默认30
            
        Returns:
            Path: 汇总文件路径
        """
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # 获取特征数据
        feature_df = self._get_feature_data(datetime.now().strftime('%Y-%m-%d'))
        
        if feature_df.empty:
            self.logger.warning("无法获取特征数据")
            return None
        
        # 获取最近N个交易日
        feature_df = feature_df.sort_values('tradeDate', ascending=False)
        recent_dates = feature_df['tradeDate'].head(days).tolist()
        
        self.logger.info(f"生成最近 {len(recent_dates)} 个交易日的情绪周期数据...")
        
        all_records = []
        
        for trade_date in recent_dates:
            date_str = str(trade_date)[:10]
            
            # 获取当日数据
            today_data = feature_df[feature_df['tradeDate'] == trade_date]
            
            if today_data.empty:
                continue
            
            # 预测
            if self.model is not None:
                prediction = self._predict_with_model(today_data)
            else:
                prediction = self._predict_with_rules(today_data)
            
            # 获取操作建议
            advice = self.OPERATION_ADVICE.get(prediction['emotion_label'], {})
            
            # 构建记录
            record = {
                'date': date_str,
                'emotion_label': prediction['emotion_label'],
                'emotion_name': prediction['emotion_name'],
                'confidence': prediction.get('confidence', 0),
                'predict_time': datetime.now().isoformat(),
                'market_data': self._extract_market_data(today_data),
                'advice': advice,
                'probabilities': prediction.get('probabilities', {})
            }
            
            all_records.append(record)
            
            # 保存每日文件
            daily_file = self.output_dir / f"{date_str}.json"
            with open(daily_file, 'w', encoding='utf-8') as f:
                json.dump(record, f, ensure_ascii=False, indent=2)
        
        # 保存汇总文件（最新30日）
        summary_file = self.output_dir / "latest_30days.json"
        summary_data = {
            'update_time': datetime.now().isoformat(),
            'total_days': len(all_records),
            'records': sorted(all_records, key=lambda x: x['date'], reverse=True)
        }
        
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(summary_data, f, ensure_ascii=False, indent=2)
        
        self.logger.info(f"汇总文件已保存: {summary_file}")
        self.logger.info(f"共生成 {len(all_records)} 个交易日数据")
        
        return summary_file


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description='🎭 市场情绪周期预测',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 预测今日情绪周期
  python predictor.py --today
  
  # 预测指定日期
  python predictor.py --date 2026-01-20
  
  # 输出JSON格式
  python predictor.py --today --json
  
  # 生成最近30日数据
  python predictor.py --recent 30
        """
    )
    
    parser.add_argument(
        '--today',
        action='store_true',
        help='预测今日情绪周期'
    )
    
    parser.add_argument(
        '--date',
        type=str,
        default=None,
        help='预测指定日期 (格式: YYYY-MM-DD)'
    )
    
    parser.add_argument(
        '--json',
        action='store_true',
        help='输出JSON格式'
    )
    
    parser.add_argument(
        '--save',
        action='store_true',
        help='保存预测结果'
    )
    
    parser.add_argument(
        '--recent',
        type=int,
        default=0,
        help='生成最近N日数据 (默认: 30)'
    )
    
    return parser.parse_args()


def main():
    """主函数"""
    args = parse_args()
    
    # 创建预测器
    predictor = EmotionCyclePredictor()
    
    # 生成最近N日数据
    if args.recent > 0:
        summary_file = predictor.save_recent_days(args.recent)
        if summary_file:
            print(f"\n[OK] 最近 {args.recent} 日数据已生成")
            print(f"     输出目录: {predictor.output_dir}")
            print(f"     汇总文件: {summary_file}")
        return None
    
    # 确定预测日期
    if args.date:
        date = args.date
    elif args.today:
        date = datetime.now().strftime('%Y-%m-%d')
    else:
        date = datetime.now().strftime('%Y-%m-%d')
    
    # 预测
    result = predictor.predict_today(date)
    
    # 输出
    if args.json:
        # JSON格式输出
        output = {
            'date': result['date'],
            'emotion_label': result['emotion_label'],
            'emotion_name': result['emotion_name'],
            'confidence': result['confidence'],
            'market_data': result.get('market_data', {}),
            'advice': result.get('advice', {}),
            'probabilities': result.get('probabilities', {}),
            'trend': result.get('trend_analysis', {})
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
    
    # 保存
    if args.save:
        predictor.save_prediction(result)
    
    return result


if __name__ == "__main__":
    main()
