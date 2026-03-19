"""
缠论核心算法库 (Chanlun Core Math)

功能：
1. K线包含关系处理 (Containment Processing)
2. 分型识别 (Fractal Detection)
3. 笔识别 (Bi/Stroke Detection)
4. 中枢识别 (Zhongshu/Center Detection) - 2025-01-14 新增
5. 背驰检测 (Divergence Detection) - 2025-01-14 新增
6. 买点识别 (Buy Point Detection: 1B/2B/3B) - 2025-01-14 新增
7. 实时买点状态机 (Current Buy State Detection) - 2025-01-14 新增

支持 Numba 加速，自动降级到纯 Python 实现。
"""
import numpy as np
import pandas as pd
from typing import Tuple, List, Dict, Union, Optional
import os

# Numba Support Check
try:
    if os.environ.get('DISABLE_NUMBA', '0') == '1':
        raise ImportError("Numba disabled by environment variable")
    from numba import jit
    HAS_NUMBA = True
except ImportError:
    HAS_NUMBA = False
    def jit(*args, **kwargs):
        def decorator(func):
            return func
        return decorator

# -----------------------------------------------------------------------------
# 1. Containment Processing (包含关系处理)
# -----------------------------------------------------------------------------

def _process_containment_python(highs, lows, opens, closes):
    """
    处理K线包含关系（纯Python实现）
    遵循缠论标准：
    - 趋势向上：高点取高(max)，低点取高(max)
    - 趋势向下：高点取低(min)，低点取低(min)
    """
    n = len(highs)
    if n < 2:
        return highs, lows, opens, closes, np.arange(n), np.ones(n, dtype=np.int32)
    
    # 结果数组
    res_h = []
    res_l = []
    res_o = []
    res_c = []
    res_idx = []
    res_counts = [] # 记录合并的K线数量
    
    # 初始状态
    curr_h = highs[0]
    curr_l = lows[0]
    curr_o = opens[0]
    curr_c = closes[0]
    curr_idx = 0
    curr_count = 1
    
    # 初始方向：假设第一根和第二根的关系决定初始方向，或者默认为向上(1)
    # 缠论通常需要看前一笔，这里简化为：如果 H[1]>H[0] 则向上，否则向下
    direction = 1 
    if n > 1:
        if highs[1] > highs[0]:
            direction = 1
        elif highs[1] < highs[0]:
            direction = -1
        # Equal case: keep default 1 or check lows
    
    i = 1
    while i < n:
        next_h = highs[i]
        next_l = lows[i]
        next_o = opens[i]
        next_c = closes[i]
        
        # 判断包含关系
        # 1. Curr contains Next (左包右)
        c1_in_c2 = (curr_h >= next_h) and (curr_l <= next_l)
        # 2. Next contains Curr (右包左)
        c2_in_c1 = (next_h >= curr_h) and (next_l <= curr_l)
        
        if c1_in_c2 or c2_in_c1:
            # 发生包含，进行合并
            curr_count += 1
            
            if direction == 1: # 向上趋势：高高低高
                curr_h = max(curr_h, next_h)
                curr_l = max(curr_l, next_l)
            else: # 向下趋势：高低低低
                curr_h = min(curr_h, next_h)
                curr_l = min(curr_l, next_l)
                
            # 收盘价/开盘价处理：通常取最后的一根作为代表，或者根据高低点重新映射
            # 这里简单策略：如果发生了合并，沿用Next的时间属性(idx)，但在数值上已经Merge
            # 为了保留K线实体感，如果合并了，Open/Close 也要相应调整吗？
            # 缠论严格只看High/Low。为了画图，我们通常取极值。
            # 修正：保留合并后的High/Low，Open/Close取Next的（因为时间上是Next）
            curr_o = next_o
            curr_c = next_c
            curr_idx = i # 更新为最新的索引
            
        else:
            # 无包含，确认前一根
            res_h.append(curr_h)
            res_l.append(curr_l)
            res_o.append(curr_o)
            res_c.append(curr_c)
            res_idx.append(curr_idx)
            res_counts.append(curr_count)
            
            # 更新方向
            if next_h > curr_h:
                direction = 1
            elif next_h < curr_h:
                direction = -1
            # else: keep previous direction
            
            # 重置当前
            curr_h = next_h
            curr_l = next_l
            curr_o = next_o
            curr_c = next_c
            curr_idx = i
            curr_count = 1
            
        i += 1
        
    # 添加最后一根
    res_h.append(curr_h)
    res_l.append(curr_l)
    res_o.append(curr_o)
    res_c.append(curr_c)
    res_idx.append(curr_idx)
    res_counts.append(curr_count)
    
    return (np.array(res_h), np.array(res_l), np.array(res_o), np.array(res_c), 
            np.array(res_idx), np.array(res_counts))

if HAS_NUMBA:
    @jit(nopython=True)
    def _process_containment_numba(highs, lows, opens, closes):
        n = len(highs)
        # 预分配最大可能长度
        res_h = np.zeros(n, dtype=np.float64)
        res_l = np.zeros(n, dtype=np.float64)
        res_o = np.zeros(n, dtype=np.float64)
        res_c = np.zeros(n, dtype=np.float64)
        res_idx = np.zeros(n, dtype=np.int64)
        res_counts = np.zeros(n, dtype=np.int32)
        
        if n < 2:
            return highs, lows, opens, closes, np.arange(n), np.ones(n, dtype=np.int32)
        
        curr_h = highs[0]
        curr_l = lows[0]
        curr_o = opens[0]
        curr_c = closes[0]
        curr_idx = 0
        curr_count = 1
        
        direction = 1 
        if highs[1] > highs[0]:
            direction = 1
        elif highs[1] < highs[0]:
            direction = -1
            
        count = 0 # 结果数组计数器
        
        i = 1
        while i < n:
            next_h = highs[i]
            next_l = lows[i]
            next_o = opens[i]
            next_c = closes[i]
            
            # 左包右 或 右包左
            c1_in_c2 = (curr_h >= next_h) and (curr_l <= next_l)
            c2_in_c1 = (next_h >= curr_h) and (next_l <= curr_l)
            
            if c1_in_c2 or c2_in_c1:
                curr_count += 1
                if direction == 1:
                    curr_h = max(curr_h, next_h)
                    curr_l = max(curr_l, next_l)
                else:
                    curr_h = min(curr_h, next_h)
                    curr_l = min(curr_l, next_l)
                
                curr_o = next_o
                curr_c = next_c
                curr_idx = i
            else:
                res_h[count] = curr_h
                res_l[count] = curr_l
                res_o[count] = curr_o
                res_c[count] = curr_c
                res_idx[count] = curr_idx
                res_counts[count] = curr_count
                count += 1
                
                if next_h > curr_h:
                    direction = 1
                elif next_h < curr_h:
                    direction = -1
                
                curr_h = next_h
                curr_l = next_l
                curr_o = next_o
                curr_c = next_c
                curr_idx = i
                curr_count = 1
            
            i += 1
            
        # Add last
        res_h[count] = curr_h
        res_l[count] = curr_l
        res_o[count] = curr_o
        res_c[count] = curr_c
        res_idx[count] = curr_idx
        res_counts[count] = curr_count
        count += 1
        
        return res_h[:count], res_l[:count], res_o[:count], res_c[:count], res_idx[:count], res_counts[:count]

    _process_containment = _process_containment_numba
else:
    _process_containment = _process_containment_python

# -----------------------------------------------------------------------------
# 2. Fractal Detection (分型识别)
# -----------------------------------------------------------------------------

def _detect_fractals_python(highs, lows, counts):
    """
    检测分型（纯Python实现）
    增加：
    1. K线数量限制 (3-9根)
    2. 强力分型判断 (Strong)
    """
    n = len(highs)
    top_fractals = np.zeros(n, dtype=np.int32)    # 0=None, 1=Normal, 2=Strong
    bottom_fractals = np.zeros(n, dtype=np.int32)
    
    if n < 3:
        return top_fractals, bottom_fractals
    
    for i in range(1, n - 1):
        # 基础分型定义: 中间高点最高，中间低点最高(顶); 中间高点最低，中间低点最低(底)
        is_top = (highs[i] > highs[i-1]) and (highs[i] > highs[i+1]) and \
                 (lows[i] > lows[i-1]) and (lows[i] > lows[i+1])
                 
        is_bottom = (highs[i] < highs[i-1]) and (highs[i] < highs[i+1]) and \
                    (lows[i] < lows[i-1]) and (lows[i] < lows[i+1])
        
        # 数量限制: 左+中+右 原始K线数量在 3-9 之间
        total_k = counts[i-1] + counts[i] + counts[i+1]
        valid_count = (total_k >= 3) and (total_k <= 9)
        
        if valid_count:
            if is_top:
                # 强力分型判断: 第3根收盘(或低点) 跌破 第1根的低点? 
                # 这里我们没有传入Closes，暂时用Low判断，或者认为只要分型成立且跌幅大
                # 定义强力顶分型: 右边K线跌破左边K线的低点 (Gap down or strong push)
                is_strong = lows[i+1] < lows[i-1] 
                top_fractals[i] = 2 if is_strong else 1
                
            if is_bottom:
                # 强力底分型: 右边K线升破左边K线的高点
                is_strong = highs[i+1] > highs[i-1]
                bottom_fractals[i] = 2 if is_strong else 1
            
    return top_fractals, bottom_fractals

