import asyncio
import json
from monitors import (
    funding_rate_monitor,
    spot_volume_monitor,
    open_interest_monitor,
    twitter_monitor
)

# === 加载配置文件 ===
with open("config.json", "r", encoding="utf-8") as f:
    config = json.load(f)

# === 通用配置 ===
bot_token = config["bot_token"]
chat_id = config["chat_id"]
interval = config.get("check_interval", 60)

# === 话题配置 ===
thread_funding = config["message_threads"]["funding_rate"]
thread_volume = config["message_threads"]["spot_volume"]
thread_oi = config["message_threads"]["open_interest"]
thread_twitter = config["message_threads"]["twitter_monitor"]

# === Twitter 监控相关 ===
twitter_bearer_token = config.get("twitter_bearer_token")
twitter_user_id = config.get("twitter_user_id")
proxy = config.get("proxy")

async def main():
    tasks = [
        asyncio.create_task(funding_rate_monitor.run_monitor(bot_token, chat_id, thread_funding)),
        asyncio.create_task(spot_volume_monitor.run_spot_volume_monitor(bot_token, chat_id, thread_volume)),
        asyncio.create_task(open_interest_monitor.run_open_interest_monitor(bot_token, chat_id, thread_oi))
    ]

    # 如果配置了推特监控所需信息，启用推特监控
    if twitter_bearer_token and twitter_user_id:
        tasks.append(
            asyncio.create_task(
                twitter_monitor.run_monitor(bot_token, chat_id, thread_twitter, twitter_bearer_token, twitter_user_id, proxy)
            )
        )

    await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(main())
