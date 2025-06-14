import aiohttp
import asyncio
from telegram import Bot
from datetime import datetime
from utils.logger import log_info, log_error, notify_error

previous_open_interest = {}
previous_prices = {}

async def fetch_symbols(session):
    url = "https://fapi.binance.com/fapi/v1/exchangeInfo"
    async with session.get(url) as resp:
        data = await resp.json()
        return [s['symbol'] for s in data['symbols'] if s['contractType'] == 'PERPETUAL']

async def fetch_open_interest(session, symbol):
    url = f"https://fapi.binance.com/fapi/v1/openInterest?symbol={symbol}"
    async with session.get(url) as resp:
        data = await resp.json()
        return float(data.get('openInterest', 0))

async def fetch_price(session, symbol):
    url = f"https://fapi.binance.com/fapi/v1/ticker/price?symbol={symbol}"
    async with session.get(url) as resp:
        data = await resp.json()
        return float(data.get('price', 0))

async def run_open_interest_monitor(bot_token, chat_id, topic_id, interval=60, threshold=0.05):
    global previous_open_interest, previous_prices
    bot = Bot(token=bot_token)
    log_info("✅ 启动持仓变化监控（每分钟轮询 + 比较 5 分钟持仓变化）")

    timeout = aiohttp.ClientTimeout(total=15)
    async with aiohttp.ClientSession(timeout=timeout, trust_env=True) as session:
        symbols = await fetch_symbols(session)

        while True:
            try:
                now = datetime.now()
                alerts = []
                for symbol in symbols:
                    try:
                        current_oi = await fetch_open_interest(session, symbol)
                        current_price = await fetch_price(session, symbol)

                        last_entry = previous_open_interest.get(symbol)
                        if last_entry:
                            last_oi, last_time = last_entry
                            oi_change = (current_oi - last_oi) / last_oi if last_oi else 0

                            last_price = previous_prices.get(symbol, current_price)
                            price_change = (current_price - last_price) / last_price if last_price else 0

                            if abs(oi_change) >= threshold:
                                emoji = "🔺" if oi_change > 0 else "🔻"
                                alerts.append(
                                    f"{emoji} <b>{symbol}</b>\n"
                                    f"🧾 当前持仓：<code>{current_oi/1e6:.2f}M</code>\n"
                                    f"📈 持仓变化：<code>{oi_change*100:.2f}%</code>\n"
                                    f"💰 当前价格：<code>{current_price:.4f} USDT</code>\n"
                                    f"💹 5分钟价格变化：<code>{price_change*100:.2f}%</code>\n"
                                )

                        # 每5分钟记录一次
                        if not last_entry or (now - last_entry[1]).seconds >= 300:
                            previous_open_interest[symbol] = (current_oi, now)
                            previous_prices[symbol] = current_price
                    except Exception as e:
                        log_error(f"❌ 处理 {symbol} 时出错: {e}")
                        continue

                if alerts:
                    message = "📉 <b>合约持仓变化预警</b>\n\n" + "\n".join(alerts)
                    await bot.send_message(chat_id=chat_id, text=message, message_thread_id=topic_id, parse_mode="HTML")
                    log_info(f"📢 推送持仓变化 {len(alerts)} 条")

            except Exception as e:
                log_error(f"❌ 持仓变化监控出错: {e}")
                await notify_error(bot_token, chat_id, f"持仓变化监控异常：{e}")

            await asyncio.sleep(interval)
