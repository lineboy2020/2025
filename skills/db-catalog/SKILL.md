---
name: db-catalog
description: 扫描和体检本地数据库目录（尤其是 data/db 下的 DuckDB 与 Parquet 文件），生成数据库清单、表结构总览、字段说明、最新更新时间、空值率、重复记录、日期范围与异常检查报告。用于用户要求“检查数据库”“生成数据库清单”“查看各表更新情况”“做数据库体检报告”“快速查询 data/db 数据情况”等场景。
---

# db-catalog

在需要查看本地数据库资产、确认各库各表最新情况、或生成数据库体检报告时，优先使用此技能。

## 默认工作流

1. 扫描 `data/db` 目录下的 `.duckdb`、`.parquet`、子目录产物。
2. 运行脚本生成 Markdown 报告。
3. 向用户汇总：
   - 有哪些库/文件
   - 每个库有哪些表
   - 行数、字段、用途判断
   - 最新日期/更新时间
   - 高空值字段
   - 业务键重复情况
   - 明显断更或异常点
4. 如果用户要深入，继续按单表做专项检查。

## 运行方式

优先直接执行：

```bash
python3 skills/db-catalog/scripts/db_catalog.py
```

如需指定目录或输出路径：

```bash
python3 skills/db-catalog/scripts/db_catalog.py \
  --db-dir /root/.openclaw/workspace/data/db \
  --output /root/.openclaw/workspace/reports/database_health_report.md
```

## 输出物

默认输出：

- `reports/database_health_report.md`
- `reports/database_health_report.json`

## 解释规范

对用户回复时，优先给出：

- 核心库（最大、最常用、最新）
- 已断更或滞后的表
- 空值率高的关键字段
- 是否存在 `(symbol, trade_date)` 或 `(stock_code, trade_date)` 级别重复
- 是否值得补采或重建索引/口径

不要把“同一天有很多行”误判为异常；明细表天然会按证券逐行展开。应优先看业务键重复。

## 深入检查建议

用户若继续追问，可进一步做：

- 单表字段口径解释
- 最近 N 个交易日覆盖检查
- 多库日期对齐检查
- 新旧备份差异对比
- 输出为 Obsidian 笔记或日报
