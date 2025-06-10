import aiohttp
import asyncio
from telegram import Bot
from utils.logger import log_info, log_error, notify_error

previous_open_interest = {}

async def fetch_symbols(session):
    url = "https://fapi.binance.com/fapi/v1/exchangeInfo"
    async with session.get(url) as resp:
        data = await resp.json()
        return [s['symbol'] for s in data['symbols'] if s['contractType'] == 'PERPETUAL']

async def fetch_open_interest(session, symbol):
    url = f"https://fapi.binance.com/fapi/v1/openInterest?symbol={symbol}"
    async with session.get(url) as resp:
        data = await resp.json()
        return float(data['openInterest'])

async def run_open_interest_monitor(bot_token, chat_id, topic_id, interval=300, threshold=0.05):
    global previous_open_interest
    bot = Bot(token=bot_token)
    log_info("✅ 启动持仓变化监控")

    timeout = aiohttp.ClientTimeout(total=15)
    async with aiohttp.ClientSession(timeout=timeout, trust_env=True) as session:
        symbols = await fetch_symbols(session)

        while True:
            try:
                alerts = []
                for symbol in symbols:
                    try:
                        current = await fetch_open_interest(session, symbol)
                        last = previous_open_interest.get(symbol)

                        if last:
                            change = (current - last) / last
                            if abs(change) >= threshold:
                                emoji = "🔺" if change > 0 else "🔻"
                                alerts.append(
                                    f"{emoji} <b>{symbol}</b>\n"
                                    f"当前持仓：<code>{current:.2f}</code>\n"
                                    f"变化：<code>{change*100:.2f}%</code>\n"
                                )

                        previous_open_interest[symbol] = current
                    except:
                        continue

                if alerts:
                    message = "📉 <b>合约持仓变化预警</b>\n\n" + "\n".join(alerts)
                    await bot.send_message(chat_id=chat_id, text=message, message_thread_id=topic_id, parse_mode="HTML")
                    log_info(f"📢 推送持仓变化 {len(alerts)} 条")

            except Exception as e:
                log_error(f"❌ 持仓变化监控出错: {e}")
                await notify_error(bot_token, chat_id, f"持仓变化监控异常：{e}")

            await asyncio.sleep(interval)