if HAS_NUMBA:
    @jit(nopython=True)
    def _detect_fractals_numba(highs, lows, counts):
        n = len(highs)
        top_fractals = np.zeros(n, dtype=np.int32)
        bottom_fractals = np.zeros(n, dtype=np.int32)
        
        if n < 3:
            return top_fractals, bottom_fractals
        
        for i in range(1, n - 1):
            is_top = (highs[i] > highs[i-1]) and (highs[i] > highs[i+1]) and \
                     (lows[i] > lows[i-1]) and (lows[i] > lows[i+1])
                     
            is_bottom = (highs[i] < highs[i-1]) and (highs[i] < highs[i+1]) and \
                        (lows[i] < lows[i-1]) and (lows[i] < lows[i+1])
            
            total_k = counts[i-1] + counts[i] + counts[i+1]
            valid_count = (total_k >= 3) and (total_k <= 9)
            
            if valid_count:
                if is_top:
                    is_strong = lows[i+1] < lows[i-1]
                    top_fractals[i] = 2 if is_strong else 1
                if is_bottom:
                    is_strong = highs[i+1] > highs[i-1]
                    bottom_fractals[i] = 2 if is_strong else 1
                    
        return top_fractals, bottom_fractals

    _detect_fractals = _detect_fractals_numba
else:
    _detect_fractals = _detect_fractals_python

# -----------------------------------------------------------------------------
# 2.5 Bi (Stroke) Detection (笔识别)
# -----------------------------------------------------------------------------

def _check_momentum(start_idx, end_idx, direction, highs, lows):
    """
    检查动量：统计区间内创新高/新低的次数
    Args:
        start_idx: 笔起点
        end_idx: 笔终点
        direction: 1=Up, -1=Down
    Returns:
        bool: 是否满足动量要求(>=4次突破)
    """
    count = 0
    if direction == 1: # Up
        current_max = highs[start_idx]
        # 从起点后一根开始遍历到终点
        for k in range(start_idx + 1, end_idx + 1):
            if highs[k] > current_max:
                count += 1
                current_max = highs[k]
    else: # Down
        current_min = lows[start_idx]
        for k in range(start_idx + 1, end_idx + 1):
            if lows[k] < current_min:
                count += 1
                current_min = lows[k]
                
    return count >= 4

def _detect_bi_python(fractal_indices, fractal_types, highs, lows, valid_indices):
    """
    识别笔 (Python实现) - 增强版
    规则：
    1. 顶底交替
    2. 至少4根K线距离 (index diff >= 4)
    3. 动量过滤：一笔内必须至少有4次创新高(上笔)或创新低(下笔)
    4. 延伸逻辑：在未确认反向笔之前，如果出现更高顶(向上笔)或更低底(向下笔)，则延伸
    """
    bi_list = []
    if len(fractal_indices) < 2:
        return bi_list

    # 当前笔的潜在起点
    curr_start_idx = fractal_indices[0]
    curr_start_type = fractal_types[0] # 1=Top, -1=Bottom
    
    # 当前笔的潜在终点 (Candidate)
    candidate_idx = None
    candidate_type = 0
    
    i = 1
    while i < len(fractal_indices):
        next_idx = fractal_indices[i]
        next_type = fractal_types[i]
        
        # Case A: 当前起点是底(-1)，寻找顶(1)
        if curr_start_type == -1:
            if next_type == 1: # 遇到顶
                # 验证基本条件
                dist_ok = (next_idx - curr_start_idx) >= 4
                price_ok = highs[next_idx] > lows[curr_start_idx]
                
                if dist_ok and price_ok:
                    # 验证动量
                    momentum_ok = _check_momentum(curr_start_idx, next_idx, 1, highs, lows)
                    
                    if momentum_ok:
                        if candidate_idx is None:
                            # 发现第一个候选顶
                            candidate_idx = next_idx
                            candidate_type = 1
                        else:
                            # 已有候选顶，检查是否延伸 (Higher High)
                            if highs[next_idx] > highs[candidate_idx]:
                                candidate_idx = next_idx
                                # 即使后面跌破了，但只要没成笔，更高的顶就是更好的终点
            
            elif next_type == -1: # 遇到另一个底
                if candidate_idx is not None:
                    # 检查 候选顶 -> 新底 是否构成一笔 (确认上一笔)
                    dist_ok = (next_idx - candidate_idx) >= 4
                    price_ok = lows[next_idx] < highs[candidate_idx]
                    momentum_ok = _check_momentum(candidate_idx, next_idx, -1, highs, lows)
                    
                    if dist_ok and price_ok and momentum_ok:
                        # === 确认上一笔 (底 -> 候选顶) ===
                        bi_list.append({
                            'start_idx': curr_start_idx,
                            'end_idx': candidate_idx,
                            'type': 1, # Up
                            'start_price': lows[curr_start_idx],
                            'end_price': highs[candidate_idx]
                        })
                        # 状态流转
                        curr_start_idx = candidate_idx
                        curr_start_type = 1 # 新起点是顶
                        
                        candidate_idx = next_idx # 新候选是底
                        candidate_type = -1
                    else:
                        # 新底无法确认向下笔
                        # 检查是否跌破原起点？如果跌破原起点，且之前没成笔，说明原起点选错了（或者趋势延续）
                        if lows[next_idx] < lows[curr_start_idx]:
                             # 这里比较复杂。标准缠论中，如果没成笔就跌破底，说明前一笔向下笔还在延伸。
                             # 但我们这里假设curr_start_idx是确定的起点。
                             # 如果没成笔，我们忽略这个底，继续看是否有更高顶。
                             pass
                else:
                    # 还没有候选顶，就出现了新底
                    # 如果新底更低，说明之前的底不是最低，更新起点
                    if lows[next_idx] < lows[curr_start_idx]:
                        curr_start_idx = next_idx

        # Case B: 当前起点是顶(1)，寻找底(-1)
        elif curr_start_type == 1:
            if next_type == -1: # 遇到底
                dist_ok = (next_idx - curr_start_idx) >= 4
                price_ok = lows[next_idx] < highs[curr_start_idx]
                
                if dist_ok and price_ok:
                    # 验证动量
                    momentum_ok = _check_momentum(curr_start_idx, next_idx, -1, highs, lows)
                    
                    if momentum_ok:
                        if candidate_idx is None:
                            candidate_idx = next_idx
                            candidate_type = -1
                        else:
                            # 延伸：更低的底
                            if lows[next_idx] < lows[candidate_idx]:
                                candidate_idx = next_idx
            
            elif next_type == 1: # 遇到另一个顶
                if candidate_idx is not None:
                    # 检查 候选底 -> 新顶 是否构成一笔
                    dist_ok = (next_idx - candidate_idx) >= 4
                    price_ok = highs[next_idx] > lows[candidate_idx]
                    momentum_ok = _check_momentum(candidate_idx, next_idx, 1, highs, lows)
                    
                    if dist_ok and price_ok and momentum_ok:
                        # === 确认上一笔 (顶 -> 候选底) ===
                        bi_list.append({
                            'start_idx': curr_start_idx,
                            'end_idx': candidate_idx,
                            'type': -1, # Down
                            'start_price': highs[curr_start_idx],
                            'end_price': lows[candidate_idx]
                        })
                        curr_start_idx = candidate_idx
                        curr_start_type = -1
                        
                        candidate_idx = next_idx
                        candidate_type = 1
                else:
                    # 没有候选底，出现新顶
                    # 如果新顶更高，更新起点
                    if highs[next_idx] > highs[curr_start_idx]:
                        curr_start_idx = next_idx
                        
        i += 1
        
    # 循环结束，如果有候选笔，也加上（作为最后一笔实笔）
    if candidate_idx is not None:
        bi_list.append({
            'start_idx': curr_start_idx,
            'end_idx': candidate_idx,
            'type': candidate_type,
            'start_price': lows[curr_start_idx] if curr_start_type == -1 else highs[curr_start_idx],
            'end_price': highs[candidate_idx] if candidate_type == 1 else lows[candidate_idx]
        })
        
    return bi_list

