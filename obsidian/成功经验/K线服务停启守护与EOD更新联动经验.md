# K线服务停启守护与 EOD 更新联动经验

## 一、背景

在当前工作区里，K 线服务会持续读取 DuckDB 数据库：

- 服务目录：`/root/.openclaw/workspace/kline-viewer`
- 实际运行进程：`python3 -m uvicorn scripts.kline_server:app --host 0.0.0.0 --port 9000`
- 盘后更新入口：`/root/.openclaw/workspace/skills/eod-full-update/scripts/eod_full_update.py`

如果在盘后更新期间不停止 K 线服务，容易带来以下风险：

- 服务读取到更新中的半成品数据
- 数据库文件占用或读写冲突
- 更新成功但服务端仍持有旧状态
- 人工手动停/启容易遗漏

因此需要把这件事从“人为记得操作”升级成“受控守护流程”。

---

## 二、最终方案

新增统一守护脚本：

- `skills/eod-full-update/scripts/run_eod_with_kline_guard.py`

它负责统一执行以下流程：

1. 停止 K 线服务
2. 执行 `eod_full_update.py`
3. 校验 `kline_eod.duckdb` 更新结果
4. 重启 K 线服务
5. 记录 JSON 日志到：
   - `skills/eod-full-update/logs/run_eod_with_kline_guard_*.json`

这比“拆成多个定时任务”更稳，因为停服、更新、校验、重启全部在一个受控入口内完成。

---

## 三、关键实现点

### 1. K 线服务识别

通过 `ps` 匹配真实运行命令：

```bash
python3 -m uvicorn scripts.kline_server:app --host 0.0.0.0 --port 9000
```

脚本内部使用 `find_kline_pids()` 定位 PID，再发送 `SIGTERM`，超时后再 `SIGKILL`。

### 2. K 线服务启动

守护脚本使用：

```bash
python3 -m uvicorn scripts.kline_server:app --host 0.0.0.0 --port 9000
```

在目录：

- `/root/.openclaw/workspace/kline-viewer`

下启动，并写入：

- `skills/eod-full-update/logs/kline_server.log`
- `kline-viewer/kline_server.pid`

### 3. 更新成功判定

不是只看 `eod_full_update.py` 的退出码，而是额外检查：

- `data/db/kline_eod.duckdb` 是否存在
- `market_daily` 是否有数据
- `MAX(trade_date)` 是否达到目标日期

这比“命令退出 0 就算成功”更可靠。

### 4. 失败恢复策略

当前脚本默认：

- 如果更新失败，但没有指定 `--no-restart-on-fail`
- 仍然尝试恢复 K 线服务，保证服务连续性

如果更看重数据一致性，可以使用：

```bash
python3 scripts/run_eod_with_kline_guard.py --no-restart-on-fail
```

让失败后保持停机，避免继续提供旧/不完整数据。

---

## 四、真实演练结果

本次实际使用：

```bash
python3 /root/.openclaw/workspace/skills/eod-full-update/scripts/run_eod_with_kline_guard.py --date 2026-03-17
```

真实结果如下：

### 停服务
- 原 K 线服务 PID：`2340826`
- `stop_kline.status = stopped`

### 执行更新
- `run_eod.status = ok`
- `returncode = 0`

### 校验数据库
- `validate_db.status = ok`
- `max_trade_date = 2026-03-18`
- `row_count = 2107961`

### 重启服务
- 新 K 线服务 PID：`2367506`
- `start_kline.status = started`

结论：

## “停服务 → 更新 → 校验 → 重启服务” 真实链路已跑通。

---

## 五、为什么这是更优做法

### 旧做法的问题
- 靠人手动停/开，容易忘
- 多个定时任务拆开执行，顺序与失败处理不稳
- 无法统一校验结果

### 新做法的优势
- 单入口执行，流程完整
- 明确的停服与恢复逻辑
- 校验结果更可靠
- 有日志留痕
- 可直接替换现有 EOD 调度入口

---

## 六、建议的后续动作

### 1. 将现有 EOD 定时任务改为调用守护脚本
把原来直接调用：

```bash
python3 scripts/eod_full_update.py
```

改为：

```bash
python3 scripts/run_eod_with_kline_guard.py
```

### 2. 视风险偏好决定失败后的默认行为
- 偏服务连续性：失败后仍自动恢复服务
- 偏数据一致性：失败后不恢复服务，等待人工检查

### 3. 后续可进一步统一启动入口
当前 K 线服务实际启动命令是 `uvicorn scripts.kline_server:app`，后续若需要可统一封装到 `kline-viewer/scripts/main.py` 管理，但这不是当前必须项。

---

## 七、关键文件

- K 线服务：
  - `/root/.openclaw/workspace/kline-viewer/scripts/kline_server.py`
  - `/root/.openclaw/workspace/kline-viewer/scripts/main.py`
- EOD 更新：
  - `/root/.openclaw/workspace/skills/eod-full-update/scripts/eod_full_update.py`
- 新增守护脚本：
  - `/root/.openclaw/workspace/skills/eod-full-update/scripts/run_eod_with_kline_guard.py`
- 日志目录：
  - `/root/.openclaw/workspace/skills/eod-full-update/logs/`

---

## 八、结论

这次优化的本质，不是“记得先停服务再更新”，而是：

## 把 K 线服务与盘后数据更新改造成统一的受控切换流程。

一旦进入受控流程，系统就具备了：

- 更新前自动停服
- 更新后自动校验
- 成功后自动恢复服务
- 失败时可按策略处理

这是一个可复用、可调度、可持续维护的运维改进。
