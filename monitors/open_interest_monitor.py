import asyncio
from datetime import datetime, timedelta
import io
from typing import Optional, cast, List, Dict, Any

import aiohttp
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd
from telegram import Bot
import matplotlib.font_manager as fm
from mplfinance.original_flavor import candlestick_ohlc
import numpy as np

from .base_monitor import BaseMonitor
from utils.logger import log_error, log_info

font_path = 'C:/Windows/Fonts/msyh.ttc'
my_font = fm.FontProperties(fname=font_path)
matplotlib.rcParams['font.sans-serif'] = [my_font.get_name()]
matplotlib.rcParams['axes.unicode_minus'] = False  # 解决负号显示为方块的问题

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
        # 新增：保存最近2分钟的数据用于检测2分钟内变化
        self.oi_history = {}  # {symbol: [(timestamp, oi_value), ...]}
        self.price_history = {}  # {symbol: [(timestamp, price_value), ...]}
        self.max_history_minutes = 2  # 保存2分钟的历史数据

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
            current_time = datetime.now()

            # 2. 更新历史数据
            if symbol not in self.oi_history:
                self.oi_history[symbol] = []
            if symbol not in self.price_history:
                self.price_history[symbol] = []
            
            # 添加当前数据到历史记录
            self.oi_history[symbol].append((current_time, current_oi))
            self.price_history[symbol].append((current_time, current_price))
            
            # 清理超过2分钟的历史数据
            cutoff_time = current_time.replace(second=0, microsecond=0) - timedelta(minutes=self.max_history_minutes)
            self.oi_history[symbol] = [(t, v) for t, v in self.oi_history[symbol] if t >= cutoff_time]
            self.price_history[symbol] = [(t, v) for t, v in self.price_history[symbol] if t >= cutoff_time]

            # 3. 检查2分钟内的变化
            if len(self.oi_history[symbol]) >= 2:
                # 获取2分钟前的数据
                oldest_oi = self.oi_history[symbol][0][1]
                oldest_price = self.price_history[symbol][0][1]
                
                # 计算2分钟内的变化
                oi_change = (current_oi - oldest_oi) / oldest_oi if oldest_oi else 0
                price_change = (current_price - oldest_price) / oldest_price if oldest_price else 0

                # 4. 如果2分钟内变化超过阈值，则发送警报
                if abs(oi_change) >= self.threshold:
                    await self._send_alert_and_chart(symbol, current_oi, oi_change, current_price, price_change, price_data, oldest_oi, oldest_price)

            # 5. 更新状态（保持向后兼容）
            self.previous_open_interest[symbol] = (current_oi, current_time)
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

    async def _send_alert_and_chart(self, symbol, current_oi, oi_change, current_price, price_change, price_data, oldest_oi, oldest_price):
        """生成并发送警报消息和图表。"""
        trading_action = self._get_trading_action(oi_change, price_change)
        
        alert_caption = (
            f"{trading_action} <b>{symbol}</b>\n"
            f"⏰ <b>2分钟内变化检测</b>\n\n"
            f"🧾 持仓量变化:\n"
            f"   <code>{oldest_oi/1e6:.2f}M</code> → <code>{current_oi/1e6:.2f}M</code>\n"
            f"   📈 变化幅度: <code>{oi_change*100:.2f}%</code>\n\n"
            f"💰 价格变化:\n"
            f"   <code>{oldest_price:.4f}</code> → <code>{current_price:.4f} USDT</code>\n"
            f"   💹 变化幅度: <code>{price_change*100:.2f}%</code>"
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
            f"  - 检测逻辑: 2分钟内变化{self.threshold * 100}%\n"
        )
        if self.watchlist:
            status += f"  - 监控列表: <code>{', '.join(self.watchlist)}</code>\n"
            status += f"  - (当前总计: {len(self.symbols)}个)\n"
        else:
            status += f"  - 监控列表: 全部永续合约 ({len(self.symbols)}个)\n"
        
        if self.invalid_symbols:
            status += f"  - 已忽略的无效合约: {len(self.invalid_symbols)}个\n"
            
        return status

    async def test_monitor(self, symbol: str = "BTCUSDT") -> str:
        """手动测试监控器功能，检查指定交易对的当前状态。"""
        try:
            # 获取当前数据
            oi_data = await self._fetch_binance_data("/fapi/v1/openInterest", {'symbol': symbol})
            current_oi = float(oi_data.get('openInterest', 0))
            
            klines = await self._fetch_binance_data("/fapi/v1/klines", {'symbol': symbol, 'interval': '1m', 'limit': 60})
            price_data = [(int(k[0]), float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5])) for k in klines]
            current_price = price_data[-1][4]

            # 检查是否有2分钟的历史数据
            if symbol in self.oi_history and len(self.oi_history[symbol]) >= 2:
                oldest_oi = self.oi_history[symbol][0][1]
                oldest_price = self.price_history[symbol][0][1] if symbol in self.price_history else current_price
                
                oi_change = (current_oi - oldest_oi) / oldest_oi if oldest_oi else 0
                price_change = (current_price - oldest_price) / oldest_price if oldest_price else 0
                
                trading_action = self._get_trading_action(oi_change, price_change)
                
                result = (
                    f"🔍 <b>{symbol} 持仓异动测试结果</b>\n"
                    f"⏰ <b>2分钟内变化检测</b>\n\n"
                    f"🧾 持仓量变化:\n"
                    f"   <code>{oldest_oi/1e6:.2f}M</code> → <code>{current_oi/1e6:.2f}M</code>\n"
                    f"   📈 变化幅度: <code>{oi_change*100:.2f}%</code>\n\n"
                    f"💰 价格变化:\n"
                    f"   <code>{oldest_price:.4f}</code> → <code>{current_price:.4f} USDT</code>\n"
                    f"   💹 变化幅度: <code>{price_change*100:.2f}%</code>\n\n"
                    f"🎯 市场行为: {trading_action}\n"
                    f"⚡ 触发阈值: <code>{self.threshold*100}%</code>\n"
                    f"📊 历史数据点: <code>{len(self.oi_history[symbol])}</code>个\n\n"
                )
                
                if abs(oi_change) >= self.threshold:
                    result += "✅ <b>已达到触发条件，将发送警报！</b>"
                else:
                    result += f"⚠️ <b>未达到触发条件 (需要 {self.threshold*100}% 变化)</b>"
            else:
                result = (
                    f"🔍 <b>{symbol} 持仓异动测试结果</b>\n\n"
                    f"📊 当前持仓量: <code>{current_oi/1e6:.2f}M</code>\n"
                    f"💰 当前价格: <code>{current_price:.4f} USDT</code>\n"
                    f"⏰ 正在建立2分钟基准数据\n"
                    f"⚡ 触发阈值: <code>{self.threshold*100}%</code>\n"
                    f"📊 历史数据点: <code>{len(self.oi_history.get(symbol, []))}</code>个\n\n"
                    f"ℹ️ 需要至少2个数据点才能开始监控2分钟内变化"
                )
            
            return result
            
        except Exception as e:
            return f"❌ 测试失败: {str(e)}"

    async def _generate_chart(self, symbol: str, price_data: list) -> io.BytesIO:
        """生成币安APP风格的价格K线+持仓量+O.I. NV+多空比图表"""
        try:
            # 1. 数据准备
            # price_data: [(timestamp, open, high, low, close, volume), ...]
            df_price = pd.DataFrame(price_data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df_price['timestamp'] = pd.to_datetime(df_price['timestamp'], unit='ms')
            df_price.set_index('timestamp', inplace=True)
            
            # 获取持仓量和多空比历史（与check逻辑一致）
            tasks = [
                self._fetch_binance_data("/futures/data/openInterestHist", {'symbol': symbol, 'period': '5m', 'limit': 48}),
                self._fetch_binance_data("/futures/data/globalLongShortAccountRatio", {'symbol': symbol, 'period': '5m', 'limit': 48})
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 处理持仓量数据
            if isinstance(results[0], Exception):
                log_error(f"❌ {self.monitor_name}: Failed to fetch OI history for {symbol}: {results[0]}")
                df_oi = pd.DataFrame(columns=['oi'])
            else:
                oi_hist_raw = results[0]
                oi_data = [(int(d['timestamp']), float(d['sumOpenInterest'])) for d in oi_hist_raw]
                df_oi = pd.DataFrame(oi_data, columns=['timestamp', 'oi'])
                df_oi['timestamp'] = pd.to_datetime(df_oi['timestamp'], unit='ms')
                df_oi.set_index('timestamp', inplace=True)
            
            # 处理多空比数据
            if isinstance(results[1], Exception):
                log_error(f"❌ {self.monitor_name}: Failed to fetch long/short ratio for {symbol}: {results[1]}")
                df_ls = pd.DataFrame(columns=['ls_ratio'])
            else:
                ls_hist_raw = results[1]
                ls_data = [(int(d['timestamp']), float(d['longShortRatio'])) for d in ls_hist_raw]
                df_ls = pd.DataFrame(ls_data, columns=['timestamp', 'ls_ratio'])
                df_ls['timestamp'] = pd.to_datetime(df_ls['timestamp'], unit='ms')
                df_ls.set_index('timestamp', inplace=True)
            
            # 区间裁剪（与K线对齐）
            start_time = df_price.index[0]
            end_time = df_price.index[-1]
            
            if len(df_oi) > 0:
                df_oi = df_oi[(df_oi.index >= start_time) & (df_oi.index <= end_time)]
            if len(df_ls) > 0:
                df_ls = df_ls[(df_ls.index >= start_time) & (df_ls.index <= end_time)]
            
            # 2. 绘图
            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10), sharex=True, gridspec_kw={'height_ratios': [3, 1]})
            
            # 主图：K线+底部绿色持仓量柱状+O.I. NV
            ohlc = []
            for idx, row in df_price.iterrows():
                t = mdates.date2num(idx)
                ohlc.append([t, row['open'], row['high'], row['low'], row['close']])
            
            ax1.set_facecolor('white')
            ax1.spines['top'].set_visible(False)
            ax1.spines['right'].set_visible(False)
            ax1.spines['left'].set_color('#888')
            ax1.spines['bottom'].set_color('#888')
            ax1.tick_params(axis='both', colors='#444', labelsize=12)
            
            # K线
            if len(df_price) > 1:
                bar_width = float((mdates.date2num(df_price.index[1]) - mdates.date2num(df_price.index[0])) * 0.7)
            else:
                bar_width = 0.02
            
            candlestick_ohlc(ax1, ohlc, width=bar_width, colorup='#e54d42', colordown='#39b54a', alpha=0.95)
            
            # 底部绿色持仓量柱状
            price_min = min(df_price['low'])
            price_max = max(df_price['high'])
            price_range = price_max - price_min
            
            if len(df_oi) > 0:
                oi_max = df_oi['oi'].max()
                oi_height = price_range * 0.10
                
                # 确保持仓量数据与价格数据对齐
                oi_aligned = df_oi.reindex(df_price.index, method='ffill').fillna(0)
                norm_oi = oi_aligned['oi'] / oi_max * oi_height
                
                ax1.bar(df_price.index, norm_oi, width=bar_width, color='#39b54a', alpha=0.28, label='持仓量', align='center', bottom=price_min)
                
                # O.I. NV名义价值线
                oi_nv_raw = oi_aligned['oi'] * df_price['close']
                oi_nv_max = oi_nv_raw.max()
                norm_oi_nv = oi_nv_raw / oi_nv_max * oi_height
                ax1.plot(df_price.index, norm_oi_nv + price_min, color='#ffce34', linewidth=2, label='O.I. NV（名义价值）', alpha=0.95)
            
            ax1.set_ylabel("价格 (USDT)", fontsize=13, fontweight='bold', color='#222', fontproperties=my_font)
            ax1.grid(False)
            ax1.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
            plt.setp(ax1.xaxis.get_majorticklabels(), rotation=0, fontproperties=my_font, color='#444')
            handles, labels = ax1.get_legend_handles_labels()
            ax1.legend(handles, labels, loc='upper right', fontsize=11, prop=my_font, frameon=False)
            ax1.set_title(f"{symbol} 持仓异动分析", fontsize=15, fontweight='bold', color='#222', fontproperties=my_font, pad=10)
            
            # 多空比区块
            if len(df_ls) > 0:
                ls_ratio = df_ls['ls_ratio']
                if len(df_ls) > 1:
                    bar_width2 = float((mdates.date2num(df_ls.index[1]) - mdates.date2num(df_ls.index[0])) * 0.7)
                else:
                    bar_width2 = 0.02
                
                long_mask = ls_ratio >= 1
                short_mask = ls_ratio < 1
                
                if long_mask.any():
                    ax2.bar(df_ls.index[long_mask], ls_ratio[long_mask], color='#39b54a', width=bar_width2, label='多头比例', alpha=0.7, align='center')
                if short_mask.any():
                    ax2.bar(df_ls.index[short_mask], ls_ratio[short_mask], color='#e54d42', width=bar_width2, label='空头比例', alpha=0.7, align='center')
                
                ax2.axhline(y=1.0, color='#607d8b', linestyle='--', alpha=0.7, linewidth=2)
                ax2.text(df_ls.index[0], 1.0, ' 中性线', verticalalignment='bottom', fontsize=11, color='#607d8b', fontproperties=my_font)
                
                handles2, labels2 = ax2.get_legend_handles_labels()
                ax2.legend(handles2, labels2, loc='upper left', fontsize=12, prop=my_font, frameon=False)
            
            ax2.set_ylabel("多空比", fontsize=14, fontweight='bold', fontproperties=my_font)
            ax2.set_xlabel("时间", fontsize=14, fontweight='bold', fontproperties=my_font)
            ax2.grid(False)
            ax2.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
            ax2.xaxis.set_major_locator(mdates.MinuteLocator(interval=5))
            plt.setp(ax2.xaxis.get_majorticklabels(), rotation=45, fontproperties=my_font)
            
            # 统计信息
            if len(df_price) > 0:
                price_change = ((df_price['close'].iloc[-1] - df_price['close'].iloc[0]) / df_price['close'].iloc[0]) * 100
                oi_change = 0
                if len(df_oi) > 0:
                    oi_change = ((df_oi['oi'].iloc[-1] - df_oi['oi'].iloc[0]) / df_oi['oi'].iloc[0]) * 100
                stats_text = f"区间变化: 价格 {price_change:+.2f}% | 持仓量 {oi_change:+.2f}%"
                fig.text(0.5, 0.02, stats_text, ha='center', fontsize=11, bbox=dict(boxstyle='round,pad=0.5', facecolor='#ecf0f1', alpha=0.8), fontproperties=my_font)
            
            buf = io.BytesIO()
            plt.savefig(buf, format='png', dpi=150, bbox_inches='tight', facecolor='#f8f9fa', edgecolor='none')
            plt.close(fig)
            buf.seek(0)
            return buf
            
        except Exception as e:
            log_error(f"❌ {self.monitor_name}: Chart generation failed for {symbol}: {str(e)}")
            # 返回一个简单的错误图表
            fig, ax = plt.subplots(figsize=(10, 6))
            ax.text(0.5, 0.5, f'图表生成失败\n{str(e)}', ha='center', va='center', transform=ax.transAxes, fontsize=14)
            ax.set_title(f"{symbol} 持仓异动分析", fontsize=16, fontweight='bold')
            buf = io.BytesIO()
            plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
            plt.close(fig)
            buf.seek(0)
            return buf

# 调用示例
# asyncio.run(run_open_interest_monitor(bot_token="你的token", chat_id=12345678, topic_id=123))