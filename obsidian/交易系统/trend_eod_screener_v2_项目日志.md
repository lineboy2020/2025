# trend_eod_screener v2 项目日志

## 说明
该文档用于记录本项目每天的推进情况。

---

## 2026-03-17
### 今日完成
- 确认升级目标与约束
- 阅读并分析现有 `trend_eod_screener` 代码结构
- 检查本地 A 股数据库结构：
  - `kline_eod.duckdb`
  - `limit_up.duckdb`
- 梳理 `market-emotion` 与 `main-force-intent` 现状
- 新增研究配置：`config.v2.json`
- 新增回测脚本：`scripts/backtest_nextday_strategy.py`
- 更新 README，补充研究版说明
- 跑通第一版 6 个月回测

### 今日结果
- overall 样本 147
- 次日收盘赚钱率 53.06%
- 次日触达 +3% 25.85%
- `leader` 模式优于 `trend` 模式

### 关键判断
- 当前结果无法支撑高胜率高收益承诺
- 研究方向正确，但过滤条件仍然偏宽
- 下一步应该缩样本、强过滤、补情绪与主力意图联动

### 当前问题 / 阻塞
- `market-emotion` 历史输出覆盖不足，回测里多数样本落为“未知”
- `main-force-intent` 还未深度嵌入，只用了代理评分
- 仓库未配置 git user.name / user.email，暂时无法 commit

### 当日追加更新（阶段收束 + 实战落地）
- 已确认第三轮 Top3 leader 为当前最优 baseline
- 已新增实战输出器：`scripts/generate_live_candidates.py`
- 实战输出器用途：
  - 输出当日 Top3 候选股
  - 输出买入窗口、参考价、3/5/8 分批计划、7% 止损价
  - 输出风险标签
- README 已同步更新
- 项目正式进入“研究版 → 实战辅助输出”阶段

### 当日追加更新（Bug 修复完成）
- 已定位并修复实战输出器的关键 bug：错误复用回测 `next_day_exists` 过滤条件
- 该 bug 会导致最新交易日因为不存在次日数据而被误筛为 0 票
- 已在 `build_candidates()` 中拆分回测/实战模式
- 已为实战输出器增加 `signal_mode` 标识：
  - `leader_priority`
  - `trend_fallback`
  - `generic_fallback`
- 2026-03-16 修复后已恢复正常出票

### 当日追加更新（次日跟踪器补齐）
- 已新增 `scripts/track_nextday_live.py`
- 可读取 `live_candidates.json` 并在次日评估：
  - +3 / +5 / +8 是否触发
  - -7 是否触发
  - 次日收盘收益
  - 模拟交易计划收益
- 至此，策略已具备“出票 → 次日跟踪 → 汇总评估”的基础闭环能力

### 当日追加更新（盘中监控器原型）
- 已新增 `scripts/monitor_intraday_signals.py`
- 目标：接入 THS realtime / snapshot 数据，补齐盘中预警层
- 当前原型能力：
  - 读取 live candidates
  - 获取实时价 / 快照摘要
  - 判断 +3 / +5 / +8 / -7
  - 估计资金状态 strengthening / neutral / weakening
  - 输出盘中建议动作
- 当前仍属原型版，后续还需根据实际返回字段做进一步字段适配和稳定性增强
- 已定位一处接线问题：`monitor_intraday_signals.py` 初版未把 `skills/ths-data-fetcher/scripts` 加入 `sys.path`，导致 `unified_ths_downloader` 导入失败；现已修复并进入重测

### 当日追加更新（统一状态机 v1 开始）
- 已开始统一 `generate_live_candidates.py` / `monitor_intraday_signals.py` / `track_nextday_live.py` 的输出字段
- 当前新增统一字段：`strategy_state`
- 候选层已支持：
  - `leader_priority_ready`
  - `trend_fallback_ready`
  - `generic_fallback_ready`
- 盘中层已支持：
  - `intraday_monitoring`
  - `capital_strengthening`
  - `capital_weakening`
  - `tp3_triggered`
  - `tp5_triggered`
  - `tp8_triggered`
  - `stoploss_triggered`
- 次日层已支持：
  - `pending_next_day_data`
  - `closed_by_eod`
  - `tp3_triggered`
  - `tp5_triggered`
  - `tp8_triggered`
  - `stoploss_triggered`
- 这一步的目标是先把三层输出收口到统一状态定义，再继续精修盘中判定与自动化调度

### 当日追加更新（盘中监控器精修 + 一键入口）
- 已增强盘中监控器：
  - 增加价格触发容差，减少边界误判
  - 增加 `buy_sell_imbalance` 粗略资金失衡指标
  - 增加 `alert_level`（low / medium / high / critical）
  - 建议动作细化为更接近实盘助手语义
- 已新增一键运行入口：`scripts/run_strategy_pipeline.py`
- 当前可一键串行运行：
  - 候选生成
  - 盘中监控
  - 次日跟踪
- 下一步将继续做字段适配、报告格式优化、再考虑自动化调度

