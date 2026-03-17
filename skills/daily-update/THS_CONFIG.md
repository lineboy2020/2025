# 同花顺配置指南

## 配置位置

同花顺配置保存在以下位置：

```
~/.openclaw/workspace/skills/daily-update/.env
```

## 配置内容

```bash
# 同花顺账户配置
THS_SDK_USERNAME=hss130
THS_SDK_PASSWORD=335d9e
THS_HTTP_ACCESS_TOKEN=72a6f6c407b2d433353cdbfa46c8571c152fa724.signs_Njc0Nzc1OTU4
```

## 配置项说明

| 配置项 | 说明 | 获取方式 |
|--------|------|---------|
| THS_SDK_USERNAME | 同花顺SDK用户名 | 同花顺iFinD官网注册 |
| THS_SDK_PASSWORD | 同花顺SDK密码 | 同花顺iFinD官网注册 |
| THS_HTTP_ACCESS_TOKEN | HTTP接口访问令牌 | 同花顺iFinD官网获取 |

## 使用方式

### 1. 在脚本中加载配置

```python
import os
from pathlib import Path

# 加载环境变量
env_file = Path(__file__).parent.parent / '.env'
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ[key] = value
```

### 2. 使用SDK模式

```python
import iFinDPy

# 登录
username = os.environ.get('THS_SDK_USERNAME', 'hss130')
password = os.environ.get('THS_SDK_PASSWORD', '335d9e')
result = iFinDPy.THS_iFinDLogin(username, password)

if result == 0:
    print("登录成功")
else:
    print(f"登录失败: {result}")

# 使用问财接口（仅SDK模式支持）
df = iFinDPy.THS_WCQuery("2026-03-13,涨停", 'table')

# 登出
iFinDPy.THS_iFinDLogout()
```

### 3. 使用HTTP模式

```python
import requests

base_url = "https://quantapi.51ifind.com/api/v1"
token = os.environ.get('THS_HTTP_ACCESS_TOKEN')

headers = {
    'Authorization': f'Bearer {token}',
    'Content-Type': 'application/json'
}

# 注意：HTTP模式不支持问财接口(THS_WCQuery)
```

## 重要注意事项

### 接口模式选择

| 接口 | 模式 | 说明 | 使用场景 |
|------|------|------|---------|
| `THS_WCQuery` | SDK | 问财选股，支持自然语言查询 | 盘中实时数据获取（涨停数、涨跌家数等） |
| `/smart_stock_picking` | HTTP API | 智能选股，支持自然语言查询 | 股票筛选、条件选股 |
| `/real_time_quotation` | HTTP API | 实时行情 | 获取股票实时价格 |
| `/cmd_history_quotation` | HTTP API | 历史行情 | 获取日线/分钟线数据 |

**关键经验：**

1. **问财接口(`THS_WCQuery`)只能使用SDK模式**，不支持HTTP模式
   - 用途：获取市场统计数据（涨停数、跌停数、上涨家数等）
   - 示例：`THS_WCQuery("2026-03-13,涨停", 'table')`

2. **智能选股接口(`/smart_stock_picking`)使用HTTP模式**
   - 用途：根据条件筛选股票
   - 示例：`api.smart_stock_picking("涨幅大于5%")`

3. **实时行情接口(`/real_time_quotation`)使用HTTP模式**
   - 用途：获取股票实时价格

```python
# ✅ SDK模式 - 问财选股（获取市场统计数据）
df = iFinDPy.THS_WCQuery("2026-03-13,涨停", 'table')

# ✅ HTTP模式 - 智能选股（条件筛选股票）
api = iFinDAPI(access_token='xxx')
result = api.smart_stock_picking("涨停")

# ❌ 错误：HTTP模式不支持问财
# HTTP API返回404错误
```

### 登录状态检查

```python
# 检查是否已登录
if not self._logged_in:
    self.login()
```

### 错误处理

```python
try:
    result = iFinDPy.THS_WCQuery(query, 'table')
    if result.errorcode != 0:
        print(f"查询失败: {result.errmsg}")
        return None
    df = result.data
except Exception as e:
    print(f"异常: {e}")
    return None
```

## 技能配置复制

新技能需要同花顺配置时，复制配置文件：

```bash
cp ~/.openclaw/workspace/skills/daily-update/.env \
   ~/.openclaw/workspace/skills/新技能目录/.env
```

## 验证配置

测试脚本：

```python
#!/usr/bin/env python3
import os
import iFinDPy

# 加载配置
with open('.env') as f:
    for line in f:
        if '=' in line and not line.startswith('#'):
            key, value = line.strip().split('=', 1)
            os.environ[key] = value

# 测试登录
username = os.environ.get('THS_SDK_USERNAME')
password = os.environ.get('THS_SDK_PASSWORD')

result = iFinDPy.THS_iFinDLogin(username, password)
if result == 0:
    print("✅ 登录成功")
    
    # 测试问财查询
    result = iFinDPy.THS_WCQuery("2026-03-13,涨停", 'table')
    if result.errorcode == 0:
        print(f"✅ 问财查询成功: {len(result.data)} 条数据")
    else:
        print(f"❌ 问财查询失败: {result.errmsg}")
    
    iFinDPy.THS_iFinDLogout()
else:
    print(f"❌ 登录失败: {result}")
```

## 常见问题

### Q: HTTP模式返回404错误？
A: 问财接口(`THS_WCQuery`)不支持HTTP模式，必须使用SDK模式。如果需要筛选股票，可以使用HTTP模式的`/smart_stock_picking`智能选股接口。

### Q: SDK登录失败？
A: 检查用户名密码是否正确，或尝试重新获取Access Token。

### Q: 环境变量未加载？
A: 确保在导入iFinDPy之前加载环境变量。

## 相关技能

使用同花顺配置的技能：
- daily-update
- ths-data-fetcher
- t0-strategy
- market-emotion
- eod-full-update

## 实战经验总结

### 1. 盘中情绪监测使用SDK模式

获取实时市场数据（涨停数、涨跌家数）必须使用SDK模式的问财接口：

```python
# ✅ 正确：使用SDK模式获取实时数据
import iFinDPy

# 登录
iFinDPy.THS_iFinDLogin(username, password)

# 获取涨停股票数
df = iFinDPy.THS_WCQuery("2026-03-13,涨停", 'table')
limit_up_count = len(df)

# 获取上涨家数
df = iFinDPy.THS_WCQuery("2026-03-13,上涨", 'table')
rise_count = len(df)

# 登出
iFinDPy.THS_iFinDLogout()
```

### 2. 智能选股使用HTTP模式

筛选符合条件的股票使用HTTP模式的智能选股接口：

```python
# ✅ 正确：使用HTTP模式筛选股票
from ths_api import iFinDAPI

api = iFinDAPI(access_token='xxx')
result = api.smart_stock_picking("涨幅大于5%且市盈率小于20")
stocks = result.get('stocks', [])
```

### 3. 错误避免

| 错误 | 原因 | 解决方案 |
|------|------|---------|
| HTTP 404 | 用HTTP模式调用问财 | 改用SDK模式 |
| SDK登录失败 | 用户名密码错误 | 检查.env配置 |
| Token无效 | access_token过期 | 使用refresh_token重新获取 |

---

*最后更新: 2026-03-13*
