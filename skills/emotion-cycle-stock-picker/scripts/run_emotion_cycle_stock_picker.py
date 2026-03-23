#!/usr/bin/env python3
import argparse
import csv
import json
import subprocess
from datetime import datetime
from pathlib import Path

WORKSPACE = Path('/root/.openclaw/workspace')
REPORT_DIR = WORKSPACE / 'reports' / 'emotion-cycle-stock-picker'
REPORT_DIR.mkdir(parents=True, exist_ok=True)


def run_json(cmd):
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    text = res.stdout.strip()
    start = text.rfind('\n{')
    if start != -1:
        text = text[start+1:]
    return json.loads(text)


def pick_strategy(emotion_name: str):
    mapping = {
        '冰点期': {
            'strategy': '低位首板+超跌反弹+新题材试错',
            'searches': [
                '流通市值小于80亿，跌幅大于3%，成交额大于2亿',
                '近5日跌幅大于10%，今日涨幅大于0%，流通市值小于100亿',
                '非ST，流通市值小于80亿，换手率大于3%，成交额大于2亿'
            ]
        },
        '启动期': {
            'strategy': '1进2+低位转强+放量突破',
            'searches': [
                '非ST，涨幅大于2%，换手率大于5%，成交额大于3亿',
                '近3日涨幅大于5%，流通市值小于150亿，成交额大于3亿'
            ]
        },
        '发酵期': {
            'strategy': '主线扩散+龙头跟随+趋势加速',
            'searches': [
                '近5日涨幅大于8%，成交额大于5亿，换手率大于5%',
                '非ST，涨幅大于3%，流通市值小于200亿，成交额大于5亿'
            ]
        },
        '高潮期': {
            'strategy': '最强核心去弱留强',
            'searches': [
                '涨停，成交额大于5亿',
                '近3日涨幅大于15%，成交额大于8亿'
            ]
        },
        '退潮期': {
            'strategy': '防守观察+低位独立逻辑',
            'searches': [
                '非ST，流通市值小于80亿，涨幅大于0%，成交额大于2亿',
                '近5日跌幅大于8%，今日涨幅大于0%，换手率大于3%'
            ]
        },
    }
    return mapping.get(emotion_name, mapping['冰点期'])


def mock_candidate_pool(searches, size=50):
    pool = []
    for i in range(size):
        pool.append({
            'symbol': f'MOCK{i+1:04d}.SZ',
            'name': f'候选股{i+1}',
            'search_source': searches[i % len(searches)],
            'emotion_strategy': 'auto',
            'intent_score': round(100 - i * 0.8, 2),
            'confidence': '中' if i > 10 else '高',
            'advice': '观察/试错' if i > 10 else '优先关注',
            'rank': i + 1,
        })
    return pool


def save_csv(path: Path, rows):
    if not rows:
        return
    with path.open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--date', type=str, default=None)
    parser.add_argument('--skip-intent', action='store_true')
    args = parser.parse_args()

    emotion_cmd = ['python3', str(WORKSPACE / 'skills/market-emotion/scripts/main.py')]
    if args.date:
        emotion_cmd += ['--date', args.date, '--json']
    else:
        emotion_cmd += ['--today', '--json']
    emotion = run_json(emotion_cmd)

    subprocess.run(['python3', str(WORKSPACE / 'skills/db-catalog/scripts/db_catalog.py')], check=True)

    emotion_name = emotion.get('emotion_name', '未知')
    strat = pick_strategy(emotion_name)
    candidate_pool = mock_candidate_pool(strat['searches'], size=50)
    top10 = candidate_pool[:10]

    trade_date = emotion.get('date') or datetime.now().strftime('%Y-%m-%d')
    snapshot_path = REPORT_DIR / f'emotion_snapshot_{trade_date}.json'
    pool_path = REPORT_DIR / f'candidate_pool_50_{trade_date}.csv'
    top10_path = REPORT_DIR / f'final_top10_{trade_date}.csv'
    report_path = REPORT_DIR / f'selection_report_{trade_date}.md'

    snapshot_path.write_text(json.dumps(emotion, ensure_ascii=False, indent=2), encoding='utf-8')
    save_csv(pool_path, candidate_pool)
    save_csv(top10_path, top10)

    report = f'''# 情绪周期选股报告\n\n- 日期: {trade_date}\n- 情绪周期: {emotion_name}\n- 置信度: {emotion.get('confidence')}\n- 操作建议: {emotion.get('advice', {}).get('操作策略', '')}\n- 本次选股策略: {strat['strategy']}\n\n## 初筛条件\n'''
    for s in strat['searches']:
        report += f'- {s}\n'
    report += f'''\n## 产出\n- 50只候选池: `{pool_path}`\n- 最终10只: `{top10_path}`\n- 情绪快照: `{snapshot_path}`\n'''
    report_path.write_text(report, encoding='utf-8')

    print(json.dumps({
        'date': trade_date,
        'emotion_name': emotion_name,
        'strategy': strat['strategy'],
        'candidate_pool_size': len(candidate_pool),
        'final_top10_size': len(top10),
        'snapshot_path': str(snapshot_path),
        'candidate_pool_path': str(pool_path),
        'top10_path': str(top10_path),
        'report_path': str(report_path),
        'note': '当前版本已打通技能骨架与结果落盘；ths-smart-stock-picking 与 main-force-intent 的真实接口调用待下一轮接入。'
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
