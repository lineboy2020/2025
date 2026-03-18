#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
WORKSPACE = ROOT.parent.parent
KLINE_DIR = WORKSPACE / 'kline-viewer'
KLINE_CMD = ['python3', '-m', 'uvicorn', 'scripts.kline_server:app', '--host', '0.0.0.0', '--port', '9000']
EOD_SCRIPT = ROOT / 'scripts' / 'eod_full_update.py'
DB_PATH = WORKSPACE / 'data' / 'db' / 'kline_eod.duckdb'
LOG_DIR = ROOT / 'logs'
LOG_DIR.mkdir(parents=True, exist_ok=True)
PID_FILE = KLINE_DIR / 'kline_server.pid'


def log(msg: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def find_kline_pids() -> list[int]:
    out = subprocess.run(['ps', '-eo', 'pid,args'], capture_output=True, text=True, check=True)
    pids = []
    for line in out.stdout.splitlines():
        if 'python3 -m uvicorn scripts.kline_server:app' in line and 'grep' not in line:
            parts = line.strip().split(None, 1)
            if parts:
                pids.append(int(parts[0]))
    return pids


def stop_kline(timeout: int = 30) -> dict:
    pids = find_kline_pids()
    if not pids:
        return {'status': 'already_stopped', 'pids': []}
    log(f'停止 K 线服务: {pids}')
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    deadline = time.time() + timeout
    while time.time() < deadline:
        remain = find_kline_pids()
        if not remain:
            return {'status': 'stopped', 'pids': pids}
        time.sleep(1)
    remain = find_kline_pids()
    for pid in remain:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    time.sleep(1)
    return {'status': 'killed', 'pids': pids}


def port_open(host='127.0.0.1', port=9000, timeout=1.0) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        return sock.connect_ex((host, port)) == 0


def start_kline(timeout: int = 30) -> dict:
    if find_kline_pids() or port_open():
        return {'status': 'already_running'}
    log('启动 K 线服务...')
    log_file = open(LOG_DIR / 'kline_server.log', 'a', encoding='utf-8')
    proc = subprocess.Popen(
        KLINE_CMD,
        cwd=str(KLINE_DIR),
        stdout=log_file,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    PID_FILE.write_text(str(proc.pid), encoding='utf-8')
    deadline = time.time() + timeout
    while time.time() < deadline:
        if port_open():
            return {'status': 'started', 'pid': proc.pid}
        if proc.poll() is not None:
            return {'status': 'failed', 'returncode': proc.returncode}
        time.sleep(1)
    return {'status': 'timeout', 'pid': proc.pid}


def run_eod(date_str: str | None = None) -> dict:
    cmd = ['python3', str(EOD_SCRIPT)]
    if date_str:
        cmd += ['--date', date_str]
    log(f'执行 EOD 更新: {" ".join(cmd)}')
    proc = subprocess.run(cmd, cwd=str(ROOT), text=True)
    return {'status': 'ok' if proc.returncode == 0 else 'failed', 'returncode': proc.returncode}


def validate_db(date_str: str | None = None) -> dict:
    if not DB_PATH.exists():
        return {'status': 'failed', 'reason': 'db_missing'}
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        max_trade_date = con.execute('SELECT MAX(trade_date) FROM market_daily').fetchone()[0]
        row_count = con.execute('SELECT COUNT(*) FROM market_daily').fetchone()[0]
    finally:
        con.close()
    max_trade_date_str = str(max_trade_date) if max_trade_date is not None else None
    ok = bool(row_count and max_trade_date_str)
    if date_str:
        ok = ok and (max_trade_date_str >= date_str)
    return {
        'status': 'ok' if ok else 'failed',
        'max_trade_date': max_trade_date_str,
        'row_count': row_count,
    }


def main():
    parser = argparse.ArgumentParser(description='Guarded EOD update with kline service stop/start')
    parser.add_argument('--date', default=None)
    parser.add_argument('--no-restart-on-fail', action='store_true')
    args = parser.parse_args()

    summary = {'date': args.date, 'steps': {}}
    summary['steps']['stop_kline'] = stop_kline()
    summary['steps']['run_eod'] = run_eod(args.date)
    summary['steps']['validate_db'] = validate_db(args.date)

    should_restart = summary['steps']['run_eod']['status'] == 'ok' and summary['steps']['validate_db']['status'] == 'ok'
    if should_restart:
        summary['steps']['start_kline'] = start_kline()
    elif not args.no_restart_on_fail:
        summary['steps']['start_kline'] = start_kline()
        summary['steps']['warning'] = 'EOD failed or validation failed; kline restarted for service continuity'
    else:
        summary['steps']['start_kline'] = {'status': 'skipped'}

    out_path = LOG_DIR / f"run_eod_with_kline_guard_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    ok = summary['steps']['run_eod']['status'] == 'ok' and summary['steps']['validate_db']['status'] == 'ok'
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
