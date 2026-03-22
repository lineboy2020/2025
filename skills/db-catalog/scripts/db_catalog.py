#!/usr/bin/env python3
from __future__ import annotations
import argparse
import json
from pathlib import Path
from datetime import date, datetime
import duckdb
import pyarrow.parquet as pq


def fmt(v):
    return 'NULL' if v is None else str(v)


def parse_dt(v):
    if v is None or v == 'NULL':
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v)[:10]
    try:
        return datetime.strptime(s, '%Y-%m-%d').date()
    except Exception:
        return None


def stale_days(max_value):
    d = parse_dt(max_value)
    if not d:
        return None
    return (date.today() - d).days


def detect_usage(col_names):
    s = set(col_names)
    if {'open', 'high', 'low', 'close'} <= s and 'trade_date' in s:
        return '日线/行情数据'
    if 'main_net_inflow' in s:
        return '资金流数据'
    if 'is_limit_up' in s or 'consecutive_boards' in s:
        return '涨停/连板数据'
    if 'concepts' in s and 'is_st' in s:
        return '股票基础信息与概念标签'
    if 'reason' in s and 'net_amount' in s:
        return '龙虎榜/席位数据'
    return '通用数据表'


def inspect_duckdb(db_path: Path):
    result = {'file': db_path.name, 'type': 'duckdb', 'tables': []}
    con = duckdb.connect(str(db_path), read_only=True)
    tables = [r[0] for r in con.execute('SHOW TABLES').fetchall()]
    for t in tables:
        table = {'name': t}
        row_count = con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
        cols = con.execute(f'DESCRIBE SELECT * FROM "{t}"').fetchall()
        col_names = [c[0] for c in cols]
        col_types = {c[0]: c[1] for c in cols}
        table['row_count'] = row_count
        table['column_count'] = len(cols)
        table['usage'] = detect_usage(col_names)
        table['columns'] = []
        for name in col_names:
            nulls = con.execute(f'SELECT SUM(CASE WHEN "{name}" IS NULL THEN 1 ELSE 0 END) FROM "{t}"').fetchone()[0] or 0
            rate = (nulls / row_count * 100) if row_count else 0
            table['columns'].append({
                'name': name,
                'type': col_types[name],
                'null_rate': round(rate, 4),
                'high_null': rate >= 80,
            })
        table['date_checks'] = []
        table['latest_date'] = None
        for dc in [c for c in col_names if 'date' in c.lower() or 'time' in c.lower()][:6]:
            try:
                mn, mx = con.execute(f'SELECT MIN("{dc}"), MAX("{dc}") FROM "{t}"').fetchone()
                table['date_checks'].append({'column': dc, 'min': fmt(mn), 'max': fmt(mx)})
                if table['latest_date'] is None and mx is not None:
                    table['latest_date'] = fmt(mx)
            except Exception as e:
                table['date_checks'].append({'column': dc, 'error': str(e)})
        table['duplicate_checks'] = []
        for a, b in [('symbol', 'trade_date'), ('stock_code', 'trade_date'), ('symbol', 'date'), ('code', 'trade_date')]:
            if a in col_names and b in col_names:
                dup = con.execute(f'''SELECT COUNT(*) FROM (
                    SELECT "{a}", "{b}", COUNT(*) c FROM "{t}" GROUP BY 1,2 HAVING COUNT(*)>1
                ) x''').fetchone()[0]
                table['duplicate_checks'].append({'key': [a, b], 'duplicate_groups': dup})
        result['tables'].append(table)
    con.close()
    return result


