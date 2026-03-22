# OpenClaw 日常运维命令手册

**整理日期**: 2026-03-16  
**适用系统**: Linux (OpenClaw Workspace)

---

## 📊 K-line 服务管理

### 查看服务状态
```bash
# 检查端口是否监听
lsof -i :9000

# 或
netstat -tlnp | grep 9000
```

### 启动 K-line 服务
```bash
cd /root/.openclaw/workspace/kline-viewer
nohup python3 -m uvicorn scripts.kline_server:app --host 0.0.0.0 --port 9000 > server.log 2>&1 &
```

### 停止 K-line 服务
```bash
# 查找进程并杀死
ps aux | grep kline_server | grep -v grep | awk '{print $2}' | xargs kill -9

# 或
pkill -f kline_server
```

### 查看日志
```bash
# 实时查看日志
tail -f /root/.openclaw/workspace/kline-viewer/server.log

# 查看最新100行
tail -100 /root/.openclaw/workspace/kline-viewer/server.log
```

### 测试服务
```bash
# 测试API接口
curl -s "http://localhost:9000/api/kline/000001.SZ?period=daily&limit=100" | python3 -m json.tool

# 访问Web界面
curl -s http://localhost:9000/static/kline.html?code=000001.SZ | head -20
```

---

## ⏰ 定时任务管理

### 查看系统 crontab（仅历史兼容/其他任务）
```bash
crontab -l
```

### 查看 OpenClaw cron（推荐）
```bash
openclaw cron list
```

### 编辑系统 crontab
```bash
crontab -e
```

### 当前定时任务列表
```
# 腾讯云监控
*/5 * * * * flock -xn /tmp/stargate.lock -c '/usr/local/qcloud/stargate/admin/start.sh > /dev/null 2>&1 &'

# 财商书籍发布 (每日19:00)
0 19 * * * cd /root/.openclaw/workspace/skills/wechat-operation/scripts && /usr/bin/python3 book_daily_publisher.py >> /root/.openclaw/workspace/skills/wechat-operation/logs/book_daily_19h.log 2>&1

# 每日A股数据更新 (当前主入口迁移到 OpenClaw cron 的 eod-full-update-daily；此处旧示例仅保留历史参考)
# 30 16 * * 1-5 cd /root/.openclaw/workspace/skills/daily-update && /usr/bin/python3 scripts/daily_update.py >> /var/log/openclaw/daily-update.log 2>&1

# T0策略扫描 (交易时段每5分钟)
*/5 9-11 * * 1-5 cd /root/.openclaw/workspace/skills/t0-strategy && /usr/bin/python3 scripts/scheduled_scan.py >> /var/log/openclaw/t0-strategy.log 2>&1
*/5 13-14 * * 1-5 cd /root/.openclaw/workspace/skills/t0-strategy && /usr/bin/python3 scripts/scheduled_scan.py >> /var/log/openclaw/t0-strategy.log 2>&1
```


### 当前推荐的数据更新入口
```bash
# 查看 OpenClaw cron
openclaw cron list

# 手动触发盘后更新
cd /root/.openclaw/workspace/skills/eod-full-update
python3 scripts/run_eod_with_kline_guard.py

# 指定日期回放
python3 scripts/run_eod_with_kline_guard.py --date 2026-03-20
```

### 查看定时任务日志
```bash
# 每日数据更新日志
tail -f /var/log/openclaw/daily-update.log

# T0策略日志
tail -f /var/log/openclaw/t0-strategy.log

# 财商书籍发布日志
tail -f /root/.openclaw/workspace/skills/wechat-operation/logs/book_daily_19h.log
```

---

## 🔧 SKILLS 查询与管理

### 查看已安装技能
```bash
# 列出所有技能目录
ls -la /root/.openclaw/workspace/skills/

# 查看技能详情
ls /root/.openclaw/workspace/skills/ | grep -v backup
```

### 当前已安装技能列表
| 技能名称 | 路径 | 功能 |
|----------|------|------|
| akshare | skills/akshare | 中国金融数据获取 |
| chanlun-analysis | skills/chanlun-analysis | 缠论技术分析 |
| daily-quant-review | skills/daily-quant-review | 每日量化复盘 |
| daily-update | skills/daily-update | 每日数据更新 |
| dingtalk-notify | skills/dingtalk-notify | 钉钉通知 |
| eod-full-update | skills/eod-full-update | 盘后数据全量更新 |
| end-stock-picker | skills/end-stock-picker | 尾盘选股 |
| fupan | skills/fupan | AI量化复盘 |
| imap-smtp-email | skills/imap-smtp-email | 邮件发送 |
| kline-viewer | skills/kline-viewer | K线展示服务 |
| main-force-intent | skills/main-force-intent | 主力意图识别 |
| market-emotion | skills/market-emotion | 市场情绪周期 |
| notion | skills/notion | Notion API |
| obsidian | skills/obsidian | Obsidian笔记 |
| qqbot-cron | skills/qqbot-cron | QQ定时提醒 |
| sina-bigorder | skills/sina-bigorder | 新浪财经大单数据 |
| t0-strategy | skills/t0-strategy | T0日内策略 |
| ths-smart-stock-picking | skills/ths-smart-stock-picking | 同花顺智能选股 |
| trend-eod-backtest | skills/trend-eod-backtest | 趋势尾盘选股回测 |
| trend_eod_screener | skills/trend_eod_screener | 趋势尾盘选股 |
| wechat-operation | skills/wechat-operation | 微信公众号运营 |

### 查看技能文档
```bash
# 查看技能README
cat /root/.openclaw/workspace/skills/{skill-name}/README.md

# 查看技能SKILL.md
cat /root/.openclaw/workspace/skills/{skill-name}/SKILL.md
```

