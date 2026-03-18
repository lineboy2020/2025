-- 将明显停牌/无成交的静止壳数据补为 0
-- 规则：amount is null, volume is null, 且 OHLC 四价相等

UPDATE market_daily
SET volume = 0,
    amount = 0
WHERE trade_date BETWEEN '2025-03-01' AND '2026-03-17'
  AND amount IS NULL
  AND volume IS NULL
  AND open = high
  AND high = low
  AND low = close;
