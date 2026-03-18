# qingxu 真实计算替换与异常日期回补经验

## 一、问题现象

在前端数据检查页中，`qingxu.parquet` 的部分字段看起来“很多是空的”，重点集中在：

- `limit_up_20pct`
- `limit_down_20pct`
- `explosion_count`
- `explosion_10pct`
- `explosion_20pct`

实际排查后发现，并不是 parquet 出现了 NULL 缺失，而是这些字段在部分日期被写成了 `0`，导致前端看起来像“没有数据”。

---

## 二、根因

问题不在前端，也不在 parquet 文件本身，而在 `eod-full-update` 的 `update_qingxu()` 实现。

文件：
- `/root/.openclaw/workspace/skills/eod-full-update/scripts/eod_full_update.py`

旧逻辑中，`update_qingxu()` 只做了简化版问财统计：
- 上涨家数
- 下跌家数
- 涨停家数
- 跌停家数

但对以下字段直接写死为 `0`：
- `limit_up_20pct`
- `limit_down_20pct`
- `explosion_count`
- `explosion_10pct`
- `explosion_20pct`

这会导致 `qingxu.parquet` 中近期某些日期的情绪细项字段失真。

---

## 三、修复思路

不再在 `eod-full-update` 中维护一套“简化版 qingxu 计算”，而是直接复用已有的真实计算逻辑：

- `/root/.openclaw/workspace/skills/daily-update/scripts/qingxu.py`

关键入口：
- `update_market_emotion(...)`

这样可以统一：
- 问财取数
- 20cm/10cm 涨跌停拆分
- 炸板数统计
- 情绪指标计算

避免同一份 `qingxu.parquet` 被不同版本逻辑混写。

---

## 四、本次实际修改

### 1. 替换 `eod-full-update` 的 `update_qingxu()`
已将：
- `skills/eod-full-update/scripts/eod_full_update.py`

中的简化版逻辑替换为：
- 直接调用 `update_market_emotion(WORKSPACE_ROOT, incremental=False, use_wencai=True, dates_to_fetch=[self.trade_date])`

### 2. 新增异常日期回补脚本
新增文件：
- `skills/eod-full-update/scripts/backfill_qingxu_recent_anomalies.py`

作用：
- 自动识别最近异常日期
- 重新调用真实计算逻辑
- 回写到 `data/db/qingxu.parquet`

---

## 五、本次识别并回补的异常日期

本次识别到的近期异常日期为：
- `2026-03-07`
- `2026-03-10`
- `2026-03-11`
- `2026-03-12`
- `2026-03-13`
- `2026-03-17`
- `2026-03-18`

---

## 六、回补后的结果

关键修复结果如下：

- `2026-03-07`
  - `limit_up_20pct = 7`
  - `explosion_count = 27`
- `2026-03-10`
  - `limit_up_20pct = 7`
  - `explosion_count = 32`
- `2026-03-11`
  - `limit_up_20pct = 4`
  - `explosion_count = 24`
- `2026-03-12`
  - `limit_up_20pct = 5`
  - `explosion_count = 23`
- `2026-03-13`
  - `limit_up_20pct = 2`
  - `explosion_count = 22`
- `2026-03-17`
  - `limit_up_20pct = 4`
  - `limit_down_20pct = 1`
  - `explosion_count = 22`
- `2026-03-18`
  - `limit_up_20pct = 9`
  - `explosion_count = 24`

这说明之前页面里看到的“假 0”已经被修正。

---

## 七、经验总结

### 1. 盘后整合脚本不要偷偷维护简化版指标逻辑
如果系统里已经有：
- 一个成熟的市场情绪计算模块

那么聚合脚本最安全的做法是：
- 直接复用成熟入口
- 不要自己再拼一个“轻量版统计”

否则很容易出现：
- 基础字段正常
- 细项字段全是 0
- 前端检查页看起来像数据坏了

### 2. 前端验数页很有价值
这次问题之所以能快速暴露，就是因为已经有了网页化检查视图。

如果没有前端直接验数，很容易长期把“被写成 0 的字段”误当成“当天真实为 0”。

### 3. 异常回补应该配套做
修未来逻辑不够，最好把最近被污染的日期一起回补，否则前端页面仍然会混杂旧脏数据。

---

## 八、相关文件

- 真实计算来源：
  - `/root/.openclaw/workspace/skills/daily-update/scripts/qingxu.py`
- 已修复入口：
  - `/root/.openclaw/workspace/skills/eod-full-update/scripts/eod_full_update.py`
- 回补脚本：
  - `/root/.openclaw/workspace/skills/eod-full-update/scripts/backfill_qingxu_recent_anomalies.py`
- 数据文件：
  - `/root/.openclaw/workspace/data/db/qingxu.parquet`
- 前端检查页：
  - `http://43.153.152.97:9000/data-check`
  - `http://43.153.152.97:9000/static/data_check.html`

---

## 九、结论

本次修复的本质是：

## 用真实市场情绪计算逻辑，替换掉 `eod-full-update` 中会把细项字段写成 0 的简化版实现，
## 并把最近异常日期一并回补，保证前端验数页看到的是可信数据。
