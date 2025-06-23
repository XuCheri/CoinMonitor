import asyncio
from typing import Optional, List
from telegram import Bot
import html

from .base_monitor import BaseMonitor
from utils.logger import log_error, log_info


class TwitterMonitor(BaseMonitor):
    """
    监控指定的Twitter用户列表，并在他们发布新推文时发送Telegram通知。
    """
    TWITTER_API_URL = "https://api.twitter.com/2"

    def __init__(
        self,
        bot: Bot,
        chat_id: int,
        topic_id: int,
        proxy_url: Optional[str] = None,
        interval: int = 300,
        **kwargs
    ):
        super().__init__(bot, chat_id, topic_id, proxy_url, interval, **kwargs)
        self.bearer_token = kwargs.get("bearer_token")
        self.watch_ids: List[str] = kwargs.get("watch_ids", [])
        if not self.bearer_token:
            raise ValueError("Twitter bearer_token is required for TwitterMonitor.")
        
        self.latest_tweet_ids: dict[str, str] = {}
        self.is_first_run = True  # 标记是否为首次运行

    async def _fetch_twitter_api(self, endpoint: str, params: Optional[dict] = None) -> dict:
        """
        带重试逻辑的Twitter API请求函数。
        """
        url = f"{self.TWITTER_API_URL}{endpoint}"
        headers = {"Authorization": f"Bearer {self.bearer_token}"}
        return await self.fetch_json(url, params=params, headers=headers)

    async def _fetch_latest_tweet(self, user_id: str) -> Optional[dict]:
        """获取指定用户的最新一条推文。"""
        params = {
            "max_results": "5",
            "tweet.fields": "created_at",
            "expansions": "author_id",
            "user.fields": "name,username"
        }
        endpoint = f"/users/{user_id}/tweets"
        data = await self._fetch_twitter_api(endpoint, params=params)
        
        users = {u['id']: u for u in data.get('includes', {}).get('users', [])}
        tweets = data.get("data", [])
        
        if not tweets:
            return None
        
        latest_tweet = tweets[0]
        author = users.get(latest_tweet['author_id'])
        if author:
            latest_tweet['author_username'] = author.get('username', 'N/A')
            latest_tweet['author_name'] = author.get('name', 'N/A')

        return latest_tweet

    async def check(self):
        """监控器主逻辑：轮询用户，检查新推文。"""
        alerts_to_send = []

        for user_id in self.watch_ids:
            try:
                tweet = await self._fetch_latest_tweet(user_id)
                if not tweet:
                    continue

                tweet_id = tweet['id']
                
                if self.is_first_run:
                    self.latest_tweet_ids[user_id] = tweet_id
                    continue
                
                if self.latest_tweet_ids.get(user_id) != tweet_id:
                    self.latest_tweet_ids[user_id] = tweet_id
                    
                    text = tweet['text'].replace("<", "&lt;").replace(">", "&gt;")
                    author_name = tweet.get('author_name', user_id)
                    author_username = tweet.get('author_username', '')
                    author_link = f"https://twitter.com/{author_username}" if author_username else f"https://twitter.com/i/user/{user_id}"
                    tweet_link = f"https://twitter.com/{author_username}/status/{tweet_id}" if author_username else f"https://twitter.com/i/web/status/{tweet_id}"

                    alert_text = (
                        f"🐦 <b><a href='{author_link}'>{author_name}</a> 发布了新推文</b>\n\n"
                        f"<blockquote>{text}</blockquote>\n"
                        f"<a href='{tweet_link}'>查看原文</a>"
                    )
                    alerts_to_send.append(alert_text)

            except Exception as e:
                log_error(f"❌ {self.monitor_name}: 获取用户 {user_id} 推文失败: {e}")
            
            await asyncio.sleep(1)

        if self.is_first_run:
            log_info(f"{self.monitor_name}: 已初始化 {len(self.latest_tweet_ids)} 个用户的最新推文ID。")
            self.is_first_run = False
            return

        if alerts_to_send:
            log_info(f"📢 {self.monitor_name}: 发现 {len(alerts_to_send)} 条新推文，正在发送...")
            for alert in alerts_to_send:
                await self.send_message(alert, parse_mode="HTML", disable_web_page_preview=True)
                await asyncio.sleep(0.5)

    def add_to_watchlist(self, user_id: str) -> str:
        """动态向监控列表添加一个 Twitter User ID。"""
        if not user_id.isdigit():
            return f"❌ <b>{self.monitor_name}</b>: User ID 必须是纯数字。"

        if user_id in self.watch_ids:
            return f"🟡 <b>{self.monitor_name}</b>: User ID <code>{user_id}</code> 已在监控列表中。"

        self.watch_ids.append(user_id)
        self.is_first_run = True # 需要重新初始化
        return f"✅ <b>{self.monitor_name}</b>: 已将 User ID <code>{user_id}</code> 添加到监控列表。将在下个周期重新初始化。"

    def remove_from_watchlist(self, user_id: str) -> str:
        """动态从监控列表移除一个 Twitter User ID。"""
        if user_id not in self.watch_ids:
            return f"🟡 <b>{self.monitor_name}</b>: User ID <code>{user_id}</code> 不在监控列表中。"
        
        self.watch_ids = [uid for uid in self.watch_ids if uid != user_id]
        self.latest_tweet_ids.pop(user_id, None)
        
        return f"✅ <b>{self.monitor_name}</b>: 已从监控列表移除 User ID <code>{user_id}</code>。"

    def get_status(self) -> str:
        """返回监控器的当前状态描述。"""
        status = (
            f"<b>{self.monitor_name}</b>\n"
            f"  - 监控状态: {'运行中' if self._running else '已停止'}\n"
            f"  - 检查间隔: {self.interval}秒\n"
            f"  - 监控用户数: {len(self.watch_ids)}\n"
            f"  - 监控ID: <code>{', '.join(self.watch_ids)}</code>"
        )
        return status
