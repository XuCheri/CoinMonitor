# CoinMonitor

CoinMonitor/
│
├── monitors/
│   ├── __init__.py
│   ├── funding_rate_monitor.py       # 资金费率监控模块（异步 aiohttp）
│   ├── spot_inflow_monitor.py        # 现货净流入排行监控模块（异步 aiohttp）
│   └── other_monitor.py              # 其他监控模块（可扩展）
│
├── config.json                      # 配置文件，存放token、chat_id、阈值等
├── monitor_bot.py                  # 主程序入口，负责调度各个监控模块
├── requirements.txt                # 依赖文件
└── README.md                      # 项目说明文档（建议写）
