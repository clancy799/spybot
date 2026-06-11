import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config import BOT_TOKEN, SUPER_ADMIN_ID
from database.engine import init_db
from middlewares.db import DbSessionMiddleware
from handlers import common, shop, admin, game
from handlers.admin import set_games_ref
from handlers.game import games

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)



async def send_daily_backup(bot, admin_id: int):
    import subprocess, os
    from datetime import datetime
    while True:
        await asyncio.sleep(86400)  # 24 сағат
        try:
            db_url = os.environ.get("DATABASE_URL", "")
            filename = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.sql"
            subprocess.run(["pg_dump", db_url, "-f", filename], capture_output=True)
            with open(filename, "rb") as f:
                await bot.send_document(admin_id, f, caption=f"📦 DB Backup {datetime.now().strftime('%Y-%m-%d')}")
            os.remove(filename)
        except Exception as e:
            await bot.send_message(admin_id, f"❌ Backup қатесі: {e}")

async def main():
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    # Middleware — барлық handler-ге session береді
    dp.update.middleware(DbSessionMiddleware())

    # Роутерлерді тіркеу
    dp.include_router(common.router)
    dp.include_router(shop.router)
    dp.include_router(admin.router)
    dp.include_router(game.router)

    # admin.py-ға games сілтемесін беру
    set_games_ref(games)

    # Деректер базасын инициализациялау
    import subprocess
    subprocess.run(["alembic", "upgrade", "head"])
    await init_db()
    logger.info("✅ База данных инициализирована!")

    # Ботты іске қосу
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("✅ Бот запущен!")
    asyncio.ensure_future(send_daily_backup(bot, SUPER_ADMIN_ID))
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
