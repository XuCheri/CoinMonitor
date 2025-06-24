# CoinMonitor - 加密货币市场监控机器人

一个基于 Telegram Bot 的加密货币市场监控系统，支持多种监控功能，包括资金费率、持仓量、价格异动、现货成交额、Twitter监控和**账户持仓监控**。**自动监测所有币种**，无需手动配置监控列表。

## 🚀 最新更新

### 重大改进 (2025-06-24)
- 🌟 **新增持仓监控器** - 支持获取币安账户当前持仓和历史仓位记录
- 🌟 **持仓命令增强** - 支持参数化查询（/position [天数]）和别名命令（/mypos）
- 🌟 **自动监测所有币种** - 所有监控器现在自动获取并监测币安的所有可用交易对
- 🔧 **资金费率监控优化** - 添加 `/funding` 命令，支持手动触发检查
- 🛡️ **网络连接优化** - 修复代理配置问题，添加重试机制和后备方案
- 📊 **智能阈值调整** - 资金费率阈值优化为1%，能检测到更多有意义的异常
- 🎯 **监控器状态改进** - 显示监控币种数量和无效合约统计

### 修复内容
- ✅ 修复了代理配置键名不匹配问题
- ✅ 添加了网络连接重试机制
- ✅ 改进了错误处理和日志输出
- ✅ 修复了资金费率监控的手动触发功能

## 📋 功能特性

### 监控模块
1. **资金费率监控** (`FundingRateMonitor`)
   - 🎯 **自动监测所有永续合约**的资金费率异常
   - ⏰ 每半小时自动检查一次
   - 🔧 支持 `/funding` 命令手动触发检查
   - 📊 1%阈值，检测真正有意义的费率异常

2. **持仓量监控** (`OpenInterestMonitor`)
   - 🎯 **自动监测所有永续合约**的持仓量变化
   - 📈 结合价格变动分析市场行为（多头/空头开仓/平仓）
   - 📊 生成包含价格、持仓量、多空比的综合图表
   - 🔧 支持动态添加/移除监控项目

3. **价格异动监控** (`PriceSpikeMonitor`)
   - 🎯 **自动监测所有永续合约**的价格波动
   - ⚡ 支持多种触发条件（连续长蜡烛、单根蜡烛振幅、价格变化）
   - 📊 生成K线图表辅助分析
   - 🔧 支持动态配置触发阈值

4. **现货成交额监控** (`SpotVolumeMonitor`)
   - 📊 每天8点自动推送成交额排行榜
   - 🎯 **自动监测所有现货交易对**
   - 📈 支持自定义Top N数量

5. **Twitter监控** (`TwitterMonitor`)
   - 🐦 监控指定用户的新推文
   - ⏰ 实时发送通知
   - 🔧 支持自定义监控用户列表

6. **持仓监控** (`PositionMonitor`) 🆕
   - 📊 **获取币安账户当前持仓**（期货+现货）
   - 📈 **历史交易记录查询**（支持自定义时间范围）
   - 💰 **盈亏分析**（未实现盈亏、已实现盈亏）
   - ⏰ **定期报告推送**（可配置时间间隔）
   - 🔧 **手动查询**（支持 `/position [天数]` 和 `/mypos [天数]` 命令）
   - 📋 **详细持仓报告**（包含杠杆、开仓价、标记价等）
   - 🎯 **参数化查询**（支持1-30天历史数据查询）

### 交互命令
- `/status` - 查看所有监控器状态和配置
- `/funding` - **手动触发资金费率检查**
- `/position [天数]` - **手动获取持仓报告**（支持1-30天参数）🆕
- `/mypos [天数]` - **持仓报告别名命令**（功能同/position）🆕
- `/config <monitor> [action] [params]` - 动态配置监控器
- `/coin <symbol>` - 查询单个币种的综合信息

## 🛠️ 安装

1. **克隆项目**
```bash
git clone <repository-url>
cd CoinMonitor
```

2. **安装依赖**
```bash
pip install -r requirements.txt
```

3. **配置设置**
复制 `config.json` 并修改配置：
```json
{
  "telegram_token": "你的TelegramBotToken",
  "chat_id": "你的ChatID",
  "proxy_url": "http://127.0.0.1:7890",
  "binance": {
    "api_key": "你的币安API密钥",
    "api_secret": "你的币安API密钥",
    "testnet": false
  },
  "monitors": {
    "funding_rate": {
      "enabled": true,
      "topic_id": 2,
      "threshold": 0.01,
      "interval": 600
    },
    "open_interest": {
      "enabled": true,
      "topic_id": 117,
      "interval": 600,
      "threshold": 0.1
    },
    "price_spike": {
      "enabled": true,
      "topic_id": 658,
      "interval": 60,
      "threshold": 0.05
    },
    "spot_volume": {
      "enabled": true,
      "topic_id": 13,
      "interval": 3600,
      "top_n": 20,
      "min_volume_usd": 50000000
    },
    "twitter_monitor": {
      "enabled": false,
      "topic_id": 155,
      "interval": 300,
      "bearer_token": "你的TwitterBearerToken",
      "watch_ids": ["目标用户的numeric ID"]
    },
    "position_monitor": {
      "enabled": false,
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

**注意**: 持仓监控器需要配置币安API密钥才能使用。请确保API密钥具有读取权限。

## 🚀 运行

```bash
python monitor_bot.py
```

## 📖 使用说明

### 自动监测功能
- 🎯 **无需手动配置** - 所有监控器自动获取币安的所有可用交易对
- 📊 **智能过滤** - 自动过滤无效或已下架的交易对
- 🔄 **实时更新** - 自动检测新上线的交易对

### 资金费率监控
```bash
# 手动触发资金费率检查
/funding

