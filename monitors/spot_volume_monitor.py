import asyncio
from datetime import datetime
from typing import Optional

from .base_monitor import BaseMonitor
from utils.logger import log_error, log_info


class SpotVolumeMonitor(BaseMonitor):
    """
    每天8点发送币安现货市场24小时成交额最高的币种排行榜。
    """
    SPOT_API_URL = "https://api.binance.com/api/v3"

    def __init__(self, bot, chat_id: int, topic_id: int, proxy_url: Optional[str] = None, interval: int = 60, top_n: int = 20, **kwargs):
        super().__init__(bot, chat_id, topic_id, proxy_url, interval, **kwargs)
        self.top_n = top_n
        self.last_checked_hour = -1

    async def check(self):
        """
        周期性运行，但在每天8点才执行实际的检查逻辑。
        """
        now = datetime.now()
        hour = now.hour
        
        # 检查是否到达预定时间（8点）且本小时内未检查过
        if hour == 8 and hour != self.last_checked_hour:
            log_info(f"⏰ {self.monitor_name}: Reached {now:%H:%M}, sending daily volume report.")
            self.last_checked_hour = hour
            
            await self._send_volume_report()
        elif hour != 8:
            # 重置检查记录，以便下一个周期能正确触发
            self.last_checked_hour = -1

    async def _send_volume_report(self):
        """
        获取24小时ticker数据，计算成交额排名，并发送报告。
        """
        log_info(f"{self.monitor_name}: Fetching spot 24hr ticker data...")
        try:
            # 1. 获取数据
            url = f"{self.SPOT_API_URL}/ticker/24hr"
            data = await self.fetch_json(url)

            # 2. 数据处理与排序
            usdt_pairs = [d for d in data if d.get('symbol', '').endswith("USDT")]
            if not usdt_pairs:
                log_info(f"{self.monitor_name}: No USDT pairs found in the response.")
                return
            
            top_pairs = sorted(usdt_pairs, key=lambda x: float(x.get('quoteVolume', 0)), reverse=True)[:self.top_n]

            # 3. 格式化消息
            message = f"📊 <b>币安现货24H成交额排行 Top {self.top_n}</b>\n\n"
            for idx, item in enumerate(top_pairs, start=1):
                symbol = item.get('symbol', 'N/A')
                price = float(item.get('lastPrice', 0))
                volume_24h = float(item.get('quoteVolume', 0)) / 1_000_000  # 转换为百万
                price_change_percent = float(item.get('priceChangePercent', 0))
                
                emoji = "📈" if price_change_percent >= 0 else "📉"
                message += (
                    f"{idx:02d}. <b>{symbol}</b> {emoji}\n"
                    f"   ├ 价格: <code>{price:.4f}</code>\n"
                    f"   ├ 24h成交额: <code>{volume_24h:.2f}M</code>\n"
                    f"   └ 24h涨跌: <code>{price_change_percent:.2f}%</code>\n\n"
                )
            
            # 4. 发送消息
            await self.send_message(message, parse_mode="HTML")
            log_info(f"📢 {self.monitor_name}: Sent Top {self.top_n} spot volume report.")

        except Exception as e:
            # 错误已经在基类的 run 方法中被捕获和记录，这里可以只记录特定的上下文
            log_error(f"❌ An error occurred in {self.monitor_name} check: {e}")
            # 重新抛出异常，让基类处理日志和通知
            raise e

    def get_status(self) -> str:
        """返回监控器的当前状态描述。"""
        return (
            f"<b>{self.monitor_name}</b>\n"
            f"  - 监控状态: {'运行中' if self._running else '已停止'}\n"
            f"  - 推送时间: 每天8点\n"
            f"  - 排行榜数量: Top {self.top_n}"
        )
