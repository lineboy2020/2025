#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
一键运行策略管线：
1. 生成实战候选
2. 生成盘中监控报告（可选）
3. 生成次日跟踪报告（若次日数据可用）

目标：先把“能一键跑通”落地。
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from datetime import datetime

ROOT = Path('/root/.openclaw/workspace')
SKILL = ROOT / 'skills/trend_eod_screener'
REPORT = SKILL / 'reports'
SCRIPTS = SKILL / 'scripts'


def run(cmd):
    p = subprocess.run(cmd, text=True, capture_output=True)
    return {
        'cmd': cmd,
        'returncode': p.returncode,
        'stdout': p.stdout,
        'stderr': p.stderr,
    }


def main():
    parser = argparse.ArgumentParser(description='一键运行策略管线')
    parser.add_argument('--date', type=str, default='')
    parser.add_argument('--with-intraday', action='store_true')
    parser.add_argument('--use-prev-candidates', action='store_true', help='盘中监控优先读取上一交易日候选池')
    parser.add_argument('--with-followup', action='store_true')
    parser.add_argument('--with-digest', action='store_true')
    parser.add_argument('--changes-only', action='store_true')
    parser.add_argument('--state-cache', type=str, default=str(REPORT / 'intraday_alert_state.json'))
    parser.add_argument('--json-out', type=str, default=str(REPORT / 'pipeline_run.json'))
    args = parser.parse_args()

    trade_date = args.date or datetime.utcnow().strftime('%Y-%m-%d')
    live_json = REPORT / f'live_candidates_{trade_date}.json'
    live_md = REPORT / f'live_candidates_{trade_date}.md'
    intraday_json = REPORT / f'intraday_monitor_{trade_date}.json'
    intraday_md = REPORT / f'intraday_monitor_{trade_date}.md'
    followup_json = REPORT / f'live_followup_{trade_date}.json'
    followup_md = REPORT / f'live_followup_{trade_date}.md'
    digest_md = REPORT / f'intraday_digest_{trade_date}.md'

    result = {
        'status': 'ok',
        'trade_date': trade_date,
        'steps': []
    }

    result['steps'].append(run([
        'python3', str(SCRIPTS / 'generate_live_candidates.py'),
        '--date', trade_date,
        '--json-out', str(live_json),
        '--md-out', str(live_md),
    ]))

    if args.with_intraday:
        cmd = [
            'python3', str(SCRIPTS / 'monitor_intraday_signals.py'),
            '--json-out', str(intraday_json),
            '--md-out', str(intraday_md),
            '--current-date', trade_date,
        ]
        if not args.use_prev_candidates:
            cmd.extend(['--input', str(live_json)])
        result['steps'].append(run(cmd))

    if args.with_followup:
        result['steps'].append(run([
            'python3', str(SCRIPTS / 'track_nextday_live.py'),
            '--input', str(live_json),
            '--json-out', str(followup_json),
            '--md-out', str(followup_md),
        ]))

    if args.with_digest and args.with_intraday:
        cmd = [
            'python3', str(SCRIPTS / 'render_alert_digest.py'),
            '--input', str(intraday_json),
            '--md-out', str(digest_md),
            '--state-cache', str(args.state_cache),
        ]
        if args.changes_only:
            cmd.append('--changes-only')
        result['steps'].append(run(cmd))

    Path(args.json_out).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