# -----------------------------------------------------------------------------
# 3. Public API
# -----------------------------------------------------------------------------

def calculate_fractals(df: pd.DataFrame) -> pd.DataFrame:
    """
    计算分型特征
    Args:
        df: DataFrame with 'high', 'low', 'open', 'close', 'date'/'time'
    Returns:
        DataFrame with original index, plus:
        - fractal_type: 'top' / 'bottom' / 'strong_top' / 'strong_bottom' / 'single_k_top' / 'single_k_bottom'
        - is_fractal: bool
    """
    if df.empty:
        return pd.DataFrame()

    # Data Prep
    highs = df['high'].values.astype(np.float64)
    lows = df['low'].values.astype(np.float64)
    opens = df['open'].values.astype(np.float64)
    closes = df['close'].values.astype(np.float64)
    
    # 1. Standard Fractals with Inclusion
    p_highs, p_lows, p_opens, p_closes, valid_indices, counts = _process_containment(highs, lows, opens, closes)
    top_flags, bottom_flags = _detect_fractals(p_highs, p_lows, counts)
    
    result = df.copy()
    result['fractal_type'] = None
    result['is_fractal'] = False
    
    fractal_types = np.array([None] * len(df), dtype=object)
    
    # Fill Standard Fractals
    for i in range(len(valid_indices)):
        orig_idx = valid_indices[i]
        
        if top_flags[i] > 0:
            val = top_flags[i]
            if val == 4: # Strong + SingleK
                fractal_types[orig_idx] = 'strong_top' # Prioritize Strong? Or create new type 'strong_single_k_top'?
                # For simplicity, let's map: 1=top, 2=strong_top, 3=single_k_top, 4=strong_top (or single_k_top?)
                # User asked for "Single K labeled 'Dan'", "Strong labeled 'Qiang'".
                # If both, maybe "Qiang"?
                fractal_types[orig_idx] = 'strong_top'
            elif val == 3:
                fractal_types[orig_idx] = 'single_k_top'
            elif val == 2:
                fractal_types[orig_idx] = 'strong_top'
            else:
                fractal_types[orig_idx] = 'top'
                
        elif bottom_flags[i] > 0:
            val = bottom_flags[i]
            if val == 4:
                fractal_types[orig_idx] = 'strong_bottom'
            elif val == 3:
                fractal_types[orig_idx] = 'single_k_bottom'
            elif val == 2:
                fractal_types[orig_idx] = 'strong_bottom'
            else:
                fractal_types[orig_idx] = 'bottom'

    # 2. Single K Reversal (单K反转/反包) - Check on Raw Data
    # 逻辑: 一根K线反包前2根 或 强势反包前1根
    n = len(df)
    for i in range(2, n):
        # 单K反转顶: 创新高后收盘新低 (穿头破脚)
        if (highs[i] > highs[i-1]) and (lows[i] < lows[i-1]) and (closes[i] < lows[i-1]):
             fractal_types[i] = 'single_k_top'
             
        # 单K反转底: 创新低后收盘新高 (穿头破脚)
        # 1. L[i] < L[i-1] (创新低)
        # 2. Close[i] > High[i-1] (收盘站上最高，强势)
        elif (lows[i] < lows[i-1]) and (closes[i] > highs[i-1]):
             fractal_types[i] = 'single_k_bottom'
            
    result['fractal_type'] = fractal_types
    result['is_fractal'] = result['fractal_type'].notnull()
    
    return result

def calculate_central_pivots(bi_list: List[Dict]) -> List[Dict]:
    """
    识别中枢 (Central Pivots)
    定义：至少三笔重叠部分
    """
    pivots = []
    if len(bi_list) < 3:
        return pivots
        
    # Sliding window of 3 bis
    for i in range(len(bi_list) - 2):
        b1 = bi_list[i]
        b2 = bi_list[i+1]
        b3 = bi_list[i+2]
        
        # Determine overlap range
        # High of the low points
        # ZG = min(Highs), ZD = max(Lows) of the overlap
        
        h1 = max(b1['start_price'], b1['end_price'])
        l1 = min(b1['start_price'], b1['end_price'])
        h2 = max(b2['start_price'], b2['end_price'])
        l2 = min(b2['start_price'], b2['end_price'])
        h3 = max(b3['start_price'], b3['end_price'])
        l3 = min(b3['start_price'], b3['end_price'])
        
        zg = min(h1, h2, h3)
        zd = max(l1, l2, l3)
        
        if zg > zd:
            pivots.append({
                'start_bi_idx': i,
                'end_bi_idx': i+2, # Initial pivot covers 3 bis
                'zg': zg,
                'zd': zd,
                'start_dt': b1.get('start_dt', ''),
                'end_dt': b3.get('end_dt', '')
            })
            # Note: Real pivots can extend. This is a simplified "Atomic Pivot" detection.
            
    return pivots

def check_buy_sell_points(bi_list: List[Dict], pivots: List[Dict]) -> Dict:
    """
    识别买卖点 (2买, 3买)
    基于最后一笔的状态
    """
    res = {'buy_type': None, 'desc': ''}
    if len(bi_list) < 3:
        return res
        
    last_bi = bi_list[-1]
    
    # 必须是向下笔结束（准备买入）
    if last_bi['type'] != 'down':
        return res
    
    current_idx = len(bi_list) - 1 # Last bi index
    
    # --- 3买 (3B) 优先检查 ---
    # 结构：中枢 -> 离开笔(Up) -> 回调笔(Down) 不触及 ZG
    # 寻找最近的一个有效中枢（必须在离开笔之前结束）
    # 离开笔是 last_bi的前一笔 (current_idx - 1)
    # 所以中枢必须结束于 current_idx - 2 或更早
    
    valid_3b_pivot = None
    if pivots:
        for p in reversed(pivots):
            if p['end_bi_idx'] <= current_idx - 2:
                valid_3b_pivot = p
                break
    
    if valid_3b_pivot:
        leave_bi = bi_list[-2] # 倒数第二笔
        return_bi = bi_list[-1] # 最后一笔
        
        # 离开笔必须是向上
        if leave_bi['type'] == 'up':
            # 离开笔的高点必须有效突破中枢ZG (有一定的力度)
            if leave_bi['end_price'] > valid_3b_pivot['zg']:
                # 回调笔不触及中枢ZG
                if return_bi['end_price'] > valid_3b_pivot['zg']:
                    res['buy_type'] = '3B'
                    res['desc'] = f"三买: 回调不破中枢高点 (Low: {return_bi['end_price']:.2f} > ZG: {valid_3b_pivot['zg']:.2f})"
                    return res

    # --- 2买 (2B) ---
    # 结构：下跌(A) -> 上涨(B, 一买) -> 下跌(C, 二买)
    # C.low > A.low
    
    # 倒数第3笔 (A)
    bi_a = bi_list[-3]
    # 倒数第2笔 (B)
    bi_b = bi_list[-2]
    # 倒数第1笔 (C)
    bi_c = last_bi
    
    if bi_a['type'] == 'down' and bi_b['type'] == 'up' and bi_c['type'] == 'down':
        if bi_c['end_price'] > bi_a['end_price']:
            # 潜在二买
            res['buy_type'] = '2B'
            res['desc'] = f"二买: 回调不破低 (Low: {bi_c['end_price']:.2f} > {bi_a['end_price']:.2f})"
            return res

    return res

