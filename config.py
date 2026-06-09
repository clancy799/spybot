import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.environ.get("BOT_TOKEN")
SUPER_ADMIN_ID = int(os.environ.get("SUPER_ADMIN_ID", 0))
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://user:password@localhost/spybot")
# Railway DATABASE_URL postgres:// болады, asyncpg үшін postgresql+asyncpg:// керек
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)
