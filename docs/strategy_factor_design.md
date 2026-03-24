# 多因子量化策略 - 因子体系详细设计

**基于可用数据源的因子推荐**

---

## 📊 可用数据源汇总

| 数据源 | 关键字段 | 更新频率 |
|--------|----------|----------|
| **情绪数据** | 涨停数、跌停数、涨跌比、情绪分数、情绪周期 | 每日 |
| **涨停数据** | 涨停股票、连板数、封板资金、涨停时间、概念 | 每日 |
| **龙虎榜数据** | 买卖金额、净额、上榜原因、营业部 | 每日 |
| **资金流向** | 主力净流入、净流入占比 | 每日 |
| **日线数据** | 开高低收、成交量、成交额、换手率 | 每日 |
| **指数数据** | 上证涨跌、涨跌家数 | 每日 |

---

## 🎯 推荐因子体系（动态权重）

### 因子权重分配（根据情绪周期动态调整）

```python
FACTOR_WEIGHTS = {
    '冰点期': {
        '情绪周期': 0.35,      # 情绪判断最重要
        '龙虎榜': 0.25,        # 关注机构抄底
        '资金流向': 0.20,      # 资金流入信号
        '技术形态': 0.15,      # 底部形态
        '基本面': 0.05,        # 基本面兜底
    },
    '启动期': {
        '情绪周期': 0.25,
        '板块轮动': 0.25,      # 板块启动关键
        '资金流向': 0.25,      # 资金流入关键
        '技术形态': 0.20,      # 突破形态
        '龙虎榜': 0.05,
    },
    '发酵期': {
        '情绪周期': 0.20,
        '板块轮动': 0.30,      # 板块扩散重要
        '资金流向': 0.25,
        '技术形态': 0.20,
        '龙虎榜': 0.05,
    },
    '高潮期': {
        '情绪周期': 0.30,      # 警惕情绪转折
        '龙虎榜': 0.25,        # 关注机构出货
        '资金流向': 0.20,
        '技术形态': 0.15,
        '板块轮动': 0.10,
    },
    '退潮期': {
        '情绪周期': 0.40,      # 空仓判断最重要
        '龙虎榜': 0.20,        # 关注避险板块
        '资金流向': 0.15,
        '技术形态': 0.15,
        '板块轮动': 0.10,
    }
}
```

---

## 📈 六大因子详细设计

### 1️⃣ 市场情绪周期因子 (Emotion Factor)

**数据来源**: `emotion_features.parquet`

#### 子因子

| 子因子 | 计算方法 | 权重 | 说明 |
|--------|----------|------|------|
| 情绪周期标签 | 模型预测 | 40% | 冰点/启动/发酵/高潮/退潮 |
| 情绪分数 | 0-100分 | 30% | 综合情绪强度 |
| 涨停趋势 | 3日涨停数变化 | 15% | 判断情绪方向 |
| 涨跌比 | 上涨家数/下跌家数 | 15% | 市场广度 |

#### 评分规则
```python
def emotion_score(row):
    score = 0
    
    # 情绪周期 (40分)
    cycle_scores = {'冰点期': 20, '启动期': 60, '发酵期': 80, '高潮期': 100, '退潮期': 30}
    score += cycle_scores.get(row['emotion_name'], 50) * 0.4
    
    # 情绪分数 (30分)
    score += min(100, row['emotion_score']) * 0.3
    
    # 涨停趋势 (15分)
    if row['limit_up_trend_3d'] > 0:
        score += min(15, 15 + row['limit_up_trend_3d'])
    else:
        score += max(0, 15 + row['limit_up_trend_3d'] * 0.5)
    
    # 涨跌比 (15分)
    rise_ratio = row['rise_fall_ratio']
    if rise_ratio >= 2.0:
        score += 15
    elif rise_ratio >= 1.0:
        score += 10
    elif rise_ratio >= 0.5:
        score += 5
    else:
        score += max(0, rise_ratio * 10)
    
    return min(100, score)
```

---

### 2️⃣ 板块轮动因子 (Sector Factor)

**数据来源**: `limit_up.duckdb` + `ths-smart-stock-picking`

#### 子因子

| 子因子 | 计算方法 | 权重 | 说明 |
|--------|----------|------|------|
| 板块涨停占比 | 板块涨停数/总涨停数 | 30% | 板块热度 |
| 板块连板高度 | 板块最高连板数 | 25% | 板块强度 |
| 板块持续性 | 连续3日有涨停 | 20% | 持续性 |
| 板块资金净流入 | 板块内个股资金流入总和 | 25% | 资金支持 |

