# Obsidian Scripts

## generate_market_emotion_note.py

自动生成当日市场情绪跟踪文档。

### 用法

```bash
python3 /root/.openclaw/workspace/obsidian/scripts/generate_market_emotion_note.py
```

### 可选参数

```bash
# 强制覆盖
python3 /root/.openclaw/workspace/obsidian/scripts/generate_market_emotion_note.py --force

# 指定日期
python3 /root/.openclaw/workspace/obsidian/scripts/generate_market_emotion_note.py --date 2026-03-18

# 指定接口
python3 /root/.openclaw/workspace/obsidian/scripts/generate_market_emotion_note.py --api http://127.0.0.1:9000/api/chart/qingxu?limit=240
```
