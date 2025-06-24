# 持仓监控器使用指南

## 概述

持仓监控器是CoinMonitor项目的一个新功能模块，用于获取币安账户的当前持仓和历史仓位信息，帮助用户进行交易复盘和风险管理。

## 功能特性

### 🎯 核心功能
- **实时持仓监控**: 获取期货和现货账户的当前持仓状态
- **历史交易记录**: 查看指定时间范围内的交易历史
- **盈亏分析**: 计算未实现盈亏和已实现盈亏
- **定期报告**: 支持定时推送持仓报告
- **手动查询**: 支持手动触发持仓报告

### 📊 报告内容
- 期货持仓详情（数量、方向、杠杆、盈亏等）
- 现货余额信息
- 历史交易记录
- 持仓统计指标

## 安装配置

### 1. 安装依赖
```bash
pip install python-binance pandas numpy python-dateutil
```

### 2. 配置币安API
在 `config.json` 中添加币安API配置：

```json
{
  "binance": {
    "api_key": "your_binance_api_key",
    "api_secret": "your_binance_api_secret",
    "testnet": false
  },
  "monitors": {
    "position_monitor": {
      "enabled": true,
      "topic_id": 999,
      "interval": 3600,
      "auto_report": true,
      "report_time": "09:00",
      "include_history": true,
      "history_days": 7
    }
  }
}
```

### 3. 获取币安API密钥
1. 登录币安账户
2. 进入API管理页面
3. 创建新的API密钥
4. 确保API密钥具有以下权限：
   - 读取权限（必需）
   - 期货交易权限（如果需要期货数据）
   - 现货交易权限（如果需要现货数据）

## 使用方法

### 启动监控器
```bash
python monitor_bot.py
```

### Telegram命令

#### `/position` - 手动获取持仓报告
```
/position
```
立即获取当前持仓报告，包含期货持仓、现货余额和历史交易记录。

#### `/config position_monitor` - 查看配置
```
/config position_monitor
```
查看持仓监控器的当前配置。

#### `/config position_monitor set <key> <value>` - 修改配置
```
/config position_monitor set interval 1800
/config position_monitor set history_days 14
/config position_monitor set auto_report false
```

### 配置参数说明

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `enabled` | boolean | false | 是否启用监控器 |
| `topic_id` | integer | 999 | Telegram话题ID |
| `interval` | integer | 3600 | 检查间隔（秒） |
| `auto_report` | boolean | true | 是否自动发送报告 |
| `report_time` | string | "09:00" | 自动报告时间 |
| `include_history` | boolean | true | 是否包含历史交易 |
| `history_days` | integer | 7 | 历史记录天数 |

## 测试功能

### 运行测试脚本
```bash
python test_position_monitor.py
```

测试脚本会验证：
- API连接是否正常
- 持仓数据获取是否成功
- 报告生成是否正常

### 测试前准备
1. 确保已正确配置币安API密钥
2. 确保账户中有持仓或交易记录
3. 检查网络连接和代理设置

## 报告示例

### 期货持仓报告
```
📊 币安账户持仓报告

🎯 期货持仓
总持仓数: 2
多仓: 1 | 空仓: 1
平均杠杆: 10.0x
未实现盈亏: 125.50 USDT

• BTCUSDT LONG
  数量: 0.0100 | 杠杆: 10x
  开仓价: 45000.0000 | 标记价: 45250.0000
  盈亏: 25.00 USDT (+0.56%)

• ETHUSDT SHORT
  数量: 0.5000 | 杠杆: 10x
  开仓价: 3000.0000 | 标记价: 2995.0000
  盈亏: 100.50 USDT (+0.17%)
```

### 现货余额报告
```
💰 现货余额
• BTC: 0.001234
• ETH: 0.050000
• USDT: 1000.00

现货总价值: 1000.00 USDT
```

## 安全注意事项

### API密钥安全
- 不要将API密钥提交到代码仓库
- 定期轮换API密钥
- 只授予必要的权限（读取权限即可）

### 数据隐私
- 持仓数据包含敏感信息，请妥善保管
- 建议在私有聊天中使用
- 定期清理历史数据

## 故障排除

### 常见问题

#### 1. API连接失败
**错误**: `币安API客户端初始化失败`
**解决**: 
- 检查API密钥是否正确
- 确认网络连接正常
- 检查代理设置

#### 2. 权限不足
**错误**: `APIError(code=-2015): Invalid API-key, IP, or permissions`
**解决**:
- 检查API密钥权限设置
- 确认IP白名单配置
- 验证API密钥是否有效

#### 3. 数据为空
**现象**: 报告显示无持仓或无交易记录
**可能原因**:
- 账户确实没有持仓
- 查询时间范围内无交易
- API权限不足

### 调试模式
启用详细日志输出：
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## 扩展功能

### 自定义报告格式
可以修改 `format_position_report` 方法来自定义报告格式。

### 添加更多指标
可以在 `calculate_position_metrics` 方法中添加更多统计指标。

### 集成其他交易所
可以扩展支持其他交易所的API。

## 更新日志

### v1.0.0
- 初始版本发布
- 支持期货和现货持仓监控
- 支持历史交易记录查询
- 支持Telegram消息推送

## 技术支持

如果遇到问题，请：
1. 查看日志文件
2. 运行测试脚本
3. 检查配置文件
4. 联系开发者

---

**注意**: 本工具仅用于数据查询和分析，不构成投资建议。请谨慎使用，注意风险控制。 