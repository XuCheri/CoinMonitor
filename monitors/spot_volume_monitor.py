import aiohttp
import asyncio
from telegram import Bot
from utils.logger import log_info, log_error, notify_error

async def fetch_spot_24hr_ticker(session):
    url = "https://api.binance.com/api/v3/ticker/24hr"
    async with session.get(url) as resp:
        return await resp.json()

async def run_spot_volume_monitor(bot_token, chat_id, topic_id, top_n=20, interval=86400):
    bot = Bot(token=bot_token)
    log_info("✅ 启动现货成交额排行榜监控")

    timeout = aiohttp.ClientTimeout(total=20)
    async with aiohttp.ClientSession(timeout=timeout, trust_env=True) as session:
        while True:
            try:
                data = await fetch_spot_24hr_ticker(session)
                usdt_pairs = [d for d in data if d['symbol'].endswith("USDT")]
                top = sorted(usdt_pairs, key=lambda x: float(x['quoteVolume']), reverse=True)[:top_n]

                msg = f"📊 <b>24H 成交额排行榜（Top {top_n}）</b>\n\n"
                for idx, item in enumerate(top, start=1):
                    symbol = item['symbol']
                    price = float(item['lastPrice'])
                    volume = float(item['quoteVolume']) / 1e6
                    change = float(item['priceChangePercent'])

                    msg += (
                        f"{idx:02d}. <b>{symbol}</b>\n"
                        f"    💵 最新价格：<code>{price:.4f}</code>\n"
                        f"    🔄 成交额：<code>{volume:.2f}M</code>\n"
                        f"    📈 涨跌幅：<code>{change:.2f}%</code>\n\n"
                    )

                await bot.send_message(chat_id=chat_id, text=msg, message_thread_id=topic_id, parse_mode="HTML")
                log_info(f"📢 已推送成交额排行榜 Top {top_n}")
            except Exception as e:
                log_error(f"❌ 成交额监控出错: {e}")
                await notify_error(bot_token, chat_id, f"成交额监控异常：{e}")
            await asyncio.sleep(interval)
