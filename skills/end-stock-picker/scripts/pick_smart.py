#!/usr/bin/env python3
"""
同花顺智能选股 + 技术面筛选整合版
使用同花顺智能选股API进行初步筛选，再进行技术面分析
"""
import argparse
import sys
import os
import json
from datetime import datetime, timedelta
from pathlib import Path

# 添加同花顺API路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'ths-smart-stock-picking' / 'scripts'))
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'ths-data-fetcher' / 'scripts'))

try:
    from ths_api import iFinDAPI
    THS_API_AVAILABLE = True
except ImportError:
    print("⚠️ 同花顺智能选股API不可用")
    THS_API_AVAILABLE = False

try:
    from unified_ths_downloader import UnifiedTHSDownloader
    THS_DATA_AVAILABLE = True
except ImportError:
    print("⚠️ 同花顺数据下载器不可用")
    THS_DATA_AVAILABLE = False

try:
    import pandas as pd
    import numpy as np
except ImportError:
    print("请先安装依赖: pip install pandas numpy")
    sys.exit(1)


class THSSmartStockPicker:
    """同花顺智能选股整合器"""
    
    def __init__(self, access_token, top=10):
        self.access_token = access_token
        self.top = top
        self.candidates = []
        self.today = datetime.now().strftime('%Y-%m-%d')
        
        # 初始化API客户端
        if THS_API_AVAILABLE:
            try:
                self.api = iFinDAPI(access_token=access_token)
                print("✅ 同花顺智能选股API初始化成功")
            except Exception as e:
                print(f"❌ API初始化失败: {e}")
                self.api = None
        else:
            self.api = None
        
        # 初始化数据下载器
        if THS_DATA_AVAILABLE:
            try:
                self.downloader = UnifiedTHSDownloader(use_http=True)
                print("✅ 同花顺数据下载器初始化成功")
            except Exception as e:
                print(f"❌ 数据下载器初始化失败: {e}")
                self.downloader = None
        else:
            self.downloader = None
    
    def smart_filter(self, condition):
        """使用智能选股API进行初步筛选"""
        if not self.api:
            print("❌ API不可用")
            return []
        
        print(f"\n🔍 智能选股条件: {condition}")
        result = self.api.smart_stock_picking(condition)
        
        if result.get('success'):
            stocks = result['stocks']
            print(f"✅ 初步筛选: {len(stocks)} 只股票")
            return stocks
        else:
            print(f"❌ 筛选失败: {result.get('errmsg', '未知错误')}")
            return []
    
    def get_stock_history(self, code):
        """获取个股历史数据"""
        if not self.downloader:
            return None
        
        try:
            end_date = datetime.now().strftime('%Y%m%d')
            start_date = (datetime.now() - timedelta(days=30)).strftime('%Y%m%d')
            
            results = self.downloader.download_history_data(
                stock_codes=[code],
                start_date=start_date,
                end_date=end_date,
                indicators='tradeDate,open,high,low,close,amount,volume'
            )
            
            if code in results and not results[code].empty:
                hist = results[code].copy()
                hist = hist.sort_values('tradeDate')
                
                # 计算技术指标
                hist['实体涨幅'] = (hist['close'] - hist['open']) / hist['open'] * 100
                hist['MA20'] = hist['close'].rolling(window=20).mean()
                hist['成交额_MA20'] = hist['amount'].rolling(window=20).mean()
                
                # 判断形态
                hist['形态'] = self._identify_pattern(hist)
                
                return hist
            
            return None
        except Exception as e:
            print(f"  获取历史数据失败 {code}: {e}")
            return None
    
    def _identify_pattern(self, hist_df):
        """识别K线形态"""
        patterns = []
        for i in range(len(hist_df)):
            if i < 1:
                patterns.append('未知')
                continue
            
            row = hist_df.iloc[i]
            
            # 大阳线
            if row['实体涨幅'] > 8:
                patterns.append('大阳线')
            # 十字星
            elif abs(row['实体涨幅']) < 1:
                patterns.append('十字星')
            # 阳线
            elif row['实体涨幅'] > 0:
                patterns.append('阳线')
            # 阴线
            else:
                patterns.append('阴线')
        
        return patterns
    
    def technical_analysis(self, code):
        """技术面分析"""
        hist = self.get_stock_history(code)
        if hist is None or len(hist) < 20:
            return None
        
        # 检查近10日是否有大阳线
        recent = hist.tail(10)
        big_yang = recent[recent['形态'] == '大阳线']
        
        if len(big_yang) == 0:
            return None
        
        # 取最近的大阳线
        latest_big_yang = big_yang.iloc[-1]
        big_yang_idx = hist[hist['tradeDate'] == latest_big_yang['tradeDate']].index[0]
        adjust_days = len(hist) - big_yang_idx - 1
        
        # 检查条件
        if adjust_days < 2:
            return None
        if latest_big_yang['amount'] < latest_big_yang['成交额_MA20'] * 2:
            return None
        if latest_big_yang['close'] <= latest_big_yang['MA20']:
            return None
        
        latest = hist.iloc[-1]
        if latest['close'] <= latest_big_yang['low']:
            return None
        if latest['amount'] > latest_big_yang['amount'] * 0.6:
            return None
        
        # 计算评分
        score = self._calculate_score(latest_big_yang, adjust_days, latest, hist)
        
        return {
            'code': code,
            'score': score,
            'pattern': latest['形态'],
            'adjust_days': adjust_days,
            'price': latest['close'],
            'volume_ratio': latest['amount'] / latest_big_yang['amount'],
            'big_yang_date': latest_big_yang['tradeDate'],
        }
    
    def _calculate_score(self, big_yang, adjust_days, latest, hist):
        """计算评分"""
        score = 0
        
        # 形态评分
        pattern_scores = {'十字星': 40, '阳线': 35, '阴线': 10}
        score += pattern_scores.get(latest['形态'], 10)
        
        # 调整天数
        if adjust_days >= 5: score += 20
        elif adjust_days >= 3: score += 15
        else: score += 10
        
        # 缩量程度
        vr = latest['amount'] / big_yang['amount']
        if vr < 0.3: score += 20
        elif vr < 0.4: score += 15
        elif vr < 0.5: score += 10
        else: score += 5
        
        return min(score, 100)
    
    def pick_stocks(self, smart_condition="涨幅大于5%"):
        """执行选股"""
        print("\n" + "=" * 60)
        print("🎯 同花顺智能选股 + 技术面筛选")
        print("=" * 60)
        
        # 第1步：智能选股初步筛选
        stock_codes = self.smart_filter(smart_condition)
        if not stock_codes:
            print("⚠️ 初步筛选无结果")
            return []
        
        # 限制分析数量（避免API调用过多）
        stock_codes = stock_codes[:50]
        
        # 第2步：技术面深度分析
        print(f"\n📊 技术面分析 {len(stock_codes)} 只股票...")
        candidates = []
        
        for i, code in enumerate(stock_codes):
            if (i + 1) % 10 == 0:
                print(f"  已分析 {i+1}/{len(stock_codes)}...")
            
            result = self.technical_analysis(code)
            if result:
                candidates.append(result)
                print(f"  ✅ {code}: {result['score']}分")
        
        # 排序并选取TOP
        candidates.sort(key=lambda x: x['score'], reverse=True)
        self.candidates = candidates[:self.top]
        
        print(f"\n✅ 选股完成，筛选出 {len(self.candidates)} 只优质股票")
        return self.candidates
    
    def format_report(self):
        """格式化报告"""
        lines = [
            f"🎯 同花顺智能选股报告 - {self.today}",
            "",
            "=" * 60,
            "",
            f"【选股结果】TOP {len(self.candidates)}",
            "",
        ]
        
        if not self.candidates:
            lines.append("⚠️ 未找到符合条件的股票")
        else:
            for i, stock in enumerate(self.candidates, 1):
                emoji = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
                lines.append(f"{emoji} [{stock['score']}分] {stock['code']}")
                lines.append(f"   价格: ¥{stock['price']:.2f}")
                lines.append(f"   形态: {stock['pattern']} | 调整: {stock['adjust_days']}天")
                lines.append(f"   大阳线: {stock['big_yang_date']} | 缩量: {stock['volume_ratio']:.1%}")
                lines.append("")
        
        lines.extend([
            "=" * 60,
            "",
            "【说明】",
            "• 数据来源: 同花顺iFinD API",
            "• 选股逻辑: 智能筛选 + 技术面分析",
            "• 风险提示: 仅供参考，不构成投资建议",
            "",
        ])
        
        return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="同花顺智能选股整合版")
    parser.add_argument("--condition", default="涨幅大于5%", help="智能选股条件")
    parser.add_argument("--top", type=int, default=10, help="显示前几名")
    parser.add_argument("--output", help="输出文件路径")
    
    args = parser.parse_args()
    
    # 从配置文件读取 Access Token
    config_path = Path(__file__).parent.parent.parent / 'ths-data-fetcher' / 'scripts' / 'config.json'
    ACCESS_TOKEN = None
    
    try:
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                ACCESS_TOKEN = config.get('data_skills', {}).get('ths_http', {}).get('access_token')
                if ACCESS_TOKEN:
                    print(f"✅ 已从配置文件读取 Token: {ACCESS_TOKEN[:20]}...")
    except Exception as e:
        print(f"⚠️ 读取配置文件失败: {e}")
    
    if not ACCESS_TOKEN:
        # 备用 token
        ACCESS_TOKEN = "72a6f6c407b2d433353cdbfa46c8571c152fa724.signs_Njc0Nzc1OTU4"
        print(f"⚠️ 使用备用 Token: {ACCESS_TOKEN[:20]}...")
    
    # 创建选股器
    picker = THSSmartStockPicker(access_token=ACCESS_TOKEN, top=args.top)
    
    # 执行选股
    picker.pick_stocks(smart_condition=args.condition)
    
    # 输出报告
    report = picker.format_report()
    print("\n" + report)
    
    # 保存报告
    if args.output:
        os.makedirs(os.path.dirname(args.output) if os.path.dirname(args.output) else '.', exist_ok=True)
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(report)
        print(f"\n💾 报告已保存: {args.output}")


if __name__ == "__main__":
    main()
