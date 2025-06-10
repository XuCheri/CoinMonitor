import aiohttp
import asyncio
from telegram import Bot, Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from datetime import datetime, timedelta, timezone
from utils.logger import log_info, log_error, notify_error

# 用于记录最近一次检查时间，避免重复触发
last_checked_minute = -1

async def fetch_json(session, url):
    async with session.get(url) as response:
        response.raise_for_status()
        return await response.json()

async def fetch_price_change(session, symbol, interval):
    url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval={interval}&limit=2"
    data = await fetch_json(session, url)
    if len(data) < 2:
        return 0
    open_price = float(data[0][1])
    close_price = float(data[1][4])
    return (close_price - open_price) / open_price * 100

async def check_market(session, threshold):
    funding_url = "https://fapi.binance.com/fapi/v1/premiumIndex"
    ticker_url = "https://fapi.binance.com/fapi/v1/ticker/24hr"
    spot_price_url = "https://api.binance.com/api/v3/ticker/price"

    funding_data = await fetch_json(session, funding_url)
    ticker_data = await fetch_json(session, ticker_url)
    spot_price_data = await fetch_json(session, spot_price_url)

    ticker_dict = {item['symbol']: item for item in ticker_data}
    spot_price_dict = {item['symbol']: float(item['price']) for item in spot_price_data}

    alert_list = []

    for item in funding_data:
        symbol = item['symbol']
        if not symbol.endswith('USDT'):
            continue

        funding_rate = float(item['lastFundingRate'])
        mark_price = float(item['markPrice'])
        next_funding_time = int(item['nextFundingTime']) // 1000
        funding_time = datetime.fromtimestamp(next_funding_time, tz=timezone.utc) + timedelta(hours=8)
        funding_time_str = funding_time.strftime("%H:%M")

        ticker = ticker_dict.get(symbol)
        spot_price = spot_price_dict.get(symbol)
        spot_price_str = f"{spot_price:.4f} USDT" if spot_price and spot_price > 0 else "无现货"

        if ticker and abs(funding_rate) >= threshold:
            price_change = float(ticker['priceChangePercent'])
            volume = float(ticker['quoteVolume'])
            open_interest_url = f"https://fapi.binance.com/fapi/v1/openInterest?symbol={symbol}"
            open_interest_data = await fetch_json(session, open_interest_url)
            open_interest = float(open_interest_data['openInterest']) / 1e6

            change_30m = await fetch_price_change(session, symbol, "30m")
            change_1h = await fetch_price_change(session, symbol, "1h")
            change_4h = await fetch_price_change(session, symbol, "4h")

            alert_list.append({
                "symbol": symbol,
                "funding_rate": funding_rate,
                "mark_price": mark_price,
                "spot_price_str": spot_price_str,
                "price_change": price_change,
                "volume": volume,
                "open_interest": open_interest,
                "change_30m": change_30m,
                "change_1h": change_1h,
                "change_4h": change_4h,
                "funding_time": funding_time_str
            })

    alert_list.sort(key=lambda x: abs(x['funding_rate']), reverse=True)
    return alert_list

async def send_alerts(bot, chat_id, topic_id, alerts):
    message = "⚠️ <b>异常资金费率预警</b>\n\n"
    for a in alerts:
        msg = (
            f"🚨 <b>{a['symbol']}</b>\n"
            f"💰 资金费率：<code>{a['funding_rate']*100:.4f}%</code>\n"
            f"📊 合约价格：<code>{a['mark_price']:.4f} USDT</code>\n"
            f"💱 现货价格：<code>{a['spot_price_str']}</code>\n"
            f"📈 24H涨跌幅：<code>{a['price_change']:.2f}%</code>\n"
            f"⏰ 30m：<code>{a['change_30m']:.2f}%</code> | "
            f"1H：<code>{a['change_1h']:.2f}%</code> | "
            f"4H：<code>{a['change_4h']:.2f}%</code>\n"
            f"🔄 成交额：<code>{a['volume']/1e6:.2f}M</code>\n"
            f"🧾 持仓量：<code>{a['open_interest']:.2f}M</code>\n"
            f"📅 结算时间：<code>{a['funding_time']}</code>\n\n"
        )
        if len(message) + len(msg) > 4000:
            message += "⚠️ 消息过长已截断部分内容\n"
            break
        message += msg

    await bot.send_message(chat_id=chat_id, text=message, message_thread_id=topic_id, parse_mode="HTML")

async def periodic_monitor(bot_token, chat_id, topic_id, threshold):
    bot = Bot(token=bot_token)
    timeout = aiohttp.ClientTimeout(total=20)
    async with aiohttp.ClientSession(timeout=timeout, trust_env=True) as session:
        while True:
            now = datetime.now()
            minute = now.minute
            global last_checked_minute
            if minute in (0, 30) and minute != last_checked_minute:
                last_checked_minute = minute
                try:
                    alerts = await check_market(session, threshold)
                    if alerts:
                        await send_alerts(bot, chat_id, topic_id, alerts)
                        log_info(f"📢 定时推送 {len(alerts)} 条资金费率预警")
                except Exception as e:
                    log_error(f"❌ 定时监控出错: {e}")
                    await notify_error(bot_token, chat_id, f"资金费率监控异常：{e}")
            await asyncio.sleep(10)

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot = context.bot
    message = update.effective_message
    config = context.application.bot_data.get("monitor_config", {})
    
    if "数据" in message.text and message.message_thread_id == config.get("topic_id"):
        log_info("📥 收到用户消息“监控”触发监测")
        try:
            timeout = aiohttp.ClientTimeout(total=20)
            async with aiohttp.ClientSession(timeout=timeout, trust_env=True) as session:
                alerts = await check_market(session, config.get("threshold", 0.001))
                if alerts:
                    await send_alerts(bot, message.chat_id, message.message_thread_id, alerts)
                    log_info(f"📢 用户触发推送 {len(alerts)} 条资金费率预警")
                else:
                    await bot.send_message(
                        chat_id=message.chat_id,
                        message_thread_id=message.message_thread_id,
                        text="✅ 当前暂无异常资金费率",
                    )
        except Exception as e:
            log_error(f"❌ 用户触发监控出错: {e}")
            await notify_error(bot.token, message.chat_id, f"资金费率监控异常：{e}")


async def run_monitor(bot_token, chat_id, topic_id, threshold=0.001):
    log_info("✅ 启动资金费率监控模块")
    app = Application.builder().token(bot_token).build()

    app.bot_data["monitor_config"] = {
        "chat_id": chat_id,
        "topic_id": topic_id,
        "threshold": threshold,
    }

    app.add_handler(MessageHandler(filters.TEXT, message_handler))

    asyncio.create_task(periodic_monitor(bot_token, chat_id, topic_id, threshold))

    await app.initialize()
    await app.start()
    await app.updater.start_polling()