def calculate_bi(df: pd.DataFrame) -> List[Dict[str, Union[int, float, str]]]:
    """
    计算笔 (Stroke)
    Args:
        df: 包含分型信息的DataFrame (通常是calculate_fractals的输出)
            需要包含: 'high', 'low', 'fractal_type', 'date'/'time'
    Returns:
        List of Bi dicts
    """
    if df.empty or 'fractal_type' not in df.columns:
        # Try calculating fractals first if not present
        if not df.empty and 'high' in df.columns:
             df = calculate_fractals(df)
        else:
             return []

    # 提取分型点
    # valid_indices 是包含处理后的索引，这里我们需要原始索引
    # 只需要遍历 df 找到 is_fractal=True 的行
    
    # 构造输入给 _detect_bi 的数据
    fractal_rows = df[df['is_fractal']].copy()
    if fractal_rows.empty:
        return []
    
    # 关键修复: 将DataFrame索引映射到0-based数组索引
    # 创建索引映射: original_idx -> array_position
    df_reset = df.reset_index(drop=True)
    idx_map = {orig_idx: pos for pos, orig_idx in enumerate(df.index)}
    
    # 将fractal_indices转换为数组位置
    fractal_indices = np.array([idx_map[idx] for idx in fractal_rows.index.values])
    
    # Type mapping: top/strong_top -> 1, bottom/strong_bottom -> -1
    type_map = {
        'top': 1, 'strong_top': 1, 'single_k_top': 1,
        'bottom': -1, 'strong_bottom': -1, 'single_k_bottom': -1
    }
    fractal_types = fractal_rows['fractal_type'].map(type_map).fillna(0).values.astype(int)
    
    # 使用reset后的数组(0-based索引)
    highs = df_reset['high'].values
    lows = df_reset['low'].values
    
    # Call core logic
    bi_list = _detect_bi_python(fractal_indices, fractal_types, highs, lows, None)
    
    # -------------------------------------------------------------------------
    # 4. Post-processing: Extension & Virtual Pen
    # -------------------------------------------------------------------------
    if bi_list:
        last_bi = bi_list[-1]
        last_idx = int(last_bi['end_idx'])
        last_type = int(last_bi['type']) # 1=Up, -1=Down
        last_price = float(last_bi['end_price'])
        
        n = len(df)
        
        # 索引边界检查：确保 last_idx 在有效范围内
        if last_idx >= n:
            last_idx = n - 1
        
        # A. Continuation (Extension) Logic
        # Extend the last pen if the price continues in the same direction beyond the current endpoint
        if last_idx < n - 1:
            if last_type == 1: # Up Pen -> Check for Higher High
                # 确保索引不越界
                start_slice = min(last_idx + 1, n)
                future_highs = highs[start_slice:n]
                if len(future_highs) > 0:
                    max_h = np.max(future_highs)
                    if max_h > last_price:
                        # Found extension
                        offset = np.argmax(future_highs)
                        new_end_idx = start_slice + offset
                        
                        # 确保不超过数组边界
                        if new_end_idx < n:
                            # Update last_bi
                            last_bi['end_idx'] = new_end_idx
                            last_bi['end_price'] = max_h
                            
                            # Update local vars
                            last_idx = new_end_idx
                            last_price = max_h
            
            else: # Down Pen -> Check for Lower Low
                start_slice = min(last_idx + 1, n)
                future_lows = lows[start_slice:n]
                if len(future_lows) > 0:
                    min_l = np.min(future_lows)
                    if min_l < last_price:
                        # Found extension
                        offset = np.argmin(future_lows)
                        new_end_idx = start_slice + offset
                        
                        # 确保不超过数组边界
                        if new_end_idx < n:
                            # Update last_bi
                            last_bi['end_idx'] = new_end_idx
                            last_bi['end_price'] = min_l
                            
                            # Update local vars
                            last_idx = new_end_idx
                            last_price = min_l

        # B. Virtual Reverse Pen Logic
        # If not at the very end, create a temporary reverse pen to the latest bar
        if last_idx < n - 1:
            start_idx = last_idx
            end_idx = n - 1
            
            # Direction is opposite
            direction = -1 if last_type == 1 else 1
            
            # 索引边界检查
            if end_idx < n:
                # End Price: High for Up, Low for Down (or use Close if preferred, but High/Low is standard)
                end_price = highs[end_idx] if direction == 1 else lows[end_idx]
                
                # Validation for Solid vs Dashed
                # 1. Price Direction Validity
                price_valid = False
                if direction == 1: # Up
                    price_valid = end_price > last_price
                else: # Down
                    price_valid = end_price < last_price
                    
                # 2. Distance Validity (>= 4 bars)
                dist_valid = (end_idx - start_idx) >= 4
                
                # If both valid, it's a "Temporary Confirmed" pen (Solid)
                # Otherwise, it's a "Virtual" pen (Dashed)
                is_virtual = not (dist_valid and price_valid)
                
                bi_list.append({
                    'start_idx': start_idx,
                    'end_idx': end_idx,
                    'type': direction,
                    'start_price': last_price,
                    'end_price': end_price,
                    'is_virtual': is_virtual
                })

    # Enrich with dates
    # Assuming df has 'date' or 'time'
    date_col = 'date' if 'date' in df.columns else ('time' if 'time' in df.columns else None)
    
    enriched_bi = []
    for bi in bi_list:
        s_idx = int(bi['start_idx'])
        e_idx = int(bi['end_idx'])
        
        # 索引边界检查
        if s_idx >= len(df):
            s_idx = len(df) - 1
        if e_idx >= len(df):
            e_idx = len(df) - 1
        
        item = {
            'start_idx': s_idx,
            'end_idx': e_idx,
            'start_price': float(bi['start_price']),
            'end_price': float(bi['end_price']),
            'type': 'up' if bi['type'] == 1 else 'down',
            'amplitude': float((bi['end_price'] - bi['start_price']) / bi['start_price']) if bi['start_price'] != 0 else 0.0,
            'is_virtual': bi.get('is_virtual', False)
        }
        
        if date_col:
            item['start_dt'] = str(df.iloc[s_idx][date_col])
            item['end_dt'] = str(df.iloc[e_idx][date_col])
            
        enriched_bi.append(item)
    
    return enriched_bi

# -----------------------------------------------------------------------------
# 4. Zhongshu (Center/Hub) Detection (中枢识别)
# -----------------------------------------------------------------------------

def calculate_zhongshu(bi_list: List[Dict]) -> List[Dict]:
    """
    识别笔中枢 (严格三笔模式)
    
    规则：
    1. 三笔方向交替（如：上-下-上 或 下-上-下）
    2. 第2笔的价格区间与第1笔、第3笔均有重叠
    3. 重叠部分即为中枢区间 [ZD, ZG]
    
    Args:
        bi_list: 笔列表，每笔包含 {start_idx, end_idx, start_price, end_price, direction}
    
    Returns:
        List of Zhongshu dicts:
        {
            'zg': 中枢上沿,
            'zd': 中枢下沿,
            'start_idx': 中枢起始K线索引,
            'end_idx': 中枢结束K线索引,
            'start_bi_idx': 起始笔在bi_list中的索引,
            'end_bi_idx': 结束笔在bi_list中的索引,
            'bi_count': 构成中枢的笔数,
            'direction': 中枢方向 ('up'=上涨中枢, 'down'=下跌中枢)
        }
    """
    zhongshu_list = []
    
    if len(bi_list) < 3:
        return zhongshu_list
    
    # 遍历寻找连续三笔构成的中枢
    i = 0
    while i <= len(bi_list) - 3:
        bi1 = bi_list[i]
        bi2 = bi_list[i + 1]
        bi3 = bi_list[i + 2]
        
        # 检查方向交替
        # Use .get() for safety since we switched to 'type'
        dir1 = bi1.get('type')
        dir2 = bi2.get('type')
        dir3 = bi3.get('type')
        
        if not (dir1 != dir2 and dir2 != dir3):
            i += 1
            continue
        
        # 计算每笔的高低点
        def get_bi_range(bi):
            return (min(bi['start_price'], bi['end_price']), 
                    max(bi['start_price'], bi['end_price']))
        
        low1, high1 = get_bi_range(bi1)
        low2, high2 = get_bi_range(bi2)
        low3, high3 = get_bi_range(bi3)
        
        # 计算三笔的重叠区间
        # 中枢下沿 ZD = max(三笔的低点)
        # 中枢上沿 ZG = min(三笔的高点)
        zd = max(low1, low2, low3)
        zg = min(high1, high2, high3)
        
        # 如果 ZG > ZD，则存在有效中枢
        if zg > zd:
            # 确定中枢方向：看第一笔方向
            # 如果第一笔向上，则是上涨趋势中的中枢（回调）
            # 如果第一笔向下，则是下跌趋势中的中枢（反弹）
            zs_direction = 'up' if dir1 == 'up' else 'down'
            
            zhongshu = {
                'zg': zg,
                'zd': zd,
                'start_idx': bi1['start_idx'],
                'end_idx': bi3['end_idx'],
                'start_bi_idx': i,
                'end_bi_idx': i + 2,
                'bi_count': 3,
                'direction': zs_direction
            }
            zhongshu_list.append(zhongshu)
            
            # 跳过已处理的笔（中枢不重叠）
            i += 3
        else:
            i += 1
    
    return zhongshu_list


# -----------------------------------------------------------------------------
# 5. Divergence Detection (背驰检测)
# -----------------------------------------------------------------------------

