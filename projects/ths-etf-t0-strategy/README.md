# 同花顺 ETF T0 策略项目

基于 `ths-strategy-template` 派生的 ETF T0 第一版骨架项目。

## 项目目标
把附件 `etf_t0_02.py` 中有价值的核心交易思想，按模板结构重写为可维护版本：
- ETF 多标的候选/标的池
- DuckDB 历史数据
- THS HTTP 实时 / 高频 / snapshot
- 日线趋势 + 30m/5m 结构判断
- 日内超跌买入 / 反弹止盈
- 控制台 / Markdown 输出

## 当前版本定位
这是 **V0 骨架迁移版**，重点是：
- 保留核心交易思路
- 去掉 QMT / Redis / 实盘执行耦合
- 先跑通研究 / 监控骨架

## 文件结构
1. `README.md`
2. `config.json`
3. `data_gateway.py`
4. `strategy_logic.py`
5. `analyzer.py`
6. `runner_backtest.py`
7. `runner_live.py`
8. `notifier.py`

## 核心策略思想（当前版）
- 日线 MA20 判断大方向
- 30分钟趋势作过滤
- 5分钟结构作触发
- 超跌买入 / 反弹止盈
- 资金强弱仅作辅助，不直接耦合实盘模块

## 当前边界
- 暂不接 QMT 实盘执行
- 暂不接 Redis / Tick Writer / RAG
- 暂不完全复刻附件全部逻辑
- 当前先作为“模板化迁移版本”的第一步

## 运行方式
### 回测
```bash
python3 runner_backtest.py --date 2026-03-17
```

### 实时
```bash
python3 runner_live.py --date 2026-03-18
```
