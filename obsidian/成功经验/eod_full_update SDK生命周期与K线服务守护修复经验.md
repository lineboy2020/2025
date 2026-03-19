# eod_full_update SDK生命周期与K线服务守护修复经验

- 时间：2026-03-19
- 主题：EOD 更新链路从 5/6 恢复到 6/6，并定位 emotion_features 剩余缺口

---

## 一、问题背景

盘后数据更新任务原本目标是 6/6 成功，但在 2026-03-19 的补跑中连续出现两个关键问题：

1. `eod_full_update.py` 的 SDK 登录生命周期过长，跨步骤持有同一个 SDK 实例，容易污染后续步骤。
2. `kline_eod.duckdb` 被 K 线服务进程占锁，导致 `kline_eod` 写库失败，任务只能停在 5/6。

后续进一步追查发现，问题不止在业务脚本，还包括调度入口与守护识别范围。

---

## 二、最终定位出的三层问题

### 1. SDK 生命周期问题
原始实现是在 EOD 主流程启动时就创建并持有 SDK 下载器，整个流程结束才统一登出。

这会导致：
- SDK 会话跨步骤长期存在
- 某一步异常可能影响后续步骤
- 日志与排障难以看清每个步骤的真实边界

### 2. 调度入口问题
原定时任务 `eod-full-update-daily` 仍然调用老入口：

```bash
python3 scripts/eod_full_update.py
```

这意味着它并没有走“停 K 线 → 更新 → 校验 → 重启”的守护流程。

### 3. 守护脚本识别范围过窄
`run_eod_with_kline_guard.py` 最初只识别：

```bash
python3 -m uvicorn scripts.kline_server:app
```

但实际持锁进程是：

```bash
python3 scripts/main.py
```

导致守护脚本会误判：
- `stop_kline = already_stopped`

实际上数据库锁仍然存在，更新继续失败。

---

## 三、修复动作

### 修复1：SDK 按步骤创建 / 释放
在 `eod_full_update.py` 中改为：
- HTTP 下载器可长驻
- SDK 下载器按需创建
- 每个 SDK 步骤完成后立即登出释放

结果：
- SDK 生命周期问题解除
- 每个步骤的边界更清晰
- SDK 问题不再是 5/6 的主因

### 修复2：调度入口改走 guard
把调度入口改为：

```bash
python3 scripts/run_eod_with_kline_guard.py
```

这样停服、更新、校验、重启成为一个受控流程，而不是依赖多个拆开的 cron 任务碰运气配合。

### 修复3：扩展 guard 的进程识别
把以下进程也纳入 K 线服务识别范围：

- `python3 scripts/main.py`
- `python scripts/main.py`

结果：
- 能正确识别并停掉真实持锁进程
- `kline_eod.duckdb` 锁冲突解除
- 2026-03-19 补跑恢复到 6/6 成功

---

## 四、实测结果

### 2026-03-19 最终补跑结果
- `qingxu` ✅
- `zhishu` ✅
- `kline_eod` ✅
- `limit_up` ✅
- `longhubang` ✅
- `emotion_features` ✅（任务状态成功）

其中：
- `kline_eod` 写入 `5489` 条
- 覆盖率 `99.95%`
- `max_trade_date = 2026-03-19`
- K 线服务已自动重启

结论：

## EOD 主链路已恢复 6/6 成功。

---

## 五、emotion_features 的剩余缺口

虽然任务层面已记为成功，但 `emotion_features` 仍存在一个剩余问题：

### 已修好
- `tradeDate` / `trade_date` 日期匹配问题
- `rise_ratio`
- `limit_up_count`
- `limit_down_count`
- `first_limit_count`

### 尚未完全补齐
- `continuous_limit_count`（连板数量）

也就是说：

## emotion_features 已从“异常”恢复到“基本可用”，但还没到完全完备。

这属于后续精修项，而不再是主链路阻塞项。

---

## 六、经验总结

### 经验1：定时任务入口必须直接走受控守护脚本
不要依赖“先停服务的一个 cron + 再更新的另一个 cron + 再启动服务的第三个 cron”这种拆散式协作。

### 经验2：守护脚本的进程识别要覆盖真实入口
服务实际可能不是只通过 uvicorn 启动，也可能通过：
- `python3 scripts/main.py`

如果识别模式不全，守护脚本会出现“看起来停了，实际没停”的假象。

### 经验3：SDK 生命周期要尽量按步骤隔离
对同花顺 SDK 这类易受会话状态影响的依赖，不要整条更新链长时间持有同一个实例。

### 经验4：任务成功率和字段完备度要分开看
当前已经恢复到 6/6 成功，但 `emotion_features` 的连板数量字段还未完全补齐。

也就是说：
- 主链路成功 ≠ 所有明细字段都已完美

---

## 七、后续动作

1. 单独补齐 `emotion_features` 的 `continuous_limit_count`
2. 明日继续跟踪验证盘后数据更新任务
3. 检查新的 guard 调度是否稳定连续工作
4. 若稳定，再把这套流程视为长期标准入口