#### 板块识别
```python
def identify_hot_sectors(limit_up_df, capital_flow_df):
    """识别热门板块"""
    sectors = {}
    
    # 统计各板块涨停数
    for _, row in limit_up_df.iterrows():
        sector = row['所属行业']
        if sector not in sectors:
            sectors[sector] = {
                'limit_up_count': 0,
                'consecutive_boards': [],
                'stocks': []
            }
        sectors[sector]['limit_up_count'] += 1
        sectors[sector]['consecutive_boards'].append(row['consecutive_boards'])
        sectors[sector]['stocks'].append(row['stock_code'])
    
    # 计算板块强度
    for sector, data in sectors.items():
        # 涨停占比
        data['limit_up_ratio'] = data['limit_up_count'] / len(limit_up_df)
        # 最高连板
        data['max_consecutive'] = max(data['consecutive_boards']) if data['consecutive_boards'] else 0
        # 平均连板
        data['avg_consecutive'] = sum(data['consecutive_boards']) / len(data['consecutive_boards']) if data['consecutive_boards'] else 0
    
    # 筛选热门板块 (涨停数>=3)
    hot_sectors = {k: v for k, v in sectors.items() if v['limit_up_count'] >= 3}
    
    return hot_sectors
```

---

### 3️⃣ 主力资金流向因子 (Capital Factor)

**数据来源**: `kline_eod.duckdb.capital_flow`

#### 子因子

| 子因子 | 计算方法 | 权重 | 说明 |
|--------|----------|------|------|
| 主力净流入金额 | 当日主力净流入 | 30% | 资金规模 |
| 主力净流入占比 | 净流入/成交额 | 30% | 资金强度 |
| 连续净流入天数 | 近5日净流入为正天数 | 25% | 持续性 |
| 资金趋势 | 3日资金变化 | 15% | 趋势方向 |

#### 评分规则
```python
def capital_flow_score(stock_code, capital_flow_df):
    """计算资金流向评分"""
    score = 0
    
    # 获取个股资金流向数据
    stock_flow = capital_flow_df[capital_flow_df['symbol'] == stock_code]
    if stock_flow.empty:
        return 50  # 无数据返回中性分
    
    row = stock_flow.iloc[0]
    net_inflow = row['main_net_inflow']
    
    # 主力净流入金额 (30分)
    if net_inflow > 100_000_000:  # >1亿
        score += 30
    elif net_inflow > 50_000_000:  # >5000万
        score += 25
    elif net_inflow > 10_000_000:  # >1000万
        score += 20
    elif net_inflow > 0:
        score += 10
    else:
        score += max(0, 10 + net_inflow / 10_000_000)  # 负流入扣分
    
    # 主力净流入占比 (30分)
    # 需要结合成交额计算
    # 假设成交额可以从market_daily获取
    
    return min(100, score)
```

---

### 4️⃣ 龙虎榜因子 (Dragon Tiger Factor) ⭐新增

**数据来源**: `longhubang.parquet`

#### 子因子

| 子因子 | 计算方法 | 权重 | 说明 |
|--------|----------|------|------|
| 龙虎榜净额 | 买入金额 - 卖出金额 | 25% | 机构态度 |
| 龙虎榜类型 | 涨幅/换手/振幅 | 25% | 上榜原因 |
| 机构参与度 | 机构专用席位买卖 | 30% | 机构行为 |
| 连续上榜 | 近3日上榜次数 | 20% | 关注度 |

