# index-nextday-forecast



## 2026-03-22 阶段结论

- `zhishu.parquet` 已扩长到 `2023-01-03 ~ 2026-03-20`
- `limit_up.parquet` / `limit_up.duckdb` 已扩长到 `2023-01-01 ~ 2026-03-20`
- `qingxu.parquet` 已扩长到 `2023-01-10 ~ 2026-03-20`
- `emotion_features.parquet` 已扩长到 `2024-03-22 ~ 2026-03-20`
- 重训后样本数从 `291` 提升到 `481`
- 单次训练准确率从 `0.4915` 提升到 `0.5258`
- 滚动回测平均准确率 `0.5208`
- 已跑赢 `always_down` / `same_day_momentum`
- 仍未跑赢 `always_up` / `mean_reversion`

### 当前定位

本技能目前仍应定位为**研究原型**，不具备上线价值。

原因：

1. 长样本修复后虽然出现正向改善，但仍未超越最强简单基线
2. 当前测试窗口上涨占比偏高，`always_up` 仍有天然优势
3. `emotion_features` 仍未完全追到 2023 年，特征层仍有继续扩长空间

详见：
- `/root/.openclaw/workspace/reports/index-nextday-forecast-stage-summary-2026-03-22.md`
