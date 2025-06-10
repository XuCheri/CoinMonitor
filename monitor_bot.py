import asyncio
from monitors import funding_rate_monitor, spot_volume_monitor, open_interest_monitor
import json

# === 加载配置 ===
with open("config.json", "r", encoding="utf-8") as f:
    config = json.load(f)

bot_token = config["bot_token"]
chat_id = config["chat_id"]
interval = config.get("check_interval", 60)

# ✅ 从配置中获取话题ID
thread_funding = config["message_threads"]["funding_rate"]
thread_volume = config["message_threads"]["spot_volume"]
thread_oi = config["message_threads"]["open_interest"]

async def main():
    await asyncio.gather(
        funding_rate_monitor.run_monitor(bot_token, chat_id, thread_funding),
        spot_volume_monitor.run_spot_volume_monitor(bot_token, chat_id, thread_volume),
        open_interest_monitor.run_open_interest_monitor(bot_token, chat_id, thread_oi)
    )

if __name__ == "__main__":
    asyncio.run(main())