#### 龙虎榜评分
```python
def dragon_tiger_score(stock_code, longhubang_df):
    """计算龙虎榜评分"""
    score = 0
    
    # 获取个股龙虎榜数据
    stock_lhb = longhubang_df[longhubang_df['stock_code'] == stock_code]
    if stock_lhb.empty:
        return 50  # 无数据返回中性分
    
    # 取最新一条
    row = stock_lhb.iloc[0]
    
    # 龙虎榜净额 (25分)
    net_amount = row['net_amount']
    if net_amount > 100_000_000:  # 净买入>1亿
        score += 25
    elif net_amount > 50_000_000:
        score += 20
    elif net_amount > 10_000_000:
        score += 15
    elif net_amount > 0:
        score += 10
    else:
        score += max(0, 10 + net_amount / 10_000_000)
    
    # 上榜类型 (25分)
    reason = row['reason']
    if '涨幅' in str(reason) and '跌幅' not in str(reason):
        score += 25  # 涨幅榜
    elif '换手' in str(reason):
        score += 20  # 换手榜
    elif '振幅' in str(reason):
        score += 15  # 振幅榜
    else:
        score += 10
    
    # 机构参与度 (30分) - 需要解析detail字段
    # 如果有机构专用席位大额买入，加分
    
    # 连续上榜 (20分)
    consecutive_count = len(stock_lhb)
    if consecutive_count >= 3:
        score += 20
    elif consecutive_count == 2:
        score += 15
    elif consecutive_count == 1:
        score += 10
    
    return min(100, score)
```

---

### 5️⃣ 技术形态因子 (Pattern Factor)

**数据来源**: `kline_eod.duckdb.market_daily`

#### 子因子

| 子因子 | 计算方法 | 权重 | 说明 |
|--------|----------|------|------|
| 均线系统 | 5/10/20/60日均线排列 | 25% | 趋势判断 |
| 量价关系 | 量价齐升/背离 | 25% | 动能判断 |
| 突破形态 | 突破前高/平台 | 25% | 入场信号 |
| 反转形态 | 早晨之星/锤头线等 | 25% | 底部信号 |

#### 形态识别
```python
def pattern_score(stock_code, market_daily_df):
    """计算技术形态评分"""
    score = 0
    
    # 获取个股日线数据 (需要最近30日)
    stock_data = market_daily_df[market_daily_df['symbol'] == stock_code]
    if len(stock_data) < 20:
        return 50
    
    # 按日期排序
    stock_data = stock_data.sort_values('trade_date')
    
    # 计算均线
    stock_data['ma5'] = stock_data['close'].rolling(5).mean()
    stock_data['ma10'] = stock_data['close'].rolling(10).mean()
    stock_data['ma20'] = stock_data['close'].rolling(20).mean()
    
    latest = stock_data.iloc[-1]
    
    # 均线系统 (25分)
    if latest['close'] > latest['ma5'] > latest['ma10'] > latest['ma20']:
        score += 25  # 多头排列
    elif latest['close'] > latest['ma5']:
        score += 15  # 站上5日线
    elif latest['close'] > latest['ma20']:
        score += 10  # 站上20日线
    
    # 量价关系 (25分)
    recent = stock_data.tail(5)
    price_up = recent['close'].iloc[-1] > recent['close'].iloc[0]
    volume_up = recent['volume'].mean() > stock_data.tail(20)['volume'].mean()
    
    if price_up and volume_up:
        score += 25  # 量价齐升
    elif price_up:
        score += 15  # 价升量平
    elif volume_up:
        score += 10  # 放量滞涨
    
    # 突破形态 (25分)
    # 检查是否突破前高
    high_20 = stock_data.tail(20)['high'].max()
    if latest['close'] > high_20 * 0.98:  # 接近或突破20日高点
        score += 25
    elif latest['close'] > stock_data.tail(60)['high'].max() * 0.95:  # 接近60日高点
        score += 20
    
    # 反转形态 (25分)
    # 早晨之星、锤头线等
    if len(stock_data) >= 3:
        last3 = stock_data.tail(3)
        # 早晨之星: 阴线+十字星+阳线，第三日突破第一日高点
        if (last3['close'].iloc[0] < last3['open'].iloc[0] and  # 第一日阴线
            abs(last3['close'].iloc[1] - last3['open'].iloc[1]) / last3['open'].iloc[1] < 0.01 and  # 第二日十字星
            last3['close'].iloc[2] > last3['open'].iloc[2] and  # 第三日阳线
            last3['close'].iloc[2] > last3['high'].iloc[0]):  # 突破第一日高点
            score += 25
    
    return min(100, score)
```

---

### 6️⃣ 基本面因子 (Fundamental Factor) ⭐新增

**数据来源**: `limit_up.duckdb` (市值数据) + 可扩展

#### 子因子

| 子因子 | 计算方法 | 权重 | 说明 |
|--------|----------|------|------|
| 流通市值 | 流通市值大小 | 30% | 流动性 |
| 总市值 | 总市值大小 | 20% | 规模 |
| 换手率 | 成交额/流通市值 | 30% | 活跃度 |
| 封板资金 | 涨停封单金额 | 20% | 涨停强度 |

