import asyncio
import logging
from aiogram import Bot, Dispatcher, BaseMiddleware
from aiogram.types import TelegramObject
from typing import Callable, Dict, Any, Awaitable

from config import settings
from database import init_db
from handlers import start, stats, finance, expenses

class AuthMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        user = data.get("event_from_user")
        if user and int(user.id) != int(settings.admin_id):
            logging.warning(f"Доступ запрещен для ID: {user.id}")
            return
        return await handler(event, data)

async def main():
    logging.basicConfig(
        level=logging.INFO, 
        format="%(asctime)s - %(levelname)s - %(message)s"
    )
    
    await init_db()

    bot = Bot(token=settings.bot_token)
    dp = Dispatcher()

    # Защита по Telegram ID
    auth_mw = AuthMiddleware()
    dp.message.middleware(auth_mw)
    dp.callback_query.middleware(auth_mw)

    # Регистрация хендлеров (expenses строго в конце)
    dp.include_routers(
        start.router,
        stats.router,
        finance.router,
        expenses.router
    )

    logging.info(f"Бот успешно запущен для ADMIN_ID: {settings.admin_id}")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())