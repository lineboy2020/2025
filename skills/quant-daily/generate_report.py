#!/usr/bin/env python3
"""
generate_report.py - 整合生成每日量化简报
"""

import json
import os
from datetime import datetime
from pathlib import Path
from urllib.request import urlopen
from fetch_news import NewsFetcher
from fetch_calendar import CalendarFetcher
from fetch_market import MarketFetcher


class ReportGenerator:
    def __init__(self):
        self.today = datetime.now()
        self.date_str = self.today.strftime('%Y年%m月%d日')
        self.weekday = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'][self.today.weekday()]
        self.workspace = Path('/root/.openclaw/workspace')

    def generate(self, output_format='text'):
        """生成完整报告"""
        print(f"正在生成 {self.date_str} 财经简报...")

        news_fetcher = NewsFetcher()
        calendar_fetcher = CalendarFetcher()
        market_fetcher = MarketFetcher()

        news_data = news_fetcher.get_all_news()
        calendar_data = calendar_fetcher.get_all_calendar()
        market_data = market_fetcher.get_all_market_data()
        project_progress = self._load_project_progress()
        emotion_data = self._load_market_emotion()
        today_focus = self._build_today_focus(emotion_data)

        if output_format == 'text':
            report = self._generate_text_report(news_data, calendar_data, market_data, emotion_data, project_progress, today_focus)
        else:
            report = self._generate_json_report(news_data, calendar_data, market_data, emotion_data, project_progress, today_focus)

        return report

    def _read_text(self, path: Path) -> str:
        if not path.exists():
            return ''
        return path.read_text(encoding='utf-8')

    def _extract_bullet_lines(self, text: str, limit: int = 8):
        lines = []
        for line in text.splitlines():
            s = line.strip()
            if s.startswith('- '):
                lines.append(s[2:])
            if len(lines) >= limit:
                break
        return lines

    def _load_project_progress(self):
        candidates = [
            self.workspace / 'memory' / '2026-03-18.md',
            self.workspace / 'obsidian' / '交易系统' / '市场情绪监控项目日志.md',
        ]
        merged = []
        for p in candidates:
            merged.extend(self._extract_bullet_lines(self._read_text(p), limit=12))
        # 去重保序
        out = []
        seen = set()
        for item in merged:
            if item not in seen:
                seen.add(item)
                out.append(item)
        return out[:8]

    def _load_market_emotion(self):
        api = 'http://127.0.0.1:9000/api/chart/qingxu?limit=240'
        try:
            with urlopen(api, timeout=10) as resp:
                data = json.loads(resp.read().decode('utf-8'))
            items = data.get('items') or []
            return items[-1] if items else {}
        except Exception:
            return {}

    def _build_today_focus(self, emotion):
        phase = emotion.get('phase_tag', '-')
        score = emotion.get('emotion_score', '-')
        focus = {
            '市场情绪模块': [
                '为自动生成脚本补“近5日情绪摘要”',
                '评估是否将评分阈值和权重配置化',
                '继续沉淀 phase_tag 的判定经验，逐步从启发式走向更稳的经验规则',
            ],
            '量化数据与更新链路': [
                '观察 eod-full-update 今日实跑稳定性',
                '确认 qingxu / limit_up / longhubang / market_daily 的盘后更新一致性',
                '继续监控同花顺 SDK 与 HTTP 路径的冲突风险，优先保证盘中链路可用',
            ],
            '策略侧': [
                '观察 trend_eod_screener 今日是否能产出前置候选',
                '跟踪 t0-strategy 在补足历史样本后的实时表现',
                f'结合市场情绪处于“{phase}”阶段（评分 {score}），优先关注主线前排与强辨识度标的',
            ]
        }
        return focus

    def _generate_text_report(self, news, calendar, market, emotion, project_progress, today_focus):
        lines = []

        lines.append('=' * 50)
        lines.append(f'📊 量化日报 | {self.date_str} {self.weekday}')
        lines.append('=' * 50)
        lines.append('')

        if emotion:
            lines.append('🧭 【昨日市场情绪回顾】')
            lines.append('-' * 30)
            lines.append(f"- 情绪评分：{emotion.get('emotion_score', '-')}")
            lines.append(f"- 红绿灯：{emotion.get('traffic_light', '-')}")
            lines.append(f"- 周期标签：{emotion.get('phase_tag', '-')}")
            lines.append(f"- 一句话结论：{emotion.get('phase_note', '-')}")
            lines.append('')
            lines.append('核心数据：')
            lines.append(f"- 上涨家数：{emotion.get('rise_count', '-')}")
            lines.append(f"- 下跌家数：{emotion.get('fall_count', '-')}")
            lines.append(f"- 涨停家数：{emotion.get('limit_up_count', '-')}")
            lines.append(f"- 跌停家数：{emotion.get('limit_down_count', '-')}")
            lines.append(f"- 样本总数：{emotion.get('total_count', '-')}")
            rr = emotion.get('rise_ratio')
            fr = emotion.get('fall_ratio')
            er = emotion.get('explosion_rate')
            lines.append(f"- 上涨占比：{float(rr) * 100:.2f}%" if rr is not None else '- 上涨占比：-')
            lines.append(f"- 下跌占比：{float(fr) * 100:.2f}%" if fr is not None else '- 下跌占比：-')
            lines.append(f"- 炸板数：{emotion.get('explosion_count', '-')}")
            lines.append(f"- 炸板率：{float(er) * 100:.2f}%" if er is not None else '- 炸板率：-')
            lines.append('')

        lines.append('🚀 【昨日项目进度】')
        lines.append('-' * 30)
        if project_progress:
            for idx, item in enumerate(project_progress, 1):
                lines.append(f'{idx}. {item}')
        else:
            lines.append('暂无项目进度记录')
        lines.append('')

        lines.append('🎯 【今日工作重点】')
        lines.append('-' * 30)
        for group, items in today_focus.items():
            lines.append(f'【{group}】')
            for item in items:
                lines.append(f'- {item}')
            lines.append('')

        lines.append('🔥 【市场概况】')
        lines.append('-' * 30)
        overview = market.get('overview', {})
        if overview:
            for name, data in overview.items():
                emoji = '🟢' if '+' in data.get('change', '') else '🔴'
                lines.append(f"{emoji} {name}: {data.get('index', '-')} ({data.get('change', '-')})")
                lines.append(f"   成交额: {data.get('volume', '-')}")
        else:
            lines.append('市场数据获取失败')
        lines.append('')

        lines.append('💰 【资金流向】')
        lines.append('-' * 30)
        fund_flow = market.get('fund_flow', {})
        for name, data in fund_flow.items():
            emoji = '🟢' if data.get('trend') == 'in' or '+' in str(data.get('value', '')) else '🔴'
            lines.append(f"{emoji} {name}: {data.get('value', '-')}")
        lines.append('')

        lines.append('📈 【热点板块】')
        lines.append('-' * 30)
        sectors = market.get('sectors', [])
        for i, sector in enumerate(sectors[:8], 1):
            emoji = '📈' if sector.get('trend') == 'up' else '📉'
            lines.append(f"{i}. {emoji} {sector.get('name', '-')} {sector.get('change', '-')}")
        lines.append('')

        lines.append('🚀 【概念热点】')
        lines.append('-' * 30)
        concepts = market.get('concepts', [])
        for i, concept in enumerate(concepts[:6], 1):
            emoji = '🔥' if '+' in str(concept.get('change', '')) else '❄️'
            lines.append(f"{i}. {emoji} {concept.get('name', '-')} {concept.get('change', '-')}")
        lines.append('')

        lines.append('🔍 【板块扫描】')
        lines.append('-' * 30)
        focus = market.get('focus_sectors', {})
        for sector_name, data in focus.items():
            status_emoji = '🟢' if data.get('status') == '强势' else '🟡' if data.get('status') == '活跃' else '🔴'
            lines.append(f"{status_emoji} {sector_name} | {data.get('status', '-')}")
            if data.get('leaders'):
                lines.append(f"   龙头: {', '.join(data['leaders'])}")
            if data.get('news'):
                lines.append(f"   💡 {data['news']}")
            lines.append('')

        lines.append('📰 【国内财经要闻】')
        lines.append('-' * 30)
        domestic_news = news.get('domestic', [])
        for i, item in enumerate(domestic_news[:10], 1):
            lines.append(f"{i}. {item.get('title', '')}")
            if item.get('brief'):
                brief = item['brief'][:60] + '...' if len(item['brief']) > 60 else item['brief']
                lines.append(f"   💬 {brief}")
        lines.append('')

        lines.append('🌍 【国际财经动态】')
        lines.append('-' * 30)
        intl_news = news.get('international', [])
        for i, item in enumerate(intl_news[:6], 1):
            lines.append(f"{i}. {item.get('title', '')}")
        lines.append('')

        lines.append('📅 【财经日历】未来30天')
        lines.append('-' * 30)
        high_events = calendar.get('high_importance', [])
        by_type = {}
        for event in high_events[:15]:
            etype = event.get('type', '其他')
            by_type.setdefault(etype, []).append(event)

        for etype, events in by_type.items():
            lines.append(f'▸ {etype}:')
            for evt in events[:4]:
                date_str = evt['date'][5:] if len(evt['date']) > 5 else evt['date']
                lines.append(f"   • {date_str} {evt.get('event', '')}")
            lines.append('')

        lines.append('⭐ 【市场亮点】')
        lines.append('-' * 30)
        top_stocks = market.get('top_stocks', {})
        zt_list = top_stocks.get('涨幅榜', [])
        if zt_list:
            lines.append('🔥 涨幅榜:')
            for stock in zt_list[:5]:
                lines.append(f"   {stock.get('name', '-')}({stock.get('code', '-')}) {stock.get('change', '-')}")
        lines.append('')

        lines.append('⚠️ 【风险提示】')
        lines.append('-' * 30)
        lines.append('• 以上内容仅供参考，不构成投资建议')
        lines.append('• 股市有风险，投资需谨慎')
        lines.append('• 数据更新时间: ' + market.get('update_time', '-'))
        lines.append('')

        lines.append('=' * 50)
        lines.append('💡 发送时间: ' + datetime.now().strftime('%Y-%m-%d %H:%M'))
        lines.append('📱 由 quant-daily 自动生成')
        lines.append('=' * 50)

        return '\n'.join(lines)

    def _generate_json_report(self, news, calendar, market, emotion, project_progress, today_focus):
        return {
            'date': self.date_str,
            'weekday': self.weekday,
            'market_emotion': emotion,
            'project_progress': project_progress,
            'today_focus': today_focus,
            'market': market,
            'news': news,
            'calendar': calendar,
            'generated_at': datetime.now().isoformat()
        }

    def save_report(self, report, output_dir='reports'):
        os.makedirs(output_dir, exist_ok=True)
        filename = self.today.strftime('%Y%m%d_report')

        text_path = os.path.join(output_dir, f'{filename}.md')
        with open(text_path, 'w', encoding='utf-8') as f:
            f.write(report if isinstance(report, str) else json.dumps(report, ensure_ascii=False, indent=2))
        print(f'报告已保存: {text_path}')

        if isinstance(report, str):
            json_report = self.generate(output_format='json')
        else:
            json_report = report

        json_path = os.path.join(output_dir, f'{filename}.json')
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(json_report, ensure_ascii=False, indent=2, fp=f)
        print(f'JSON数据已保存: {json_path}')

        return text_path, json_path


def main():
    import argparse

    parser = argparse.ArgumentParser(description='生成每日量化简报')
    parser.add_argument('--format', choices=['text', 'json'], default='text', help='输出格式')
    parser.add_argument('--output', '-o', default='reports', help='输出目录')
    parser.add_argument('--save', '-s', action='store_true', help='保存到文件')

    args = parser.parse_args()

    generator = ReportGenerator()
    report = generator.generate(output_format=args.format)

    if args.save:
        generator.save_report(report, args.output)

    if isinstance(report, str):
        print(report)
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))

    return report


if __name__ == '__main__':
    main()
