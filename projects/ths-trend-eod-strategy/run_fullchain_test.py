#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def run(cmd: list[str]) -> tuple[int, str, str]:
    p = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr


def main() -> int:
    parser = argparse.ArgumentParser(description='全链路测试：实时候选生成 + 输出验证')
    parser.add_argument('--date', default=datetime.now().strftime('%Y-%m-%d'))
    parser.add_argument('--history-mode', action='store_true', help='使用历史模式近似回放')
    args = parser.parse_args()

    json_out = ROOT / f'tail_candidates_{args.date}.json'
    md_out = ROOT / f'tail_candidates_{args.date}.md'
    cmd = ['python3', 'runner_live.py', '--date', args.date, '--json-out', str(json_out)]
    if args.history_mode:
        cmd.append('--history-mode')

    code, stdout, stderr = run(cmd)

    result = {
        'status': 'ok' if code == 0 else 'error',
        'trade_date': args.date,
        'history_mode': args.history_mode,
        'command': cmd,
        'returncode': code,
        'json_exists': json_out.exists(),
        'md_exists': md_out.exists(),
        'stdout_preview': stdout[:4000],
        'stderr_preview': stderr[:4000],
    }

    test_path = ROOT / f'fullchain_test_{args.date}.json'
    test_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if code == 0 else code


if __name__ == '__main__':
    raise SystemExit(main())
