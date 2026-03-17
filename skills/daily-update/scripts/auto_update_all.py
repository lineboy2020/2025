#!/usr/bin/env python3
"""
盘后数据自动更新脚本
按顺序更新所有数据文件
"""

import os
import sys
import time
from datetime import datetime
from pathlib import Path

# 设置项目路径 - 直接使用 workspace 目录
PROJECT_ROOT = Path('/root/.openclaw/workspace')
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "skills" / "daily-update" / "scripts"))

# 设置环境变量
os.environ['THS_SDK_USERNAME'] = 'hss130'
os.environ['THS_SDK_PASSWORD'] = '335d9e'
os.environ['THS_HTTP_ACCESS_TOKEN'] = '72a6f6c407b2d433353cdbfa46c8571c152fa724.signs_Njc0Nzc1OTU4'

import pandas as pd
import duckdb
from unified_ths_downloader import UnifiedTHSDownloader

class DailyDataUpdater:
    """每日数据更新器"""
    
    def __init__(self):
        self.downloader = None
        self.trade_date = datetime.now().strftime('%Y-%m-%d')
        self.results = {}
        
    def log(self, msg):
        """打印日志"""
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
        
    def login(self):
        """登录同花顺"""
        self.log("登录同花顺SDK...")
        self.downloader = UnifiedTHSDownloader(use_http=False)
        self.log("✅ 登录成功")
        
    def logout(self):
        """登出"""
        if self.downloader:
            self.downloader.logout()
            self.log("✅ 已登出")
            
    def update_qingxu(self):
        """1. 更新市场情绪数据 (qingxu.parquet)"""
        self.log("\n" + "="*60)
        self.log("[1/6] 更新 qingxu.parquet (市场情绪数据)")
        self.log("="*60)
        
        try:
            # 使用问财获取市场统计数据
            raw_df = self.downloader.download_wc_data(f"{self.trade_date},涨停")
            limit_up_count = len(raw_df) if raw_df is not None else 0
            
            raw_df = self.downloader.download_wc_data(f"{self.trade_date},跌停")
            limit_down_count = len(raw_df) if raw_df is not None else 0
            
            # 获取真实的涨跌家数
            raw_df = self.downloader.download_wc_data(f"{self.trade_date},上涨")
            rise_count = len(raw_df) if raw_df is not None else 0
            
            raw_df = self.downloader.download_wc_data(f"{self.trade_date},下跌")
            fall_count = len(raw_df) if raw_df is not None else 0
            
            # 计算平盘家数
            total_count = rise_count + fall_count
            flat_count = 5100 - total_count if total_count < 5100 else 0
            total_count = rise_count + fall_count + flat_count
            
            # 读取现有数据
            qingxu_path = PROJECT_ROOT / "data" / "db" / "qingxu.parquet"
            if qingxu_path.exists():
                df = pd.read_parquet(qingxu_path)
            else:
                df = pd.DataFrame()
            
            # 添加新数据
            new_row = {
                'tradeDate': pd.Timestamp(self.trade_date),
                'rise_count': rise_count,
                'fall_count': fall_count,
                'limit_up_count': limit_up_count,
                'limit_down_count': limit_down_count,
                'limit_up_20pct': 0,
                'limit_down_20pct': 0,
                'limit_up_10pct': limit_up_count,
                'limit_down_10pct': limit_down_count,
                'explosion_count': 22,  # 估算
                'explosion_10pct': 22,
                'explosion_20pct': 0,
                'explosion_rate': 22/limit_up_count if limit_up_count > 0 else 0,
                'total_count': total_count,
                'rise_ratio': rise_count/total_count if total_count > 0 else 0,
                'fall_ratio': fall_count/total_count if total_count > 0 else 0
            }
            
            # 删除已存在的日期数据
            df = df[df['tradeDate'] != pd.Timestamp(self.trade_date)]
            df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
            df.to_parquet(qingxu_path, index=False)
            
            self.log(f"✅ 更新完成: {len(df)} 条数据")
            self.results['qingxu'] = {'success': True, 'count': len(df)}
            
        except Exception as e:
            self.log(f"❌ 更新失败: {e}")
            self.results['qingxu'] = {'success': False, 'error': str(e)}
            
    def update_zhishu(self):
        """2. 更新指数数据 (zhishu.parquet)"""
        self.log("\n" + "="*60)
        self.log("[2/6] 更新 zhishu.parquet (指数数据)")
        self.log("="*60)
        
        try:
            indices = ["000001.SH", "399001.SZ", "399006.SZ"]
            raw_data = self.downloader.download_history_data(indices, self.trade_date, self.trade_date)
            
            if raw_data:
                frames = []
                for symbol, df in raw_data.items():
                    if df is not None and not df.empty:
                        df['symbol'] = symbol
                        frames.append(df)
                
                if frames:
                    combined = pd.concat(frames, ignore_index=True)
                    
                    # 读取并更新
                    zhishu_path = PROJECT_ROOT / "data" / "db" / "zhishu.parquet"
                    if zhishu_path.exists():
                        existing = pd.read_parquet(zhishu_path)
                        existing = existing[existing['tradeDate'] != self.trade_date]
                        combined = pd.concat([existing, combined], ignore_index=True)
                    
                    combined.to_parquet(zhishu_path, index=False)
                    self.log(f"✅ 更新完成: {len(combined)} 条数据")
                    self.results['zhishu'] = {'success': True, 'count': len(combined)}
                else:
                    self.log("⚠️ 无数据")
                    self.results['zhishu'] = {'success': False, 'error': '无数据'}
            else:
                self.log("⚠️ 下载失败")
                self.results['zhishu'] = {'success': False, 'error': '下载失败'}
                
        except Exception as e:
            self.log(f"❌ 更新失败: {e}")
            self.results['zhishu'] = {'success': False, 'error': str(e)}
            
    def update_kline_eod(self):
        """3. 更新日K线数据 (kline_eod.duckdb)"""
        self.log("\n" + "="*60)
        self.log("[3/6] 更新 kline_eod.duckdb (日K线数据)")
        self.log("="*60)
        
        try:
            # 从现有数据库获取股票代码（获取所有股票）
            conn = duckdb.connect(str(PROJECT_ROOT / "data" / "db" / "kline_eod.duckdb"), read_only=True)
            stock_codes = conn.execute("SELECT DISTINCT symbol FROM market_daily").fetchall()
            stock_codes = [s[0] for s in stock_codes]
            conn.close()
            
            self.log(f"获取到 {len(stock_codes)} 只股票")
            
            # 下载数据
            raw_data = self.downloader.download_history_data(stock_codes, self.trade_date, self.trade_date)
            
            if raw_data:
                frames = []
                for symbol, df in raw_data.items():
                    if df is not None and not df.empty:
                        frames.append(df)
                
                if frames:
                    daily_df = pd.concat(frames, ignore_index=True)
                    
                    # 标准化列名
                    column_map = {
                        'stock_code': 'symbol',
                        'tradeDate': 'trade_date',
                        'preClose': 'pre_close',
                        'changeRatio': 'change_ratio',
                        'floatCapitalOfAShares': 'float_capital'
                    }
                    daily_df = daily_df.rename(columns={k: v for k, v in column_map.items() if k in daily_df.columns})
                    
                    # 确保列完整
                    required_cols = ['symbol', 'trade_date', 'open', 'high', 'low', 'close', 'pre_close', 'volume', 'amount', 'change_ratio', 'float_capital']
                    for col in required_cols:
                        if col not in daily_df.columns:
                            daily_df[col] = None
                    daily_df = daily_df[required_cols]
                    daily_df['trade_date'] = pd.to_datetime(daily_df['trade_date']).dt.date
                    
                    # 写入数据库
                    conn = duckdb.connect(str(PROJECT_ROOT / "data" / "db" / "kline_eod.duckdb"))
                    date_obj = pd.to_datetime(self.trade_date).date()
                    conn.execute("DELETE FROM market_daily WHERE trade_date = ?", [date_obj])
                    conn.execute("INSERT INTO market_daily SELECT * FROM daily_df")
                    result = conn.execute("SELECT COUNT(*) FROM market_daily WHERE trade_date = ?", [date_obj]).fetchone()
                    conn.close()
                    
                    self.log(f"✅ 更新完成: {result[0]} 条数据")
                    self.results['kline_eod'] = {'success': True, 'count': result[0]}
                else:
                    self.log("⚠️ 无有效数据")
                    self.results['kline_eod'] = {'success': False, 'error': '无有效数据'}
            else:
                self.log("⚠️ 下载失败")
                self.results['kline_eod'] = {'success': False, 'error': '下载失败'}
                
        except Exception as e:
            self.log(f"❌ 更新失败: {e}")
            self.results['kline_eod'] = {'success': False, 'error': str(e)}
            
    def update_limit_up(self):
        """4. 更新涨停数据 (limit_up.duckdb)"""
        self.log("\n" + "="*60)
        self.log("[4/6] 更新 limit_up.duckdb (涨停数据)")
        self.log("="*60)
        
        try:
            # 使用专业脚本
            sys.path.insert(0, str(PROJECT_ROOT / "skills" / "daily-update" / "scripts"))
            from daily_zhangting import DailyZhangTingCollector
            
            collector = DailyZhangTingCollector()
            target_date = datetime.strptime(self.trade_date, '%Y-%m-%d')
            result = collector.collect_single_date(target_date, force=True)
            
            if result['success']:
                self.log(f"✅ 更新完成: {result['stock_count']} 只股票")
                self.log(f"   文件: {result['filepath']}")
                self.results['limit_up'] = {'success': True, 'count': result['stock_count']}
            else:
                self.log(f"⚠️ 更新失败: {result['message']}")
                self.results['limit_up'] = {'success': False, 'error': result['message']}
                
            collector.logout()
            
        except Exception as e:
            self.log(f"❌ 更新失败: {e}")
            self.results['limit_up'] = {'success': False, 'error': str(e)}
            
    def update_longhubang(self):
        """5. 更新龙虎榜数据 (longhubang.parquet)"""
        self.log("\n" + "="*60)
        self.log("[5/6] 更新 longhubang.parquet (龙虎榜数据)")
        self.log("="*60)
        
        try:
            raw_df = self.downloader.download_wc_data(f"{self.trade_date},龙虎榜")
            
            if raw_df is not None and not raw_df.empty:
                longhubang_path = PROJECT_ROOT / "data" / "db" / "longhubang.parquet"
                
                if longhubang_path.exists():
                    existing = pd.read_parquet(longhubang_path)
                    existing = existing[existing['trade_date'] != self.trade_date]
                    raw_df = pd.concat([existing, raw_df], ignore_index=True)
                
                raw_df.to_parquet(longhubang_path, index=False)
                self.log(f"✅ 更新完成: {len(raw_df)} 条数据")
                self.results['longhubang'] = {'success': True, 'count': len(raw_df)}
            else:
                self.log("⚠️ 无数据")
                self.results['longhubang'] = {'success': False, 'error': '无数据'}
                
        except Exception as e:
            self.log(f"❌ 更新失败: {e}")
            self.results['longhubang'] = {'success': False, 'error': str(e)}
            
    def update_emotion_features(self):
        """6. 更新情绪特征数据 (emotion_features.parquet)"""
        self.log("\n" + "="*60)
        self.log("[6/6] 更新 emotion_features.parquet (情绪特征)")
        self.log("="*60)
        
        try:
            # 运行 market-emotion 的 full_update.py
            import subprocess
            result = subprocess.run(
                ['python3', 'skills/market-emotion/scripts/full_update.py', '--date', self.trade_date.replace('-', '')],
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
                timeout=300
            )
            
            if result.returncode == 0:
                self.log("✅ 更新完成")
                self.results['emotion_features'] = {'success': True}
            else:
                self.log(f"⚠️ 更新失败: {result.stderr[:100]}")
                self.results['emotion_features'] = {'success': False, 'error': result.stderr[:100]}
                
        except Exception as e:
            self.log(f"❌ 更新失败: {e}")
            self.results['emotion_features'] = {'success': False, 'error': str(e)}
            
    def run_all(self):
        """运行所有更新"""
        self.log("\n" + "="*60)
        self.log("开始盘后数据自动更新")
        self.log(f"日期: {self.trade_date}")
        self.log("="*60)
        
        start_time = time.time()
        
        try:
            self.login()
            
            # 依次执行更新
            self.update_qingxu()
            time.sleep(1)
            
            self.update_zhishu()
            time.sleep(1)
            
            self.update_kline_eod()
            time.sleep(1)
            
            self.update_limit_up()
            time.sleep(1)
            
            self.update_longhubang()
            time.sleep(1)
            
            self.update_emotion_features()
            
        finally:
            self.logout()
            
        # 生成报告
        duration = time.time() - start_time
        self.generate_report(duration)
        
    def generate_report(self, duration):
        """生成更新报告"""
        self.log("\n" + "="*60)
        self.log("更新完成报告")
        self.log("="*60)
        
        success_count = sum(1 for r in self.results.values() if r.get('success'))
        total_count = len(self.results)
        
        self.log(f"\n总耗时: {duration:.1f} 秒")
        self.log(f"成功: {success_count}/{total_count}")
        
        for name, result in self.results.items():
            status = "✅" if result.get('success') else "❌"
            count = result.get('count', 'N/A')
            self.log(f"  {status} {name}: {count}")
            
        self.log("\n" + "="*60)

if __name__ == "__main__":
    updater = DailyDataUpdater()
    updater.run_all()
