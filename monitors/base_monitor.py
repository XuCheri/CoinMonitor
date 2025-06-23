import asyncio
import aiohttp
from telegram import Bot
from abc import ABC, abstractmethod
from utils.logger import log_info, log_error
import html
from typing import Optional, Any

class BaseMonitor(ABC):
    """
    一个监控器的抽象基类，包含了通用的功能：
    - aiohttp session 管理
    - 统一的运行循环和错误处理
    - Telegram 消息发送的辅助函数
    """
    def __init__(self, bot: Bot, chat_id: int, topic_id: int, proxy_url: Optional[str] = None, interval: int = 60, **kwargs):
        self.bot = bot
        self.chat_id = chat_id
        self.topic_id = topic_id
        self.proxy_url = proxy_url
        self.interval = interval
        self._running = False
        self.session: Optional[aiohttp.ClientSession] = None
        self.monitor_name = self.__class__.__name__

    async def _get_session(self) -> aiohttp.ClientSession:
        """获取或创建 aiohttp.ClientSession."""
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=20)
            self.session = aiohttp.ClientSession(timeout=timeout)
        return self.session

    @abstractmethod
    async def check(self):
        """
        监控器的核心逻辑。
        子类必须实现此方法以执行具体的监控任务。
        """
        pass
    
    @abstractmethod
    def get_status(self) -> str:
        """
        返回一个描述监控器当前状态和配置的字符串。
        子类必须实现此方法。
        """
        pass

    def update_config(self, key: str, value: str) -> str:
        """
        通用的配置更新方法。
        尝试将字符串值转换为属性的正确类型并更新。
        返回操作结果的消息。
        """
        if not hasattr(self, key):
            return f"❌ <b>{self.monitor_name}</b> 没有名为 <code>{key}</code> 的配置项。"

        try:
            # 获取属性现有的类型
            attr_type = type(getattr(self, key))
            # 转换输入值为正确的类型
            new_value = attr_type(value)
            setattr(self, key, new_value)
            return f"✅ <b>{self.monitor_name}</b> 的配置 <code>{key}</code> 已更新为 <code>{new_value}</code>。"
        except (ValueError, TypeError):
            return f"❌ 无法将值 '{value}' 转换为 <code>{key}</code> 所需的类型。"

    def add_to_watchlist(self, item: str) -> str:
        """向监控列表添加一个项目。子类应根据需要重写此方法。"""
        return f"❌ <b>{self.monitor_name}</b> 不支持添加监控项。"

    def remove_from_watchlist(self, item: str) -> str:
        """从监控列表移除一个项目。子类应根据需要重写此方法。"""
        return f"❌ <b>{self.monitor_name}</b> 不支持移除监控项。"

    async def fetch_json(self, url: str, params: Optional[dict] = None, **kwargs) -> Any:
        """使用 aiohttp 发起 GET 请求并返回 JSON 数据 (dict 或 list)。"""
        session = await self._get_session()
        async with session.get(url, proxy=self.proxy_url, params=params, **kwargs) as resp:
            resp.raise_for_status()  # 如果状态码是 4xx 或 5xx，则抛出异常
            return await resp.json()

    async def run(self):
        """监控器的主循环。"""
        log_info(f"✅ 启动 {self.monitor_name}...")
        self._running = True
        try:
            while self._running:
                try:
                    await self.check()
                except Exception as e:
                    log_error(f"❌ {self.monitor_name} 运行出错: {e}")
                    error_message = f"<b>{self.monitor_name} 异常</b>\n<pre>{html.escape(str(e))}</pre>"
                    await self.send_message(error_message, parse_mode="HTML")
                
                await asyncio.sleep(self.interval)
        finally:
            if self.session:
                await self.session.close()
            log_info(f"🛑 {self.monitor_name} 已停止。")

    def stop(self):
        """停止监控器循环。"""
        if self._running:
            self._running = False
            log_info(f"正在请求停止 {self.monitor_name}...")

    async def send_message(self, text: str, **kwargs):
        """发送 Telegram 文本消息。"""
        await self.bot.send_message(
            chat_id=self.chat_id,
            text=text,
            message_thread_id=self.topic_id,
            **kwargs
        )
    
    async def send_photo(self, photo: bytes, **kwargs):
        """发送 Telegram 图片消息。"""
        await self.bot.send_photo(
            chat_id=self.chat_id,
            photo=photo,
            message_thread_id=self.topic_id,
            **kwargs
        ) 