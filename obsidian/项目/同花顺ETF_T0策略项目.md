# 同花顺ETF T0策略项目

## 项目目标
基于 `ths-strategy-template` 生成 ETF T0 策略项目第一版骨架，吸收附件 `etf_t0_02.py` 的核心交易思想，但不直接继承其重耦合工程实现。

## 当前项目路径
- `/root/.openclaw/workspace/projects/ths-etf-t0-strategy`

## 当前版本结论（V0）
已完成第一版骨架迁移：
- 独立项目目录
- ETF T0 专用配置
- ETF T0 策略逻辑第一版
- DuckDB 历史数据 + THS HTTP 实时/高频接入
- 回测 / 实时入口验证通过

## 当前保留的核心思想
- 日线 MA20 趋势过滤
- 日内超跌买入 / 反弹止盈
- 资金强弱辅助判断
- ETF 多标的池方式运行

## 当前明确不纳入 V0 的部分
- QMT 实盘执行
- Redis 广播
- Tick Writer
- RAG / MemoryStore
- 原脚本中的大一体化主控结构

## 下一步可做
- 引入 30m / 5m 结构化重采样
- 引入 ChanAnalysis 精简版
- 引入分层仓位逻辑
- 引入真实通知出口
- 引入回测结果落库
