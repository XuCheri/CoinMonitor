from telegram import Bot
import asyncio

async def send_message(bot_token, chat_id, text, message_thread_id=None, parse_mode="HTML"):
    """
    异步发送 Telegram 消息
    """
    try:
        bot = Bot(token=bot_token)
        await bot.send_message(
            chat_id=chat_id,
            text=text,
            message_thread_id=message_thread_id,
            parse_mode=parse_mode
        )
        print(f"✅ 发送成功：{text[:30]}...")

    except Exception as e:
        print(f"❌ 发送消息失败: {e}")