### 运行技能脚本
```bash
# 示例: 运行市场情绪分析
cd /root/.openclaw/workspace/skills/market-emotion
python3 scripts/main.py --today

# 示例: 运行尾盘选股
cd /root/.openclaw/workspace/skills/end-stock-picker
python3 scripts/main.py
```

---

## 📧 邮件发送

### 发送邮件命令
```bash
cd /root/.openclaw/workspace/skills/imap-smtp-email/scripts

# 基础发送
python3 main.py --subject "主题" --body-text "内容" --to "284057209@qq.com"

# 带附件
python3 main.py --subject "主题" --body-text "内容" --to "284057209@qq.com" --attachments "/path/to/file.pdf"

# 测试模式（不实际发送）
python3 main.py --subject "测试" --body-text "测试" --dry-run
```

### 邮件配置
- **发件邮箱**: 18091660868@189.cn
- **收件邮箱**: 284057209@qq.com
- **配置文件**: `/root/.openclaw/workspace/skills/imap-smtp-email/.env`

---

## 📊 数据查询

### 查看情绪数据
```bash
# 查看最新情绪数据
cd /root/.openclaw/workspace
python3 -c "
import pandas as pd
df = pd.read_parquet('skills/market-emotion/data/index/emotion_features.parquet')
print(df[['tradeDate', 'emotion_score', 'limit_up_count', 'limit_down_count', 'rise_fall_ratio']].tail(5))
"
```

### 查看资金流向
```bash
# 查看最新资金流向
cd /root/.openclaw/workspace
python3 -c "
import duckdb
conn = duckdb.connect('data/db/kline_eod.duckdb', read_only=True)
result = conn.execute(\"SELECT * FROM capital_flow WHERE trade_date = '2026-03-16' ORDER BY main_net_inflow DESC LIMIT 10\").fetchall()
for row in result:
    print(row)
conn.close()
"
```

### 查看涨停数据
```bash
# 查看最新涨停
cd /root/.openclaw/workspace
python3 -c "
import duckdb
conn = duckdb.connect('data/db/limit_up.duckdb', read_only=True)
result = conn.execute(\"SELECT stock_code, stock_name, consecutive_boards FROM limit_up WHERE trade_date = '2026-03-16' ORDER BY consecutive_boards DESC LIMIT 10\").fetchall()
for row in result:
    print(row)
conn.close()
"
```

---

## 🔍 系统监控

### 查看进程
```bash
# 查看Python进程
ps aux | grep python | grep -v grep

# 查看特定服务
ps aux | grep -E "(kline|uvicorn|fastapi)" | grep -v grep
```

### 查看端口占用
```bash
# 查看所有监听端口
netstat -tlnp

# 查看特定端口
lsof -i :9000  # K-line服务
lsof -i :8000  # 其他服务
```

### 查看磁盘空间
```bash
df -h
```

### 查看内存使用
```bash
free -h
```

---

## 📝 日志查看

### 常用日志路径
| 日志文件 | 路径 | 说明 |
|----------|------|------|
| 每日更新日志 | /var/log/openclaw/daily-update.log | 数据更新任务 |
| T0策略日志 | /var/log/openclaw/t0-strategy.log | T0扫描任务 |
| K-line服务日志 | /root/.openclaw/workspace/kline-viewer/server.log | K线服务 |
| 财商书籍日志 | /root/.openclaw/workspace/skills/wechat-operation/logs/book_daily_19h.log | 公众号发布 |

### 实时查看日志
```bash
# 使用tail -f实时查看
tail -f /var/log/openclaw/daily-update.log

# 查看最后100行
tail -100 /var/log/openclaw/daily-update.log

# 查看包含错误的关键行
grep -i "error\|fail\|exception" /var/log/openclaw/daily-update.log | tail -20
```

---

## 🚀 快速启动命令

### 一键启动所有服务
```bash
#!/bin/bash
# start_all_services.sh

echo "启动 K-line 服务..."
cd /root/.openclaw/workspace/kline-viewer
nohup python3 -m uvicorn scripts.kline_server:app --host 0.0.0.0 --port 9000 > server.log 2>&1 &

echo "服务启动完成！"
echo "K-line服务: http://localhost:9000/static/kline.html"
```

### 一键检查所有服务状态
```bash
#!/bin/bash
# check_all_services.sh

echo "=== 服务状态检查 ==="

echo -e "\n1. K-line 服务 (端口9000):"
lsof -i :9000 > /dev/null 2>&1 && echo "   ✅ 运行中" || echo "   ❌ 未运行"

echo -e "\n2. 定时任务:"
crontab -l | grep -c "daily-update" > /dev/null && echo "   ✅ 数据更新任务已配置" || echo "   ❌ 数据更新任务未配置"
crontab -l | grep -c "t0-strategy" > /dev/null && echo "   ✅ T0策略任务已配置" || echo "   ❌ T0策略任务未配置"

echo -e "\n3. 数据文件:"
[ -f "/root/.openclaw/workspace/data/db/kline_eod.duckdb" ] && echo "   ✅ K线数据库存在" || echo "   ❌ K线数据库不存在"
[ -f "/root/.openclaw/workspace/data/db/qingxu.parquet" ] && echo "   ✅ 情绪数据存在" || echo "   ❌ 情绪数据不存在"

echo -e "\n=== 检查完成 ==="
```

---

## 📞 联系与支持

- **邮箱**: 284057209@qq.com
- **文档目录**: /root/.openclaw/workspace/docs/
- **技能目录**: /root/.openclaw/workspace/skills/

---

*最后更新: 2026-03-16*
