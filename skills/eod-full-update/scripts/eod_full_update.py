#!/usr/bin/env python3
"""
盘后数据全量更新脚本
一键更新所有A股盘后数据

Usage:
    python eod_full_update.py
    python eod_full_update.py --date 2026-03-07
    python eod_full_update.py --skip emotion_features
"""

import os
import sys
import time
import json
import argparse
from datetime import datetime
from pathlib import Path

# ==============================================================================
# 路径配置
# ==============================================================================
SKILL_DIR = Path(__file__).resolve().parent.parent
WORKSPACE_ROOT = SKILL_DIR.parent.parent

sys.path.insert(0, str(WORKSPACE_ROOT))
sys.path.insert(0, str(WORKSPACE_ROOT / "skills" / "daily-update" / "scripts"))
sys.path.insert(0, str(WORKSPACE_ROOT / "skills" / "ths-data-fetcher" / "scripts"))

# ==============================================================================
# 加载环境变量
# ==============================================================================
env_file = SKILL_DIR / ".env"
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ.setdefault(key, value)

# ==============================================================================
# 导入依赖
# ==============================================================================
import pandas as pd
import duckdb

try:
    from unified_ths_downloader import UnifiedTHSDownloader
except ImportError:
    print("❌ 无法导入 unified_ths_downloader，请确保 ths-data-fetcher 技能已安装")
    sys.exit(1)


# ==============================================================================
# 配置补全
# ==============================================================================
def ensure_skill_config_available():
    workspace_cfg = WORKSPACE_ROOT / 'config.json'
    candidate_cfgs = [
        SKILL_DIR / 'config.json',
        WORKSPACE_ROOT / 'skills' / 'ths-data-fetcher' / 'config.json',
        WORKSPACE_ROOT / 'skills' / 'ths-data-fetcher' / 'scripts' / 'config.json',
        WORKSPACE_ROOT / 'skills' / 'daily-update' / 'config.json',
    ]
    try:
        workspace_data = {}
        if workspace_cfg.exists():
            workspace_data = json.loads(workspace_cfg.read_text(encoding='utf-8'))

        changed = False

        if not isinstance(workspace_data.get('ths_sdk'), dict) or not workspace_data.get('ths_sdk', {}).get('username') or not workspace_data.get('ths_sdk', {}).get('password'):
            for cfg in candidate_cfgs:
                if not cfg.exists():
                    continue
                src = json.loads(cfg.read_text(encoding='utf-8'))
                ths_sdk = src.get('ths_sdk', {})
                if ths_sdk.get('username') and ths_sdk.get('password'):
                    workspace_data['ths_sdk'] = ths_sdk
                    changed = True
                    break

        has_http = workspace_data.get('ths_http') or workspace_data.get('data_skills', {}).get('ths_http')
        if not has_http:
            for cfg in candidate_cfgs:
                if not cfg.exists():
                    continue
                src = json.loads(cfg.read_text(encoding='utf-8'))
                http_cfg = src.get('ths_http') or src.get('data_skills', {}).get('ths_http')
                if http_cfg:
                    if 'data_skills' not in workspace_data or not isinstance(workspace_data.get('data_skills'), dict):
                        workspace_data['data_skills'] = {}
                    workspace_data['data_skills']['ths_http'] = http_cfg
                    changed = True
                    break

        if changed:
            workspace_cfg.write_text(json.dumps(workspace_data, ensure_ascii=False, indent=2), encoding='utf-8')
    except Exception:
        pass


