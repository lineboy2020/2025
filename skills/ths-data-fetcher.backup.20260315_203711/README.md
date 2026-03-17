# 同花顺数据获取技术文档 (ths-data-fetcher)

## 📋 概述

本技能提供统一的同花顺数据获取接口，支持历史行情、日内快照、实时行情、高频序列数据下载。适用于量化交易策略开发、数据分析和实时监控场景。

**核心功能：**
- ✅ 日线/周线历史行情数据
- ✅ 日内快照数据（3秒级）
- ✅ 实时行情数据（含分钟级涨跌幅）
- ✅ 高频序列数据（1分钟K线）
- ✅ 分钟K线合成（1/5/30分钟）

---

## ⚙️ 配置说明

### 配置文件位置
```
/root/.openclaw/workspace/skills/ths-data-fetcher/scripts/config.json
```

### 配置内容
```json
{
  "ths_sdk": {
    "username": "hss130",
    "password": "335d9e"
  },
  "data_skills": {
    "ths_http": {
      "enabled": true,
      "access_token": "72a6f6c407b2d433353cdbfa46c8571c152fa724.signs_Njc0Nzc1OTU4",
      "base_url": "https://quantapi.51ifind.com/api/v1"
    }
  }
}
```

**配置项说明：**
| 配置项 | 说明 | 有效期 |
|--------|------|--------|
| `ths_sdk.username` | 同花顺SDK账号 | 长期 |
| `ths_sdk.password` | 同花顺SDK密码 | 长期 |
| `ths_http.access_token` | HTTP接口Access Token | 2026-03-12 |

---

## 🔌 接口列表

### 1. 历史行情数据 (History)

**命令行调用：**
```bash
cd /root/.openclaw/workspace/skills/ths-data-fetcher/scripts
python3 main.py --use-http history \
  --codes 000001.SZ,600000.SH \
  --start-date 2026-02-01 \
  --end-date 2026-03-06 \
  --save-path ./history_daily.csv
```

**Python调用：**
```python
from unified_ths_downloader import UnifiedTHSDownloader

with UnifiedTHSDownloader(use_http=True) as downloader:
    result = downloader.download_history_data(
        stock_codes=['000001.SZ', '600000.SH'],
        start_date='2026-02-01',
        end_date='2026-03-06',
        save_path='./history_daily.csv'
    )
    # result 格式: {'000001.SZ': DataFrame, '600000.SH': DataFrame}
```

**返回字段：**
| 字段名 | 说明 | 类型 |
|--------|------|------|
| tradeDate | 交易日期 | str |
| stock_code | 股票代码 | str |
| open | 开盘价 | float |
| high | 最高价 | float |
| low | 最低价 | float |
| close | 收盘价 | float |
| preClose | 前收盘价 | float |
| volume | 成交量 | float |
| amount | 成交额 | float |
| changeRatio | 涨跌幅 | float |
| floatCapitalOfAShares | A股流通股本 | float |

---

### 2. 实时行情数据 (Realtime)

**命令行调用：**
```bash
python3 main.py --use-http realtime \
  --codes 000001.SZ,600000.SH \
  --save-path ./realtime.csv
```

**Python调用：**
```python
with UnifiedTHSDownloader(use_http=True) as downloader:
    result = downloader.download_realtime_data(
        stock_codes=['000001.SZ', '600000.SH'],
        save_path='./realtime.csv'
    )
```

**返回字段：**
| 字段名 | 说明 | 类型 |
|--------|------|------|
| tradeDate | 交易日期 | str |
| tradeTime | 交易时间 | str |
| stock_code | 股票代码 | str |
| open | 开盘价 | float |
| high | 最高价 | float |
| low | 最低价 | float |
| latest | 最新价 | float |
| preClose | 前收盘价 | float |
| volume | 成交量 | float |
| amount | 成交额 | float |
| changeRatio | 涨跌幅 | float |
| turnoverRatio | 换手率 | float |
| upperLimit | 涨停价 | float |
| downLimit | 跌停价 | float |
| mv | 流通市值 | float |
| **chg_1min** | **1分钟涨跌幅** | float |
| **chg_3min** | **3分钟涨跌幅** | float |
| **chg_5min** | **5分钟涨跌幅** | float |

---

### 3. 日内快照数据 (Snapshot)

**命令行调用：**
```bash
python3 main.py --use-http snapshot \
  --codes 000001.SZ \
  --trade-date 2026-03-05 \
  --start-time "09:30:00" \
  --end-time "15:00:00" \
  --save-path ./snapshot.csv
```

**Python调用：**
```python
with UnifiedTHSDownloader(use_http=True) as downloader:
    result = downloader.download_snapshot_data(
        stock_codes=['000001.SZ'],
        trade_date='2026-03-05',
        start_time='09:30:00',
        end_time='15:00:00',
        save_path='./snapshot.csv'
    )
```

**返回字段：**
| 字段名 | 说明 | 类型 |
|--------|------|------|
| tradeTime | 交易时间（精确到秒） | str |
| stock_code | 股票代码 | str |
| open | 开盘价 | float |
| high | 最高价 | float |
| low | 最低价 | float |
| latest | 最新价 | float |
| preClose | 前收盘价 | float |
| volume | 累计成交量 | float |
| amount | 累计成交额 | float |
| dealDirection | 买卖方向 | str |

**说明：** 快照数据为3秒级粒度，可用于聚合1/5/30分钟K线

---

### 4. 高频序列数据 (HF)

