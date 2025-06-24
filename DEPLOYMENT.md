# CoinMonitor 部署指南

## 🚀 快速部署

### 方案一：使用部署脚本（推荐）

```bash
# 1. 克隆项目
git clone <your-repo-url>
cd CoinMonitor

# 2. 修改配置文件
nano config.json

# 3. 运行部署脚本
chmod +x deploy.sh
sudo ./deploy.sh install

# 4. 启动服务
sudo ./deploy.sh start

# 5. 查看状态
sudo ./deploy.sh status

# 6. 查看日志
sudo ./deploy.sh logs
```

### 方案二：Docker部署

```bash
# 1. 修改配置文件
nano config.json

# 2. 构建并启动
docker-compose up -d

# 3. 查看日志
docker-compose logs -f coinmonitor

# 4. 停止服务
docker-compose down
```

### 方案三：手动部署

```bash
# 1. 安装依赖
sudo apt update
sudo apt install python3 python3-pip git

# 2. 创建用户
sudo useradd -m -s /bin/bash coinmonitor
sudo usermod -aG sudo coinmonitor

# 3. 克隆项目
sudo -u coinmonitor git clone <your-repo-url> /opt/coinmonitor
cd /opt/coinmonitor

# 4. 安装Python依赖
sudo -u coinmonitor python3 -m venv venv
sudo -u coinmonitor venv/bin/pip install -r requirements.txt

# 5. 创建systemd服务
sudo nano /etc/systemd/system/coinmonitor.service
```

## 📋 部署前准备

### 1. 服务器要求
- **操作系统**: Ubuntu 18.04+ / CentOS 7+ / Debian 9+
- **内存**: 最少 512MB，推荐 1GB+
- **存储**: 最少 1GB 可用空间
- **网络**: 稳定的网络连接，支持访问币安API

### 2. 必要配置
- **Telegram Bot Token**: 从 @BotFather 获取
- **Chat ID**: 目标聊天群组或频道的ID
- **代理配置**: 如果需要访问币安API

### 3. 配置文件修改
```json
{
  "telegram_token": "你的TelegramBotToken",
  "chat_id": "你的ChatID",
  "proxy_url": "http://127.0.0.1:7890",
  "monitors": {
    "funding_rate": {
      "enabled": true,
      "topic_id": 2,
      "threshold": 0.01,
      "interval": 600
    }
    // ... 其他监控器配置
  }
}
```

## 🔧 部署后配置

### 1. 代理设置（如果需要）
```bash
# 安装代理软件
sudo apt install shadowsocks-libev

# 配置代理
sudo nano /etc/shadowsocks-libev/config.json

# 启动代理
sudo systemctl start shadowsocks-libev
sudo systemctl enable shadowsocks-libev
```

### 2. 防火墙设置
```bash
# 如果使用Docker，开放必要端口
sudo ufw allow 7890  # 代理端口
sudo ufw allow 8080  # 应用端口（如果需要）
```

### 3. 日志管理
```bash
# 查看实时日志
sudo journalctl -u coinmonitor -f

# 查看历史日志
sudo journalctl -u coinmonitor --since "1 hour ago"

# 清理旧日志
sudo journalctl --vacuum-time=7d
```

## 📊 监控和维护

### 1. 服务管理
```bash
# 启动服务
sudo systemctl start coinmonitor

# 停止服务
sudo systemctl stop coinmonitor

# 重启服务
sudo systemctl restart coinmonitor

# 查看状态
sudo systemctl status coinmonitor

# 设置开机自启
sudo systemctl enable coinmonitor
```

### 2. 性能监控
```bash
# 查看资源使用
htop
df -h
free -h

# 查看网络连接
netstat -tulpn | grep python
```

### 3. 备份和恢复
```bash
# 备份配置
sudo cp /opt/coinmonitor/config.json /backup/

# 备份日志
sudo tar -czf /backup/logs-$(date +%Y%m%d).tar.gz /opt/coinmonitor/logs/
```

## 🚨 故障排除

### 1. 常见问题

#### 服务无法启动
```bash
# 检查日志
sudo journalctl -u coinmonitor -n 50

# 检查配置文件
sudo -u coinmonitor python3 -c "import json; json.load(open('config.json'))"
```

#### 网络连接问题
```bash
# 测试代理连接
curl -x http://127.0.0.1:7890 https://fapi.binance.com/fapi/v1/exchangeInfo

# 测试Telegram API
curl -x http://127.0.0.1:7890 "https://api.telegram.org/bot<YOUR_TOKEN>/getMe"
```

#### 权限问题
```bash
# 修复文件权限
sudo chown -R coinmonitor:coinmonitor /opt/coinmonitor
sudo chmod +x /opt/coinmonitor/monitor_bot.py
```

### 2. 性能优化

#### 内存优化
```bash
# 限制Python内存使用
export PYTHONMALLOC=malloc
export PYTHONDEVMODE=1
```

#### 网络优化
```bash
# 调整TCP参数
echo 'net.core.rmem_max = 16777216' >> /etc/sysctl.conf
echo 'net.core.wmem_max = 16777216' >> /etc/sysctl.conf
sysctl -p
```

## 🔄 更新部署

### 1. 代码更新
```bash
# 停止服务
sudo systemctl stop coinmonitor

# 备份当前版本
sudo cp -r /opt/coinmonitor /opt/coinmonitor.backup

# 更新代码
cd /opt/coinmonitor
sudo -u coinmonitor git pull

# 更新依赖
sudo -u coinmonitor venv/bin/pip install -r requirements.txt

# 启动服务
sudo systemctl start coinmonitor
```

### 2. 配置更新
```bash
# 备份配置
sudo cp /opt/coinmonitor/config.json /opt/coinmonitor/config.json.backup

# 修改配置
sudo nano /opt/coinmonitor/config.json

# 重启服务
sudo systemctl restart coinmonitor
```

## 📞 技术支持

如果遇到部署问题，请检查：
1. 系统日志：`sudo journalctl -u coinmonitor -f`
2. 应用日志：`tail -f /opt/coinmonitor/logs/*.log`
3. 网络连接：测试代理和API访问
4. 配置文件：确保JSON格式正确

## 🔒 安全建议

1. **使用非root用户运行**
2. **定期更新系统和依赖**
3. **配置防火墙规则**
4. **备份重要数据**
5. **监控系统资源使用**
6. **使用HTTPS代理（如果可能）** 