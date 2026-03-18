# 同花顺策略模板项目

一个少而精的量化策略开发模板，面向：
- 同花顺数据接口
- 历史回测 / 盘中实时 / 预警 / 复盘
- 文件数量控制在 8 个以内

## 设计原则
- DuckDB 作为主仓；少量策略私有数据允许使用 Parquet
- 盘中默认禁止 SDK，优先 HTTP 接口
- 策略逻辑与数据接口分离
- 回测与实盘尽量共用同一套策略逻辑
- 预警输出统一从 notifier 出口发出

## 文件结构
1. `README.md` — 项目说明
2. `config.json` — 唯一配置入口
3. `data_gateway.py` — 历史/实时数据统一入口
4. `strategy_logic.py` — 策略逻辑与示例策略
5. `analyzer.py` — 轻量统计分析与参数评估
6. `runner_backtest.py` — 历史回测入口
7. `runner_live.py` — 盘中实时计算与预警入口
8. `notifier.py` — 控制台 / Markdown / QQ / 钉钉统一通知出口

## 数据源约定
### 历史数据
- 主仓：DuckDB
- 来源：本地库优先，缺失时盘后回补
- 少量私有中间数据：允许策略内 Parquet

### 实时数据
- 默认：同花顺 HTTP
- 禁止：盘中默认使用 SDK（避免单点登录互踢）

## 运行顺序
### 1. 回测
```bash
python3 runner_backtest.py --date 2026-03-17
```

### 2. 盘中
```bash
python3 runner_live.py --date 2026-03-18
```

## 当前示例策略
- 示例名：`demo_breakout_watch`
- 类型：尾盘候选 + 次日盘中跟踪
- 输出：观察 / 部分止盈 / 止损 / 持有

## 后续扩展建议
- 网格调参扩展到多目标排序
- 环境切片（情绪周期 / 板块 / 市值）
- 策略日志统一落 DuckDB
- 多策略共享 data_gateway
