# 趋势尾盘选股技能 (Trend EOD Screener)

> 📈 基于"大阳线+缩量回调"模式的尾盘选股技能

![版本](https://img.shields.io/badge/version-1.0.0-blue)
![Python](https://img.shields.io/badge/python-≥3.9-green)
![数据源](https://img.shields.io/badge/数据源-同花顺SDK-orange)

---

## 🚀 快速开始

### 方式一：直接使用 (推荐)

如果你已经在 `trading-ai` 项目中，技能已经内置：

```python
from openclaw.skills.screener import TrendEODScreenerSkill

skill = TrendEODScreenerSkill()
result = skill.run(top_n=10)

for stock in result.data:
    print(f"{stock['rank']}. {stock['code']} {stock['name']} 得分:{stock['total_score']}")
```

### 方式二：命令行

```bash
# 基本使用 - 选出 Top 10
python -m openclaw.skills.screener.trend_eod_screener --top-n 10

# JSON 输出
python -m openclaw.skills.screener.trend_eod_screener --json

# 自定义参数
python -m openclaw.skills.screener.trend_eod_screener \
  --lookback-days 10 \
  --min-body-change 8.0 \
  --min-turnover-ratio 2.0 \
  --max-shrink-ratio 0.6 \
  --min-adjustment-days 2 \
  --top-n 10
```

---

## 📦 安装说明

### 方式一：使用打包文件安装

1. **下载技能包**

```bash
# 技能包位置
dist/trend_eod_screener-1.0.0-20260305.zip
```

2. **解压到技能目录**

```bash
# Windows
Expand-Archive -Path trend_eod_screener-1.0.0-20260305.zip -DestinationPath $HOME\.openclaw\workspace\skills\

# Linux/Mac
unzip trend_eod_screener-1.0.0-20260305.zip -d ~/.openclaw/workspace/skills/
```

3. **安装依赖**

```bash
pip install pandas>=1.5.0 numpy>=1.24.0
```

4. **配置同花顺SDK**

```bash
# 设置环境变量
export THS_USERNAME=your_username
export THS_PASSWORD=your_password

# 或在 config.json 中配置
{
  "ths_sdk": {
    "username": "your_username",
    "password": "your_password"
  }
}
```

### 方式二：一键安装

```bash
cd openclaw/skills/screener
python pack.py --install
```

### 方式三：复制技能目录

```bash
# 复制整个 screener 目录
cp -r openclaw/skills/screener /path/to/your/openclaw/skills/

# 安装依赖
pip install -r openclaw/skills/screener/requirements.txt
```

---

## 📋 参数说明

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `lookback_days` | int | 10 | 回看天数，在此范围内寻找大阳线 |
| `min_body_change` | float | 8.0 | 大阳线最小实体涨幅 (%) |
| `min_turnover_ratio` | float | 2.0 | 大阳线成交额/20日均额最小比值 |
| `max_shrink_ratio` | float | 0.6 | 当日成交额/大阳线成交额最大比值 |
| `min_adjustment_days` | int | 2 | 从大阳线起最小调整天数 |
| `top_n` | int | 10 | 返回股票数量 |
| `min_turnover_amount` | float | 5000 | 最小成交额 (万元) |

---

## 📤 输出格式

```json
{
  "success": true,
  "data": [
    {
      "rank": 1,
      "code": "301536.SZ",
      "name": "杭巨房科",
      "total_score": 99,
      "pattern": "十字星",
      "pattern_score": 90,
      "big_yang": {
        "date": "2026-02-26",
        "body_change_pct": 13.78,
        "turnover_ratio": 3.2,
        "low_price": 73.0
      },
      "adjustment_days": 3,
      "shrink_ratio": 0.26,
      "today_close": 76.0,
      "today_change_pct": 0.0,
      "today_turnover": 68785.4
    }
  ],
  "message": "选出 10 只趋势尾盘股票",
  "metadata": {
    "initial_pool_size": 414,
    "filtered_size": 65,
    "top_n": 10
  }
}
```

---

## 🧠 选股逻辑

### Step 1: 问财初选

通过同花顺问财接口进行智能初选：

```
近10日有涨幅大于8%的阳线，收盘价大于20日均线，今日成交额大于5000万，非ST
```

### Step 2: K线验证

| 条件 | 验证标准 |
|------|----------|
| 大阳线 | 实体涨幅 > 8%, 成交额 > 20日均额 × 2 |
| 缩量调整 | 今日成交额 < 大阳线成交额 × 60% |
| 调整天数 | 从大阳线起至少调整 2 天 |
| 位置不破 | 收盘价 > 大阳线最低价 |

### Step 3: 形态识别

| 形态 | 得分 | 识别条件 |
|------|------|----------|
| 十字星 | 90 | 实体/振幅 < 20%, 有上下影线 |
| 反包阳线 | 85 | 今阳包住昨阴 |
| 锤子线 | 80 | 下影线 > 实体 × 2, 收阳 |
| 阳线 | 70-80 | 收盘 > 开盘 |

### Step 4: 综合评分

| 维度 | 权重 | 评分因子 |
|------|------|----------|
| 大阳线质量 | 30% | 涨幅 + 放量倍数 |
| 调整质量 | 30% | 调整天数 + 缩量程度 |
| K线形态 | 20% | 形态分数 |
| 位置优势 | 20% | 接近大阳线低点但不破位 |

---

## 🔌 数据源

本技能使用 **同花顺SDK (iFinDPy)** 作为数据源：

| 功能 | 接口 | 说明 |
|------|------|------|
| 问财选股 | `THS_WCQuery` | 智能语义查询初选 |
| 批量K线 | `THS_HistoryQuotes` | 批量获取历史日K |

> ⚠️ **重要**: 需要同花顺SDK账号才能使用本技能

---

## 🔗 Agent 集成

### 通过 SkillRegistry 调用

```python
from openclaw.skills.registry import SkillRegistry
import asyncio

# 执行选股
result = asyncio.run(SkillRegistry.execute(
    "trend_eod_screener",
    top_n=10,
    min_body_change=8.0
))

# 获取技能 Schema (用于 LLM Tool Calling)
schema = SkillRegistry.get_skill("trend_eod_screener").get_schema()
print(schema)
```

### 与数字员工协作

```python
from openclaw.agents import TradingAgent

# 获取选股结果
screener = TrendEODScreenerSkill()
candidates = screener.run(top_n=10)

# 传递给数字员工决策
agent = TradingAgent()
decisions = agent.evaluate_candidates(
    candidates=candidates.data,
    context={"market_sentiment": "neutral"}
)
```

---

## ⚠️ 注意事项

1. **SDK 限制**: 同花顺SDK单账号只能单点登录
2. **使用时段**: 建议在尾盘 (14:30-14:55) 运行
3. **市场环境**: 适用于震荡偏强或上涨市场
4. **止损建议**: 跌破大阳线最低价 2% 止损

---

## 📁 打包文件清单

```
trend_eod_screener-1.0.0-20260305.zip
├── trend_eod_screener/
│   ├── __init__.py          # 模块入口
│   ├── trend_eod_screener.py # 核心代码
│   ├── SKILL.md              # 技能规范文档
│   ├── README.md             # 安装说明
│   ├── config.json           # 默认配置
│   ├── requirements.txt      # 依赖清单
│   ├── setup.py              # 安装脚本
│   └── MANIFEST.in           # 打包清单
```

---

## 🔬 研究版 v2.0（进行中）

新增研究骨架：
- `config.v2.json`：研究参数、情绪/主力意图过滤、双模式权重
- `scripts/backtest_nextday_strategy.py`：基于 DuckDB 的次日触达回测
- 双模式：`trend`（趋势低吸） / `leader`（前排龙头）
- 输出指标：次日收盘盈利率、+3/+5/+8 触达率、-7 止损触发率

当前研究版约束：
- 尾盘买入价暂用**当日收盘价近似 14:55 买入价**
- 主力意图先用本地因子构建 `intent_proxy_score`，后续再与 `main-force-intent` 深度融合
- 市场情绪来自 `data/db/output/*.json`，默认**退潮期不做**

示例：

```bash
python scripts/backtest_nextday_strategy.py \
  --months 6 \
  --top-n 20 \
  --json-out reports/research_summary.json \
  --csv-out reports/research_candidates.csv
```

## 📝 更新日志

### v2.0.0-research (2026-03-17)
- ✅ 增加研究版配置文件 `config.v2.json`
- ✅ 增加 DuckDB 回测脚本 `backtest_nextday_strategy.py`
- ✅ 加入情绪闸门（默认退潮期关闭）
- ✅ 加入简化主力意图代理评分
- ✅ 支持 `trend` / `leader` 双模式对照回测

### v1.0.0 (2026-03-05)

- ✅ 实现大阳线+缩量回调选股逻辑
- ✅ 同花顺SDK数据源 (问财 + 批量K线)
- ✅ K线形态识别 (十字星、反包、锤子线、阳线)
- ✅ 综合评分排序系统
- ✅ 命令行和 API 双入口
- ✅ 完整的打包和安装流程

---

## 📧 联系方式

OpenClaw Team - team@openclaw.ai

GitHub: https://github.com/openclaw/skills