#### 基本面评分
```python
def fundamental_score(stock_code, limit_up_df):
    """计算基本面评分"""
    score = 0
    
    # 从涨停数据获取基本面信息
    stock_data = limit_up_df[limit_up_df['stock_code'] == stock_code]
    if stock_data.empty:
        return 50
    
    row = stock_data.iloc[0]
    
    # 流通市值 (30分)
    float_mv = row.get('float_mv', 0)
    if 10_000_000_000 <= float_mv <= 50_000_000_000:  # 100-500亿
        score += 30  # 最佳区间
    elif float_mv > 50_000_000_000:
        score += 20  # 大盘股
    elif float_mv > 5_000_000_000:
        score += 25  # 中盘股
    else:
        score += 15  # 小盘股
    
    # 换手率 (30分)
    turnover = row.get('turnover_ratio', 0)
    if 0.05 <= turnover <= 0.20:  # 5%-20%
        score += 30
    elif turnover > 0.20:
        score += 20  # 过高换手
    elif turnover > 0.02:
        score += 15
    else:
        score += 10
    
    # 封板资金 (20分)
    seal_amount = row.get('seal_amount', 0)
    if seal_amount > 100_000_000:  # >1亿
        score += 20
    elif seal_amount > 50_000_000:
        score += 15
    elif seal_amount > 10_000_000:
        score += 10
    else:
        score += 5
    
    return min(100, score)
```

---

## 🎯 综合评分模型

### 选股流程

```python
def select_stocks(trade_date, emotion_data, top_n=15):
    """多因子选股"""
    
    # 1. 获取当前情绪周期
    emotion_cycle = emotion_data['emotion_name']
    weights = FACTOR_WEIGHTS.get(emotion_cycle, FACTOR_WEIGHTS['启动期'])
    
    # 2. 获取候选股票池
    # - 热门板块内的涨停股
    # - 龙虎榜上榜股票
    # - 资金流入前100的股票
    candidates = get_candidate_pool(trade_date)
    
    # 3. 计算各因子得分
    results = []
    for stock in candidates:
        scores = {
            '情绪周期': emotion_factor_score(stock, emotion_data),
            '板块轮动': sector_factor_score(stock),
            '资金流向': capital_factor_score(stock),
            '龙虎榜': dragon_tiger_score(stock),
            '技术形态': pattern_score(stock),
            '基本面': fundamental_score(stock),
        }
        
        # 4. 加权综合评分
        total_score = sum(
            scores[factor] * weights.get(factor, 0.2)
            for factor in scores
        )
        
        results.append({
            'stock_code': stock,
            'total_score': total_score,
            'factor_scores': scores,
            'emotion_cycle': emotion_cycle
        })
    
    # 5. 排序精选
    results.sort(key=lambda x: x['total_score'], reverse=True)
    
    # 6. 返回Top N
    return results[:top_n]
```

---

## 📊 因子权重动态调整规则

### 根据市场状态调整

```python
def adjust_weights(emotion_data, market_data):
    """根据市场状态动态调整权重"""
    
    weights = FACTOR_WEIGHTS[emotion_data['emotion_name']].copy()
    
    # 如果涨停家数激增，增加板块轮动权重
    if market_data['limit_up_change_1d'] > 20:
        weights['板块轮动'] += 0.05
        weights['情绪周期'] -= 0.05
    
    # 如果龙虎榜机构买入活跃，增加龙虎榜权重
    if market_data['institutional_buy_ratio'] > 0.6:
        weights['龙虎榜'] += 0.05
        weights['技术形态'] -= 0.05
    
    # 如果市场波动加大，增加技术形态权重
    if market_data['volatility_5d'] > 0.03:
        weights['技术形态'] += 0.05
        weights['基本面'] -= 0.05
    
    # 归一化
    total = sum(weights.values())
    weights = {k: v/total for k, v in weights.items()}
    
    return weights
```

---

## 🔄 后续优化方向

1. **机器学习优化**: 使用历史数据训练因子权重
2. **实时因子**: 接入盘中实时数据，动态调整
3. **事件驱动**: 加入业绩公告、政策等事件因子
4. **行业轮动**: 更精细的行业轮动模型
5. **风险控制**: 加入VaR、最大回撤等风险因子

---

*最后更新: 2026-03-16*