def _calculate_macd_area(closes: np.ndarray, start_idx: int, end_idx: int) -> float:
    """
    计算区间内MACD柱状图面积
    使用简化MACD: EMA12 - EMA26
    """
    # 索引边界检查
    if end_idx <= start_idx or start_idx < 0:
        return 0.0
    
    # 确保索引在有效范围内
    if end_idx >= len(closes):
        end_idx = len(closes) - 1
    if start_idx >= len(closes):
        start_idx = len(closes) - 1
    
    # 需要足够的历史数据计算EMA
    lookback = max(0, start_idx - 30)
    segment = closes[lookback:end_idx + 1]
    
    if len(segment) < 26:
        # 数据不足，使用价格变化替代
        return abs(closes[end_idx] - closes[start_idx])
    
    # 计算EMA
    def ema(data, period):
        alpha = 2 / (period + 1)
        result = np.zeros(len(data))
        result[0] = data[0]
        for i in range(1, len(data)):
            result[i] = alpha * data[i] + (1 - alpha) * result[i-1]
        return result
    
    ema12 = ema(segment, 12)
    ema26 = ema(segment, 26)
    dif = ema12 - ema26
    
    # 只取 start_idx 到 end_idx 对应的部分
    offset = start_idx - lookback
    if offset < 0:
        offset = 0
    if offset >= len(dif):
        return 0.0
    
    dif_segment = dif[offset:]
    
    # 计算面积（绝对值之和）
    return float(np.sum(np.abs(dif_segment)))


def check_divergence(bi1: Dict, bi2: Dict, closes: np.ndarray) -> Tuple[bool, float]:
    """
    检测两笔之间是否存在背驰
    
    综合评分方法 (MACD面积 + 速率):
    - MACD面积: 第二笔的MACD面积 < 第一笔
    - 速率: 第二笔的价格变化/K线数 < 第一笔
    
    Args:
        bi1: 第一笔 (推动笔)
        bi2: 第二笔 (背驰候选笔，同向)
        closes: 收盘价数组
    
    Returns:
        (is_divergence, divergence_score)
        - is_divergence: 是否背驰
        - divergence_score: 背驰强度 (0-1, 越大背驰越明显)
    """
    # 确保两笔同向
    # Use .get() for safety
    if bi1.get('type') != bi2.get('type'):
        return False, 0.0
    
    # 1. MACD面积对比
    area1 = _calculate_macd_area(closes, bi1['start_idx'], bi1['end_idx'])
    area2 = _calculate_macd_area(closes, bi2['start_idx'], bi2['end_idx'])
    
    if area1 == 0:
        macd_ratio = 1.0
    else:
        macd_ratio = area2 / area1
    
    # 2. 速率对比 (幅度/K线数)
    amp1 = abs(bi1['end_price'] - bi1['start_price'])
    amp2 = abs(bi2['end_price'] - bi2['start_price'])
    
    bars1 = max(1, bi1['end_idx'] - bi1['start_idx'])
    bars2 = max(1, bi2['end_idx'] - bi2['start_idx'])
    
    speed1 = amp1 / bars1
    speed2 = amp2 / bars2
    
    if speed1 == 0:
        speed_ratio = 1.0
    else:
        speed_ratio = speed2 / speed1
    
    # 3. 综合评分 (权重: MACD 60%, 速率 40%)
    # 比值越小，背驰越明显
    combined_ratio = 0.6 * macd_ratio + 0.4 * speed_ratio
    
    # 背驰判定: 综合比值 < 0.8 认为背驰
    is_divergence = combined_ratio < 0.8
    
    # 背驰强度: 1 - combined_ratio (限制在0-1之间)
    divergence_score = max(0.0, min(1.0, 1.0 - combined_ratio))
    
    return is_divergence, divergence_score


# -----------------------------------------------------------------------------
# 6. Buy Point Detection (买点识别: 1买/2买/3买)
# -----------------------------------------------------------------------------

def detect_buy_points(df: pd.DataFrame, bi_list: List[Dict], 
                      zhongshu_list: List[Dict] = None) -> List[Dict]:
    """
    识别缠论买点 (1买/2买/3买)
    
    定义：
    - 1买: 下跌趋势结束时的背驰点（至少两段下跌笔，第二段创新低但力度减弱）
    - 2买: 1买之后，回调不破1买低点的再次买点
    - 3买: 中枢突破后的回抽不进入中枢的买点
    
    Args:
        df: K线DataFrame，需要包含 'close', 'high', 'low'
        bi_list: 笔列表
        zhongshu_list: 中枢列表（如果为None则自动计算）
    
    Returns:
        List of Buy Point dicts:
        {
            'type': '1B' / '2B' / '3B',
            'idx': K线索引,
            'price': 买点价格,
            'confidence': 置信度 (0-1),
            'is_confirmed': 是否已确认 (False表示潜在买点),
            'related_bi': 相关笔的索引列表,
            'related_zhongshu': 相关中枢的索引 (3买时有效),
            'divergence_score': 背驰强度 (1买时有效)
        }
    """
    buy_points = []
    
    if len(bi_list) < 2:
        return buy_points
    
    closes = df['close'].values
    lows = df['low'].values
    highs = df['high'].values
    n = len(df)
    
    # 如果没有提供中枢，自动计算
    if zhongshu_list is None:
        zhongshu_list = calculate_zhongshu(bi_list)
    
    # =========================================================================
    # 1买检测: 下跌趋势背驰
    # =========================================================================
    found_1b = []  # 记录已找到的1买，用于后续2买检测
    
    for i in range(1, len(bi_list)):
        curr_bi = bi_list[i]
        prev_bi = bi_list[i - 1]
        
        # 条件1: 当前笔是下跌笔
        if curr_bi.get('type') != 'down':
            continue
        
        # 条件2: 前一笔也是下跌笔（需要至少两段下跌构成趋势）
        # 实际上是隔一笔：第i-2笔是下跌，第i-1笔是上涨（反弹），第i笔是下跌
        if i < 2:
            continue
        
        prev_down_bi = None
        for j in range(i - 1, -1, -1):
            if bi_list[j].get('type') == 'down':
                prev_down_bi = bi_list[j]
                break
        
        if prev_down_bi is None:
            continue
        
        # 条件3: 当前下跌笔创新低
        if curr_bi['end_price'] >= prev_down_bi['end_price']:
            continue
        
        # 条件4: 检测背驰
        is_div, div_score = check_divergence(prev_down_bi, curr_bi, closes)
        
        if is_div:
            # 1买确认：背驰后的底分型确认点
            buy_idx = curr_bi['end_idx']
            buy_price = curr_bi['end_price']
            
            # 检查是否已确认（后续有上涨笔）
            is_confirmed = False
            if i < len(bi_list) - 1:
                next_bi = bi_list[i + 1]
                if next_bi.get('type') == 'up':
                    is_confirmed = True
            
            bp = {
                'type': '1B',
                'idx': buy_idx,
                'price': buy_price,
                'confidence': min(1.0, 0.5 + div_score * 0.5),  # 背驰越强置信度越高
                'is_confirmed': is_confirmed,
                'related_bi': [i - 1, i] if i > 0 else [i],
                'related_zhongshu': None,
                'divergence_score': div_score
            }
            buy_points.append(bp)
            found_1b.append(bp)
    
    # =========================================================================
    # 2买检测: 1买后回调不破1买低点
    # =========================================================================
    for bp1 in found_1b:
        bp1_idx = bp1['idx']
        bp1_price = bp1['price']
        
        # 寻找1买之后的下跌笔
        for i, bi in enumerate(bi_list):
            if bi['start_idx'] <= bp1_idx:
                continue
            
            if bi.get('type') != 'down':
                continue
            
            # 条件: 回调低点 > 1买低点
            if bi['end_price'] > bp1_price:
                # 检查是否已确认（后续有上涨突破回调高点）
                is_confirmed = False
                if i < len(bi_list) - 1:
                    next_bi = bi_list[i + 1]
                    if next_bi.get('type') == 'up':
                        # 简化确认：有上涨笔即认为确认
                        is_confirmed = True
                
                # 计算置信度：回调幅度越小，置信度越高
                if bp1_price > 0:
                    retrace_ratio = (bi['start_price'] - bi['end_price']) / (bi['start_price'] - bp1_price)
                    confidence = max(0.3, min(0.9, 1.0 - retrace_ratio * 0.5))
                else:
                    confidence = 0.5
                
                bp = {
                    'type': '2B',
                    'idx': bi['end_idx'],
                    'price': bi['end_price'],
                    'confidence': confidence,
                    'is_confirmed': is_confirmed,
                    'related_bi': [i],
                    'related_zhongshu': None,
                    'divergence_score': 0.0
                }
                buy_points.append(bp)
                break  # 每个1买只找第一个2买
    
    # =========================================================================
    # 3买检测: 中枢突破后回抽不进入中枢
    # =========================================================================
    for zs_idx, zs in enumerate(zhongshu_list):
        zg = zs['zg']  # 中枢上沿
        zd = zs['zd']  # 中枢下沿
        zs_end_idx = zs['end_idx']
        
        # 寻找中枢之后的笔
        breakthrough_bi = None  # 突破笔
        pullback_bi = None      # 回抽笔
        
        for i, bi in enumerate(bi_list):
            if bi['start_idx'] <= zs_end_idx:
                continue
            
            # 寻找向上突破中枢上沿的笔
            if breakthrough_bi is None:
                if bi.get('type') == 'up' and bi['end_price'] > zg:
                    breakthrough_bi = (i, bi)
                continue
            
            # 寻找突破后的回抽笔
            if bi.get('type') == 'down':
                pullback_bi = (i, bi)
                break
        
        if breakthrough_bi is None or pullback_bi is None:
            continue
        
        bt_i, bt_bi = breakthrough_bi
        pb_i, pb_bi = pullback_bi
        
        # 条件: 回抽低点 > 中枢上沿 (不进入中枢)
        if pb_bi['end_price'] > zg:
            # 检查是否已确认
            is_confirmed = False
            if pb_i < len(bi_list) - 1:
                next_bi = bi_list[pb_i + 1]
                if next_bi.get('type') == 'up':
                    is_confirmed = True
            
            # 置信度：回抽离中枢上沿越远，置信度越高
            if zg > 0:
                margin_ratio = (pb_bi['end_price'] - zg) / zg
                confidence = max(0.4, min(0.95, 0.6 + margin_ratio * 5))
            else:
                confidence = 0.5
            
            bp = {
                'type': '3B',
                'idx': pb_bi['end_idx'],
                'price': pb_bi['end_price'],
                'confidence': confidence,
                'is_confirmed': is_confirmed,
                'related_bi': [bt_i, pb_i],
                'related_zhongshu': zs_idx,
                'divergence_score': 0.0
            }
            buy_points.append(bp)
    
    # 按索引排序
    buy_points.sort(key=lambda x: x['idx'])
    
    return buy_points


