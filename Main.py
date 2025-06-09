# Main.py  ─────────────────────────────────────────────────────────────
import asyncio, logging, os, sys, sqlite3
from datetime import datetime
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from Handlers import router
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

dp = Dispatcher()

# ——— функция-пульс — обновляет таблицу heartbeat каждую минуту ———
async def heartbeat_loop(db_path: str = "bot_logs.db"):
    while True:
        try:
            conn = sqlite3.connect(db_path)
            conn.execute("""CREATE TABLE IF NOT EXISTS heartbeat
                            (id INTEGER PRIMARY KEY CHECK (id = 1),
                             ts TEXT)""")
            conn.execute("INSERT OR REPLACE INTO heartbeat (id, ts) VALUES (1,?)",
                         (datetime.utcnow().isoformat(),))
            conn.commit()
            conn.close()
        except Exception as e:
            logging.error(f"Heartbeat error: {e}")
        await asyncio.sleep(5)        # ← период, при желании измените
# ───────────────────────────────────────────────────────────────────────

async def main() -> None:
    bot = Bot(token=BOT_TOKEN,
              default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp.include_router(router)

    # запускаем пульс параллельно с polling
    asyncio.create_task(heartbeat_loop())

    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Бот выключен")
