import aiohttp
import asyncio
import io
import matplotlib.pyplot as plt
from mplfinance.original_flavor import candlestick_ohlc
import matplotlib.dates as mdates
from telegram import Bot, InputFile
from datetime import datetime, timedelta
from utils.logger import log_info, log_error, notify_error

previous_prices = {}
previous_open_interest = {}

async def fetch_symbols(session):
    url = "https://fapi.binance.com/fapi/v1/exchangeInfo"
    async with session.get(url) as resp:
        data = await resp.json()
        return [s['symbol'] for s in data['symbols'] if s['contractType'] == 'PERPETUAL']

async def fetch_klines(session, symbol, interval="1m", limit=20):
    url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval={interval}&limit={limit}"
    async with session.get(url) as resp:
        return await resp.json()

async def fetch_open_interest(session, symbol):
    url = f"https://fapi.binance.com/fapi/v1/openInterest?symbol={symbol}"
    async with session.get(url) as resp:
        data = await resp.json()
        return float(data.get('openInterest', 0))

def generate_candle_chart(symbol, klines):
    ohlc = []
    for entry in klines:
        timestamp = mdates.date2num(datetime.fromtimestamp(entry[0] / 1000))
        ohlc.append((timestamp, float(entry[1]), float(entry[2]), float(entry[3]), float(entry[4])))

    fig, ax = plt.subplots(figsize=(6, 3))
    candlestick_ohlc(ax, ohlc, width=0.0005, colorup='g', colordown='r')
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
    plt.title(f"{symbol} 1分钟蜡烛图 (20min)")
    plt.xlabel("时间")
    plt.ylabel("价格 (USDT)")
    plt.xticks(rotation=45)
    plt.tight_layout()

    buffer = io.BytesIO()
    plt.savefig(buffer, format='png')
    buffer.seek(0)
    plt.close()
    return buffer

async def run_price_spike_monitor(bot_token, chat_id, topic_id, interval=60):
    bot = Bot(token=bot_token)
    log_info("✅ 启动价格异动监控（蜡烛图 + 持仓）")

    timeout = aiohttp.ClientTimeout(total=15)
    async with aiohttp.ClientSession(timeout=timeout, trust_env=True) as session:
        symbols = await fetch_symbols(session)

        while True:
            try:
                alerts = []
                charts = []

                for symbol in symbols:
                    try:
                        klines = await fetch_klines(session, symbol, "1m", 20)
                        if len(klines) < 3:
                            continue

                        spikes = []
                        for entry in klines:
                            high = float(entry[2])
                            low = float(entry[3])
                            amplitude = (high - low) / low if low > 0 else 0
                            spikes.append(amplitude)

                        last_amplitude = spikes[-1]
                        prev_amplitude = spikes[-2]
                        close_change = (float(klines[-1][4]) - float(klines[-2][4])) / float(klines[-2][4])

                        trigger = (
                            (last_amplitude >= 0.01253 and prev_amplitude >= 0.01253) or
                            last_amplitude >= 0.02 or
                            abs(close_change) >= 0.015
                        )

                        if trigger:
                            current_price = float(klines[-1][4])
                            current_oi = await fetch_open_interest(session, symbol)
                            previous_oi = previous_open_interest.get(symbol)

                            if previous_oi:
                                oi_change = (current_oi - previous_oi) / previous_oi if previous_oi > 0 else 0
                            else:
                                oi_change = 0

                            previous_open_interest[symbol] = current_oi

                            emoji = "📈" if close_change > 0 else "📉"
                            alerts.append(
                                f"{emoji} <b>{symbol}</b> 满足条件触发预警\n"
                                f"💰 当前价格：<code>{current_price:.4f} USDT</code>\n"
                                f"📊 1分钟变化：<code>{close_change*100:.2f}%</code>\n"
                                f"📶 最近振幅：<code>{last_amplitude*100:.2f}%</code>\n"
                                f"🧾 当前持仓量：<code>{current_oi/1e6:.2f}M</code>\n"
                                f"🔁 持仓变化：<code>{oi_change*100:.2f}%</code>"
                            )

                            charts.append((symbol, klines))

                    except Exception as e:
                        log_error(f"❌ 处理 {symbol} 时出错: {e}")
                        continue

                if alerts:
                    message = "🚨 <b>价格异动预警</b>\n\n" + "\n\n".join(alerts)
                    await bot.send_message(chat_id=chat_id, text=message, message_thread_id=topic_id, parse_mode="HTML")

                    for symbol, kline_data in charts:
                        chart_image = generate_candle_chart(symbol, kline_data)
                        await bot.send_photo(chat_id=chat_id, photo=InputFile(chart_image, filename=f"{symbol}.png"), message_thread_id=topic_id)

                    log_info(f"📢 推送价格异动 {len(alerts)} 条 + 蜡烛图")

            except Exception as e:
                log_error(f"❌ 价格异动监控出错: {e}")
                await notify_error(bot_token, chat_id, f"价格异动监控异常：{e}")

            await asyncio.sleep(interval)