# 查看资金费率监控器状态
/config funding_rate
```

### 持仓监控
```bash
# 手动获取持仓报告（默认近7天历史）
/position

# 获取指定天数的持仓报告
/position 3    # 近3天历史
/position 14   # 近14天历史

# 使用别名命令
/mypos         # 等同于 /position
/mypos 1       # 近1天历史

# 查看持仓监控器状态
/config position_monitor

# 修改配置参数
/config position_monitor set interval 1800
/config position_monitor set history_days 14
/config position_monitor set auto_report false
```

**持仓监控器功能：**
- 📊 **实时持仓监控** - 获取期货和现货账户的当前持仓状态
- 📈 **历史交易记录** - 查看指定时间范围内的交易历史（1-30天）
- 💰 **盈亏分析** - 计算未实现盈亏和已实现盈亏
- ⏰ **定期报告** - 支持定时推送持仓报告
- 🔧 **手动查询** - 支持参数化查询，灵活获取不同时间段的数据

### 配置管理
使用 `/config` 命令动态管理监控器：

```bash
# 查看监控器状态
/config open_interest

# 修改配置参数
/config open_interest set threshold 0.1

# 添加特定币种到监控列表（可选）
/config open_interest add SOLUSDT

# 移除特定币种（可选）
/config open_interest remove ETHUSDT
```

### 监控器状态
使用 `/status` 命令查看所有监控器的运行状态，包括：
- 📊 监控币种数量
- ⚡ 运行状态
- 🔧 配置参数
- 🚫 无效合约统计

### 币种查询
使用 `/coin BTCUSDT` 查询特定币种的综合市场信息，包括：
- 💰 现货价格和涨跌幅
- 📊 24小时成交额
- 🧾 合约持仓量
- 💸 资金费率

## 🏗️ 架构设计

### 模块化设计
- **BaseMonitor**: 抽象基类，提供通用功能（网络请求、消息发送、错误处理）
- **具体监控器**: 继承BaseMonitor，实现特定监控逻辑
- **BotRunner**: 主程序类，管理所有监控器和命令处理

### 并发处理
- 使用 `asyncio.gather` 并发执行API请求
- 每个监控器独立运行，互不影响
- 支持优雅停机和信号处理

### 错误处理
- 统一的异常捕获和日志记录
- 自动重试机制（最多3次）
- 无效交易对的智能过滤
- 网络连接失败时的后备方案

### 网络优化
- 代理支持（HTTP代理）
- 连接超时设置（20秒）
- 智能重试机制
- 后备币种列表（当无法获取所有币种时）

## 🔧 添加新监控器

1. 继承 `BaseMonitor` 类
2. 实现 `check()` 和 `get_status()` 方法
3. 在 `MONITOR_CLASSES` 中注册
4. 在配置文件中添加配置

示例：
```python
class NewMonitor(BaseMonitor):
    def __init__(self, bot, chat_id, topic_id, proxy_url=None, interval=60, **kwargs):
        super().__init__(bot, chat_id, topic_id, proxy_url, interval, **kwargs)
        # 初始化特定参数
    
    async def check(self):
        # 实现监控逻辑
        pass
    
    def get_status(self) -> str:
        # 返回状态描述
        return f"<b>{self.monitor_name}</b>\n..."
```

## 📊 监控统计

### 当前监控范围
- 🎯 **514个永续合约** - 自动监测所有币安永续合约
- 📊 **483个现货交易对** - 自动监测所有USDT现货交易对
- ⚡ **实时更新** - 自动检测新上线和下架的交易对

### 性能优化
- 🔄 **并发请求** - 使用asyncio.gather提高API请求效率
- 🎯 **智能过滤** - 自动过滤无效交易对，减少不必要的请求
- 📊 **批量处理** - 批量获取和处理数据，提高效率

## 📝 日志

系统使用统一的日志格式：
- `[INFO]` - 正常运行信息
- `[ERROR]` - 错误信息
- `[WARNING]` - 警告信息

日志示例：
```
2025-06-24 04:50:47,408 - [INFO] - ✅ 成功获取 483 个USDT交易对的资金费率
2025-06-24 04:50:47,408 - [INFO] - 📊 资金费率排名前20:
2025-06-24 04:50:47,408 - [INFO] -  1. MILKUSDT: -0.1500% (价格: 0.0643)
```

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📄 许可证

MIT License

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

**持仓监控器特殊参数：**
- `api_key` / `api_secret` - 币安API密钥（在binance配置中）
- `testnet` - 是否使用测试网络（在binance配置中）
