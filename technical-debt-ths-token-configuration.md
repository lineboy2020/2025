---
created: 2026-03-06 14:58
type: #issue #ths #token #configuration
status: ✅ 已解决
---

# 📝 技术债务记录：同花顺Token配置统一问题

## 📋 问题描述

多个使用同花顺数据的技能存在**Token硬编码**问题，导致：
- Token过期后需要逐个文件修改
- 容易遗漏，造成部分技能无法使用
- 维护困难，配置分散

## 🔍 受影响技能

| 技能 | 文件路径 | 原状态 | 修复状态 |
|------|----------|--------|----------|
| end-stock-picker | scripts/pick_smart.py | 硬编码旧Token | ✅ 已修复 |
| trend_eod_screener | - | 未检查 | ⚠️ 待检查 |
| ths-smart-stock-picking | - | 未检查 | ⚠️ 待检查 |

## ✅ 修复方案

### 标准做法（推荐）

所有使用同花顺HTTP接口的技能，都应该：

1. **从统一配置文件读取Token**
   ```python
   import json
   from pathlib import Path
   
   config_path = Path(__file__).parent.parent.parent / 'ths-data-fetcher' / 'scripts' / 'config.json'
   
   if config_path.exists():
       with open(config_path, 'r', encoding='utf-8') as f:
           config = json.load(f)
           access_token = config.get('data_skills', {}).get('ths_http', {}).get('access_token')
   ```

2. **备用Token兜底**
   ```python
   if not access_token:
       access_token = "备用Token"  # 配置文件读取失败时使用
   ```

3. **配置文件位置**
   ```
   /root/.openclaw/workspace/skills/ths-data-fetcher/scripts/config.json
   ```

## 📁 统一配置文件格式

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

## 🔧 修复示例

### 修复前（错误做法）
```python
# 硬编码在代码中
ACCESS_TOKEN = "2d2e8f7cbbcbd9750a2dcadb6d9a1b72a997538b.signs_Njc0Nzc1OTU4"
```

### 修复后（正确做法）
```python
# 从配置文件读取
import json
from pathlib import Path

config_path = Path(__file__).parent.parent.parent / 'ths-data-fetcher' / 'scripts' / 'config.json'
ACCESS_TOKEN = None

try:
    if config_path.exists():
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
            ACCESS_TOKEN = config.get('data_skills', {}).get('ths_http', {}).get('access_token')
            if ACCESS_TOKEN:
                print(f"✅ 已从配置文件读取 Token: {ACCESS_TOKEN[:20]}...")
except Exception as e:
    print(f"⚠️ 读取配置文件失败: {e}")

if not ACCESS_TOKEN:
    ACCESS_TOKEN = "备用Token"
    print(f"⚠️ 使用备用 Token")
```

## ⚠️ 待检查技能清单

- [ ] `trend_eod_screener` - 检查是否有硬编码Token
- [ ] `ths-smart-stock-picking` - 检查是否有硬编码Token
- [ ] `quant-daily` - 检查是否有硬编码Token
- [ ] `end-stock-picker/pick_backtest.py` - 检查是否有硬编码Token

## 📋 开发规范

### 新建技能时使用同花顺数据的规范

1. **不要硬编码Token**
2. **统一从 `ths-data-fetcher/scripts/config.json` 读取**
3. **提供备用Token机制**
4. **在SKILL.md中说明配置依赖**

### 配置文件变更时

1. 只需修改 `ths-data-fetcher/scripts/config.json`
2. 所有依赖技能自动获取新配置
3. 无需逐个修改技能文件

## 🔗 相关文件

- 统一配置文件：`/root/.openclaw/workspace/skills/ths-data-fetcher/scripts/config.json`
- 已修复文件：`/root/.openclaw/workspace/skills/end-stock-picker/scripts/pick_smart.py`

## 🏷️ 标签
#technical-debt #ths #configuration #token #best-practice

---

*记录时间: 2026-03-06 14:58*  
*记录者: OpenClaw*
