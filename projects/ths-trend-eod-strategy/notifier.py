#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from typing import Dict, List


def print_console(lines: List[str]) -> None:
    for line in lines:
        print(line)


def write_markdown(path: str, title: str, lines: List[str]) -> None:
    content = ['# ' + title, ''] + lines
    Path(path).write_text('\n'.join(content), encoding='utf-8')


def build_summary_lines(results: List[Dict]) -> List[str]:
    out = []
    for r in results:
        out.append(f"- {r['symbol']} {r['name']} | 状态={r['strategy_state']} | 收益={r.get('current_return_pct')}% | 动作={r['suggested_action']}")
    return out


def qq_payload_placeholder() -> Dict:
    return {'enabled': True, 'mode': 'placeholder'}


def dingtalk_payload_placeholder() -> Dict:
    return {'enabled': True, 'mode': 'placeholder'}
