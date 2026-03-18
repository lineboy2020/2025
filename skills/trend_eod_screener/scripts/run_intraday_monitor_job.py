#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""稳定版盘中跟踪任务入口：显式选择最近一份非空候选池并执行监控。"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/.openclaw/workspace')
SCRIPT = ROOT / 'skills/trend_eod_screener/scripts/monitor_intraday_signals.py'
REPORT_DIR = ROOT / 'skills/trend_eod_screener/reports'


def candidate_count_of(path: Path) -> int:
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
        return int(payload.get('candidate_count') or len(payload.get('candidates') or []))
    except Exception:
        return -1


def resolve_latest_nonempty_candidates() -> Path:
    files = sorted(REPORT_DIR.glob('live_candidates_*.json'))
    dated = []
    for f in files:
        stem = f.stem.replace('live_candidates_', '')
        try:
            d = datetime.strptime(stem, '%Y-%m-%d').date()
            dated.append((d, f))
        except Exception:
            continue
    dated.sort(key=lambda x: x[0], reverse=True)
    for _, f in dated:
        if candidate_count_of(f) > 0:
            return f
    fallback = REPORT_DIR / 'live_candidates.json'
    return fallback


def main() -> int:
    candidate_file = resolve_latest_nonempty_candidates()
    current_date = datetime.utcnow().strftime('%Y-%m-%d')
    json_out = REPORT_DIR / 'intraday_monitor.json'
    md_out = REPORT_DIR / 'intraday_monitor.md'

    cmd = [
        sys.executable,
        str(SCRIPT),
        '--input', str(candidate_file),
        '--current-date', current_date,
        '--json-out', str(json_out),
        '--md-out', str(md_out),
    ]
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
    print(json.dumps({
        'status': 'ok' if proc.returncode == 0 else 'error',
        'candidate_file': str(candidate_file),
        'candidate_count': candidate_count_of(candidate_file) if candidate_file.exists() else None,
        'current_date': current_date,
        'json_out': str(json_out),
        'md_out': str(md_out),
        'returncode': proc.returncode,
        'stdout_tail': proc.stdout[-2000:],
        'stderr_tail': proc.stderr[-2000:],
    }, ensure_ascii=False, indent=2))
    return proc.returncode


if __name__ == '__main__':
    raise SystemExit(main())