### 当日追加更新（盘中稳定性增强）
- 已统一次日待跟踪状态：`nextday_pending` → `pending_next_day_data`
- 已把盘中资金状态判定收口为 `classify_capital_state()`
- 已新增 `summary_text`，为后续 QQ 预警摘要做准备
- 已增强盘中 Markdown 报告可读性
- 当前优先级明确：先把盘中层做稳，再进入调度自动化

### 当日追加更新（资金判断增强 + 摘要层）
- 已显式使用 `dealDirection`（5=买入，1=卖出，15=中性）增强盘中资金判断
- `classify_capital_state()` 已支持：
  - `strong_strengthening`
  - `strengthening`
  - `neutral`
  - `weakening`
  - `strong_weakening`
- 已新增盘中预警摘要脚本：`scripts/render_alert_digest.py`
- 当前摘要层可直接复用 `summary_text` 生成简洁预警内容，为后续 QQ 推送做准备
- 已核实：THS snapshot 的 `dealDirection` 字段名适配无误，但本次 2026-03-16 样本原始返回值全空
- 这不是策略代码误读，而是数据源该字段当次无有效值；系统已补充 `direction_source=unavailable` 标识，避免资金方向误判
- 已新增 THS_HF 方向替代方案：`buyVolume / sellVolume`
- 当前盘中资金判断优先级已调整为：
  1. HF `buyVolume / sellVolume`
  2. snapshot `dealDirection`
  3. snapshot amount 尾段/首段降级规则
- 已把 `render_alert_digest.py` 升级为支持巡检状态缓存与 `--changes-only` 模式
- 已把一键入口补到 `--with-digest --changes-only`，为“可巡检预警版”收口
- 已开始修复每日更新链路中的两个基础问题：
  1. `zhishu.parquet` 写入后自动同步到主 `data/db`
  2. `qingxu` 若未产出新数据，不再被 `daily_update.py` 记为成功

### 当日追加更新（daily-update 最终验收）
- 已完成 `daily-update` 本轮问题闭环修复与实测验收
- 已修复 THS 配置链问题：根 `config.json` 自动补全 `ths_sdk / ths_http`，SDK 登录恢复正常
- 已修复 `zhishu.parquet` 路径错位：写入后自动同步到主 `data/db/zhishu.parquet`
- 已修复 `qingxu` 假成功问题，并改为按当天定向更新；`2026-03-17` 情绪数据已成功写入 `data/db/qingxu.parquet`
- 已定位并解除 `kline_eod.duckdb` 文件锁冲突（占锁进程：`python3 scripts/main.py`）
- 已修复 `capital_flow` 动态列名映射：问财列 `主力资金流向[20260317]` 现在可正确写入 `main_net_inflow`
- 已完成 `capital_flow` 当日补刷：`2026-03-17` 共 `1487` 行，`main_net_inflow` 非空 `1487` 行
- 已修复 `limit_up` 归一化中 `trade_date` 被错误对齐为 `NaN` 的问题
- 已完成 `limit_up.duckdb` 当日补刷：`2026-03-17` 共写入 `52` 条，最新日期已更新至 `2026-03-17`
- 结论：`daily-update` 主链路已恢复可用，当前这轮已通过最终验收

### 当日追加更新（2026-03-19：实测联通 + 涨幅口径修复）
- 已将 `projects/ths-trend-eod-strategy` 作为独立实测项目落地，补齐 `ths_http access_token` 与 `ths_sdk` 配置后，盘中 HTTP 实时链路已打通。
- 已新增一键全链路测试入口：
  - `run_fullchain_test.py`
  - `run_afternoon_live.sh`
- 2026-03-19 实测已成功生成：
  - `tail_candidates_2026-03-19.json`
  - `tail_candidates_2026-03-19.md`
  - `fullchain_test_2026-03-19.json`
- 盘中实测确认：候选会随实时行情变化，说明不是静态缓存结果，而是实时接入驱动。
- 同时定位并修复一个关键 BUG：
  - 原先 `intraday_gain_pct` 误按 `当前价 / 开盘价 - 1` 计算
  - 导致涨停/大涨股被低估为 4%~6%，错误进入候选池
  - 现已改为优先使用 `changeRatio`，其次用 `preClose` 计算真实日内涨幅
- 修复后已立即重跑，候选池发生明显变化，说明筛选逻辑已回归更可信状态。
- 结论：当前策略已从“能跑通”升级到“实时实测有效”，但自动调度与长期稳定性仍需后续补强。

### 下一步
- 深度接入情绪文件与规则
- 将主力意图真实分析结果接入回测
- 增强题材/板块强度评分
- 对比 Top3 / Top5 / Top10 的结果差异
- 输出第二版回测摘要
- 后续再补下午固定时点自动调度与结果推送收口

### 当日追加更新（第二轮增强开始）
- 发现 `market-emotion` 历史输出文件仅有 2 天，不足以支撑 6 个月回测
- 已决定在研究版中加入“情绪规则兜底”，避免样本大量落到 `未知`
- 已开始把 3 日 / 5 日主力净流入累积加入评分体系
- 已开始强化连板、封单、题材热度的生态评分