# ==============================================================================
# 主类
# ==============================================================================
class EODFullUpdater:
    """盘后数据全量更新器"""

    def __init__(self, date_str=None):
        ensure_skill_config_available()
        self.trade_date = date_str or datetime.now().strftime('%Y-%m-%d')
        self.results = {}
        self.data_dir = WORKSPACE_ROOT / "data" / "db"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.downloader_http = None
        self.downloader_sdk = None

    def log(self, msg):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

    def login(self):
        self.log("登录同花顺...")
        has_http = bool(os.environ.get('THS_HTTP_ACCESS_TOKEN'))
        self.downloader_http = UnifiedTHSDownloader(use_http=True) if has_http else None
        self.downloader_sdk = UnifiedTHSDownloader(use_http=False)
        self.log(f"✅ 登录成功 (HTTP可用: {bool(self.downloader_http)}, SDK可用: True)")

    def logout(self):
        for d in [self.downloader_http, self.downloader_sdk]:
            if d:
                try:
                    d.logout()
                except Exception:
                    pass
        self.log("✅ 已登出")

    def _wc_downloader(self):
        return self.downloader_http or self.downloader_sdk

    def _normalize_daily_df(self, df: pd.DataFrame) -> pd.DataFrame:
        work = df.copy()
        rename_map = {
            'stock_code': 'symbol', 'thscode': 'symbol', '股票代码': 'symbol', '代码': 'symbol',
            'open': 'open', 'high': 'high', 'low': 'low', 'close': 'close',
            'preclose': 'pre_close', 'preClose': 'pre_close', 'pre_close': 'pre_close',
            'volume': 'volume', '成交量': 'volume',
            'amount': 'amount', '成交额': 'amount',
            'changeratio': 'change_ratio', 'changeRatio': 'change_ratio', 'change_ratio': 'change_ratio',
            'time': 'trade_date', 'tradeDate': 'trade_date', 'trade_date': 'trade_date',
            'floatcapitalofashares': 'float_capital', 'floatCapitalOfAShares': 'float_capital'
        }
        work = work.rename(columns={k: v for k, v in rename_map.items() if k in work.columns})
        if 'trade_date' not in work.columns:
            raise RuntimeError(f'no trade_date in columns: {list(work.columns)}')
        work['trade_date'] = pd.to_datetime(work['trade_date']).dt.date
        cols = ['symbol', 'trade_date', 'open', 'high', 'low', 'close', 'pre_close', 'volume', 'amount', 'change_ratio', 'float_capital']
        for c in cols:
            if c not in work.columns:
                work[c] = None
        return work[cols].dropna(subset=['symbol', 'trade_date']).drop_duplicates(['symbol', 'trade_date'], keep='last')

    def _get_stock_codes(self):
        db_path = self.data_dir / "kline_eod.duckdb"
        if db_path.exists():
            conn = duckdb.connect(str(db_path), read_only=True)
            try:
                stock_codes = [s[0] for s in conn.execute("SELECT DISTINCT symbol FROM market_daily WHERE symbol IS NOT NULL ORDER BY symbol").fetchall()]
                if stock_codes:
                    return stock_codes
            finally:
                conn.close()

        raw_df = self._wc_downloader().download_wc_data(f"{self.trade_date},全部A股")
        for col in ['股票代码', 'stock_code', '代码']:
            if raw_df is not None and not raw_df.empty and col in raw_df.columns:
                return raw_df[col].dropna().astype(str).tolist()
        return []

    def update_qingxu(self):
        self.log("\n" + "=" * 60)
        self.log(f"[1/6] 更新 qingxu.parquet (市场情绪数据)")
        self.log("=" * 60)
        try:
            queries = {
                'limit_up': f"{self.trade_date},涨停",
                'limit_down': f"{self.trade_date},跌停",
                'rise': f"{self.trade_date},上涨",
                'fall': f"{self.trade_date},下跌"
            }
            counts = {}
            wc = self._wc_downloader()
            for key, query in queries.items():
                try:
                    raw_df = wc.download_wc_data(query)
                    counts[key] = len(raw_df) if raw_df is not None else 0
                except Exception as e:
                    self.log(f"  ⚠️ {key} 查询失败: {e}")
                    counts[key] = 0

            total_count = counts['rise'] + counts['fall']
            flat_count = max(0, 5100 - total_count)
            total_count = counts['rise'] + counts['fall'] + flat_count

            qingxu_path = self.data_dir / "qingxu.parquet"
            df = pd.read_parquet(qingxu_path) if qingxu_path.exists() else pd.DataFrame()
            trade_date_value = str(self.trade_date)
            if not df.empty and 'tradeDate' in df.columns:
                df['tradeDate'] = df['tradeDate'].astype(str)

            new_row = {
                'tradeDate': trade_date_value,
                'rise_count': counts['rise'],
                'fall_count': counts['fall'],
                'limit_up_count': counts['limit_up'],
                'limit_down_count': counts['limit_down'],
                'limit_up_20pct': 0,
                'limit_down_20pct': 0,
                'limit_up_10pct': counts['limit_up'],
                'limit_down_10pct': counts['limit_down'],
                'explosion_count': 0,
                'explosion_10pct': 0,
                'explosion_20pct': 0,
                'explosion_rate': 0.0,
                'total_count': total_count,
                'rise_ratio': counts['rise'] / total_count if total_count > 0 else 0,
                'fall_ratio': counts['fall'] / total_count if total_count > 0 else 0
            }
            if not df.empty and 'tradeDate' in df.columns:
                df = df[df['tradeDate'] != trade_date_value]
            df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
            df.to_parquet(qingxu_path, index=False)
            self.log(f"✅ 更新完成: {len(df)} 条历史数据")
            self.results['qingxu'] = {'success': True, 'count': len(df)}
        except Exception as e:
            self.log(f"❌ 更新失败: {e}")
            self.results['qingxu'] = {'success': False, 'error': str(e)}

    def update_zhishu(self):
        self.log("\n" + "=" * 60)
        self.log("[2/6] 更新 zhishu.parquet (指数数据)")
        self.log("=" * 60)
        try:
            indices = ["000001.SH", "399001.SZ", "399006.SZ"]
            raw_data = self.downloader_sdk.download_history_data(indices, self.trade_date, self.trade_date)
            frames = []
            if raw_data:
                for symbol, df in raw_data.items():
                    if df is not None and not df.empty:
                        df['symbol'] = symbol
                        frames.append(df)
            if not frames:
                self.log("⚠️ 无有效数据")
                self.results['zhishu'] = {'success': False, 'error': '无有效数据'}
                return

            combined = pd.concat(frames, ignore_index=True)
            if 'tradeDate' not in combined.columns:
                combined['tradeDate'] = self.trade_date

            zhishu_path = self.data_dir / "zhishu.parquet"
            if zhishu_path.exists():
                existing = pd.read_parquet(zhishu_path)
                if 'tradeDate' in existing.columns:
                    existing['tradeDate'] = pd.to_datetime(existing['tradeDate']).dt.strftime('%Y-%m-%d')
                    existing = existing[existing['tradeDate'] != self.trade_date]
                combined = pd.concat([existing, combined], ignore_index=True)

            combined.to_parquet(zhishu_path, index=False)
            self.log(f"✅ 更新完成: {len(combined)} 条历史数据")
            self.results['zhishu'] = {'success': True, 'count': len(combined)}
        except Exception as e:
            self.log(f"❌ 更新失败: {e}")
            self.results['zhishu'] = {'success': False, 'error': str(e)}

    def update_kline_eod(self):
        self.log("\n" + "=" * 60)
        self.log("[3/6] 更新 kline_eod.duckdb (日K线数据，强制SDK)")
        self.log("=" * 60)
        try:
            self.log("  获取股票代码列表...")
            stock_codes = self._get_stock_codes()
            if not stock_codes:
                self.log("⚠️ 股票列表为空")
                self.results['kline_eod'] = {'success': False, 'error': '股票列表为空'}
                return

            self.log(f"  获取到 {len(stock_codes)} 只股票")
            batch_size = 520
            all_frames = []
            ok_codes = 0

            for i in range(0, len(stock_codes), batch_size):
                batch = stock_codes[i:i + batch_size]
                self.log(f"  下载批次 {i // batch_size + 1}/{(len(stock_codes) - 1) // batch_size + 1} ({len(batch)}只，SDK)...")
                try:
                    raw_data = self.downloader_sdk.download_history_data(batch, self.trade_date, self.trade_date)
                    if raw_data:
                        for symbol, df in raw_data.items():
                            if df is not None and not df.empty:
                                norm = self._normalize_daily_df(df)
                                if not norm.empty:
                                    all_frames.append(norm)
                                    ok_codes += 1
                except Exception as e:
                    self.log(f"    ⚠️ 批次下载失败: {e}")
                time.sleep(0.2)

            if not all_frames:
                self.log("⚠️ 无有效数据")
                self.results['kline_eod'] = {'success': False, 'error': '无有效数据'}
                return

            daily_df = pd.concat(all_frames, ignore_index=True).drop_duplicates(['symbol', 'trade_date'], keep='last')
            coverage = ok_codes / max(len(stock_codes), 1)
            self.log(f"  下载覆盖率: {ok_codes}/{len(stock_codes)} = {coverage:.2%}")
            if coverage < 0.85:
                raise RuntimeError(f"下载覆盖率过低: {coverage:.2%}，拒绝覆盖写库")

            db_path = self.data_dir / "kline_eod.duckdb"
            conn = duckdb.connect(str(db_path))
            conn.execute("""
                CREATE TABLE IF NOT EXISTS market_daily (
                    symbol VARCHAR,
                    trade_date DATE,
                    open DOUBLE,
                    high DOUBLE,
                    low DOUBLE,
                    close DOUBLE,
                    pre_close DOUBLE,
                    volume DOUBLE,
                    amount DOUBLE,
                    change_ratio DOUBLE,
                    float_capital DOUBLE
                )
            """)
            conn.register('daily_view', daily_df)
            conn.execute("CREATE OR REPLACE TEMP TABLE market_daily_stage AS SELECT * FROM daily_view")
            stage_count = conn.execute("SELECT COUNT(*) FROM market_daily_stage").fetchone()[0]
            if stage_count < max(1000, int(len(stock_codes) * 0.80)):
                conn.close()
                raise RuntimeError(f"临时表记录数异常过低: {stage_count}，拒绝覆盖写库")

            date_obj = pd.to_datetime(self.trade_date).date()
            conn.execute("DELETE FROM market_daily WHERE trade_date = ?", [date_obj])
            conn.execute("INSERT INTO market_daily SELECT * FROM market_daily_stage")
            result = conn.execute("SELECT COUNT(*) FROM market_daily WHERE trade_date = ?", [date_obj]).fetchone()[0]
            conn.close()
            self.log(f"✅ 更新完成: {result} 条数据")
            self.results['kline_eod'] = {'success': True, 'count': result, 'coverage': coverage}
        except Exception as e:
            self.log(f"❌ 更新失败: {e}")
            self.results['kline_eod'] = {'success': False, 'error': str(e)}

    def update_limit_up(self):
        self.log("\n" + "=" * 60)
        self.log("[4/6] 更新 limit_up.parquet (涨停数据)")
        self.log("=" * 60)
        try:
            raw_df = self._wc_downloader().download_wc_data(f"{self.trade_date},涨停")
            if raw_df is None or raw_df.empty:
                self.log("⚠️ 无涨停数据")
                self.results['limit_up'] = {'success': True, 'count': 0}
                return

            column_mapping = {}
            if '股票代码' in raw_df.columns:
                column_mapping['股票代码'] = 'symbol'
            if '股票简称' in raw_df.columns:
                column_mapping['股票简称'] = 'name'
            if '最新价' in raw_df.columns:
                column_mapping['最新价'] = 'close'
            if '涨跌幅' in raw_df.columns:
                column_mapping['涨跌幅'] = 'change_ratio'
            if '成交量' in raw_df.columns:
                column_mapping['成交量'] = 'volume'
            if '成交额' in raw_df.columns:
                column_mapping['成交额'] = 'amount'
            if '首次涨停时间' in raw_df.columns:
                column_mapping['首次涨停时间'] = 'limit_up_time'
            if '连板数' in raw_df.columns:
                column_mapping['连板数'] = 'continuous_boards'
            if column_mapping:
                raw_df = raw_df.rename(columns=column_mapping)

            raw_df['trade_date'] = self.trade_date
            for col in ['symbol', 'name', 'trade_date']:
                if col not in raw_df.columns:
                    raw_df[col] = None

            limit_up_path = self.data_dir / "limit_up.parquet"
            if limit_up_path.exists():
                existing = pd.read_parquet(limit_up_path)
                if 'trade_date' in existing.columns:
                    existing = existing[existing['trade_date'] != self.trade_date]
                raw_df = pd.concat([existing, raw_df], ignore_index=True)

            raw_df.to_parquet(limit_up_path, index=False)
            today_count = len(raw_df[raw_df['trade_date'] == self.trade_date])
            self.log(f"✅ 更新完成: {today_count} 只涨停股票")
            self.results['limit_up'] = {'success': True, 'count': today_count}
        except Exception as e:
            self.log(f"❌ 更新失败: {e}")
            self.results['limit_up'] = {'success': False, 'error': str(e)}

    def update_longhubang(self):
        self.log("\n" + "=" * 60)
        self.log("[5/6] 更新 longhubang.parquet (龙虎榜数据)")
        self.log("=" * 60)
        try:
            raw_df = self._wc_downloader().download_wc_data(f"{self.trade_date},龙虎榜")
            if raw_df is None or raw_df.empty:
                self.log("⚠️ 无龙虎榜数据")
                self.results['longhubang'] = {'success': True, 'count': 0}
                return

            raw_df['trade_date'] = str(self.trade_date)
            longhubang_path = self.data_dir / "longhubang.parquet"
            if longhubang_path.exists():
                existing = pd.read_parquet(longhubang_path)
                if 'trade_date' in existing.columns:
                    existing['trade_date'] = existing['trade_date'].astype(str)
                    existing = existing[existing['trade_date'] != str(self.trade_date)]
                raw_df = pd.concat([existing, raw_df], ignore_index=True)

            raw_df.to_parquet(longhubang_path, index=False)
            today_count = len(raw_df[raw_df['trade_date'] == str(self.trade_date)])
            self.log(f"✅ 更新完成: {today_count} 条数据")
            self.results['longhubang'] = {'success': True, 'count': today_count}
        except Exception as e:
            self.log(f"❌ 更新失败: {e}")
            self.results['longhubang'] = {'success': False, 'error': str(e)}

    def update_emotion_features(self):
        self.log("\n" + "=" * 60)
        self.log("[6/6] 更新 emotion_features.parquet (情绪特征)")
        self.log("=" * 60)
        try:
            qingxu_path = self.data_dir / "qingxu.parquet"
            limit_up_path = self.data_dir / "limit_up.parquet"
            features = {}

            if qingxu_path.exists():
                qingxu_df = pd.read_parquet(qingxu_path)
                today_data = qingxu_df[qingxu_df['tradeDate'] == pd.Timestamp(self.trade_date)]
                if not today_data.empty:
                    features['rise_ratio'] = today_data.iloc[0]['rise_ratio']
                    features['limit_up_count'] = today_data.iloc[0]['limit_up_count']
                    features['limit_down_count'] = today_data.iloc[0]['limit_down_count']

            if limit_up_path.exists():
                limit_df = pd.read_parquet(limit_up_path)
                if not limit_df.empty and 'trade_date' in limit_df.columns:
                    today_limit = limit_df[limit_df['trade_date'].astype(str) == str(self.trade_date)]
                    if not today_limit.empty and 'continuous_boards' in today_limit.columns:
                        series = pd.to_numeric(today_limit['continuous_boards'], errors='coerce').dropna()
                        if not series.empty:
                            features['max_continuous_boards'] = float(series.max())
                            features['avg_continuous_boards'] = float(series.mean())

            if not features:
                self.log("⚠️ 无特征数据可更新")
                self.results['emotion_features'] = {'success': True, 'count': 0}
                return

            features['trade_date'] = self.trade_date
            emotion_path = self.data_dir / "emotion_features.parquet"
            if emotion_path.exists():
                existing = pd.read_parquet(emotion_path)
                existing = existing[existing['trade_date'] != self.trade_date]
                new_df = pd.concat([existing, pd.DataFrame([features])], ignore_index=True)
            else:
                new_df = pd.DataFrame([features])

            new_df.to_parquet(emotion_path, index=False)
            self.log(f"✅ 更新完成: {len(features)} 个特征")
            self.results['emotion_features'] = {'success': True, 'count': len(features)}
        except Exception as e:
            self.log(f"❌ 更新失败: {e}")
            self.results['emotion_features'] = {'success': False, 'error': str(e)}

    def run_all(self, skip=None):
        skip = skip or []
        self.log("\n" + "=" * 60)
        self.log("开始盘后数据自动更新")
        self.log(f"日期: {self.trade_date}")
        self.log("=" * 60)
        start_time = time.time()
        try:
            self.login()
            tasks = [
                ('qingxu', self.update_qingxu),
                ('zhishu', self.update_zhishu),
                ('kline_eod', self.update_kline_eod),
                ('limit_up', self.update_limit_up),
                ('longhubang', self.update_longhubang),
                ('emotion_features', self.update_emotion_features)
            ]
            for name, task_func in tasks:
                if name in skip:
                    self.log(f"\n⏭️ 跳过 {name}")
                    continue
                task_func()
                time.sleep(1)
        finally:
            self.logout()

        duration = time.time() - start_time
        self.generate_report(duration)
        return self.results

    def generate_report(self, duration):
        self.log("\n" + "=" * 60)
        self.log("更新完成报告")
        self.log("=" * 60)
        success_count = sum(1 for r in self.results.values() if r.get('success'))
        total_count = len(self.results)
        self.log(f"\n总耗时: {duration:.1f} 秒")
        self.log(f"成功: {success_count}/{total_count}")
        for name, result in self.results.items():
            status = "✅" if result.get('success') else "❌"
            count = result.get('count', 'N/A')
            extra = ''
            if 'coverage' in result:
                extra = f" (coverage={result['coverage']:.2%})"
            self.log(f"  {status} {name}: {count}{extra}")
        self.log("\n" + "=" * 60)


def main():
    parser = argparse.ArgumentParser(description='盘后数据全量更新')
    parser.add_argument('--date', type=str, help='指定日期 (YYYY-MM-DD)，默认今天')
    parser.add_argument('--skip', type=str, nargs='+', help='跳过的任务 (如: emotion_features)')
    parser.add_argument('--list', action='store_true', help='列出所有任务')
    args = parser.parse_args()

    if args.list:
        print("可用任务列表:")
        print("  1. qingxu          - 市场情绪数据")
        print("  2. zhishu          - 指数行情数据")
        print("  3. kline_eod       - 日K线数据（强制SDK）")
        print("  4. limit_up        - 涨停数据")
        print("  5. longhubang      - 龙虎榜数据")
        print("  6. emotion_features- 情绪特征数据")
        return

    updater = EODFullUpdater(date_str=args.date)
    updater.run_all(skip=args.skip)


if __name__ == "__main__":
    main()
