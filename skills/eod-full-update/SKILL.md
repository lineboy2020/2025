---
name: eod-full-update
description: 盘后数据全量更新技能。一键更新所有A股盘后数据，包括市场情绪、指数行情、日K线、涨停数据、龙虎榜、情绪特征等。
---

# 盘后数据全量更新技能 (EOD Full Update)

## 概述

本技能是当前生产环境的**主盘后更新入口**。实际定时任务调用 `scripts/run_eod_with_kline_guard.py`，由守护脚本负责停/启 K 线服务、执行更新、校验结果，再恢复服务。

本技能自动按顺序更新以下数据：

| 序号 | 数据类型 | 目标文件 | 说明 |
|------|---------|---------|------|
| 1 | 市场情绪 | `qingxu.parquet` | 涨跌家数、涨停跌停数 |
| 2 | 指数行情 | `zhishu.parquet` | 上证指数、深证成指、创业板指 |
| 3 | 日K线数据 | `kline_eod.duckdb` | 全市场股票日线数据 |
| 4 | 涨停数据 | `limit_up.parquet` + `limit_up.duckdb` | 先更新 parquet，再同步回 DuckDB |
| 5 | 龙虎榜数据 | `longhubang.parquet` | 龙虎榜成交明细 |
| 6 | 情绪特征 | `emotion_features.parquet` | 市场周期判断特征数据 |
| 7 | 资金流回写 | `kline_eod.duckdb.capital_flow` | 优先由 `archive/zijin` 分区数据回写 |

## 安装

1. 确保已配置同花顺账号（环境变量或 `.env` 文件）
2. 安装依赖：`pip install pandas duckdb pyarrow requests`
3. 确保数据目录存在：`data/db/`

## 使用方法

### 命令行

```bash
# 更新当天数据
cd /root/.openclaw/workspace/skills/eod-full-update
python3 scripts/run_eod_with_kline_guard.py

# 更新指定日期数据
python3 scripts/run_eod_with_kline_guard.py --date 2026-03-07

# 仅更新部分数据
python3 scripts/eod_full_update.py --skip emotion_features

# 显示帮助
python3 scripts/run_eod_with_kline_guard.py --help
```

### Python 调用

```python
from scripts.eod_full_update import EODFullUpdater

updater = EODFullUpdater()
updater.run_all()  # 更新当天
updater.run_all(date_str='2026-03-07')  # 更新指定日期
```

## 配置

配置优先级说明：
- 工作区根目录 `config.json`（最高优先，推荐统一维护）
- 技能目录 `config.json`
- `.env`
- 代码默认值

创建 `.env` 文件：

```bash
THS_SDK_USERNAME=your_username
THS_SDK_PASSWORD=your_password
THS_HTTP_ACCESS_TOKEN=your_token
```

或使用环境变量：

```bash
export THS_SDK_USERNAME=your_username
export THS_SDK_PASSWORD=your_password
export THS_HTTP_ACCESS_TOKEN=your_token
```

## 输出示例

```
[06:15:23] ============================================================
[06:15:23] 开始盘后数据自动更新
[06:15:23] 日期: 2026-03-13
[06:15:23] ============================================================
[06:15:25] ✅ 登录成功

[06:15:25] ============================================================
[06:15:25] [1/6] 更新 qingxu.parquet (市场情绪数据)
[06:15:25] ============================================================
[06:15:28] ✅ 更新完成: 256 条数据

[06:15:28] ============================================================
[06:15:28] [2/6] 更新 zhishu.parquet (指数数据)
[06:15:28] ============================================================
[06:15:30] ✅ 更新完成: 1024 条数据
...

[06:18:45] ============================================================
[06:18:45] 更新完成报告
[06:18:45] ============================================================
[06:18:45] 总耗时: 202.3 秒
[06:18:45] 成功: 6/6
  ✅ qingxu: 256
  ✅ zhishu: 1024
  ✅ kline_eod: 5132
  ✅ limit_up: 89
  ✅ longhubang: 156
  ✅ emotion_features: OK
```

## 依赖

- Python 3.8+
- pandas
- duckdb
- pyarrow
- requests
- iFinDPy (同花顺SDK，可选，HTTP模式可不安装)

## 定时任务

已配置自动定时任务，交易日收盘后自动运行：

| 任务名 | 时间 | 说明 |
|--------|------|------|
| eod-full-update-daily | 16:30 (周一到周五) | 自动执行盘后数据全量更新 |

**查看定时任务：**
```bash
openclaw cron list
```

**手动触发：**
```bash
openclaw cron run eod-full-update-daily
```

## 注意事项

1. 同花顺SDK同一时间只能登录一个账户
2. 建议盘后 15:30 后执行更新
3. 生产环境优先跑 `run_eod_with_kline_guard.py`，不要直接只跑 `eod_full_update.py`
4. 数据文件默认保存在 `data/db/` 目录
5. 大批量 `kline_eod` 日线更新默认强制走 SDK，不跟随 HTTP Token 自动切换
6. `limit_up` 先落地 `parquet`，再同步回 `limit_up.duckdb`，避免双轨不一致
7. `capital_flow` 优先从 `data/archive/zijin` 分区数据回写；问财直查仅作为降级路径
8. `emotion_features` 默认从 `limit_up.parquet` 读取涨停特征，避免 parquet/duckdb 源不一致
9. `kline_eod` 写库前会做覆盖率校验，避免下载不完整时误覆盖当天数据
