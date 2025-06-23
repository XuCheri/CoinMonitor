import asyncio
from datetime import datetime
import io
from typing import Optional, cast, List, Dict, Any

import aiohttp
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd
from telegram import Bot

from .base_monitor import BaseMonitor
from utils.logger import log_error, log_info


class OpenInterestMonitor(BaseMonitor):
    """
    监控永续合约的持仓量（Open Interest）变化。
    当持仓量在短时间内发生显著变化时，结合价格变动发出警报。
    """

    def __init__(self, bot: Bot, chat_id: int, topic_id: int, proxy_url: Optional[str] = None, interval: int = 60, threshold: float = 0.05, watchlist: Optional[list] = None, **kwargs):
        super().__init__(bot, chat_id, topic_id, proxy_url, interval, **kwargs)
        self.threshold = threshold
        self.watchlist = watchlist
        self.previous_open_interest = {}
        self.previous_prices = {}
        self.symbols = []
        self.invalid_symbols = set() # 用于存储无效的交易对

    async def _fetch_binance_data(self, endpoint: str, params: Optional[dict] = None) -> Any:
        """从币安U本位合约API获取数据的辅助函数。"""
        base_url = "https://fapi.binance.com"
        return await self.fetch_json(f"{base_url}{endpoint}", params=params)

    async def _initialize_symbols(self):
        """从币安获取所有永续合约交易对，如果未提供 watchlist 则使用全量。"""
        if self.watchlist:
            self.symbols = self.watchlist
            log_info(f"{self.monitor_name}: Using watchlist of {len(self.symbols)} symbols.")
            return

        log_info(f"{self.monitor_name}: Fetching all perpetual symbols from Binance...")
        max_retries = 3
        for attempt in range(max_retries):
            try:
                data = await self._fetch_binance_data("/fapi/v1/exchangeInfo")
                self.symbols = [s['symbol'] for s in data['symbols'] if s['contractType'] == 'PERPETUAL']
                log_info(f"{self.monitor_name}: Found {len(self.symbols)} perpetual symbols.")
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
        """
        监控器的主检查逻辑。
        使用 asyncio.gather 并发检查所有交易对。
        """
        if not self.symbols:
            await self._initialize_symbols()
            if not self.symbols:
                log_error(f"{self.monitor_name}: No symbols to monitor.")
                # 等待更长时间后重试，而不是快速循环
                await asyncio.sleep(self.interval * 5)
                return

        # 过滤掉已知的无效交易对
        symbols_to_check = [s for s in self.symbols if s not in self.invalid_symbols]
        tasks = [self._check_symbol(symbol) for symbol in symbols_to_check]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 检查并发任务的结果，记录任何出现的异常
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                # 确保索引在范围内，以防万一
                if i < len(symbols_to_check):
                    log_error(f"❌ {self.monitor_name}: Error checking symbol {symbols_to_check[i]}: {result}")
    
    async def _check_symbol(self, symbol: str):
        """检查单个交易对的持仓量和价格变化。"""
        try:
            # 1. 获取当前持仓量和价格
            oi_data = await self._fetch_binance_data("/fapi/v1/openInterest", {'symbol': symbol})
            current_oi = float(oi_data.get('openInterest', 0))
            
            klines = await self._fetch_binance_data("/fapi/v1/klines", {'symbol': symbol, 'interval': '1m', 'limit': 60})
            price_data = [(int(k[0]), float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5])) for k in klines]
            current_price = price_data[-1][4]

            # 2. 与上一次记录的数据进行比较
            last_entry = self.previous_open_interest.get(symbol)
            if last_entry:
                last_oi, _ = last_entry
                oi_change = (current_oi - last_oi) / last_oi if last_oi else 0
                
                last_price = self.previous_prices.get(symbol, current_price)
                price_change = (current_price - last_price) / last_price if last_price else 0

                # 3. 如果变化超过阈值，则发送警报
                if abs(oi_change) >= self.threshold:
                    await self._send_alert_and_chart(symbol, current_oi, oi_change, current_price, price_change, price_data)

            # 4. 更新状态
            self.previous_open_interest[symbol] = (current_oi, datetime.now())
            self.previous_prices[symbol] = current_price
        
        except aiohttp.ClientResponseError as e:
            # 如果收到400错误，说明交易对很可能已下架或无效
            if e.status == 400:
                log_info(f"⚠️ Symbol {symbol} seems invalid (HTTP 400). Adding to ignore list.")
                self.invalid_symbols.add(symbol)
                # 不再向上抛出异常，优雅地处理掉
                return
            # 其他HTTP错误则继续抛出，以便被上层记录
            raise e
        except Exception as e:
            # 其他类型的错误也继续抛出
            raise e

    async def _send_alert_and_chart(self, symbol, current_oi, oi_change, current_price, price_change, price_data):
        """生成并发送警报消息和图表。"""
        trading_action = self._get_trading_action(oi_change, price_change)
        
        alert_caption = (
            f"{trading_action} <b>{symbol}</b>\n"
            f"🧾 当前持仓: <code>{current_oi/1e6:.2f}M</code>\n"
            f"📈 持仓变化: <code>{oi_change*100:.2f}%</code>\n"
            f"💰 当前价格: <code>{current_price:.4f} USDT</code>\n"
            f"💹 价格变化: <code>{price_change*100:.2f}%</code>"
        )
        
        try:
            chart_buf = await self._generate_chart(symbol, price_data)
            await self.send_photo(photo=chart_buf.getvalue(), caption=alert_caption, parse_mode="HTML")
        except Exception as e:
            log_error(f"❌ {self.monitor_name}: Failed to generate chart for {symbol}: {e}")
            #即使图表生成失败，也发送文本消息
            await self.send_message(alert_caption, parse_mode="HTML")

    def _get_trading_action(self, oi_change: float, price_change: float) -> str:
        """根据持仓量和价格变化判断市场行为。"""
        if oi_change > 0 and price_change > 0: return "🔵 多头开仓" # Longs opening
        if oi_change > 0 and price_change < 0: return "🔴 空头开仓" # Shorts opening
        if oi_change < 0 and price_change > 0: return "🟠 空头平仓" # Shorts closing
        if oi_change < 0 and price_change < 0: return "🟢 多头平仓" # Longs closing
        return "⚪️"

    def add_to_watchlist(self, symbol: str) -> str:
        """动态向监控列表添加一个交易对。"""
        symbol = symbol.upper()
        if symbol in self.symbols:
            return f"🟡 <b>{self.monitor_name}</b>: <code>{symbol}</code> 已在监控列表中。"

        # 如果原本是全量监控，现在切换到 watchlist 模式
        if not self.watchlist:
            self.watchlist = list(self.symbols)

        self.watchlist.append(symbol)
        self.symbols.append(symbol)
        # 如果这个币之前被标记为无效，现在尝试重新监控它
        if symbol in self.invalid_symbols:
            self.invalid_symbols.remove(symbol)
        
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
            f"  - 变化阈值: {self.threshold * 100}%\n"
        )
        if self.watchlist:
            status += f"  - 监控列表: <code>{', '.join(self.watchlist)}</code>\n"
            status += f"  - (当前总计: {len(self.symbols)}个)\n"
        else:
            status += f"  - 监控列表: 全部永续合约 ({len(self.symbols)}个)\n"
        
        if self.invalid_symbols:
            status += f"  - 已忽略的无效合约: {len(self.invalid_symbols)}个\n"
            
        return status

    async def _generate_chart(self, symbol: str, price_data: list) -> io.BytesIO:
        """生成包含价格、持仓量历史和多空比的图表。"""
        # 1. 并发获取历史数据
        tasks = [
            self._fetch_binance_data("/futures/data/openInterestHist", {'symbol': symbol, 'period': '5m', 'limit': 48}),
            self._fetch_binance_data("/futures/data/globalLongShortAccountRatio", {'symbol': symbol, 'period': '5m', 'limit': 48})
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        oi_hist_raw, ls_hist_raw = results[0], results[1]

        if isinstance(oi_hist_raw, Exception):
            raise Exception(f"Failed to fetch OI history for chart: {oi_hist_raw}")
        assert not isinstance(oi_hist_raw, BaseException)

        if isinstance(ls_hist_raw, Exception):
            raise Exception(f"Failed to fetch L/S ratio history for chart: {ls_hist_raw}")
        assert not isinstance(ls_hist_raw, BaseException)

        oi_data = [(int(d['timestamp']), float(d['sumOpenInterest'])) for d in oi_hist_raw]
        ls_data = [(int(d['timestamp']), float(d['longShortRatio'])) for d in ls_hist_raw]
        
        # 2. 创建 Pandas DataFrames
        df_price = pd.DataFrame(price_data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']) # type: ignore
        df_price['timestamp'] = pd.to_datetime(df_price['timestamp'], unit='ms')
        df_price.set_index('timestamp', inplace=True)

        df_oi = pd.DataFrame(oi_data, columns=['timestamp', 'oi']) # type: ignore
        df_oi['timestamp'] = pd.to_datetime(df_oi['timestamp'], unit='ms')
        df_oi.set_index('timestamp', inplace=True)

        df_ls = pd.DataFrame(ls_data, columns=['timestamp', 'ls_ratio']) # type: ignore
        df_ls['timestamp'] = pd.to_datetime(df_ls['timestamp'], unit='ms')
        df_ls.set_index('timestamp', inplace=True)

        # 3. 绘制图表
        fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(12, 10), sharex=True, gridspec_kw={'height_ratios': [3, 1.5, 1]})
        fig.tight_layout(pad=3.0)
        ax1.set_title(f"{symbol} Price & OI Overview", fontsize=14)

        # 价格 K线
        for i in range(len(df_price)):
            o, h, l, c = df_price.iloc[i][['open', 'high', 'low', 'close']]
            color = 'g' if c >= o else 'r'
            ax1.plot([df_price.index[i], df_price.index[i]], [l, h], color=color, linewidth=1, alpha=0.8)
            ax1.plot([df_price.index[i], df_price.index[i]], [o, c], color=color, linewidth=5, solid_capstyle='round')
        ax1.set_ylabel("Price (USDT)")
        ax1.grid(True)

        # 持仓量
        ax2.bar(df_oi.index, df_oi['oi'], color='lightgreen', width=0.002, label='Open Interest')
        ax2.plot(df_oi.index, df_oi['oi'].rolling(3).mean(), color='orange', linewidth=1.5, label='OI 3P MA')
        ax2.set_ylabel("Open Interest")
        ax2.legend()
        ax2.grid(True)

        # 多空比
        ax3.bar(df_ls.index, df_ls['ls_ratio'], color='lightblue', width=0.002, label='L/S Ratio')
        ax3.plot(df_ls.index, df_ls['ls_ratio'].rolling(3).mean(), color='gold', linewidth=1.5, label='L/S 3P MA')
        ax3.set_ylabel("L/S Ratio")
        ax3.set_xlabel("Time")
        ax3.legend()
        ax3.grid(True)
        ax3.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))

        # 4. 保存图表到内存
        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        plt.close(fig)
        buf.seek(0)
        return buf

# 调用示例
# asyncio.run(run_open_interest_monitor(bot_token="你的token", chat_id=12345678, topic_id=123))