def detect_sell_points(df: pd.DataFrame, bi_list: List[Dict],
                       zhongshu_list: List[Dict] = None) -> List[Dict]:
    """
    检测1/2/3类卖点
    
    卖点定义（买点的镜像）:
    1卖: 上涨趋势结束时的背驰点（两段上涨笔，第二段新高但力度减弱）
    2卖: 1卖之后，反弹不破1卖高点的再次卖出点
    3卖: 中枢跌破后的反抽不进入中枢的卖点
    
    参数:
        df: K线数据
        bi_list: 笔列表
        zhongshu_list: 中枢列表
    
    返回:
        List[Dict]: 卖点列表，每个卖点包含 type, idx, price, confidence, is_confirmed 等
    """
    if not bi_list or len(bi_list) < 3:
        return []
    
    sell_points = []
    closes = df['close'].values if 'close' in df.columns else None
    
    # ========== 1卖: 背驰顶 ==========
    # 寻找连续上涨结构（至少两段上涨笔）
    for i in range(2, len(bi_list)):
        bi_curr = bi_list[i]
        bi_prev = bi_list[i - 2]  # 跳过中间的下跌笔
        
        # 都是上涨笔
        if bi_curr.get('type') != 'up' or bi_prev.get('type') != 'up':
            continue
        
        # 第二段创新高
        if bi_curr['end_price'] <= bi_prev['end_price']:
            continue
        
        # 检查背驰
        if closes is not None:
            is_divergence, div_score = check_divergence(bi_prev, bi_curr, closes)
        else:
            is_divergence = False
            div_score = 0.0
        
        if is_divergence:
            # 检查是否已确认（后续出现下跌笔）
            is_confirmed = False
            if i < len(bi_list) - 1:
                next_bi = bi_list[i + 1]
                if next_bi.get('type') == 'down':
                    is_confirmed = True
            
            confidence = max(0.5, min(0.95, 0.5 + div_score * 0.4))
            
            sp = {
                'type': '1S',
                'idx': bi_curr['end_idx'],
                'price': bi_curr['end_price'],
                'confidence': confidence,
                'is_confirmed': is_confirmed,
                'related_bi': [i - 2, i],
                'related_zhongshu': None,
                'divergence_score': div_score
            }
            sell_points.append(sp)
    
    # ========== 2卖: 反弹不破1卖高点 ==========
    for sp in [s for s in sell_points if s['type'] == '1S']:
        sp_idx = sp['idx']
        sp_price = sp['price']
        
        # 在1卖之后寻找：下跌笔 + 上涨笔（反弹）
        for i in range(len(bi_list)):
            bi = bi_list[i]
            if bi['start_idx'] <= sp_idx:
                continue
            
            # 找到1卖后的上涨笔（反弹）
            if bi.get('type') != 'up':
                continue
            
            # 反弹高点 < 1卖高点
            if bi['end_price'] >= sp_price:
                continue
            
            # 检查是否已确认
            is_confirmed = False
            if i < len(bi_list) - 1:
                next_bi = bi_list[i + 1]
                if next_bi.get('type') == 'down':
                    is_confirmed = True
            
            # 置信度
            margin_ratio = (sp_price - bi['end_price']) / sp_price if sp_price > 0 else 0
            confidence = max(0.4, min(0.9, 0.5 + margin_ratio * 3))
            
            sp2 = {
                'type': '2S',
                'idx': bi['end_idx'],
                'price': bi['end_price'],
                'confidence': confidence,
                'is_confirmed': is_confirmed,
                'related_bi': [i],
                'related_zhongshu': None,
                'divergence_score': 0.0
            }
            sell_points.append(sp2)
            break  # 只取第一个2卖
    
    # ========== 3卖: 跌破中枢后反抽不进入中枢 ==========
    if zhongshu_list:
        for zs_idx, zs in enumerate(zhongshu_list):
            zg = zs.get('zg', 0)  # 中枢上沿
            zd = zs.get('zd', 0)  # 中枢下沿
            zs_end_idx = zs.get('end_idx', 0)
            
            if zg <= 0 or zd <= 0:
                continue
            
            # 找中枢之后的笔
            breakdown_bi = None  # 跌破笔
            pullback_bi = None   # 反抽笔
            
            for i, bi in enumerate(bi_list):
                if bi['start_idx'] <= zs_end_idx:
                    continue
                
                # 跌破笔：下跌笔，低点 < 中枢下沿
                if breakdown_bi is None:
                    if bi.get('type') == 'down' and bi['end_price'] < zd:
                        breakdown_bi = (i, bi)
                # 反抽笔：跌破后的上涨笔
                elif pullback_bi is None:
                    if bi.get('type') == 'up':
                        pullback_bi = (i, bi)
                        break
            
            if breakdown_bi is None or pullback_bi is None:
                continue
            
            bd_i, bd_bi = breakdown_bi
            pb_i, pb_bi = pullback_bi
            
            # 条件：反抽高点 < 中枢下沿（不进入中枢）
            if pb_bi['end_price'] < zd:
                # 检查是否已确认
                is_confirmed = False
                if pb_i < len(bi_list) - 1:
                    next_bi = bi_list[pb_i + 1]
                    if next_bi.get('type') == 'down':
                        is_confirmed = True
                
                # 置信度
                if zd > 0:
                    margin_ratio = (zd - pb_bi['end_price']) / zd
                    confidence = max(0.4, min(0.95, 0.6 + margin_ratio * 5))
                else:
                    confidence = 0.5
                
                sp = {
                    'type': '3S',
                    'idx': pb_bi['end_idx'],
                    'price': pb_bi['end_price'],
                    'confidence': confidence,
                    'is_confirmed': is_confirmed,
                    'related_bi': [bd_i, pb_i],
                    'related_zhongshu': zs_idx,
                    'divergence_score': 0.0
                }
                sell_points.append(sp)
    
    # 按索引排序
    sell_points.sort(key=lambda x: x['idx'])
    
    return sell_points


