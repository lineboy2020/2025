---
name: "每日A股数据更新-daily-update"
description: "执行 OpenClaw 每日盘后数据更新。用户要求更新指数/情绪/DuckDB/涨停/龙虎榜时调用。"
---

# OpenClaw 每日数据更新技能

## 概述

该技能提供盘后数据更新所需的底层脚本与数据处理组件。当前生产环境的主调度入口已切换到 `skills/eod-full-update`；本技能主要作为底层实现层，被 `eod-full-update` 复用。
- 指数行情：`data/db/zhishu.parquet`
- 市场情绪：`data/db/qingxu.parquet`
- DuckDB 日线库底层更新脚本：`data/db/kline_eod.duckdb`
- 涨停数据库底层更新脚本：`data/db/limit_up.duckdb`
- 龙虎榜数据库底层更新脚本：`data/db/longhubang.parquet`

## 目录结构

```text
daily-update/
├── SKILL.md
├── moban.md
├── config.json
├── .env.example
├── requirements.txt
└── scripts/
    ├── daily_update.py
    ├── get_index.py
    ├── get_longhubang.py
    ├── get_zhangting.py
    ├── qingxu.py
    ├── update_duckdb_daily.py
    ├── unified_ths_downloader.py
    └── unified_ths_zijin.py
```

## 当前定位

- **主生产入口**：`skills/eod-full-update/scripts/run_eod_with_kline_guard.py`
- **本技能定位**：底层脚本层 / 数据处理组件
- **适用场景**：单独调试某个更新子步骤、回补某类数据、排查底层链路

## 使用方法

```bash
cd d:/akshare/trading-ai
python /root/.openclaw/workspace/skills/daily-update/scripts/daily_update.py
python /root/.openclaw/workspace/skills/daily-update/scripts/update_duckdb_daily.py --eod --from-ths
python /root/.openclaw/workspace/skills/daily-update/scripts/get_longhubang.py --date 2026-03-06
```

## 配置说明

1. 复制 `.trae/skills/daily-update/.env.example` 到项目根目录 `.env`。
2. 根据实际环境填充同花顺账号、密码和 HTTP Token。
3. 如需独立配置，可在 `.trae/skills/daily-update/config.json` 中维护技能专用参数。
4. `daily_update.use_ths_direct=true` 表示 DuckDB 盘后库优先走同花顺直连增量。

## 依赖

- pandas
- duckdb
- pyarrow
- requests
- iFinDPy

## 说明

- 若用户只是要求“执行每日盘后更新”或“跑生产更新”，优先使用 `eod-full-update`。
- 若需要单独排查 `capital_flow`、`limit_up`、`longhubang` 等底层子链路，再使用本技能。
- `capital_flow` 当前优先从 `data/archive/zijin` 分区数据回写 DuckDB；问财直查仅作为降级路径。

## 触发场景

- 用户要求每日盘后自动更新数据
- 用户要求修复/重建 OpenClaw 更新链路
- 用户要求重新同步指数、情绪、DuckDB、涨停库、龙虎榜
