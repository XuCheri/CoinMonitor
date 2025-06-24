# CoinMonitor - 币安交易监控机器人

一个功能强大的币安交易监控机器人，支持多种监控功能，通过Telegram实时推送交易信息。

## 🚀 功能特性

### 📊 持仓监控器 (PositionMonitor)
- **实时持仓监控**：获取当前期货和现货持仓信息
- **历史盈亏分析**：精确计算已实现盈亏，支持复杂加减仓场景
- **智能报告**：自动生成持仓报告，包含未实现盈亏、杠杆、保证金等信息
- **手动查询**：支持Telegram命令手动获取持仓报告
- **时间范围**：支持查询指定天数的历史数据

### 📈 其他监控器
- **资金费率监控** (FundingRateMonitor)：监控期货资金费率变化
- **持仓量监控** (OpenInterestMonitor)：监控期货持仓量变化
- **价格异动监控** (PriceSpikeMonitor)：监控价格剧烈波动
- **现货交易量监控** (SpotVolumeMonitor)：监控现货交易量异常
- **Twitter监控** (TwitterMonitor)：监控相关Twitter动态

## 🛠️ 安装配置

### 1. 环境要求
- Python 3.8+
- 币安API密钥
- Telegram Bot Token

### 2. 安装依赖
```bash
pip install -r requirements.txt
```

### 3. 配置文件
复制 `config.json` 并填入你的配置：

```json
{
  "bot_token": "YOUR_TELEGRAM_BOT_TOKEN",
  "chat_id": YOUR_CHAT_ID,
  "proxy_url": "http://127.0.0.1:7890",
  "binance": {
    "api_key": "YOUR_BINANCE_API_KEY",
    "api_secret": "YOUR_BINANCE_API_SECRET",
    "testnet": false
  },
  "monitors": {
    "position_monitor": {
      "enabled": true,
      "interval": 3600,
      "auto_report": true,
      "report_time": "09:00",
      "include_history": true,
      "history_days": 1
    }
  }
}
```

## 📱 使用方法

### 启动机器人
```bash
python monitor_bot.py
```

### Telegram命令

#### 持仓监控命令
- `/position [天数]` - 获取持仓报告（默认1天）
- `/mypos [天数]` - 获取持仓报告（默认1天）
- `/status` - 查看监控器状态

#### 通用命令
- `/start` - 启动机器人
- `/stop` - 停止机器人
- `/help` - 显示帮助信息

### 持仓报告示例

```
📊 币安账户持仓报告

🎯 期货持仓
总持仓数: 4
多仓: 2 | 空仓: 2
平均杠杆: 61.2x
未实现盈亏: -376.69 USDT

• MEMEFIUSDT LONG
  数量: 4313475.0000 | 杠杆: 25x
  开仓价: 0.0012 | 标记价: 0.0012
  盈亏: 62.20 USDT (+1.25%)

📈 今日持仓盈亏详情

• HIFIUSDT LONG
  数量: 68218.0000
  开均价: 0.0891  平均价: 0.0880
  盈亏: -86.35 USDT 🔴
  时间: 2025-06-24 10:00
```

## 🏗️ 项目结构

```
CoinMonitor/
├── monitor_bot.py              # 主程序入口
├── config.json                 # 配置文件
├── requirements.txt            # 依赖包列表
├── README.md                   # 项目说明
├── DEPLOYMENT.md              # 部署指南
├── monitors/                   # 监控器模块
│   ├── __init__.py
│   ├── base_monitor.py        # 基础监控器类
│   ├── position_monitor.py    # 持仓监控器
│   ├── funding_rate_monitor.py
│   ├── open_interest_monitor.py
│   ├── price_spike_monitor.py
│   ├── spot_volume_monitor.py
│   └── twitter_monitor.py
├── utils/                      # 工具模块
│   ├── __init__.py
│   ├── logger.py              # 日志工具
│   └── telegram_helper.py     # Telegram工具
├── logs/                       # 日志文件
├── Dockerfile                  # Docker配置
├── docker-compose.yml         # Docker Compose配置
└── deploy.sh                  # 部署脚本
```

## 🔧 配置说明

### 持仓监控器配置
- `enabled`: 是否启用监控器
- `interval`: 检查间隔（秒）
- `auto_report`: 是否自动发送报告
- `report_time`: 自动报告时间（格式：HH:MM）
- `include_history`: 是否包含历史盈亏
- `history_days`: 历史数据天数

### 币安API配置
- `api_key`: 币安API密钥
- `api_secret`: 币安API密钥
- `testnet`: 是否使用测试网络

## 🚀 部署

### Docker部署
```bash
# 构建镜像
docker build -t coinmonitor .

# 运行容器
docker-compose up -d
```

### 直接部署
```bash
# 安装依赖
pip install -r requirements.txt

# 配置config.json
# 启动机器人
python monitor_bot.py
```

## 📝 更新日志

### v1.0.0 (2025-06-24)
- ✅ 完成持仓监控器开发
- ✅ 实现精确的历史盈亏计算
- ✅ 支持FIFO队列配对逻辑
- ✅ 优化报告格式，合并同方向持仓
- ✅ 完善项目文档和部署配置

## 🤝 贡献

欢迎提交Issue和Pull Request来改进这个项目。

## 📄 许可证

MIT License

## ⚠️ 免责声明

本项目仅供学习和研究使用，不构成投资建议。使用本软件进行交易的风险由用户自行承担。
