#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description='趋势尾盘历史回测入口')
    parser.add_argument('--date', required=True)
    args = parser.parse_args()
    print(json.dumps({
        'date': args.date,
        'status': 'todo',
        'message': 'V0阶段先完成尾盘实时筛选骨架，历史回测下一步接入。'
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
