import asyncio
import aiohttp
from telegram import Bot
import json
from datetime import datetime, timezone, timedelta

# === 读取配置 ===
with open("config.json", "r", encoding="utf-8") as f:
    config = json.load(f)

bot_token = config["bot_token"]
chat_id = config["chat_id"]
topic_id = config["message_threads"]["funding_rate"]
threshold = config["funding_rate_threshold"]
interval = config["check_interval"]

bot = Bot(token=bot_token)

# === 请求函数 ===
async def fetch_json(session, url):
    async with session.get(url) as response:
        response.raise_for_status()
        return await response.json()

# 获取K线涨跌幅
async def fetch_price_change(session, symbol, interval):
    url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval={interval}&limit=2"
    data = await fetch_json(session, url)
    if len(data) < 2:
        return 0
    open_price = float(data[0][1])
    close_price = float(data[1][4])
    change = (close_price - open_price) / open_price * 100
    return change

# === 资金费率监控函数 ===
async def check_market(session, threshold):
    funding_url = "https://fapi.binance.com/fapi/v1/premiumIndex"
    ticker_url = "https://fapi.binance.com/fapi/v1/ticker/24hr"

    funding_data = await fetch_json(session, funding_url)
    ticker_data = await fetch_json(session, ticker_url)
    ticker_dict = {item['symbol']: item for item in ticker_data}

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
        if ticker:
            price_change = float(ticker['priceChangePercent'])
            volume = float(ticker['quoteVolume'])

            if abs(funding_rate) >= threshold:
                # 获取持仓量
                open_interest_url = f"https://fapi.binance.com/fapi/v1/openInterest?symbol={symbol}"
                open_interest_data = await fetch_json(session, open_interest_url)
                open_interest = float(open_interest_data['openInterest']) / 1e6  # 单位 M

                # 获取K线涨跌幅
                change_30m = await fetch_price_change(session, symbol, "30m")
                change_1h = await fetch_price_change(session, symbol, "1h")
                change_4h = await fetch_price_change(session, symbol, "4h")

                alert_list.append({
                    "symbol": symbol,
                    "funding_rate": funding_rate,
                    "mark_price": mark_price,
                    "price_change": price_change,
                    "volume": volume,
                    "open_interest": open_interest,
                    "change_30m": change_30m,
                    "change_1h": change_1h,
                    "change_4h": change_4h,
                    "funding_time": funding_time_str
                })

    # 按资金费率绝对值降序排序
    alert_list.sort(key=lambda x: abs(x['funding_rate']), reverse=True)

    return alert_list

# === 主监控流程 ===
async def main():
    print("✅ 启动资金费率监控…")

    timeout = aiohttp.ClientTimeout(total=20, connect=10, sock_read=10)
    async with aiohttp.ClientSession(timeout=timeout, trust_env=True) as session:
        while True:
            try:
                alerts = await check_market(session, threshold)
                if alerts:
                    message = "⚠️ <b>异常资金费率预警</b>\n\n"
                    for a in alerts:
                        message += (
                            f"🚨 <b>{a['symbol']}</b>\n"
                            f"💰 资金费率：<code>{a['funding_rate']*100:.4f}%</code>\n"
                            f"📊 标记价格：<code>{a['mark_price']:.4f} USDT</code>\n"
                            f"📈 24H涨跌幅：<code>{a['price_change']:.2f}%</code>\n"
                            f"⏰ 30m：<code>{a['change_30m']:.2f}%</code> | "
                            f"1H：<code>{a['change_1h']:.2f}%</code> | "
                            f"4H：<code>{a['change_4h']:.2f}%</code>\n"
                            f"🔄 成交额：<code>{a['volume']/1e6:.2f}M USDT</code>\n"
                            f"🧾 持仓量：<code>{a['open_interest']:.2f}M</code>\n"
                            f"📅 结算时间：<code>{a['funding_time']}</code>\n\n"
                        )
                    await bot.send_message(chat_id=chat_id, text=message, message_thread_id=topic_id, parse_mode="HTML")
                    print(f"📢 已推送 {len(alerts)} 条预警")
                else:
                    print("👌 暂无异常资金费率")

            except Exception as e:
                print(f"❌ 出错：{e}")

            await asyncio.sleep(interval)

if __name__ == "__main__":
    asyncio.run(main())
