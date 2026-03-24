# 数据更新问题修复经验总结

**日期**: 2026-03-16  
**问题**: 每日数据更新任务出现多个数据缺失和类型错误

---

## 📋 问题列表

### 1. 情绪数据 (qingxu.parquet) - 数据为0
**症状**: 3月16日所有市场数据（涨停、跌停、上涨家数等）全部为0

**原因**: 
- `calc_market_emotion` 函数中 `trade_date` 列类型不一致
- 合并新旧数据时，`existing_df` 和 `result_df` 的日期列类型不同（一个是字符串，一个是Timestamp）
- 保存到 parquet 时出现 `ArrowTypeError`

**修复**: 
```python
# 在 update_market_emotion 函数中，合并数据前强制类型转换
existing_df['tradeDate'] = existing_df['tradeDate'].astype(str)
result_df['tradeDate'] = result_df['tradeDate'].astype(str)
```

---

### 2. 资金流向数据 (capital_flow) - 缺失
**症状**: kline_eod.duckdb 中 capital_flow 表没有3月16日数据

**原因**: 
- `update_duckdb_daily.py` 中每个更新函数创建独立的 `UnifiedTHSDownloader` 实例
- 下载历史行情数据后，SDK会话被断开（`Your account has been logged out`）
- 后续的资金流向查询失败

**修复**: 
- 修改 `update_eod_from_ths()` 和 `update_limit_up_from_ths()` 函数，支持传入统一的 `downloader` 实例
- 在 `run_update()` 中创建统一的 `downloader`，确保所有问财查询在同一个SDK会话中完成

```python
def update_eod_from_ths(downloader=None):
    # ...
    if downloader is None:
        downloader = UnifiedTHSDownloader(use_http=False)
        close_downloader = True
    # ...
    finally:
        if close_downloader:
            downloader.logout()

def run_update(...):
    # ...
    downloader = UnifiedTHSDownloader(use_http=False)
    try:
        update_eod_from_ths(downloader)
        update_limit_up_from_ths(downloader)
    finally:
        downloader.logout()
```

---

### 3. 龙虎榜数据 (longhubang.parquet) - ArrowTypeError
**症状**: 保存龙虎榜数据时出现 `ArrowTypeError: object of type <class 'str'> cannot be converted to int`

**原因**: 
- `save_incremental` 方法中，`new_df` 的 `trade_date` 是 `date` 类型
- `old_df` 的 `trade_date` 可能是 `object` 类型
- 合并后类型不一致，保存 parquet 失败

**修复**: 
```python
def save_incremental(self, new_df: pd.DataFrame) -> Path:
    # 确保 trade_date 列类型一致（转换为字符串）
    new_df = new_df.copy()
    new_df['trade_date'] = pd.to_datetime(new_df['trade_date']).dt.strftime('%Y-%m-%d')
    
    if self.output_path.exists():
        old_df = pd.read_parquet(self.output_path)
        old_df['trade_date'] = pd.to_datetime(old_df['trade_date']).dt.strftime('%Y-%m-%d')
        merged = pd.concat([old_df, new_df], ignore_index=True)
    # ...
```

---

## 🔧 修复文件清单

| 文件 | 修复内容 |
|------|----------|
| `skills/daily-update/scripts/qingxu.py` | 日期列类型统一 |
| `skills/daily-update/scripts/update_duckdb_daily.py` | SDK会话管理优化 |
| `skills/daily-update/scripts/get_longhubang.py` | 日期列类型统一 |

---

## 📝 经验总结

### 1. 数据类型一致性
- **Parquet文件对数据类型敏感**，合并不同来源的数据时，必须确保列类型一致
- **日期列**是最容易出现类型问题的，建议统一转换为字符串格式保存

### 2. SDK会话管理
- **同花顺SDK会话有生命周期**，频繁登录/登出可能导致会话失效
- **最佳实践**: 在一个统一的会话中完成所有相关查询，最后统一登出
- **避免**: 每个查询都创建新的downloader实例

### 3. 错误处理
- **日志记录**: 确保关键错误被记录到日志中，便于排查
- **回退机制**: 当问财接口失败时，应有本地数据回退方案

### 4. 测试验证
- **每日数据更新后**，应验证关键数据表是否有今日数据
- **监控指标**: 涨停数、跌停数、上涨家数、资金流向等不应为0或缺失

---

## ✅ 验证命令

```bash
# 验证情绪数据
python3 skills/daily-update/scripts/qingxu.py --today

# 验证DuckDB更新
python3 skills/daily-update/scripts/update_duckdb_daily.py --eod

# 验证龙虎榜数据
python3 skills/daily-update/scripts/get_longhubang.py --date 2026-03-16

# 检查数据状态
python3 -c "
import pandas as pd
import duckdb

# 检查情绪数据
df = pd.read_parquet('data/db/qingxu.parquet')
print(df[df['tradeDate'] == '2026-03-16'])

# 检查资金流向
conn = duckdb.connect('data/db/kline_eod.duckdb', read_only=True)
result = conn.execute(\"SELECT COUNT(*) FROM capital_flow WHERE trade_date = '2026-03-16'\").fetchone()
print(f'资金流向: {result[0]} 条')
conn.close()
"
```

---

## 🎯 后续建议

1. **增加数据完整性检查**: 在 daily_update.py 最后增加验证步骤，确保所有数据表都有今日数据
2. **监控告警**: 当关键数据缺失时，发送告警通知
3. **定期维护**: 每周检查一次数据更新日志，及时发现潜在问题
4. **文档更新**: 当修改数据更新逻辑时，同步更新本文档

---

*最后更新: 2026-03-16*