**命令行调用（当日数据）：**
```bash
python3 main.py --use-http hf \
  --codes 000001.SZ \
  --start-time "2026-03-06 09:30:00" \
  --end-time "2026-03-06 15:00:00" \
  --save-path ./hf_1min.csv
```

**Python调用：**
```python
with UnifiedTHSDownloader(use_http=True) as downloader:
    result = downloader.download_hf_data(
        stock_codes=['000001.SZ'],
        start_time='2026-03-06 09:30:00',
        end_time='2026-03-06 15:00:00',
        save_path='./hf_1min.csv'
    )
```

**返回字段：**
| 字段名 | 说明 | 类型 |
|--------|------|------|
| tradeTime | 交易时间 | str |
| stock_code | 股票代码 | str |
| open | 开盘价 | float |
| high | 最高价 | float |
| low | 最低价 | float |
| close | 收盘价 | float |
| avgPrice | 均价 | float |
| volume | 成交量 | float |
| amount | 成交额 | float |
| change | 涨跌额 | float |
| changeRatio | 涨跌幅 | float |
| turnoverRatio | 换手率 | float |
| sellVolume | 内盘（卖出量） | float |
| buyVolume | 外盘（买入量） | float |
| changeRatio_accumulated | 累计涨跌幅 | float |

**注意：** HTTP接口高频数据仅支持当日数据，历史分钟数据请使用快照接口聚合

---

## 📊 分钟K线合成方法

### 从快照数据合成分钟K线

```python
import pandas as pd

# 1. 读取快照数据
df = pd.read_csv('snapshot.csv')
df['tradeTime'] = pd.to_datetime(df['tradeTime'])
df.set_index('tradeTime', inplace=True)

# 2. 合成1分钟K线
df_1min = df.resample('1min').agg({
    'open': 'first',
    'high': 'max',
    'low': 'min',
    'latest': 'last',  # 作为收盘价
    'volume': 'last',  # 取最后一笔累计成交量
    'amount': 'last'
})
# 计算真实成交量（差分）
df_1min['volume_diff'] = df_1min['volume'].diff().fillna(df_1min['volume'])
df_1min['amount_diff'] = df_1min['amount'].diff().fillna(df_1min['amount'])
df_1min['changeRatio'] = ((df_1min['latest'] - df_1min['open']) / df_1min['open'] * 100).round(2)

# 3. 合成5分钟K线
df_5min = df.resample('5min').agg({
    'open': 'first',
    'high': 'max',
    'low': 'min',
    'latest': 'last',
    'volume': 'last',
    'amount': 'last'
})
df_5min['volume_diff'] = df_5min['volume'].diff().fillna(df_5min['volume'])
df_5min['changeRatio'] = ((df_5min['latest'] - df_5min['open']) / df_5min['open'] * 100).round(2)

# 4. 合成30分钟K线
df_30min = df.resample('30min').agg({
    'open': 'first',
    'high': 'max',
    'low': 'min',
    'latest': 'last',
    'volume': 'last',
    'amount': 'last'
})
df_30min['volume_diff'] = df_30min['volume'].diff().fillna(df_30min['volume'])
df_30min['changeRatio'] = ((df_30min['latest'] - df_30min['open']) / df_30min['open'] * 100).round(2)
```

### 从1分钟数据合成5/30分钟K线

```python
# 读取1分钟数据
df_1min = pd.read_csv('hf_1min.csv')
df_1min['tradeTime'] = pd.to_datetime(df_1min['tradeTime'])
df_1min.set_index('tradeTime', inplace=True)

# 合成5分钟K线
df_5min = df_1min.resample('5min').agg({
    'open': 'first',
    'high': 'max',
    'low': 'min',
    'close': 'last',
    'volume': 'sum',
    'amount': 'sum'
})

# 合成30分钟K线
df_30min = df_1min.resample('30min').agg({
    'open': 'first',
    'high': 'max',
    'low': 'min',
    'close': 'last',
    'volume': 'sum',
    'amount': 'sum'
})
```

---

## 📁 数据文件位置

测试数据默认保存在：
- 实时行情：`/tmp/ths_realtime_test.csv`
- 快照数据：`/tmp/ths_snapshot_*.csv`
- 高频数据：`/tmp/ths_hf_*.csv`
- 历史数据：`/tmp/ths_history_*.csv`

---

## ⚠️ 常见问题

### Q1: HTTP接口返回401错误
**原因：** Access Token已过期
**解决：** 更新config.json中的access_token

### Q2: 高频数据返回"date index is invalid"
**原因：** HTTP接口高频数据仅支持当日数据
**解决：** 使用快照接口获取历史分钟数据

### Q3: 如何获取历史5分钟/30分钟数据
**解决：** 使用快照接口获取历史3秒数据，然后通过resample聚合

### Q4: 股票代码格式
**支持格式：**
- `000001.SZ` (深交所)
- `600000.SH` (上交所)
- `000001` (自动补全.SZ)
- `600000` (自动补全.SH)

---

## 🔗 相关技能

- `daily-quant-review` - 每日A股量化复盘
- `end-stock-picker` - 尾盘选股
- `ths-smart-stock-picking` - 同花顺智能选股

---

## 📝 更新日志

| 日期 | 版本 | 说明 |
|------|------|------|
| 2026-03-06 | v1.0 | 初始版本，支持HTTP接口获取实时/历史/快照数据 |

---

## 📞 技术支持

如遇问题，请检查：
1. config.json配置是否正确
2. Access Token是否在有效期内
3. 股票代码格式是否正确
4. 日期范围是否在有效交易日内
