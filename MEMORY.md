# OpenClaw 长期记忆

## 邮件发送能力

### 已配置的邮箱

#### 189邮箱（主用）
- **发件地址**: 18091660868@189.cn
- **SMTP服务器**: smtp.189.cn:465
- **加密方式**: SSL
- **配置文件**: `/root/.openclaw/workspace/skills/imap-smtp-email/.env`
- **状态**: ✅ 已验证可用
- **测试记录**: 2026-03-04 成功发送邮件到 284057209@qq.com

### 技能位置
```
/root/.openclaw/workspace/skills/imap-smtp-email/
├── .env              # 配置文件（含授权码）
├── .env.example      # 配置模板
├── README.md         # 使用说明
└── scripts/
    ├── main.py                   # 命令行入口
    └── email_auto_sender.py      # 核心发送模块
```

## 用户邮箱

### 主邮箱
- **邮箱地址**: 284057209@qq.com
- **用途**: 接收策略报告、数据更新通知、系统告警
- **记录时间**: 2026-03-16

### 快速发送命令
```bash
cd /root/.openclaw/workspace/skills/imap-smtp-email/scripts

# 基础发送
python3 main.py --subject "主题" --body-text "内容" --to "收件人"

# 带附件
python3 main.py --subject "主题" --body-text "内容" --to "收件人" --attachments "/path/to/file.pdf"

# 测试模式（不实际发送）
python3 main.py --subject "测试" --body-text "测试" --dry-run
```

### 189邮箱SMTP设置
| 协议 | 服务器 | 端口 | 加密 |
|------|--------|------|------|
| SMTP | smtp.189.cn | 465 | SSL |
| POP3 | pop.189.cn | 995 | SSL |
| IMAP | imap.189.cn | 993 | SSL |

### 获取授权码
189邮箱 → 设置 → 账户与安全 → 客户端授权码

---

## 同花顺账户配置

### 账户信息
| 配置项 | 值 |
|--------|-----|
| **用户名** | hss130 |
| **密码** | 335d9e |
| **HTTP Access Token** | 72a6f6c407b2d433353cdbfa46c8571c152fa724.signs_Njc0Nzc1OTU4 |
| **API Base URL** | https://quantapi.51ifind.com/api/v1 |

### 已配置技能
- **ths-data-fetcher** - 同花顺数据获取统一接口
- **daily-update** - 每日A股数据更新
- **ths-smart-stock-picking** - 同花顺iFinD智能选股

### 配置文件位置
```
/root/.openclaw/workspace/skills/daily-update/.env
/root/.openclaw/workspace/skills/ths-data-fetcher/.env
```

### .env 文件格式
```
THS_SDK_USERNAME=hss130
THS_SDK_PASSWORD=335d9e
THS_HTTP_ACCESS_TOKEN=72a6f6c407b2d433353cdbfa46c8571c152fa724.signs_Njc0Nzc1OTU4
```

> ⚠️ **注意**: 该账户已配置并验证可用。后续任何需要同花顺数据接口的技能，直接使用此配置，**无需再次询问用户**。

---

## 常用技能清单

### 金融数据（A股）
- **akshare** - 中国金融数据获取
- **daily-quant-review** - 每日A股量化复盘
- **ths-data-fetcher** - 同花顺数据获取
- **end-stock-picker** - 尾盘选股
- **ths-smart-stock-picking** - 同花顺智能选股

### 自动化与通知
- **qqbot-cron** - QQ Bot 定时提醒
- **dingtalk-notify** - 钉钉机器人通知
- **imap-smtp-email** - 邮件自动发送 ✅
- **wechat-operation** - 微信公众号运营

### 办公协作
- **feishu-doc** - 飞书文档
- **feishu-drive** - 飞书云盘
- **feishu-wiki** - 飞书知识库

### 系统工具
- **weather** - 天气查询
- **healthcheck** - 主机安全检查
- **skill-creator** - 技能创建
- **clawhub** - 技能管理

---

## 用户偏好

- **测试QQ**: 27B4B34AFACA60C236DC67425960CAD8
- **常用收件邮箱**: 284057209@qq.com
- **邮件发件**: 18091660868@189.cn
- **活跃时段**: 早晨 (GMT+8 06:00-07:00)

---

## 重要日期

- **2026-03-04** - 邮件发送技能配置成功并验证
- **2026-03-07** - 同花顺账户配置记录 / daily-update技能配置 / 数据库更新

---

*最后更新: 2026-03-07*
