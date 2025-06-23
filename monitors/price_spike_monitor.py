import asyncio
import io
from datetime import datetime
from typing import Optional

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from mplfinance.original_flavor import candlestick_ohlc
from telegram import Bot

from .base_monitor import BaseMonitor
from utils.logger import log_error, log_info


class PriceSpikeMonitor(BaseMonitor):
    """
    监控价格在短时间内的大幅波动（插针）。
    满足特定振幅或价格变动条件时发出警报。
    """

    def __init__(
        self,
        bot: Bot,
        chat_id: int,
        topic_id: int,
        proxy_url: Optional[str] = None,
        interval: int = 60,
        watchlist: Optional[list] = None,
        spike_config: Optional[dict] = None,
        **kwargs
    ):
        super().__init__(bot, chat_id, topic_id, proxy_url, interval, **kwargs)
        self.watchlist = watchlist
        self.symbols = []
        self.previous_open_interest = {}

        default_config = {
            "long_candle_spike": 0.01253, # 连续两根长下影线
            "single_candle_spike": 0.02, # 单根蜡烛振幅
            "price_change_1m": 0.015, # 1分钟价格变动
            "price_change_5m": 0.02, # 5分钟价格变动
        }
        self.spike_config = spike_config if spike_config is not None else default_config

    async def _fetch_binance_data(self, endpoint: str, params: Optional[dict] = None) -> list:
        """从币安U本位合约API获取数据的辅助函数。"""
        base_url = "https://fapi.binance.com"
        # 此处返回的数据是 list, 不是 dict, 所以 fetch_json 可能不适用, 需要看 BaseMonitor 实现
        # 假设 BaseMonitor.fetch_json 能正确处理
        return await self.fetch_json(f"{base_url}{endpoint}", params=params)

    async def _initialize_symbols(self):
        """初始化要监控的交易对列表。"""
        if self.watchlist:
            self.symbols = self.watchlist
            log_info(f"{self.monitor_name}: Using watchlist of {len(self.symbols)} symbols.")
            return

        log_info(f"{self.monitor_name}: Fetching all perpetual symbols from Binance...")
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # fetch_json 在 BaseMonitor 中返回 dict, 但 exchangeInfo 返回的是 dict
                data = await self.fetch_json("https://fapi.binance.com/fapi/v1/exchangeInfo")
                self.symbols = [s['symbol'] for s in data['symbols'] if s['contractType'] == 'PERPETUAL']
                log_info(f"{self.monitor_name}: Found {len(self.symbols)} symbols.")
                return
            except Exception as e:
                log_error(f"❌ {self.monitor_name}: Failed to fetch symbols (attempt {attempt + 1}/{max_retries}): {str(e)}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(5)  # 等待5秒后重试
                else:
                    log_error(f"❌ {self.monitor_name}: All retry attempts failed. Using fallback symbols.")
                    # 使用一些常见的交易对作为后备
                    self.symbols = [
                        "BTCUSDT", "ETHUSDT", "BNBUSDT", "ADAUSDT", "SOLUSDT",
                        "DOTUSDT", "DOGEUSDT", "AVAXUSDT", "MATICUSDT", "LINKUSDT"
                    ]
                    log_info(f"{self.monitor_name}: Using fallback list of {len(self.symbols)} symbols.")

    async def check(self):
        """监控器主逻辑：并发检查，汇总并发送警报。"""
        if not self.symbols:
            await self._initialize_symbols()
            if not self.symbols:
                log_error(f"{self.monitor_name}: No symbols to monitor.")
                await asyncio.sleep(self.interval * 5)
                return

        tasks = [self._check_symbol(symbol) for symbol in self.symbols]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        alerts = []
        charts = []
        for res in results:
            if isinstance(res, dict):
                alerts.append(res['alert_text'])
                charts.append(res['chart_data'])
            elif isinstance(res, Exception):
                log_error(f"❌ {self.monitor_name}: A check task failed: {res}")

        if alerts:
            log_info(f"📢 {self.monitor_name}: Found {len(alerts)} price spikes. Sending alerts.")
            message = "🚨 <b>价格异动预警</b>\n\n" + "\n\n".join(alerts)
            await self.send_message(message, parse_mode="HTML")

            chart_tasks = [self._send_chart(chart_info) for chart_info in charts]
            await asyncio.gather(*chart_tasks, return_exceptions=True)
    
    async def _send_chart(self, chart_info: dict):
        """生成并发送单个图表。"""
        try:
            chart_image_buf = self._generate_chart(
                chart_info['symbol'],
                chart_info['klines'],
                f"{chart_info['symbol']} 1分钟K线 (近1小时)"
            )
            await self.send_photo(photo=chart_image_buf.getvalue())
        except Exception as e:
            log_error(f"❌ {self.monitor_name}: Failed to send chart for {chart_info.get('symbol', 'N/A')}: {e}")

    async def _check_symbol(self, symbol: str) -> Optional[dict]:
        """检查单个交易对是否有价格异动。"""
        # 1. 获取K线数据
        klines_60m = await self._fetch_binance_data("/fapi/v1/klines", {'symbol': symbol, 'interval': '1m', 'limit': 60})
        if len(klines_60m) < 20: # 需要足够的数据进行分析
            return None

        klines_20m = klines_60m[-20:]

        # 2. 计算振幅和价格变化
        amplitudes = [((float(k[2]) - float(k[3])) / float(k[3])) if float(k[3]) > 0 else 0 for k in klines_20m]
        
        last_amplitude = amplitudes[-1]
        prev_amplitude = amplitudes[-2]
        
        c = self.spike_config
        close_change_1m = (float(klines_20m[-1][4]) - float(klines_20m[-2][4])) / float(klines_20m[-2][4])
        close_change_5m = (float(klines_20m[-1][4]) - float(klines_20m[-6][4])) / float(klines_20m[-6][4])

        # 3. 判断是否触发预警
        triggered = (
            (last_amplitude >= c['long_candle_spike'] and prev_amplitude >= c['long_candle_spike']) or
            last_amplitude >= c['single_candle_spike'] or
            abs(close_change_1m) >= c['price_change_1m'] or
            abs(close_change_5m) >= c['price_change_5m']
        )

        if triggered:
            # 4. 获取额外数据并格式化消息
            current_price = float(klines_20m[-1][4])
            oi_data = await self.fetch_json(f"https://fapi.binance.com/fapi/v1/openInterest?symbol={symbol}")
            current_oi = float(oi_data.get('openInterest', 0))

            last_oi = self.previous_open_interest.get(symbol, 0)
            oi_change = (current_oi - last_oi) / last_oi if last_oi > 0 else 0
            self.previous_open_interest[symbol] = current_oi

            emoji = "📈" if close_change_1m > 0 else "📉"
            alert_text = (
                f"{emoji} <b>{symbol}</b> 价格异动\n"
                f"💰 现价: <code>{current_price:.4f}</code>\n"
                f"📊 1m变化: <code>{close_change_1m*100:.2f}%</code> | 5m变化: <code>{close_change_5m*100:.2f}%</code>\n"
                f"📶 K线振幅: <code>{last_amplitude*100:.2f}%</code>\n"
                f"🧾 持仓: <code>{current_oi/1e6:.2f}M</code> (变化: <code>{oi_change*100:.2f}%</code>)"
            )
            
            chart_data = {'symbol': symbol, 'klines': klines_60m}
            return {'alert_text': alert_text, 'chart_data': chart_data}
        
        return None

    def add_to_watchlist(self, symbol: str) -> str:
        """动态向监控列表添加一个交易对。"""
        symbol = symbol.upper()
        if symbol in self.symbols:
            return f"🟡 <b>{self.monitor_name}</b>: <code>{symbol}</code> 已在监控列表中。"

        if not self.watchlist:
            self.watchlist = list(self.symbols)

        self.watchlist.append(symbol)
        self.symbols.append(symbol)
        return f"✅ <b>{self.monitor_name}</b>: 已将 <code>{symbol}</code> 添加到监控列表。"

    def remove_from_watchlist(self, symbol: str) -> str:
        """动态从监控列表移除一个交易对。"""
        symbol = symbol.upper()
        if symbol not in self.symbols:
            return f"🟡 <b>{self.monitor_name}</b>: <code>{symbol}</code> 不在监控列表中。"

        if self.watchlist:
            self.watchlist = [s for s in self.watchlist if s != symbol]
        self.symbols = [s for s in self.symbols if s != symbol]
        return f"✅ <b>{self.monitor_name}</b>: 已从监控列表移除 <code>{symbol}</code>。"

    def get_status(self) -> str:
        """返回监控器的当前状态描述。"""
        status = (
            f"<b>{self.monitor_name}</b>\n"
            f"  - 监控状态: {'运行中' if self._running else '已停止'}\n"
            f"  - 检查间隔: {self.interval}秒\n"
            f"  - 触发条件:\n"
            f"    - 连续长蜡烛振幅: > {self.spike_config['long_candle_spike'] * 100:.2f}%\n"
            f"    - 单根蜡烛振幅: > {self.spike_config['single_candle_spike'] * 100:.2f}%\n"
            f"    - 1分钟价格变化: > {self.spike_config['price_change_1m'] * 100:.2f}%\n"
            f"    - 5分钟价格变化: > {self.spike_config['price_change_5m'] * 100:.2f}%\n"
        )
        if self.watchlist:
            status += f"  - 监控列表: <code>{', '.join(self.watchlist)}</code> ({len(self.symbols)}个)\n"
        else:
            status += f"  - 监控列表: 全部永续合约 ({len(self.symbols)}个)\n"
        return status

    def _generate_chart(self, symbol: str, klines: list, title: str) -> io.BytesIO:
        """使用 mplfinance 生成K线图。"""
        ohlc = []
        for entry in klines:
            timestamp = mdates.date2num(datetime.fromtimestamp(int(entry[0]) / 1000))
            ohlc.append((timestamp, float(entry[1]), float(entry[2]), float(entry[3]), float(entry[4])))

        fig, ax = plt.subplots(figsize=(10, 5))
        candlestick_ohlc(ax, ohlc, width=0.0006, colorup='g', colordown='r', alpha=0.8)
        
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
        ax.set_title(title, fontsize=14)
        ax.set_ylabel("价格 (USDT)")
        ax.grid(True)
        
        plt.xticks(rotation=30)
        plt.tight_layout()

        buffer = io.BytesIO()
        plt.savefig(buffer, format='png')
        buffer.seek(0)
        plt.close(fig)
        return buffer
