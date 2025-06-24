#!/usr/bin/env python3
"""
持仓监控器测试脚本
用于测试持仓监控器的基本功能
"""

import asyncio
import json
import sys
from datetime import datetime
from monitors.position_monitor import PositionMonitor
from utils.logger import log_info, log_error

class MockBot:
    """模拟Telegram Bot对象"""
    async def send_message(self, chat_id, text, **kwargs):
        print(f"📱 发送消息到 {chat_id}:")
        print(text)
        print("-" * 50)
    
    async def send_photo(self, chat_id, photo, **kwargs):
        print(f"📷 发送图片到 {chat_id}")

async def test_position_monitor():
    """测试持仓监控器"""
    print("🧪 开始测试持仓监控器...")
    
    # 加载配置
    try:
        with open('config.json', 'r', encoding='utf-8') as f:
            config = json.load(f)
    except FileNotFoundError:
        print("❌ 找不到 config.json 文件")
        return
    except json.JSONDecodeError as e:
        print(f"❌ 配置文件格式错误: {e}")
        return
    
    # 获取币安配置
    binance_config = config.get("binance", {})
    api_key = binance_config.get("api_key")
    api_secret = binance_config.get("api_secret")
    
    if not api_key or not api_secret or api_key == "YOUR_BINANCE_API_KEY":
        print("❌ 请在 config.json 中配置正确的币安API密钥")
        print("示例:")
        print('"binance": {')
        print('  "api_key": "your_api_key_here",')
        print('  "api_secret": "your_api_secret_here",')
        print('  "testnet": false')
        print('}')
        return
    
    # 创建模拟Bot
    mock_bot = MockBot()
    
    # 创建持仓监控器
    try:
        monitor = PositionMonitor(
            bot=mock_bot,
            chat_id=config["chat_id"],
            topic_id=999,  # 测试用topic_id
            proxy_url=config.get("proxy_url"),
            interval=3600,
            api_key=api_key,
            api_secret=api_secret,
            testnet=binance_config.get("testnet", False),
            auto_report=True,
            report_time="09:00",
            include_history=True,
            history_days=7
        )
        
        print("✅ 持仓监控器初始化成功")
        
        # 测试获取状态
        print("\n📊 监控器状态:")
        print(monitor.get_status())
        
        # 测试获取当前持仓
        print("\n🔍 测试获取当前持仓...")
        try:
            current_positions = await monitor.get_current_positions()
            print(f"✅ 成功获取当前持仓，期货持仓数: {len(current_positions.get('futures', []))}")
            print(f"现货余额数: {len(current_positions.get('spot', []))}")
        except Exception as e:
            print(f"❌ 获取当前持仓失败: {e}")
        
        # 测试获取历史仓位
        print("\n📈 测试获取历史仓位...")
        try:
            position_history = await monitor.get_position_history(days=3)
            print(f"✅ 成功获取历史仓位，交易记录数: {len(position_history)}")
        except Exception as e:
            print(f"❌ 获取历史仓位失败: {e}")
        
        # 测试生成报告
        print("\n📋 测试生成持仓报告...")
        try:
            report = monitor.format_position_report(current_positions, position_history)
            print("✅ 持仓报告生成成功")
            print("\n" + "="*50)
            print("📊 持仓报告预览:")
            print("="*50)
            print(report[:500] + "..." if len(report) > 500 else report)
        except Exception as e:
            print(f"❌ 生成持仓报告失败: {e}")
        
        # 测试手动获取报告
        print("\n🔄 测试手动获取报告...")
        try:
            manual_report = await monitor.get_manual_report()
            print("✅ 手动报告获取成功")
        except Exception as e:
            print(f"❌ 手动报告获取失败: {e}")
        
    except Exception as e:
        print(f"❌ 持仓监控器初始化失败: {e}")
        return
    
    print("\n🎉 测试完成!")

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    asyncio.run(test_position_monitor()) 