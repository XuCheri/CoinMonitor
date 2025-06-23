import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any, Tuple, cast

from telegram import Bot
from .base_monitor import BaseMonitor
from utils.logger import log_error, log_info


class FundingRateMonitor(BaseMonitor):
    """
    监控合约资金费率。
    - 定期（每半小时）检查高资金费率的币种并发送汇总报告。
    - 提供一个可被外部调用的方法来按需触发检查。
    """
    def __init__(self, bot: Bot, chat_id: int, topic_id: int, proxy_url: Optional[str] = None, interval: int = 60, threshold: float = 0.001, **kwargs):
        # 基础间隔设为1分钟，check方法内部会判断是否是整点或半点
        super().__init__(bot, chat_id, topic_id, proxy_url, interval, **kwargs)
        self.threshold = threshold
        self.last_checked_minute = -1

    async def check(self):
        """
        周期性运行，但在特定分钟（0, 30）才执行实际的检查逻辑。
        """
        now = datetime.now()
        minute = now.minute
        
        # 检查是否到达预定时间且本分钟内未检查过
        if minute in (0, 30) and minute != self.last_checked_minute:
            log_info(f"⏰ {self.monitor_name}: Reached {now:%H:%M}, checking funding rates.")
            self.last_checked_minute = minute
            
            await self._check_and_send_alerts()
        elif minute not in (0, 30):
            # 重置检查记录，以便下一个周期能正确触发
            self.last_checked_minute = -1

    async def _check_and_send_alerts(self):
        """检查并发送资金费率警报"""
        alerts = await self.get_funding_rate_alerts()
        if alerts:
            log_info(f"📢 {self.monitor_name}: Found {len(alerts)} high funding rates. Sending alert.")
            await self._send_alerts_message(alerts)
        else:
            log_info(f"✅ {self.monitor_name}: No high funding rates found at this time.")

    async def manual_check(self):
        """手动触发资金费率检查"""
        log_info(f"🔍 {self.monitor_name}: Manual funding rate check triggered.")
        await self._check_and_send_alerts()

    async def get_funding_rate_alerts(self) -> List[Dict[str, Any]]:
        """
        获取资金费率警报。
        此方法获取并处理所有相关数据，返回一个警报字典列表，可被周期任务或按需命令调用。
        """
        try:
            # 1. 并发获取基础数据
            urls = {
                "funding": "https://fapi.binance.com/fapi/v1/premiumIndex",
                "ticker": "https://fapi.binance.com/fapi/v1/ticker/24hr",
                "spot_price": "https://api.binance.com/api/v3/ticker/price"
            }
            tasks = [self.fetch_json(url) for url in urls.values()]
            # 如果任何一个请求失败，gather 会立即抛出异常
            results = await asyncio.gather(*tasks)
            funding_data, ticker_data, spot_price_data = results[0], results[1], results[2]

            ticker_dict = {item['symbol']: item for item in ticker_data}
            spot_price_dict = {item['symbol']: float(item['price']) for item in spot_price_data}
            
            # 2. 筛选出费率异常的币种
            symbols_to_check = []
            for item in funding_data:
                if item.get('symbol') and item['symbol'].endswith('USDT') and abs(float(item['lastFundingRate'])) >= self.threshold:
                    symbols_to_check.append(item['symbol'])
            
            # 3. 并发获取这些币种的额外数据 (K线)
            kline_tasks = [self._fetch_price_changes(symbol) for symbol in symbols_to_check]
            extra_data_results = await asyncio.gather(*kline_tasks)

            extra_data_dict = {}
            for res in extra_data_results:
                if not isinstance(res, Exception):
                    symbol, changes = res
                    extra_data_dict[symbol] = changes

            # 4. 组装警报信息
            alerts = []
            for item in funding_data:
                symbol = item['symbol']
                if symbol not in symbols_to_check:
                    continue

                open_interest_data = await self.fetch_json(f"https://fapi.binance.com/fapi/v1/openInterest?symbol={symbol}")
                
                kline_changes = extra_data_dict.get(symbol, {})
                ticker = ticker_dict.get(symbol)
                spot_price = spot_price_dict.get(symbol)

                alerts.append({
                    "symbol": symbol,
                    "funding_rate": float(item['lastFundingRate']),
                    "mark_price": float(item['markPrice']),
                    "spot_price_str": f"{spot_price:.4f}" if spot_price else "N/A",
                    "price_change": float(ticker['priceChangePercent']) if ticker else 0,
                    "volume": float(ticker['quoteVolume']) if ticker else 0,
                    "open_interest": float(open_interest_data.get('openInterest', 0)) / 1e6,
                    "funding_time": (datetime.fromtimestamp(int(item['nextFundingTime']) // 1000, tz=timezone.utc) + timedelta(hours=8)).strftime("%H:%M"),
                    **kline_changes
                })

            alerts.sort(key=lambda x: abs(x['funding_rate']), reverse=True)
            return alerts
            
        except Exception as e:
            log_error(f"❌ {self.monitor_name}: Failed to get funding rate data: {e}")
            return []

    def get_status(self) -> str:
        """返回监控器的当前状态描述。"""
        return (
            f"<b>{self.monitor_name}</b>\n"
            f"  - 监控状态: {'运行中' if self._running else '已停止'}\n"
            f"  - 检查周期: 每小时的0分和30分\n"
            f"  - 费率阈值: {self.threshold * 100:.4f}%\n"
            f"  - (支持交互命令: <code>/funding</code>)"
        )

    async def _fetch_price_changes(self, symbol: str) -> Tuple[str, Dict[str, float]]:
        """获取单个币种的 30m, 1h, 4h 价格变化。"""
        intervals = {"30m": "30m", "1h": "1h", "4h": "4h"}
        changes: Dict[str, Any] = {"symbol": symbol}
        
        async def get_change(interval_key, interval_val):
            url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval={interval_val}&limit=2"
            data = await self.fetch_json(url)
            if len(data) < 2: return 0
            return (float(data[1][4]) - float(data[0][1])) / float(data[0][1]) * 100
        
        tasks = [get_change(k, v) for k,v in intervals.items()]
        results = await asyncio.gather(*tasks)

        for i, key in enumerate(intervals.keys()):
            changes[f"change_{key}"] = results[i] if not isinstance(results[i], Exception) else 0.0

        return symbol, changes

    async def _send_alerts_message(self, alerts: list):
        """格式化并发送汇总的警报消息。"""
        message = "⚠️ <b>异常资金费率预警</b>\n\n"
        for a in alerts:
            msg_part = (
                f"🚨 <b>{a['symbol']}</b> ({a['funding_time']}结算)\n"
                f"<b>费率: <code>{a['funding_rate']*100:.4f}%</code></b>\n"
                f"价格: <code>{a['mark_price']:.4f}</code> (现货: <code>{a['spot_price_str']}</code>)\n"
                f"24h:<code>{a['price_change']:.2f}%</code>|30m:<code>{a.get('change_30m', 0):.2f}%</code>|1h:<code>{a.get('change_1h', 0):.2f}%</code>|4h:<code>{a.get('change_4h', 0):.2f}%</code>\n"
                f"成交额: <code>{a['volume']/1e6:.2f}M</code> | 持仓: <code>{a['open_interest']:.2f}M</code>\n\n"
            )
            if len(message) + len(msg_part) > 4096:
                message += "⚠️ 消息过长，已截断部分内容..."
                break
            message += msg_part

        await self.send_message(message, parse_mode="HTML")

