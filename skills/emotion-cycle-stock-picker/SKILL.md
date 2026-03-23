---
name: emotion-cycle-stock-picker
description: 基于A股市场情绪周期自动选择选股策略、构建股票池、用主力意图模型排序并产出次日实盘候选标的。用于用户要求“根据情绪周期选股”“按情绪周期生成明日股票池”“生成明天实盘交易标的”“把市场情绪、同花顺智能选股、主力意图排序串成一条链路”时使用。
---

# emotion-cycle-stock-picker

按下面流程执行情绪驱动选股：

1. 先获取当日市场情绪周期
   - 优先运行：`python3 /root/.openclaw/workspace/skills/market-emotion/scripts/main.py --today --json`
   - 如果用户指定日期，用 `--date YYYY-MM-DD --json`

2. 再检查本地数据库新鲜度
   - 运行：`python3 /root/.openclaw/workspace/skills/db-catalog/scripts/db_catalog.py`
   - 重点确认：
     - `kline_eod.duckdb.market_daily`
     - `kline_eod.duckdb.capital_flow`
     - `limit_up.duckdb.limit_up`
   - 若关键表断更，要在结果里明确提示风险。

3. 根据情绪周期选择选股策略
   - 冰点期：偏防守，低位首板/超跌反弹/新题材试错，小市值优先，避免高位老龙头
   - 启动期：偏进攻，1进2、低位转强、板块新龙
   - 发酵期：做主线扩散，龙头跟随、中位换手板、趋势加速
   - 高潮期：只保留最强核心，防止过度扩散，强调去弱留强
   - 退潮期：大幅收缩候选池，偏防守，只允许低位独立逻辑或空仓观察

4. 构建初筛股票池（目标 50 只）
   - 数据源组合：
     - 同花顺智能选股技能（主）
     - 本地 DuckDB / Parquet 数据（辅）
     - limit_up / capital_flow / market_daily 交叉过滤
   - 尽量把条件写成可解释的自然语言筛选语句，并记录到结果中。
   - 如果单一条件不足 50 只，可分批查询后合并去重。
   - 如果明显超过 50 只，优先按本地数据做二次过滤（成交额、涨跌幅、资金流、连板状态、流通市值等）。

5. 用主力意图模型排序
   - 候选池 50 只确定后，调用主力意图分析脚本逐只评分
   - 产出排序表，至少包含：
     - symbol
     - name
     - emotion_strategy
     - intent_score
     - confidence
     - advice
     - rank

6. 最终压缩到 10 只次日实盘标的
   - 优先保留：
     - 策略匹配度高
     - 主力意图评分高
     - 资金流验证更强
     - 不同题材适度分散
   - 避免 10 只全部来自同一弱板块。

7. 保存结果
   - 默认输出到：
     - `/root/.openclaw/workspace/reports/emotion-cycle-stock-picker/`
   - 文件建议：
     - `emotion_snapshot_YYYY-MM-DD.json`
     - `candidate_pool_50_YYYY-MM-DD.csv`
     - `final_top10_YYYY-MM-DD.csv`
     - `selection_report_YYYY-MM-DD.md`

8. 向用户汇报时必须包含
   - 当前情绪周期
   - 对应操作建议
   - 本次采用的筛选逻辑
   - 50 只股票池是否已完成
   - 最终 10 只名单
   - 数据是否存在断更风险

## 资源文件

- 执行脚本：`scripts/run_emotion_cycle_stock_picker.py`
- 策略映射参考：`references/strategy-map.md`

## 使用方式

```bash
python3 /root/.openclaw/workspace/skills/emotion-cycle-stock-picker/scripts/run_emotion_cycle_stock_picker.py
```

指定日期：

```bash
python3 /root/.openclaw/workspace/skills/emotion-cycle-stock-picker/scripts/run_emotion_cycle_stock_picker.py --date 2026-03-23
```

只生成策略与候选池，不跑主力意图排序：

```bash
python3 /root/.openclaw/workspace/skills/emotion-cycle-stock-picker/scripts/run_emotion_cycle_stock_picker.py --skip-intent
```
