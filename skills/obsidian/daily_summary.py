#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from datetime import datetime, timedelta
from pathlib import Path

WORKSPACE = Path('/root/.openclaw/workspace')
MEMORY_DIR = WORKSPACE / 'memory'
OUTPUT_DIR = WORKSPACE / 'obsidian' / '每日总结'

SECTION_MAP = {
    'tasks': '## 📋 今日完成的任务',
    'experience': '## 💡 成功经验与技巧',
    'data': '## 📊 重要数据更新',
    'todos': '## 📝 待办事项',
    'thoughts': '## 💭 思考与改进',
}

TASK_KEYWORDS = [
    '完成', '已完成', '新增', '升级', '重写', '接入', '修复', '确认', '发布', '验证', '补齐', '切到', '稳定工作',
]
EXPERIENCE_KEYWORDS = [
    '经验', '结论', '根因', '真正问题', '注意', '值得', '建议', '闭环', '定位到', '判断', '阶段结论',
]
DATA_KEYWORDS = [
    '接口', '字段', '端口', 'draftid', '草稿id', 'duckdb', 'parquet', 'api', 'llm_enabled', 'model=', 'success=true', '返回',
]
TODO_KEYWORDS = [
    '下一步', '计划', '需要', '待', '明天', '后续', '继续',
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='生成 Obsidian 每日总结')
    parser.add_argument('--date', help='日期，格式 YYYY-MM-DD，默认按本地时间的昨日生成')
    parser.add_argument('--force', action='store_true', help='覆盖已存在文件')
    parser.add_argument('--memory-file', help='指定输入 memory 文件路径')
    parser.add_argument('--summary-file', help='直接从现成摘要文本文件生成')
    parser.add_argument('--summary-text', help='直接传入摘要文本生成')
    parser.add_argument('--title-prefix', default='# 每日总结 - ', help='标题前缀')
    return parser.parse_args()


def default_target_date() -> str:
    return (datetime.utcnow() + timedelta(hours=8) - timedelta(days=1)).strftime('%Y-%m-%d')


def normalize_lines(text: str) -> list[str]:
    out = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        line = re.sub(r'^[-*]\s*', '', line)
        line = re.sub(r'^\d+[.)、]\s*', '', line)
        out.append(line)
    return out


def classify_line(line: str) -> str:
    lower = line.lower()
    if any(k in line for k in TODO_KEYWORDS):
        return 'todos'
    if any(k in line for k in EXPERIENCE_KEYWORDS):
        return 'experience'
    if any(k in lower for k in [k.lower() for k in DATA_KEYWORDS]):
        return 'data'
    if any(k in line for k in TASK_KEYWORDS):
        return 'tasks'
    return 'tasks'


def collect_sections(lines: list[str]) -> dict[str, list[str]]:
    sections = {k: [] for k in SECTION_MAP}
    for line in lines:
        bucket = classify_line(line)
        if line not in sections[bucket]:
            sections[bucket].append(line)

    if not sections['experience']:
        for line in lines:
            if '根因' in line or '结论' in line:
                sections['experience'].append(line)
    if not sections['data']:
        for line in lines:
            if any(token in line.lower() for token in ['api', 'duckdb', 'parquet', '字段', '端口', '模型']):
                sections['data'].append(line)
    if not sections['todos']:
        sections['todos'] = [
            '检查明日定时任务',
            '回顾今日关键变更是否已形成文档沉淀',
            '确认需要继续推进的下一步事项',
        ]
    if not sections['thoughts']:
        sections['thoughts'] = ['（手动填写）']
    return sections


def build_content(date_str: str, sections: dict[str, list[str]]) -> str:
    generated_time = (datetime.utcnow() + timedelta(hours=8)).strftime('%Y-%m-%d %H:%M')
    parts = [
        f'# 每日总结 - {date_str}',
        '',
        f'**生成时间**: {generated_time}',
        '',
        '---',
        '',
    ]
    for key in ['tasks', 'experience', 'data', 'todos', 'thoughts']:
        parts.append(SECTION_MAP[key])
        parts.append('')
        items = sections.get(key) or []
        if key == 'thoughts' and items == ['（手动填写）']:
            parts.append('（手动填写）')
        else:
            for idx, item in enumerate(items, start=1):
                if key == 'todos':
                    parts.append(f'- [ ] {item}')
                else:
                    parts.append(f'{idx}. {item}')
        parts.extend(['', '', '---', ''])
    parts.append(f'*自动生成于 {generated_time}*')
    parts.append('')
    return '\n'.join(parts)


def load_input_text(args: argparse.Namespace, date_str: str) -> str:
    if args.summary_text:
        return args.summary_text
    if args.summary_file:
        return Path(args.summary_file).read_text(encoding='utf-8')
    if args.memory_file:
        path = Path(args.memory_file)
    else:
        path = MEMORY_DIR / f'{date_str}.md'
    if not path.exists():
        raise FileNotFoundError(f'未找到输入文件: {path}')
    return path.read_text(encoding='utf-8')


def main() -> int:
    args = parse_args()
    date_str = args.date or default_target_date()
    output_path = OUTPUT_DIR / f'{date_str}.md'
    if output_path.exists() and not args.force:
        print(f'EXISTS {output_path}')
        return 0

    text = load_input_text(args, date_str)
    lines = normalize_lines(text)
    sections = collect_sections(lines)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path.write_text(build_content(date_str, sections), encoding='utf-8')
    print(f'WROTE {output_path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
