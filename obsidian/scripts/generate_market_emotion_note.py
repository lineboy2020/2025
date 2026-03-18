#!/usr/bin/env python3
"""自动生成当日市场情绪 Obsidian 跟踪文档"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from urllib.request import urlopen

WORKSPACE = Path('/root/.openclaw/workspace')
OUTPUT_DIR = WORKSPACE / 'obsidian' / '每日总结'
DEFAULT_API = 'http://127.0.0.1:9000/api/chart/qingxu?limit=240'


def fetch_latest(api_url: str) -> dict:
    with urlopen(api_url) as resp:
        data = json.loads(resp.read().decode('utf-8'))
    items = data.get('items') or []
    if not items:
        raise RuntimeError('qingxu 接口未返回 items')
    return items[-1]


def pct(v) -> str:
    try:
        return f"{float(v) * 100:.2f}%"
    except Exception:
        return '-'


def num(v) -> str:
    try:
        return f"{int(float(v))}"
    except Exception:
        return '-'


def build_content(d: dict) -> str:
    trade_date = d.get('date', datetime.utcnow().strftime('%Y-%m-%d'))
    return f"""# {trade_date} 市场情绪跟踪

## 一、核心结论
- 情绪评分：{d.get('emotion_score', '-')}
- 红绿灯：{d.get('traffic_light', '-')}
- 周期标签：{d.get('phase_tag', '-')}
- 一句话结论：{d.get('phase_note', '待补充')}

## 二、核心数据
- 上涨家数：{num(d.get('rise_count'))}
- 下跌家数：{num(d.get('fall_count'))}
- 涨停家数：{num(d.get('limit_up_count'))}
- 跌停家数：{num(d.get('limit_down_count'))}
- 样本总数：{num(d.get('total_count'))}
- 上涨占比：{pct(d.get('rise_ratio'))}
- 下跌占比：{pct(d.get('fall_ratio'))}
- 炸板数：{num(d.get('explosion_count'))}
- 炸板率：{pct(d.get('explosion_rate'))}

## 三、结构观察
- 市场广度观察：待补充
- 主线题材观察：待补充
- 高位股/连板股观察：待补充
- 情绪与指数共振情况：待补充

## 四、阶段判断
- 当前更像：{d.get('phase_tag', '-')}
- 判断依据：{d.get('phase_note', '待补充')}
- 与前一交易日相比：待补充

## 五、交易含义
- 今日策略适配：待补充
- 次日预期：待补充
- 风险提示：待补充

## 六、项目/技术备注
- 数据来源：`/api/chart/qingxu`
- 页面：`/static/qingxu.html`
- 若今日有规则调整、页面改版、接口改动，请同步补充到项目日志与成功经验。
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--api', default=DEFAULT_API, help='qingxu API 地址')
    parser.add_argument('--date', default=None, help='覆盖输出日期，默认取接口 latest date')
    parser.add_argument('--force', action='store_true', help='存在同名文件时覆盖')
    args = parser.parse_args()

    latest = fetch_latest(args.api)
    trade_date = args.date or latest.get('date') or datetime.utcnow().strftime('%Y-%m-%d')
    out = OUTPUT_DIR / f'{trade_date}-市场情绪跟踪.md'
    if out.exists() and not args.force:
        print(f'EXISTS {out}')
        return 0

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out.write_text(build_content({**latest, 'date': trade_date}), encoding='utf-8')
    print(f'WROTE {out}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
