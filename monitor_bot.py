import asyncio
from telegram import Bot
import requests
import json
import time

# === 读取配置 ===
with open("config.json", "r", encoding="utf-8") as f:
    config = json.load(f)

bot_token = config["bot_token"]
chat_id = config["chat_id"]
topic_id = config["message_threads"]["funding_rate"]
threshold = config["funding_rate_threshold"]
interval = config["check_interval"]

bot = Bot(token=bot_token)

def get_symbols():
    url = "https://fapi.binance.com/fapi/v1/exchangeInfo"
    response = requests.get(url).json()
    symbols = [s['symbol'] for s in response['symbols'] if s['contractType'] == 'PERPETUAL']
    return symbols

def get_funding_data():
    url = "https://fapi.binance.com/fapi/v1/premiumIndex"
    return requests.get(url).json()

def get_ticker_data():
    url = "https://fapi.binance.com/fapi/v1/ticker/24hr"
    return requests.get(url).json()

def check_market(threshold=0.001):
    funding_data = get_funding_data()
    ticker_data = get_ticker_data()

    ticker_dict = {item['symbol']: item for item in ticker_data}
    alert_list = []

    for item in funding_data:
        symbol = item['symbol']
        if not symbol.endswith('USDT'):
            continue

        funding_rate = float(item['lastFundingRate'])
        mark_price = float(item['markPrice'])

        ticker = ticker_dict.get(symbol)
        if ticker:
            price_change = float(ticker['priceChangePercent'])
            volume = float(ticker['quoteVolume'])  # 24H成交额 USDT

            if abs(funding_rate) >= threshold:
                alert_list.append(
                    f"🚨 <b>{symbol}</b>\n"
                    f"📊 标记价格：<code>{mark_price:.4f} USDT</code>\n"
                    f"💰 资金费率：<code>{funding_rate*100:.4f}%</code>\n"
                    f"📈 24H涨跌幅：<code>{price_change:.2f}%</code>\n"
                    f"🔄 24H成交额：<code>{volume/1e6:.2f}M USDT</code>"
                )

    return alert_list

async def main():
    print("启动监控…")
    while True:
        try:
            alerts = check_market(threshold)
            if alerts:
                message = "\n\n".join(alerts)
                await bot.send_message(chat_id=chat_id, text=message, message_thread_id=topic_id, parse_mode="HTML")
                print(f"已推送 {len(alerts)} 条预警")
            else:
                print("暂无异常资金费率")
        except Exception as e:
            print(f"出错：{e}")

        await asyncio.sleep(interval)

if __name__ == "__main__":
    asyncio.run(main())
