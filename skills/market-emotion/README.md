# 🎭 市场情绪周期技能

A股市场情绪周期判断与操作建议系统。

**版本**: v2.2.0 | **更新时间**: 2026-03-10

## 功能特点

- **每日判断**：收盘后自动分析当前市场情绪周期
- **明确建议**：给出仓位、策略、选股方向等具体操作指导
- **置信度评估**：基于XGBoost模型的概率预测
- **历史回顾**：支持查询历史任意交易日的情绪周期

## 快速开始

```bash
cd .trae/skills/market-emotion

# 预测今日
python scripts/main.py --today

# JSON格式输出
python scripts/main.py --today --json

# 指定日期
python scripts/main.py --date 2026-02-09

# 生成最近30日数据
python scripts/main.py --recent 30
```

## 情绪周期说明

| 周期 | Emoji | 仓位建议 | 核心策略 |
|:----:|:-----:|:--------:|:---------|
| 冰点期 | 🥶 | 空仓/10% | 低吸首板，观望为主 |
| 启动期 | 🌱 | 30~50% | 1进2打板，高低切换 |
| 发酵期 | 🔥 | 50~70% | 持有龙头，加仓主升 |
| 高潮期 | 🚀 | 70~100% | 重仓龙头，做妖股 |
| 退潮期 | 📉 | <10% | 空仓避险，等新周期 |

## 输出示例

```
============================================================
[*] 市场情绪周期判断结果
============================================================

[日期] 交易日期: 2026-02-09

[预测] 情绪周期: 【发酵期】
       置信度: 78.6%

[市场数据]
   涨停家数: 124    跌停家数: 5
   涨跌比: 6.08     炸板率: 22.6%

============================================================
[操作建议]
============================================================

[仓位] 仓位建议: 50%~70%仓位
[策略] 操作策略: 持有龙头，加仓主升、接龙头为主
[选股] 选股方向:
   - 龙头股：连板最高的股票，加仓主升浪
   - 龙头跟随股：同板块2-3板股
   - 龙头首阴：龙头断板首日低吸
```

## 独立部署

本技能已完全独立封装，可直接复制到其他平台使用。

### 部署步骤

```bash
# 1. 复制整个技能目录
cp -r market-emotion/ /path/to/target/skills/

# 2. 复制数据文件
cp data/index/emotion_features.parquet market-emotion/data/index/
cp models/emotion_cycle_xgb.pkl market-emotion/models/

# 3. 安装依赖
cd market-emotion
pip install -r requirements.txt

# 4. 运行
python scripts/main.py --today
```

### 需要复制的文件

| 文件 | 说明 |
|------|------|
| `data/index/emotion_features.parquet` | 特征数据（50维） |
| `models/emotion_cycle_xgb_v3.pkl`（默认） | XGBoost模型 |

### 自定义路径

可通过命令行参数指定数据和模型目录：

```bash
python scripts/main.py --today --model-dir /path/to/models --data-dir /path/to/data
```

## 数据源说明

特征数据 `emotion_features.parquet` 的数据来源（统一使用主项目数据库）：

| 数据源 | 路径 | 说明 |
|--------|------|------|
| 市场情绪数据 | `data/db/qingxu.parquet` | 涨跌家数、涨停数、炸板率等 |
| 上证指数数据 | `data/db/zhishu.parquet` | 指数K线、涨跌幅 |
| 涨停详情数据 | `data/db/limit_up.duckdb` | 涨停股票、连板高度、首板数 |

**数据获取方式**:
- **同花顺问财接口** (THS_WCQuery) - 每日A股涨跌统计、炸板数据

**技能内置文件**:
- `data/index/emotion_features.parquet` - 50维特征数据（构建后的结果）
- `data/output/*.json` - 每日预测结果

> 📌 **优化说明**: 本技能直接调用主项目数据库，不再维护重复的数据文件。

## 特征数据更新

特征数据文件 `data/index/emotion_features.parquet` 需要定期更新以包含最新交易日的数据。

### 更新方法（推荐）

使用技能自带的完整更新脚本：

```bash
cd .trae/skills/market-emotion

# 完整更新（获取数据 + 构建特征 + 预测）
python scripts/full_update.py

# 更新最近3天数据
python scripts/full_update.py --days 3

# 更新指定日期
python scripts/full_update.py --date 2026-03-06

# 跳过数据获取（仅更新特征和预测）
python scripts/full_update.py --skip-fetch

# 跳过特征更新（仅预测）
python scripts/full_update.py --skip-features
```

### 其他更新方式

#### 使用主项目的更新脚本

如果技能部署在主项目中，也可以使用主项目的更新脚本：

```bash
# 从主项目根目录运行
python indicators/emotion_cycle/daily_update.py
```

#### 手动复制

从主项目复制更新后的特征文件：

```bash
cp data/index/emotion_features.parquet .trae/skills/market-emotion/data/index/
```

### 当前数据状态

```bash
# 查看数据文件信息
python -c "import pandas as pd; df = pd.read_parquet('.trae/skills/market-emotion/data/index/emotion_features.parquet'); print(f'日期范围: {df[\"tradeDate\"].min()} ~ {df[\"tradeDate\"].max()}'); print(f'样本数: {len(df)}')"
```

## 更新日志

- **v2.2.0** (2026-03-10): 
  - ✅ 优化数据源，删除后端API依赖
  - ✅ 统一使用主项目数据库（qingxu.parquet, zhishu.parquet, limit_up.duckdb）
  - ✅ 删除重复的技能内数据文件
  - ✅ 简化脚本结构，删除冗余脚本
  - ✅ 新增 full_update.py 完整更新脚本

- **v2.1.0** (2026-03-09): 独立技能封装
- **v2.0.0** (2026-02-07): 规则标签优化
- **v1.0.0** (2026-01-20): 初始版本

## 风险提示

⚠️ 本工具仅供参考，不构成投资建议。投资有风险，入市需谨慎。