def get_structure_features(df: pd.DataFrame, bi_list: List[Dict] = None) -> Dict[str, float]:
    """
    Extract Chanlun structural features for RAG Memory (Vector Store).
    
    Features (Standardized for KNN):
    - f_trend_ma20: (Close - MA20) / MA20
    - f_bi_dir: 1.0 (Up) or -1.0 (Down)
    - f_bi_amp: Amplitude of the last completed Bi
    - f_bi_extend: Current extension from last Bi end ((Close - BiEnd) / BiEnd)
    - f_vol_ratio: Volatility ratio (ATR/Price) or simple (High-Low)/Close
    - f_rsi: RSI 14 (if available or calculated)
    """
    if df.empty:
        return {}
        
    features = {}
    close = df['close'].values
    high = df['high'].values
    low = df['low'].values
    n = len(df)
    
    # 1. MA Trend
    # Simple moving average 20
    if n >= 20:
        ma20 = np.mean(close[-20:])
        features['trend_ma20'] = (close[-1] - ma20) / ma20
    else:
        features['trend_ma20'] = 0.0
        
    # 2. Bi Features
    if bi_list and len(bi_list) > 0:
        last_bi = bi_list[-1]
        features['bi_dir'] = 1.0 if last_bi.get('type') == 'up' else -1.0
        features['bi_amp'] = last_bi.get('amplitude', 0.0)
        features['bi_extend'] = (close[-1] - last_bi['end_price']) / last_bi['end_price']
    else:
        features['bi_dir'] = 0.0
        features['bi_amp'] = 0.0
        features['bi_extend'] = 0.0
        
    # 3. Volatility (High-Low)/Close
    features['volatility'] = (high[-1] - low[-1]) / close[-1]
    
    # 4. RSI (Simple approx or real)
    # Calculate last RSI-14 on the fly if not present
    if 'rsi' in df.columns:
        features['rsi'] = df['rsi'].iloc[-1] / 100.0 # Normalize 0-1
    elif n > 15:
        delta = np.diff(close[-15:])
        up = delta[delta > 0].sum()
        down = -delta[delta < 0].sum()
        if down == 0:
            features['rsi'] = 1.0
        else:
            rs = up / down
            features['rsi'] = (100 - (100 / (1 + rs))) / 100.0
    else:
        features['rsi'] = 0.5
        
    return features


# -----------------------------------------------------------------------------
# 7. Current Buy State Detection (实时买点状态机)
# -----------------------------------------------------------------------------

def _get_window_size(period: str) -> int:
    """
    根据周期动态调整窗口大小
    - 日线/周线: 7笔
    - 30分钟/60分钟: 9笔
    - 5分钟/15分钟/1分钟: 5笔
    """
    period_lower = period.lower() if period else 'daily'
    
    if period_lower in ['daily', 'weekly', 'monthly', 'd', 'w', 'm']:
        return 7
    elif period_lower in ['30m', '60m', '30min', '60min']:
        return 9
    else:  # 5m, 15m, 1m
        return 5


