# index-nextday-forecast 阶段总结（2026-03-22）

## 1. 本阶段目标

围绕 `skills/index-nextday-forecast`，本阶段重点不是继续盲目调模型，而是先修复样本链路，验证该研究原型在更长历史样本上的真实表现。

核心目标：

1. 补齐 `zhishu.parquet` 历史长度
2. 补齐 `limit_up.parquet` / `limit_up.duckdb` 历史长度
3. 查清 `qingxu.parquet` 为什么只从 `2025-01-02` 开始
4. 扩长 `emotion_features.parquet`
5. 在扩长后的样本上重新训练并做滚动回测
6. 与简单基线做完整比较，判断是否具备继续推进价值

---

## 2. 关键问题定位过程

### 2.1 初始问题：`zhishu.parquet` 极短

最初排查发现：

- `data/db/zhishu.parquet` 总行数仅 **26**
- 其中上证指数可用行数仅 **4**
- 范围只有 **2026-03-09 ~ 2026-03-16**

而：

- `qingxu.parquet` 有 **292** 行
- `emotion_features.parquet` 有 **292** 行
- 二者范围均为 **2025-01-02 ~ 2026-03-20**

结论：
> `index-nextday-forecast` 最初样本严重不足，首要短板是 `zhishu.parquet` 历史长度不够。

---

### 2.2 `zhishu` 补长到 3 年

使用现有脚本补齐历史后：

- `data/db/zhishu.parquet` 扩长到 **776** 行
- 范围变为 **2023-01-03 ~ 2026-03-20**

这一步解决了指数历史样本不足问题。

---

### 2.3 `limit_up` 补长到 3 年

在修正回补脚本调用方法与快照路径之后，最终完成：

- `data/db/limit_up.parquet`
- `data/db/limit_up.duckdb`

均扩长到：

- **84265** 行
- **1175** 个交易日
- 范围：**2023-01-01 ~ 2026-03-20**

结论：
> `limit_up` 链路已从“最近几天可用”恢复为“3 年历史可用”。

---

### 2.4 `qingxu` 的真正根因

`qingxu.parquet` 迟迟无法扩长，最初怀疑是：

- 底层全市场日线历史不够
- 写回逻辑截断
- 停牌过滤误杀
- 显式日期硬编码

逐项排查后全部排除。

最终定位到：

#### `kline_eod.duckdb.market_daily` 在 2023 / 2024 年缺关键字段

字段有效率检查结果：

- 2023：
  - `change_ratio_notnull_ratio = 0.0`
  - `pre_close_valid_ratio = 0.0`
- 2024：
  - `change_ratio_notnull_ratio = 0.0`
  - `pre_close_valid_ratio = 0.0`
- 2025 起恢复正常

而 `calc_market_emotion()` 明确依赖：

- `changeRatio.notna()`
- `preClose.notna()`
- `preClose > 0`

因此导致 `qingxu` 只能从 **2025-01-02** 才开始产出。

---

### 2.5 对 `qingxu.py` 做历史兼容补算

采用最短路径修复，而不是先重建整张 `market_daily`：

在 `skills/daily-update/scripts/qingxu.py` 中，对 DuckDB 读取后的数据增加兼容补算逻辑：

- 若 `preClose` 缺失：用同股票前一交易日 `close` 补算
- 若 `changeRatio` 缺失：用 `(close / preClose - 1) * 100` 补算

然后绕过整套 CLI 的长链路，用一次性脚本直接：

1. `load_daily_data_from_duckdb()`
2. `calc_market_emotion(df)`
3. 直接写回 `data/db/qingxu.parquet`

最终结果：

- `qingxu.parquet` 扩长到 **771** 行
- 范围：**2023-01-10 ~ 2026-03-20**

结论：
> `qingxu` 历史长度问题已实质修复。

---

### 2.6 `emotion_features` 扩长

在 `qingxu` 修复后，重新运行：

- `skills/market-emotion/scripts/full_update.py --skip-fetch`

结果：

- `data/index/emotion_features.parquet` 扩长到 **482** 行
- 范围：**2024-03-22 ~ 2026-03-20**

说明：

- 特征工程层确实被扩长了
- 但仍存在约 1 年左右的前段损耗
- 该损耗应来自特征构造窗口或字段可用性，而不是 `qingxu` / `zhishu` / `limit_up` 主数据长度本身

---

## 3. 重训与回测结果

### 3.1 重训结果

在扩长后的特征数据上重新训练 `index-nextday-forecast`：

- 样本数：**481**
- 准确率：**0.5258**

