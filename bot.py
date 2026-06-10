import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config import BOT_TOKEN
from database.engine import init_db
from middlewares.db import DbSessionMiddleware
from handlers import common, shop, admin, game
from handlers.admin import set_games_ref
from handlers.game import games

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


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
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
