import asyncio
import json
import signal
import sys
from typing import List, Dict, Any, Optional
import html
import aiohttp
from datetime import datetime

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

from utils.logger import log_info, log_error
from monitors import (
    BaseMonitor,
    FundingRateMonitor,
    OpenInterestMonitor,
    PriceSpikeMonitor,
    SpotVolumeMonitor,
    TwitterMonitor
)

# 映射监控器名称到类
MONITOR_CLASSES = {
    "funding_rate": FundingRateMonitor,
    "open_interest": OpenInterestMonitor,
    "price_spike": PriceSpikeMonitor,
    "spot_volume": SpotVolumeMonitor,
    "twitter_monitor": TwitterMonitor,
}

class BotRunner:
    def __init__(self, config_path: str):
        self.config = self._load_config(config_path)
        self.monitors: Dict[str, BaseMonitor] = {}
        self.app: Optional[Application] = None
        self.monitor_tasks: List[asyncio.Task] = []
        self.session: Optional[aiohttp.ClientSession] = None

        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    def _load_config(self, config_path: str) -> Dict[str, Any]:
        log_info(f"从 {config_path} 加载配置...")
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            log_error(f"❌ 无法加载或解析配置文件: {e}")
            sys.exit(1)

    def _initialize_telegram_bot(self):
        token = self.config.get("telegram_token")
        if not token:
            log_error("❌ Telegram token 未在 config.json 中配置。")
            sys.exit(1)
        
        app_builder = Application.builder().token(token)
        
        proxy_url = self.config.get("proxy_url")
        if proxy_url:
            log_info(f"使用代理: {proxy_url}")
            app_builder.proxy(proxy_url)
            app_builder.get_updates_proxy(proxy_url)

        self.app = app_builder.build()
        log_info("✅ Telegram Bot 初始化成功。")

    def _initialize_monitors(self):
        if not self.app or not self.app.bot:
            log_error("❌ Bot 应用未初始化，无法创建监控器。")
            return

        for name, monitor_config in self.config.get("monitors", {}).items():
            if not monitor_config.get("enabled", False):
                continue
            
            monitor_class = MONITOR_CLASSES.get(name)
            if monitor_class:
                try:
                    # 获取topic_id，如果没有配置则使用None
                    topic_id = self.config.get("message_threads", {}).get(name)
                    
                    params = {
                        "bot": self.app.bot,
                        "chat_id": self.config["chat_id"],
                        "topic_id": topic_id,
                        "proxy_url": self.config.get("proxy_url"),
                        **monitor_config,
                    }
                    monitor = monitor_class(**params)
                    self.monitors[name] = monitor
                    log_info(f"✅ 成功初始化: {monitor_class.__name__}")
                except Exception as e:
                    log_error(f"❌ 初始化 {monitor_class.__name__} 失败: {e}")

    async def _get_session(self) -> aiohttp.ClientSession:
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20))
        return self.session

    async def fetch_json(self, url: str, params: Optional[dict] = None, **kwargs) -> Any:
        session = await self._get_session()
        proxy = self.config.get("proxy_url")
        try:
            async with session.get(url, proxy=proxy, params=params, **kwargs) as resp:
                resp.raise_for_status()
                return await resp.json()
        except aiohttp.ClientError as e:
            log_error(f"HTTP 请求失败 {url}: {e}")
            return None
        except Exception as e:
            log_error(f"数据获取时发生意外错误 {url}: {e}")
            return None

    async def _status_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.monitors:
            if update.message:
                await update.message.reply_text("当前没有任何监控器在运行。")
            return
        
        status_reports = [m.get_status() for m in self.monitors.values()]
        full_report = "<b>🤖 CoinMonitor 运行状态</b>\n\n" + "\n\n".join(status_reports)
        if update.message:
            await update.message.reply_html(full_report)

    async def _config_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message or not update.message.text: return

        parts = update.message.text.split()
        usage_text = (
            "<b>/config 命令用法:</b>\n"
            "• 查看: <code>/config &lt;monitor_name&gt;</code>\n"
            "• 设置: <code>/config &lt;monitor_name&gt; set &lt;key&gt; &lt;value&gt;</code>\n"
            "• 添加: <code>/config &lt;monitor_name&gt; add &lt;item&gt;</code>\n"
            "• 移除: <code>/config &lt;monitor_name&gt; remove &lt;item&gt;</code>\n\n"
            f"<b>可用:</b> <code>{', '.join(self.monitors.keys())}</code>"
        )

        if len(parts) < 2:
            await update.message.reply_html(usage_text)
            return

        monitor_name = parts[1]
        monitor = self.monitors.get(monitor_name)

        if not monitor:
            await update.message.reply_html(f"❌ 未找到监控器: <code>{monitor_name}</code>")
            return

        action = parts[2] if len(parts) > 2 else "get_status"
        response_message = ""

        try:
            if action == "get_status": response_message = monitor.get_status()
            elif action == "set" and len(parts) == 5: response_message = monitor.update_config(parts[3], parts[4])
            elif action == "add" and len(parts) == 4: response_message = monitor.add_to_watchlist(parts[3])
            elif action == "remove" and len(parts) == 4: response_message = monitor.remove_from_watchlist(parts[3])
            else: response_message = f"❌ 无效操作或参数错误。\n\n{usage_text}"
        except Exception as e:
            log_error(f"Config command failed for {monitor_name}: {e}")
            response_message = f"❌ 内部错误: <pre>{html.escape(str(e))}</pre>"

        await update.message.reply_html(response_message)

    async def _coin_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message or not update.message.text: return

        parts = update.message.text.split()
        if len(parts) < 2:
            await update.message.reply_html("请提供一个币种，例如: <code>/coin BTCUSDT</code>")
            return

        symbol = parts[1].upper()
        
        loading_message = await update.message.reply_html(f"⏳ 正在查询 <code>{symbol}</code> 的数据...")

        ticker_task = self.fetch_json(f"https://api.binance.com/api/v3/ticker/24hr", params={"symbol": symbol})
        oi_task = self.fetch_json(f"https://fapi.binance.com/fapi/v1/openInterest", params={"symbol": symbol})
        funding_task = self.fetch_json(f"https://fapi.binance.com/fapi/v1/premiumIndex", params={"symbol": symbol})

        results = await asyncio.gather(ticker_task, oi_task, funding_task, return_exceptions=True)
        ticker_data, oi_data, funding_data = results

        message_lines = [f"<b>📊 {symbol} 综合状态报告</b>\n"]
        
        price = 0
        if isinstance(ticker_data, dict):
            price = float(ticker_data.get('lastPrice', 0))
            price_change_percent = float(ticker_data.get('priceChangePercent', 0))
            volume_usd = float(ticker_data.get('quoteVolume', 0))
            emoji = "📈" if price_change_percent >= 0 else "📉"
            message_lines.append("<b>现货市场 (Spot)</b>")
            message_lines.append(f"  - <b>价格:</b> <code>${price:,.4f}</code>")
            message_lines.append(f"  - <b>24h 涨跌:</b> <code>{price_change_percent:+.2f}%</code> {emoji}")
            message_lines.append(f"  - <b>24h 成交额:</b> <code>${volume_usd:,.0f}</code>")
        else:
            message_lines.append("<b>现货市场 (Spot)</b>: <code>无数据</code>")

        futures_lines = []
        if isinstance(oi_data, dict) and 'openInterest' in oi_data and price > 0:
            open_interest_coin = float(oi_data.get('openInterest', 0))
            if open_interest_coin > 1:
                open_interest_usd = open_interest_coin * price
                futures_lines.append(f"  - <b>总持仓量:</b> <code>${open_interest_usd:,.0f}</code>")
        
        if isinstance(funding_data, dict) and 'lastFundingRate' in funding_data:
            funding_rate = float(funding_data.get('lastFundingRate', 0)) * 100
            next_funding_time_ms = int(funding_data.get('nextFundingTime', 0))
            if next_funding_time_ms > 0:
                next_funding_dt = datetime.utcfromtimestamp(next_funding_time_ms / 1000).strftime('%H:%M UTC')
                futures_lines.append(f"  - <b>资金费率:</b> <code>{funding_rate:.4f}%</code> (下次: {next_funding_dt})")
            else:
                futures_lines.append(f"  - <b>资金费率:</b> <code>{funding_rate:.4f}%</code>")

        if futures_lines:
            message_lines.append("\n<b>合约市场 (Futures)</b>")
            message_lines.extend(futures_lines)
        
        await loading_message.edit_text("\n".join(message_lines), parse_mode="HTML")

    async def _funding_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理 /funding 命令，手动触发资金费率检查"""
        if not update.message:
            return
            
        funding_monitor = self.monitors.get("funding_rate")
        if not funding_monitor:
            await update.message.reply_html("❌ 资金费率监控器未启用或未找到。")
            return
        
        loading_message = await update.message.reply_html("⏳ 正在获取资金费率数据...")
        
        try:
            await funding_monitor.manual_check()  # type: ignore
            await loading_message.edit_text("✅ 资金费率检查完成！")
        except Exception as e:
            log_error(f"❌ 手动资金费率检查失败: {e}")
            await loading_message.edit_text(f"❌ 资金费率检查失败: {str(e)}")

    def _setup_handlers(self):
        if not self.app: return
        self.app.add_handler(CommandHandler("status", self._status_handler))
        self.app.add_handler(CommandHandler("config", self._config_handler))
        self.app.add_handler(CommandHandler("coin", self._coin_handler))
        self.app.add_handler(CommandHandler("funding", self._funding_handler))
        log_info("✅ 命令处理器设置完毕。")
    
    async def run_async(self):
        self._initialize_telegram_bot()
        self._initialize_monitors()
        self._setup_handlers()

        if not self.app:
            log_error("❌ 应用未能启动。")
            return

        log_info("🚀 启动所有监控任务...")
        self.monitor_tasks = [asyncio.create_task(m.run()) for m in self.monitors.values()]
        
        loop = asyncio.get_event_loop()
        if sys.platform != "win32":
            stop_signals = (signal.SIGINT, signal.SIGTERM)
            for sig in stop_signals:
                loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(self.shutdown(s)))

        try:
            log_info("🤖 Bot is running. 按 Ctrl+C 停止。")
            await self.app.initialize()
            await self.app.updater.start_polling()
            await self.app.start()
            
            # 如果没有任何监控任务，gather会立即返回，导致程序退出
            # 所以我们需要确保即使没有任务，程序也能持续运行
            if not self.monitor_tasks:
                log_info("🤔 未启用任何监控器，Bot 将仅响应命令。")
                # 创建一个永远不会结束的任务，以保持事件循环运行
                await asyncio.Future()

            await asyncio.gather(*self.monitor_tasks)

        except (KeyboardInterrupt, SystemExit):
            log_info("收到停止信号...")
        finally:
            await self.shutdown()

    async def shutdown(self, sig: Optional[signal.Signals] = None):
        if sig: log_info(f"收到信号 {sig.name}。正在优雅停机...")
        
        for task in self.monitor_tasks:
            if not task.done():
                task.cancel()
        
        try:
            if self.app and self.app.updater and self.app.updater.running:
                await self.app.updater.stop()
        except Exception as e:
            log_error(f"停止updater时出错: {e}")
            
        try:
            if self.app:
                await self.app.stop()
                await self.app.shutdown()
        except Exception as e:
            log_error(f"停止应用时出错: {e}")
        
        if self.monitor_tasks:
            await asyncio.gather(*self.monitor_tasks, return_exceptions=True)

        if self.session and not self.session.closed:
            await self.session.close()

        log_info("👋 已安全关闭。")

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    runner = BotRunner(config_path="config.json")
    try:
        asyncio.run(runner.run_async())
    except KeyboardInterrupt:
        log_info("程序被手动中断。")