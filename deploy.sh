#!/bin/bash

# CoinMonitor 部署脚本
# 使用方法: ./deploy.sh [install|start|stop|restart|status|logs]

set -e

APP_NAME="coinmonitor"
APP_DIR="/opt/coinmonitor"
SERVICE_FILE="/etc/systemd/system/${APP_NAME}.service"
USER="coinmonitor"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 日志函数
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 检查是否为root用户
check_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "此脚本需要root权限运行"
        exit 1
    fi
}

# 安装依赖
install_dependencies() {
    log_info "安装系统依赖..."
    apt-get update
    apt-get install -y python3 python3-pip python3-venv git curl wget
    
    # 安装Docker（可选）
    if command -v docker &> /dev/null; then
        log_info "Docker已安装"
    else
        log_warn "Docker未安装，如需使用Docker部署请手动安装"
    fi
}

# 创建用户
create_user() {
    if id "$USER" &>/dev/null; then
        log_info "用户 $USER 已存在"
    else
        log_info "创建用户 $USER..."
        useradd -m -s /bin/bash $USER
        usermod -aG sudo $USER
    fi
}

# 安装应用
install_app() {
    log_info "安装 CoinMonitor..."
    
    # 创建应用目录
    mkdir -p $APP_DIR
    chown $USER:$USER $APP_DIR
    
    # 复制文件
    cp -r . $APP_DIR/
    chown -R $USER:$USER $APP_DIR
    
    # 创建虚拟环境
    su - $USER -c "cd $APP_DIR && python3 -m venv venv"
    su - $USER -c "cd $APP_DIR && source venv/bin/activate && pip install -r requirements.txt"
    
    # 创建日志目录
    mkdir -p $APP_DIR/logs
    chown $USER:$USER $APP_DIR/logs
    
    log_info "应用安装完成"
}

# 创建systemd服务
create_service() {
    log_info "创建systemd服务..."
    
    cat > $SERVICE_FILE << EOF
[Unit]
Description=CoinMonitor Bot
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=$USER
Group=$USER
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/venv/bin/python monitor_bot.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=$APP_NAME
Environment=PYTHONPATH=$APP_DIR
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    systemctl enable $APP_NAME
    
    log_info "systemd服务创建完成"
}

# 启动服务
start_service() {
    log_info "启动 $APP_NAME 服务..."
    systemctl start $APP_NAME
    sleep 2
    systemctl status $APP_NAME --no-pager
}

# 停止服务
stop_service() {
    log_info "停止 $APP_NAME 服务..."
    systemctl stop $APP_NAME
}

# 重启服务
restart_service() {
    log_info "重启 $APP_NAME 服务..."
    systemctl restart $APP_NAME
    sleep 2
    systemctl status $APP_NAME --no-pager
}

# 查看状态
show_status() {
    systemctl status $APP_NAME --no-pager
}

# 查看日志
show_logs() {
    journalctl -u $APP_NAME -f
}

# 主函数
main() {
    case "$1" in
        "install")
            check_root
            install_dependencies
            create_user
            install_app
            create_service
            log_info "安装完成！使用 './deploy.sh start' 启动服务"
            ;;
        "start")
            check_root
            start_service
            ;;
        "stop")
            check_root
            stop_service
            ;;
        "restart")
            check_root
            restart_service
            ;;
        "status")
            show_status
            ;;
        "logs")
            show_logs
            ;;
        *)
            echo "使用方法: $0 {install|start|stop|restart|status|logs}"
            echo ""
            echo "命令说明:"
            echo "  install  - 安装 CoinMonitor"
            echo "  start    - 启动服务"
            echo "  stop     - 停止服务"
            echo "  restart  - 重启服务"
            echo "  status   - 查看服务状态"
            echo "  logs     - 查看实时日志"
            exit 1
            ;;
    esac
}

main "$@" 