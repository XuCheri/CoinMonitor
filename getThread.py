from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

BOT_TOKEN = "8129443696:AAF-25-gQV6WCfNDikN09l6bicMHOESW3rU"

async def thread_id_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if msg.message_thread_id:
        print(f"🧵 来自话题消息，话题 ID：{msg.message_thread_id}")
    else:
        print("📩 普通消息，无话题 ID")

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.ALL, thread_id_handler))
    print("✅ 机器人已启动，等待消息...")
    app.run_polling()  # 注意这里不是 await，是同步调用

if __name__ == "__main__":
    main()
