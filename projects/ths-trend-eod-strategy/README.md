# 同花顺趋势尾盘策略项目

基于 `ths-strategy-template` 派生的 **趋势尾盘实战策略项目**。

## 项目定位
这不是盘后研究版，而是：
- **今天尾盘实时筛买入候选**
- **最迟 14:50 买入参考**
- **明天按规则卖出**

## 当前版本目标
当前默认版本已固化为 **V1 平衡版**：
- 实时尾盘候选筛选入口
- 历史回测入口
- DuckDB + THS HTTP 数据入口
- 风险标签 / 买入计划 / 次日卖出规则
- `market-emotion` 市场环境分层

## 当前默认 V1（平衡版）
- 基础参数：
  - `max_candidates = 2`
  - `min_turnover_amount = 5e8`
  - `max_intraday_gain_pct = 7.0`
  - `tail_strength_threshold = 0.5`
- 市场环境：
  - 发酵期 / 高潮期 → 做 2 只
  - 启动期 → 做 2 只
  - 冰点期 / 退潮期 → 不做

## 文件结构
1. `README.md`
2. `config.json`
3. `data_gateway.py`
4. `strategy_logic.py`
5. `analyzer.py`
6. `runner_backtest.py`
7. `runner_live.py`
8. `notifier.py`

## 核心原则
- 盘中默认禁用 SDK，统一使用 THS HTTP
- 历史主仓使用 DuckDB
- 实盘语义与研究语义分离
- 今天尾盘筛选，不再错误依赖当天 EOD 研究底表

## 当前边界
- V0 先做骨架与语义矫正
- 暂不接真实下单
- 暂不接 Redis / RAG / Tick 存储
- 暂不复刻旧 `trend_eod_screener` 的全部研究模块
