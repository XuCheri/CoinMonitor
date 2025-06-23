#!/usr/bin/env python3
"""
测试资金费率监控器
"""
import asyncio
import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from monitors.funding_rate_monitor import FundingRateMonitor
from utils.logger import log_info, log_error

class MockBot:
    async def send_message(self, text, **kwargs):
        log_info(f"📤 MockBot发送消息: {text[:100]}...")
    
    async def send_photo(self, photo, **kwargs):
        log_info(f"📤 MockBot发送图片: {kwargs.get('caption', '')[:100]}...")

async def test_funding_monitor():
    """测试资金费率监控器"""
    log_info("🔍 开始测试资金费率监控器...")
    
    # 创建模拟的Bot和监控器
    mock_bot = MockBot()
    monitor = FundingRateMonitor(
        bot=mock_bot,
        chat_id=123456,
        topic_id=2,
        proxy_url="http://127.0.0.1:7890",
        interval=60,
        threshold=0.01  # 1%阈值
    )
    
    try:
        # 测试获取资金费率警报
        log_info("📊 测试获取资金费率警报...")
        alerts = await monitor.get_funding_rate_alerts()
        
        if alerts:
            log_info(f"✅ 找到 {len(alerts)} 个异常资金费率")
            for i, alert in enumerate(alerts[:5], 1):  # 只显示前5个
                log_info(f"{i}. {alert['symbol']}: {alert['funding_rate']*100:+.4f}%")
            
            # 测试发送警报消息
            log_info("📤 测试发送警报消息...")
            await monitor._send_alerts_message(alerts)
        else:
            log_info("✅ 当前没有异常资金费率")
            
    except Exception as e:
        log_error(f"❌ 测试失败: {e}")

if __name__ == "__main__":
    asyncio.run(test_funding_monitor()) 