def inspect_parquet(pq_path: Path):
    pf = pq.ParquetFile(pq_path)
    schema = pf.schema_arrow
    rows = pf.metadata.num_rows
    cols = schema.names
    con = duckdb.connect()
    qpath = str(pq_path).replace("'", "''")
    item = {
        'file': pq_path.name,
        'type': 'parquet',
        'row_count': rows,
        'column_count': len(cols),
        'usage': detect_usage(cols),
        'columns': [],
        'date_checks': [],
        'latest_date': None
    }
    for n in cols:
        nulls = con.execute(f"SELECT SUM(CASE WHEN \"{n}\" IS NULL THEN 1 ELSE 0 END) FROM read_parquet('{qpath}')").fetchone()[0] or 0
        rate = (nulls / rows * 100) if rows else 0
        item['columns'].append({'name': n, 'type': str(schema.field(n).type), 'null_rate': round(rate, 4), 'high_null': rate >= 80})
    for dc in [c for c in cols if 'date' in c.lower() or 'time' in c.lower()][:6]:
        try:
            mn, mx = con.execute(f"SELECT MIN(\"{dc}\"), MAX(\"{dc}\") FROM read_parquet('{qpath}')").fetchone()
            item['date_checks'].append({'column': dc, 'min': fmt(mn), 'max': fmt(mx)})
            if item['latest_date'] is None and mx is not None:
                item['latest_date'] = fmt(mx)
        except Exception as e:
            item['date_checks'].append({'column': dc, 'error': str(e)})
    con.close()
    return item


