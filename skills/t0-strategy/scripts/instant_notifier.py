#!/usr/bin/env python3
"""
T0策略即时通知器 v2.0
信号触发时立即发送通知（QQ + 钉钉）
"""

import os
import sys
import json
import requests
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Optional

# 添加技能路径
skill_dir = Path(__file__).parent.parent
sys.path.insert(0, str(skill_dir))
sys.path.insert(0, str(skill_dir.parent / 'dingtalk-notify' / 'scripts'))

class T0InstantNotifier:
    """T0策略即时通知器"""
    
    def __init__(self):
        self.skill_dir = skill_dir
        self.state_file = skill_dir / '.notified_signals.json'
        self.audit_log = skill_dir / 'logs' / 'notification_audit.jsonl'
        
        # 通知目标配置
        self.target_qq = "27B4B34AFACA60C236DC67425960CAD8"
        self.dingtalk_webhook = self._load_dingtalk_config()
        
    def _load_dingtalk_config(self) -> Optional[str]:
        """加载钉钉配置"""
        # 尝试从技能目录加载
        config_paths = [
            skill_dir / 'dingtalk.env',
            skill_dir.parent / 'dingtalk-notify' / 'config' / 'dingtalk.env',
            Path('/root/.openclaw/workspace/skills/dingtalk-notify/config/dingtalk.env')
        ]
        
        for config_path in config_paths:
            if config_path.exists():
                try:
                    with open(config_path) as f:
                        for line in f:
                            if line.startswith('DINGTALK_WEBHOOK='):
                                return line.split('=', 1)[1].strip()
                except:
                    pass
        
        # 尝试环境变量
        return os.environ.get('DINGTALK_WEBHOOK')
    
    def load_state(self) -> Dict:
        """加载已通知的信号状态"""
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r') as f:
                    return json.load(f)
            except:
                return {}
        return {}
    
    def save_state(self, state: Dict):
        """保存信号状态"""
        try:
            with open(self.state_file, 'w') as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            print(f"保存状态失败: {e}")
    
    def _get_cooldown_minutes(self, signal_type: str) -> int:
        """按信号类型返回冷却时间（分钟）"""
        if signal_type == '买入':
            return 30
        if signal_type == '卖出':
            return 15
        return 20

    def is_signal_notified(self, signal: Dict) -> bool:
        """检查信号是否处于冷却期内"""
        state = self.load_state()
        today = datetime.now().strftime('%Y-%m-%d')
        stock = signal['stock_code']
        signal_type = signal['signal_type']
        current_ts = datetime.strptime(signal['timestamp'], '%Y-%m-%d %H:%M:%S')
        cooldown = self._get_cooldown_minutes(signal_type)

        notified_today = state.get(today, {})
        stock_records = notified_today.get(stock, {})
        last_ts_str = stock_records.get(signal_type)
        if not last_ts_str:
            return False

        try:
            last_ts = datetime.strptime(last_ts_str, '%Y-%m-%d %H:%M:%S')
        except Exception:
            return False

        return current_ts - last_ts < timedelta(minutes=cooldown)
    
    def mark_signal_notified(self, signal: Dict):
        """标记信号已通知（按股票+信号类型记录最后通知时间）"""
        state = self.load_state()
        today = datetime.now().strftime('%Y-%m-%d')
        stock = signal['stock_code']
        signal_type = signal['signal_type']
        ts = signal['timestamp']

        if today not in state or not isinstance(state[today], dict):
            state[today] = {}
        if stock not in state[today] or not isinstance(state[today][stock], dict):
            state[today][stock] = {}

        state[today][stock][signal_type] = ts

        dates = sorted(state.keys())[-3:]
        state = {k: state[k] for k in dates}
        self.save_state(state)
    
    def append_audit_log(self, signal: Dict, event: str, detail: str = ''):
        """记录通知审计日志，包括被冷却拦截的重复信号"""
        try:
            self.audit_log.parent.mkdir(parents=True, exist_ok=True)
            row = {
                'ts': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'event': event,
                'stock_code': signal.get('stock_code'),
                'signal_type': signal.get('signal_type'),
                'signal_timestamp': signal.get('timestamp'),
                'detail': detail,
            }
            with open(self.audit_log, 'a', encoding='utf-8') as f:
                f.write(json.dumps(row, ensure_ascii=False) + '\n')
        except Exception as e:
            print(f"⚠️ 审计日志写入失败: {e}")

    def format_qq_message(self, signal: Dict) -> str:
        """格式化QQ通知消息"""
        stock = signal['stock_code']
        signal_type = signal['signal_type']
        strength = signal['signal_strength']
        market = signal['market_state']
        
        # 信号图标
        if signal_type == '买入':
            icon = "🟢"
            action = "买入"
        else:
            icon = "🔴"
            action = "卖出"
        
        # 强度图标
        if strength == '强信号':
            strength_icon = "🔥🔥🔥"
        elif strength == '中信号':
            strength_icon = "🔥🔥"
        else:
            strength_icon = "🔥"
        
        msg_parts = [
            f"{icon} 【T0{action}信号】{strength_icon}",
            "",
            f"📊 {stock}",
            f"⏰ {signal['timestamp']}",
            f"📈 市场状态: {market}",
            "",
            f"💰 入场价: {signal['entry_price']:.2f}",
            f"📊 建议仓位: {signal['position_ratio']*100:.1f}%",
            "",
            f"🛑 止损价: {signal['stop_loss']:.2f}",
            f"🎯 止盈价: {signal['take_profit']:.2f}",
            "",
            f"📉 RSI: {signal['rsi_value']:.1f}",
            f"📊 量比: {signal['volume_ratio']:.2f}",
            "",
            "📋 触发条件:"
        ]
        
        for reason in signal.get('reasons', []):
            msg_parts.append(f"   ✓ {reason}")
        
        msg_parts.append("")
        msg_parts.append("⚠️ 风控提醒:")
        msg_parts.append(f"   • 最长持仓: 2小时")
        msg_parts.append(f"   • 移动止盈: 盈利1%后回撤50%触发")
        msg_parts.append(f"   • 14:30前强制平仓")
        
        return "\n".join(msg_parts)
    
    def format_dingtalk_markdown(self, signal: Dict) -> str:
        """格式化钉钉Markdown消息（包含关键词）"""
        stock = signal['stock_code']
        signal_type = signal['signal_type']
        strength = signal['signal_strength']
        market = signal['market_state']
        
        # 信号颜色
        if signal_type == '买入':
            color = "#52c41a"  # 绿色
            action = "买入"
        else:
            color = "#f5222d"  # 红色
            action = "卖出"
        
        reasons_text = "\n".join([f"- {r}" for r in signal.get('reasons', [])])
        
        # 包含关键词【监控】以满足钉钉机器人安全设置
        markdown = f"""## <font color='{color}'>⚡ T0{action}信号 - {strength}</font> 【监控】

**股票代码**: {stock}  
**信号时间**: {signal['timestamp']}  
**市场状态**: {market}

---

### 📊 交易参数

| 项目 | 数值 |
|------|------|
| 入场价 | **{signal['entry_price']:.2f}** |
| 建议仓位 | **{signal['position_ratio']*100:.1f}%** |
| 止损价 | {signal['stop_loss']:.2f} |
| 止盈价 | {signal['take_profit']:.2f} |

---

### 📈 技术指标

- RSI: {signal['rsi_value']:.1f}
- 量比: {signal['volume_ratio']:.2f}
- MA5: {signal['ma5']:.2f}
- MA20: {signal['ma20']:.2f}

---

### ✅ 触发条件

{reasons_text}

---

### ⚠️ 风控提醒

1. 最长持仓: 2小时
2. 移动止盈: 盈利1%后回撤50%触发
3. 14:30前强制平仓

> 💡 **提示**: 本信号仅供参考，不构成投资建议。请结合自身风险承受能力决策。
"""
        return markdown
    
    def send_qq_notification(self, message: str) -> bool:
        """发送QQ通知"""
        try:
            import subprocess
            cmd = [
                'openclaw', 'message', 'send',
                '--channel', 'qqbot',
                '--target', self.target_qq,
                '--message', message
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            if result.returncode == 0:
                print(f"✅ QQ通知已发送")
                return True
            else:
                print(f"⚠️ QQ发送失败: {result.stderr[:100]}")
                return False
        except Exception as e:
            print(f"❌ QQ通知异常: {e}")
            return False
    
    def send_dingtalk_notification(self, markdown: str, title: str = "T0策略信号") -> bool:
        """发送钉钉通知"""
        if not self.dingtalk_webhook:
            print("⚠️ 钉钉Webhook未配置，跳过钉钉通知")
            return False
        
        try:
            payload = {
                "msgtype": "markdown",
                "markdown": {
                    "title": title,
                    "text": markdown
                }
            }
            
            response = requests.post(
                self.dingtalk_webhook,
                json=payload,
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get('errcode') == 0:
                    print(f"✅ 钉钉通知已发送")
                    return True
                else:
                    print(f"⚠️ 钉钉发送失败: {result.get('errmsg')}")
                    return False
            else:
                print(f"⚠️ 钉钉HTTP错误: {response.status_code}")
                return False
                
        except Exception as e:
            print(f"❌ 钉钉通知异常: {e}")
            return False
    
    def notify_signal(self, signal: Dict) -> bool:
        """
        发送信号通知（去重）
        
        Returns:
            bool: 是否成功发送新通知
        """
        signal_desc = f"{signal['stock_code']}_{signal['signal_type']}_{signal['timestamp']}"
        
        # 检查是否已通知（冷却时间去重）
        if self.is_signal_notified(signal):
            print(f"📭 信号仍在冷却期，跳过: {signal_desc}")
            self.append_audit_log(signal, event='cooldown_skip', detail='signal suppressed by cooldown window')
            return False
        
        print(f"🎯 新信号 detected: {signal_desc}")
        
        # 格式化消息
        qq_message = self.format_qq_message(signal)
        dingtalk_markdown = self.format_dingtalk_markdown(signal)
        
        # 发送通知
        qq_ok = self.send_qq_notification(qq_message)
        dingtalk_ok = self.send_dingtalk_notification(dingtalk_markdown)
        
        # 标记已通知
        if qq_ok or dingtalk_ok:
            self.mark_signal_notified(signal)
            self.append_audit_log(signal, event='notified', detail=f'qq={qq_ok}, dingtalk={dingtalk_ok}')
            print(f"✅ 信号通知完成")
            return True
        else:
            self.append_audit_log(signal, event='notify_failed', detail='all channels failed')
            print(f"❌ 信号通知失败")
            return False
    
    def notify_signals_batch(self, signals: list) -> int:
        """
        批量通知信号
        
        Returns:
            int: 成功发送的新信号数量
        """
        if not signals:
            return 0
        
        sent_count = 0
        for signal in signals:
            if self.notify_signal(signal):
                sent_count += 1
        
        return sent_count


# 便捷函数
def notify_signal(signal: Dict) -> bool:
    """发送单个信号通知"""
    notifier = T0InstantNotifier()
    return notifier.notify_signal(signal)


def notify_signals_batch(signals: list) -> int:
    """批量发送信号通知"""
    notifier = T0InstantNotifier()
    return notifier.notify_signals_batch(signals)


if __name__ == "__main__":
    # 测试
    test_signal = {
        'stock_code': '000001.SZ',
        'signal_type': '买入',
        'signal_strength': '强信号',
        'market_state': '多头',
        'entry_price': 12.35,
        'position_ratio': 0.20,
        'stop_loss': 12.22,
        'take_profit': 12.53,
        'rsi_value': 32.5,
        'volume_ratio': 1.85,
        'ma5': 12.28,
        'ma20': 11.98,
        'timestamp': '2026-03-13 10:35:00',
        'reasons': ['市场状态: 多头', 'RSI超卖: 32.5', '放量阳线: 量比=1.85']
    }
    
    notifier = T0InstantNotifier()
    notifier.notify_signal(test_signal)
