import aiohttp
import asyncio
from telegram import Bot
from utils.logger import log_info, log_error, notify_error

last_seen_id = None  # 用于缓存上一次推送的 tweet id

def text_limit(text, max_len=4000):
    return text if len(text) <= max_len else text[:max_len - 10] + "..."

async def fetch_latest_tweets(session, user_id, bearer_token, proxy):
    url = f"https://api.twitter.com/2/users/{user_id}/tweets?max_results=5&tweet.fields=created_at"
    headers = {
        "Authorization": f"Bearer {bearer_token}"
    }
    async with session.get(url, headers=headers, proxy=proxy) as resp:
        resp.raise_for_status()
        return await resp.json()

async def run_monitor(bot_token, chat_id, bearer_token, user_id, topic_id,proxy, interval=120):
    global last_seen_id
    bot = Bot(token=bot_token)

    log_info("✅ 启动 Twitter 推文监控")


    async with aiohttp.ClientSession() as session:
        while True:
            try:
                data = await fetch_latest_tweets(session, user_id, bearer_token, proxy)
                tweets = data.get("data", [])
                if not tweets:
                    log_info("✅ 当前无推文")
                    await asyncio.sleep(interval)
                    continue

                new_tweets = []
                for tweet in tweets:
                    if tweet["id"] == last_seen_id:
                        break
                    new_tweets.append(tweet)

                if new_tweets:
                    new_tweets.reverse()
                    for tweet in new_tweets:
                        url = f"https://twitter.com/i/web/status/{tweet['id']}"
                        text = (
                            f"🐦 <b>新推文监控</b>\n\n"
                            f"{text_limit(tweet['text'])}\n\n"
                            f"🔗 <a href='{url}'>查看推文</a>"
                        )
                        await bot.send_message(chat_id=chat_id, text=text, message_thread_id=topic_id, parse_mode="HTML")

                    last_seen_id = tweets[0]["id"]
                    log_info(f"📢 推送 {len(new_tweets)} 条新推文")
                else:
                    log_info("✅ 暂无新推文")

            except Exception as e:
                log_error(f"❌ 推文监控出错: {e}")
                await notify_error(bot_token, chat_id, f"推特监控异常：{e}")

            await asyncio.sleep(interval)