def render_markdown(report):
    lines = []
    lines.append('# data/db 数据库清单与体检报告')
    lines.append('')
    lines.append(f"- 扫描目录: `{report['db_dir']}`")
    lines.append('')
    lines.append('## 总览摘要')
    lines.append('')
    lines.append('| 对象 | 类型 | 用途 | 最新日期 | 距今(天) | 状态 |')
    lines.append('|---|---|---|---|---:|---|')
    for item in report['items']:
        if item['type'] == 'duckdb':
            for t in item['tables']:
                latest = t.get('latest_date')
                gap = stale_days(latest)
                status = '正常'
                if gap is None:
                    status = '无日期字段'
                elif gap >= report['stale_threshold_days']:
                    status = '⚠️ 疑似断更'
                lines.append(f"| {item['file']}.{t['name']} | duckdb-table | {t['usage']} | {latest or '-'} | {gap if gap is not None else '-'} | {status} |")
        else:
            latest = item.get('latest_date')
            gap = stale_days(latest)
            status = '正常'
            if gap is None:
                status = '无日期字段'
            elif gap >= report['stale_threshold_days']:
                status = '⚠️ 疑似断更'
            lines.append(f"| {item['file']} | parquet | {item['usage']} | {latest or '-'} | {gap if gap is not None else '-'} | {status} |")
    lines.append('')

    lines.append('## 异常摘要')
    lines.append('')
    found_issue = False
    for item in report['items']:
        if item['type'] == 'duckdb':
            for t in item['tables']:
                latest = t.get('latest_date')
                gap = stale_days(latest)
                if gap is not None and gap >= report['stale_threshold_days']:
                    found_issue = True
                    lines.append(f"- ⚠️ `{item['file']}.{t['name']}` 最新日期 `{latest}`，距今 `{gap}` 天，疑似断更")
                high_null = [c for c in t['columns'] if c['high_null']]
                if high_null:
                    found_issue = True
                    cols = ', '.join([f"{c['name']}({c['null_rate']:.1f}%)" for c in high_null[:8]])
                    lines.append(f"- ⚠️ `{item['file']}.{t['name']}` 高空值字段: {cols}")
                for d in t.get('duplicate_checks', []):
                    if d['duplicate_groups'] > 0:
                        found_issue = True
                        lines.append(f"- ⚠️ `{item['file']}.{t['name']}` 业务键 `{' + '.join(d['key'])}` 存在重复组 `{d['duplicate_groups']}`")
        else:
            latest = item.get('latest_date')
            gap = stale_days(latest)
            if gap is not None and gap >= report['stale_threshold_days']:
                found_issue = True
                lines.append(f"- ⚠️ `{item['file']}` 最新日期 `{latest}`，距今 `{gap}` 天，疑似断更")
            high_null = [c for c in item['columns'] if c['high_null']]
            if high_null:
                found_issue = True
                cols = ', '.join([f"{c['name']}({c['null_rate']:.1f}%)" for c in high_null[:8]])
                lines.append(f"- ⚠️ `{item['file']}` 高空值字段: {cols}")
    if not found_issue:
        lines.append('- 未发现明显断更、高空值或业务键重复异常')
    lines.append('')
    lines.append('## 文件清单')
    lines.append('')
    lines.append('| 文件 | 类型 | 行数/表数 |')
    lines.append('|---|---|---:|')
    for item in report['items']:
        metric = len(item['tables']) if item['type'] == 'duckdb' else item['row_count']
        lines.append(f"| {item['file']} | {item['type']} | {metric} |")
    lines.append('')
    for item in report['items']:
        if item['type'] == 'duckdb':
            lines.append(f"## DuckDB: `{item['file']}`")
            lines.append('')
            for t in item['tables']:
                lines.append(f"### 表: `{t['name']}`")
                lines.append(f"- 行数: **{t['row_count']}**")
                lines.append(f"- 字段数: **{t['column_count']}**")
                lines.append(f"- 用途: **{t['usage']}**")
                lines.append('')
                lines.append('| 字段 | 类型 | 空值率 |')
                lines.append('|---|---|---:|')
                for c in t['columns']:
                    flag = ' ⚠️' if c['high_null'] else ''
                    lines.append(f"| {c['name']} | {c['type']} | {c['null_rate']:.2f}%{flag} |")
                lines.append('')
                if t['date_checks']:
                    lines.append('日期检查：')
                    for d in t['date_checks']:
                        if 'error' in d:
                            lines.append(f"- {d['column']}: {d['error']}")
                        else:
                            lines.append(f"- {d['column']}: {d['min']} ~ {d['max']}")
                    lines.append('')
                if t['duplicate_checks']:
                    lines.append('重复检查：')
                    for d in t['duplicate_checks']:
                        lines.append(f"- {'+'.join(d['key'])}: 重复组数 {d['duplicate_groups']}")
                    lines.append('')
        else:
            lines.append(f"## Parquet: `{item['file']}`")
            lines.append(f"- 行数: **{item['row_count']}**")
            lines.append(f"- 字段数: **{item['column_count']}**")
            lines.append(f"- 用途: **{item['usage']}**")
            lines.append('')
            lines.append('| 字段 | 类型 | 空值率 |')
            lines.append('|---|---|---:|')
            for c in item['columns']:
                flag = ' ⚠️' if c['high_null'] else ''
                lines.append(f"| {c['name']} | {c['type']} | {c['null_rate']:.2f}%{flag} |")
            lines.append('')
            if item['date_checks']:
                lines.append('日期检查：')
                for d in item['date_checks']:
                    if 'error' in d:
                        lines.append(f"- {d['column']}: {d['error']}")
                    else:
                        lines.append(f"- {d['column']}: {d['min']} ~ {d['max']}")
                lines.append('')
    return '\n'.join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--db-dir', default='/root/.openclaw/workspace/data/db')
    ap.add_argument('--output', default='/root/.openclaw/workspace/reports/database_health_report.md')
    args = ap.parse_args()

    db_dir = Path(args.db_dir)
    out_md = Path(args.output)
    out_json = out_md.with_suffix('.json')
    out_md.parent.mkdir(parents=True, exist_ok=True)

    items = []
    for p in sorted(db_dir.iterdir()):
        if p.suffix == '.duckdb':
            items.append(inspect_duckdb(p))
        elif p.suffix == '.parquet':
            items.append(inspect_parquet(p))

    report = {'db_dir': str(db_dir), 'items': items, 'stale_threshold_days': 3}
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    out_md.write_text(render_markdown(report), encoding='utf-8')
    print(str(out_md))
    print(str(out_json))


if __name__ == '__main__':
    main()
