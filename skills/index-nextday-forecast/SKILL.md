---
name: index-nextday-forecast
description: 预测A股指数次日涨跌方向的技能。结合市场情绪周期、上证指数K线、顶底分型/笔方向特征，训练并运行“明日涨跌”方向模型，输出上涨/下跌概率、核心驱动因子与简要解释。用于用户要求“预测明天大盘涨跌”“结合情绪周期和顶底分型判断明日方向”“训练指数预测模型”“生成次日指数方向判断”等场景。
---

# index-nextday-forecast

用这个技能做：

- 训练指数次日涨跌方向模型
- 预测下一交易日上证指数方向
- 结合情绪周期 + 顶底分型 + 指数技术特征输出解释

## 当前版本定位

这是一个 **v1 可落地模型技能**，目标是先建立稳定、可训练、可迭代的指数方向预测链路。

## 默认工作流

1. 从主库读取：
   - `data/db/zhishu.parquet`
   - `data/db/qingxu.parquet`
   - `data/index/emotion_features.parquet`
2. 构建训练样本：
   - 当日特征 → 次日指数涨跌标签
3. 训练二分类模型
4. 输出预测结果：
   - 次日上涨概率
   - 次日下跌概率
   - 当前情绪周期
   - 顶底分型 / 笔方向
   - 简要解释

## 训练命令

```bash
python3 /root/.openclaw/workspace/skills/index-nextday-forecast/scripts/train_model.py
```

## 预测命令

```bash
python3 /root/.openclaw/workspace/skills/index-nextday-forecast/scripts/predict_nextday.py --date 2026-03-20
```

如果不传日期，默认使用最近交易日。

## 输出说明

重点向用户说明：

- 这是“方向概率模型”，不是点位精确预测
- 输出是 **上涨概率 / 下跌概率 + 结构解释**
- 应与市场情绪技能、主观盘面判断结合使用，不宜单独作为交易依据