def detect_current_buy_state(
    df: pd.DataFrame, 
    bi_list: List[Dict],
    period: str = 'daily',
    window_size: Optional[int] = None,
    zhongshu_list: Optional[List[Dict]] = None
) -> Dict:
    """
    实时买点状态机 - 判断当下处于什么买点状态
    
    采用滑动窗口方法，分析最近 N 笔走势，结合中枢位置判断当前是否处于买点区间。
    
    算法逻辑：
    STEP 1: 获取最近 N 笔（根据周期动态调整，或使用指定窗口大小）
    STEP 2: 检查是否存在 1买：趋势底部反转
    STEP 3: 若有 1买，检查是否出现 2买：回调不破1买低点
    STEP 4: 检查 3买（优先基于中枢）：
            - 如果有中枢，检查当前下跌笔低点是否 > 中枢上沿 (ZG)
            - 如果没有中枢，检查下跌笔低点是否 > 2买低点
    STEP 5: 输出当前状态，并设置合理止损位
    
    Args:
        df: K线DataFrame，需要包含 'close', 'high', 'low'
        bi_list: 笔列表
        period: 周期 ('daily', '30m', '5m' 等)
        window_size: 可选的自定义窗口大小，如果为None则根据周期自动选择
        zhongshu_list: 可选的中枢列表，用于更准确判断3买和设置止损
    
    Returns:
        Dict:
        {
            'current_state': '1B' | '2B' | '3B' | 'none' | 'waiting',
            'confidence': 0.0-1.0,
            'trigger_price': 建议入场价,
            'stop_loss': 止损位,
            'target_price': 目标位,
            'description': 走势描述,
            'window_bi_count': 窗口内笔数,
            'window_low': 窗口最低价,
            'window_high': 窗口最高价,
            'last_bi_direction': 最后一笔方向,
            'related_zhongshu': 相关中枢信息,
            'buy_point_details': {  # 详细信息
                '1B': {'idx': ..., 'price': ..., 'confirmed': ...} or None,
                '2B': {...} or None,
                '3B': {...} or None
            }
        }
    """
    result = {
        'current_state': 'none',
        'confidence': 0.0,
        'trigger_price': None,
        'stop_loss': None,
        'target_price': None,
        'description': '数据不足，无法判断',
        'window_bi_count': 0,
        'window_low': None,
        'window_high': None,
        'last_bi_direction': None,
        'related_zhongshu': None,
        'buy_point_details': {'1B': None, '2B': None, '3B': None}
    }
    
    # 基础检查
    if df.empty or len(bi_list) < 3:
        result['description'] = f'笔数量不足（当前{len(bi_list)}笔，至少需要3笔）'
        return result
    
    # 确定窗口大小
    n_window = window_size if window_size else _get_window_size(period)
    n_window = min(n_window, len(bi_list))  # 不能超过现有笔数
    
    # 获取窗口内的笔
    window_bi = bi_list[-n_window:]
    result['window_bi_count'] = len(window_bi)
    
    # 计算窗口内的价格范围
    window_lows = [bi['end_price'] if bi.get('type') == 'down' else bi['start_price'] for bi in window_bi]
    window_highs = [bi['end_price'] if bi.get('type') == 'up' else bi['start_price'] for bi in window_bi]
    
    window_min_price = min(window_lows)
    window_max_price = max(window_highs)
    result['window_low'] = window_min_price
    result['window_high'] = window_max_price
    
    # 最后一笔信息
    last_bi = window_bi[-1]
    result['last_bi_direction'] = last_bi.get('type')
    
    # 当前价格
    current_price = df['close'].iloc[-1]
    
    # =========================================================================
    # 获取最近的中枢信息（用于3买判断和止损设置）
    # =========================================================================
    latest_zhongshu = None
    if zhongshu_list and len(zhongshu_list) > 0:
        latest_zhongshu = zhongshu_list[-1]
        result['related_zhongshu'] = {
            'zg': latest_zhongshu.get('zg') or latest_zhongshu.get('ZG'),
            'zd': latest_zhongshu.get('zd') or latest_zhongshu.get('ZD'),
            'start_date': latest_zhongshu.get('start_date'),
            'end_date': latest_zhongshu.get('end_date')
        }
    
    # =========================================================================
    # STEP 2: 检查 1买
    # =========================================================================
    one_buy = None
    
    # 找窗口内最低点对应的笔
    min_price_idx = window_lows.index(window_min_price)
    min_bi = window_bi[min_price_idx]
    
    # 1买条件：
    # 1. 最低点所在笔是下跌笔
    # 2. 该笔是窗口内最低点
    # 3. 增强：当前价格 > 最低点（有反转迹象）
    if min_bi.get('type') == 'down':
        # 检查是否已经有反转迹象
        has_reversal = current_price > window_min_price
        
        # 如果最低点就是最后一笔，且当前价格高于最低点，说明正在形成1买
        if min_price_idx == len(window_bi) - 1:
            if has_reversal:
                one_buy = {
                    'idx': min_bi.get('end_idx', 0),
                    'price': window_min_price,
                    'confirmed': False,  # 最后一笔还没确认
                    'bi_index': min_price_idx
                }
        else:
            # 最低点不是最后一笔，检查后续是否有上涨
            subsequent_bi = window_bi[min_price_idx + 1:]
            has_up_after = any(bi.get('type') == 'up' for bi in subsequent_bi)
            
            if has_up_after:
                one_buy = {
                    'idx': min_bi.get('end_idx', 0),
                    'price': window_min_price,
                    'confirmed': True,
                    'bi_index': min_price_idx
                }
    
    if one_buy:
        result['buy_point_details']['1B'] = one_buy
    
    # =========================================================================
    # STEP 3: 检查 2买
    # =========================================================================
    two_buy = None
    
    if one_buy and one_buy['confirmed']:
        # 1买已确认，检查后续是否出现2买
        # 2买条件：1买后有上涨，然后回调，回调低点 > 1买低点
        
        one_buy_idx = one_buy['bi_index']
        subsequent_bi = window_bi[one_buy_idx + 1:]
        
        # 找1买之后的下跌笔
        for i, bi in enumerate(subsequent_bi):
            if bi.get('type') == 'down':
                down_low = bi['end_price']
                
                # 2买条件：回调低点 > 1买低点
                if down_low > one_buy['price']:
                    # 检查这个下跌笔之前是否有上涨
                    prev_bi = subsequent_bi[:i]
                    has_up_before = any(b.get('type') == 'up' for b in prev_bi)
                    
                    if has_up_before or i == 0:
                        is_last = (one_buy_idx + 1 + i) == len(window_bi) - 1
                        
                        two_buy = {
                            'idx': bi.get('end_idx', 0),
                            'price': down_low,
                            'confirmed': not is_last,
                            'bi_index': one_buy_idx + 1 + i
                        }
                        break
    
    if two_buy:
        result['buy_point_details']['2B'] = two_buy
    
    # =========================================================================
    # STEP 4: 检查 3买（优先基于中枢）
    # =========================================================================
    three_buy = None
    three_buy_based_on_zhongshu = False
    zhongshu_zg = None  # 中枢上沿
    zhongshu_zd = None  # 中枢下沿
    
    # 优先检查基于中枢的3买
    if latest_zhongshu and last_bi.get('type') == 'down':
        zhongshu_zg = latest_zhongshu.get('zg') or latest_zhongshu.get('ZG')
        zhongshu_zd = latest_zhongshu.get('zd') or latest_zhongshu.get('ZD')
        
        if zhongshu_zg is not None:
            last_bi_low = last_bi['end_price']
            
            # 3买条件（基于中枢）：当前下跌笔的低点 > 中枢上沿
            # 这说明价格回踩中枢上沿不破，形成3买
            if last_bi_low > zhongshu_zg:
                three_buy = {
                    'idx': last_bi.get('end_idx', 0),
                    'price': last_bi_low,
                    'confirmed': False,  # 最后一笔总是未确认
                    'bi_index': len(window_bi) - 1,
                    'zhongshu_zg': zhongshu_zg,
                    'zhongshu_zd': zhongshu_zd
                }
                three_buy_based_on_zhongshu = True
            # 如果低点在中枢区间内（ZD < 低点 < ZG），也可能是潜在3买
            elif zhongshu_zd is not None and zhongshu_zd < last_bi_low < zhongshu_zg:
                # 在中枢区间内，观察是否能守住中枢下沿
                three_buy = {
                    'idx': last_bi.get('end_idx', 0),
                    'price': last_bi_low,
                    'confirmed': False,
                    'bi_index': len(window_bi) - 1,
                    'zhongshu_zg': zhongshu_zg,
                    'zhongshu_zd': zhongshu_zd,
                    'in_zhongshu': True  # 标记在中枢内
                }
                three_buy_based_on_zhongshu = True
    
    # 如果没有基于中枢找到3买，使用传统方法
    if not three_buy and two_buy:
        two_buy_idx = two_buy['bi_index']
        subsequent_bi = window_bi[two_buy_idx + 1:]
        
        for i, bi in enumerate(subsequent_bi):
            if bi.get('type') == 'down':
                down_low = bi['end_price']
                
                # 3买条件（传统）：低点 > 2买低点
                if down_low > two_buy['price']:
                    is_last = (two_buy_idx + 1 + i) == len(window_bi) - 1
                    
                    three_buy = {
                        'idx': bi.get('end_idx', 0),
                        'price': down_low,
                        'confirmed': not is_last,
                        'bi_index': two_buy_idx + 1 + i
                    }
                    break
    
    if three_buy:
        result['buy_point_details']['3B'] = three_buy
    
    # =========================================================================
    # STEP 5: 确定当前状态（优先3买，并合理设置止损）
    # =========================================================================
    
    # 优先判断3买（特别是基于中枢的3买）
    if three_buy and not three_buy.get('confirmed', True):
        result['current_state'] = '3B'
        result['confidence'] = 0.90 if three_buy_based_on_zhongshu else 0.85
        result['trigger_price'] = three_buy['price']
        
        # 止损设置：基于中枢的3买，止损在中枢上沿或下沿
        if three_buy_based_on_zhongshu and zhongshu_zg:
            if three_buy.get('in_zhongshu'):
                # 在中枢内，止损设在中枢下沿
                result['stop_loss'] = zhongshu_zd if zhongshu_zd else three_buy['price'] * 0.95
                result['description'] = f"当前处于3买形成区（中枢内），低点{three_buy['price']:.2f}在中枢区间[{zhongshu_zd:.2f},{zhongshu_zg:.2f}]内，止损中枢下沿{zhongshu_zd:.2f}"
            else:
                # 在中枢上方，止损设在中枢上沿
                result['stop_loss'] = zhongshu_zg
                result['description'] = f"当前处于3买形成区，低点{three_buy['price']:.2f} > 中枢上沿{zhongshu_zg:.2f}，趋势强劲，止损中枢上沿"
        else:
            # 传统3买，止损在2买低点
            result['stop_loss'] = two_buy['price'] if two_buy else (one_buy['price'] if one_buy else three_buy['price'] * 0.95)
            result['description'] = f"当前处于3买形成区，低点{three_buy['price']:.2f}未破2买低点{two_buy['price']:.2f}，趋势强劲"
        
        result['target_price'] = window_max_price * 1.05
        
    elif three_buy and three_buy.get('confirmed', False):
        result['current_state'] = '3B'
        result['confidence'] = 0.90
        result['trigger_price'] = current_price
        result['stop_loss'] = zhongshu_zg if (three_buy_based_on_zhongshu and zhongshu_zg) else three_buy['price']
        result['target_price'] = window_max_price * 1.10
        result['description'] = f"3买已确认({three_buy['price']:.2f})，处于强势上涨趋势，可持有或加仓"
        
    elif two_buy and not two_buy['confirmed']:
        result['current_state'] = '2B'
        result['confidence'] = 0.75
        result['trigger_price'] = two_buy['price']
        result['stop_loss'] = one_buy['price'] if one_buy else window_min_price
        result['target_price'] = window_max_price
        result['description'] = f"当前处于2买形成区，结构止损锚定1买低点{one_buy['price']:.2f}，当前回调低点{two_buy['price']:.2f}未破关键结构，等待确认反转"
        
    elif two_buy and two_buy['confirmed']:
        result['current_state'] = '2B'
        result['confidence'] = 0.80
        result['trigger_price'] = current_price
        result['stop_loss'] = one_buy['price'] if one_buy else window_min_price
        result['target_price'] = window_max_price * 1.05
        result['description'] = f"2买已确认({two_buy['price']:.2f})，趋势向上，关注是否形成3买"
        
    elif one_buy and not one_buy['confirmed']:
        result['current_state'] = '1B'
        result['confidence'] = 0.60
        result['trigger_price'] = one_buy['price']
        result['stop_loss'] = one_buy['price']
        result['target_price'] = window_max_price * 0.618 + window_min_price * 0.382
        result['description'] = f"当前处于1买形成区，结构止损锚定底分型低点{one_buy['price']:.2f}，观察是否企稳反转"
        
    elif one_buy and one_buy['confirmed']:
        result['current_state'] = 'waiting'
        result['confidence'] = 0.65
        result['trigger_price'] = one_buy['price'] * 1.02
        result['stop_loss'] = one_buy['price']
        result['target_price'] = window_max_price
        result['description'] = f"1买已确认({one_buy['price']:.2f})，结构止损仍锚定底分型低点，等待回调形成2买机会"
        
    else:
        if last_bi.get('type') == 'down':
            result['current_state'] = 'none'
            result['description'] = f"下跌趋势中，最后一笔为下跌，暂无买点信号"
        else:
            result['current_state'] = 'none'
            result['description'] = f"上涨中，但未形成明确的买点结构，观望为主"
    
    return result


def get_buy_state_summary(buy_state: Dict) -> str:
    """
    生成买点状态的简洁摘要（供 AI 决策引擎使用）
    
    Args:
        buy_state: detect_current_buy_state() 的返回值
    
    Returns:
        str: 一段描述当前买点状态的文字
    """
    state = buy_state.get('current_state', 'none')
    confidence = buy_state.get('confidence', 0)
    description = buy_state.get('description', '')
    
    state_names = {
        '1B': '一买',
        '2B': '二买', 
        '3B': '三买',
        'waiting': '等待回调',
        'none': '无买点'
    }
    
    summary = f"【缠论买点状态】{state_names.get(state, state)}\n"
    summary += f"置信度: {confidence*100:.0f}%\n"
    summary += f"分析: {description}\n"
    
    if buy_state.get('trigger_price'):
        summary += f"建议入场: {buy_state['trigger_price']:.2f}\n"
    if buy_state.get('stop_loss'):
        summary += f"止损位: {buy_state['stop_loss']:.2f}\n"
    if buy_state.get('target_price'):
        summary += f"目标位: {buy_state['target_price']:.2f}\n"
    
    return summary
