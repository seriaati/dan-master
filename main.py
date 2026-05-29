import asyncio
import contextlib

from app.core.bot import DanMaster
from app.core.settings import SETTINGS
from app.db.conn import Database
from app.utils.logging import setup_logging


async def main() -> None:
    setup_logging()

    with contextlib.suppress(KeyboardInterrupt, asyncio.CancelledError):
        async with Database(), DanMaster() as bot:
            await bot.start(token=SETTINGS.discord_token)


if __name__ == "__main__":
    asyncio.run(main())
