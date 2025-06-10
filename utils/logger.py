import logging
import os
from datetime import datetime
from telegram import Bot
import asyncio

# === 日志配置 ===
log_dir = "logs"
os.makedirs(log_dir, exist_ok=True)

log_file = os.path.join(log_dir, f"{datetime.now().strftime('%Y-%m-%d')}.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] - %(message)s",
    handlers=[
        logging.FileHandler(log_file, encoding="utf-8"),
        logging.StreamHandler()
    ]
)

# === 普通日志 ===
def log_info(message):
    logging.info(message)

# === 错误日志 ===
def log_error(message):
    logging.error(message)

# === 可选：推送严重错误通知到 Telegram ===
async def notify_error(bot_token: str, chat_id: int, text: str):
    try:
        bot = Bot(token=bot_token)
        await bot.send_message(chat_id=chat_id, text=f"❌ <b>监控程序异常：</b>\n\n<code>{text}</code>", parse_mode="HTML")
        log_info("错误通知已推送 Telegram")
    except Exception as e:
        log_error(f"发送 Telegram 错误通知失败: {e}")