对比修复前：

- 修复前：**291** 样本，准确率 **0.4915**
- 修复后：**481** 样本，准确率 **0.5258**

结论：
> 长样本修复后，训练结果出现了明确改善。

---

### 3.2 滚动回测结果

滚动窗口结果：

#### 窗口 1
- 测试区间：**2025-06-04 ~ 2025-08-08**
- 测试上涨占比：**0.6875**
- 模型准确率：**0.4375**
- `always_down_acc`：**0.3125**
- `always_up_acc`：**0.6875**
- `same_day_momentum_acc`：**0.3125**
- `mean_reversion_acc`：**0.6875**

#### 窗口 2
- 测试区间：**2025-08-11 ~ 2025-10-23**
- 测试上涨占比：**0.5833**
- 模型准确率：**0.5625**
- `always_down_acc`：**0.4167**
- `always_up_acc`：**0.5833**
- `same_day_momentum_acc`：**0.4167**
- `mean_reversion_acc`：**0.5833**

#### 窗口 3
- 测试区间：**2025-10-24 ~ 2025-12-30**
- 测试上涨占比：**0.5417**
- 模型准确率：**0.5625**
- `always_down_acc`：**0.4583**
- `always_up_acc`：**0.5417**
- `same_day_momentum_acc`：**0.4583**
- `mean_reversion_acc`：**0.5417**

---

### 3.3 平均表现对比

- 模型平均准确率：**0.5208**
- `always_down`：**0.3958**
- `always_up`：**0.6042**
- `same_day_momentum`：**0.3958**
- `mean_reversion`：**0.6042**

---

## 4. 本阶段最终判断

### 可以明确确认的结论

1. **样本修复是有效的**
   - `zhishu`、`limit_up`、`qingxu`、`emotion_features` 都被显著扩长
2. **模型表现相比之前确实改善**
   - 样本数从 **291 → 481**
   - 单次训练准确率从 **49.15% → 52.58%**
3. **滚动回测已跑赢弱基线**
   - 明显优于 `always_down`
   - 明显优于 `same_day_momentum`

### 仍然不能过度乐观的地方

1. **当前模型仍未跑赢最强简单基线**
   - 未跑赢 `always_up`
   - 未跑赢 `mean_reversion`
2. **测试窗口上涨占比偏高**
   - 三个测试窗口分别为 `0.6875 / 0.5833 / 0.5417`
   - 在这种分布下，`always_up` 天然占优
3. **`emotion_features` 仍未完全追到 2023 年**
   - 当前起点仍是 **2024-03-22**
   - 说明特征层还有进一步补长空间

---

## 5. 阶段性结论（最重要）

### 当前定位
`index-nextday-forecast` 在本阶段已经从：

- “样本严重不足、结论不可信”

提升到：

- “在更长样本上具备一定正向信号，但仍未超越最强简单基线的研究原型”

### 因此当前最合适的口径是：

> **继续保留为研究原型，不具备上线价值。**

它已经比最初状态好很多，但还不能被描述为：

- 可直接上线
- 可直接指导交易
- 已具备稳定择时能力

---

## 6. 建议的后续方向

### 方向 A：继续优化当前任务
适合继续研究，但不保证有效：

1. 继续扩长 `emotion_features` 到更接近 2023 年
2. 增加更多滚动窗口与更长测试区间
3. 检查类别分布偏斜问题
4. 做概率校准与阈值优化，而不是只做 0/1 方向判断

### 方向 B：重新定义任务目标
如果方向预测始终跑不赢 `always_up / mean_reversion`，更现实的方案是：

1. 改成**极端日识别**（大涨 / 大跌预警）
2. 改成**择时过滤器**（只在高置信度情形下给出信号）
3. 改成**风险分层**（低风险 / 高风险，而非单纯涨跌）
4. 改成与情绪周期结合的“是否参与”问题，而不是裸方向预测

---

## 7. 本阶段沉淀

本阶段最重要的成果，不只是模型数值提升，而是把整个样本链路真正梳理通了：

- `zhishu` 历史补齐
- `limit_up` 历史补齐
- `qingxu` 根因定位并修复
- `emotion_features` 扩长
- `index-nextday-forecast` 在更长样本上完成重训与完整基线对比

这些工作使得后续继续研究时，不会再被“数据本身太短”这个伪问题反复干扰。

---

**阶段结论一句话版：**

> 数据链路已经打通，模型相比之前明显改善，但当前仍未跑赢最强简单基线，因此 `index-nextday-forecast` 继续定位为研究原型，不具备上线价值。
