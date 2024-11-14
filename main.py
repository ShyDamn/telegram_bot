import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv
import os
from database.redis_client import RedisClient
from bot.services.notification_service import NotificationService
from bot.services.price_checker import PriceChecker
import logging
import signal

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

load_dotenv()
bot_token = os.getenv('TELEGRAM_TOKEN')

if not bot_token:
    logging.error("Error: TELEGRAM_TOKEN not found in .env file.")
    exit(1)

bot = Bot(token=bot_token)
dp = Dispatcher()
redis_client = RedisClient()

async def middleware_handler(handler, event, data):
    data['redis_client'] = redis_client
    return await handler(event, data)

dp.update.middleware(middleware_handler)

@dp.message(Command('start'))
async def start_command(message: types.Message, redis_client: RedisClient):
    user_id = message.from_user.id
    token = redis_client.get_user_token(user_id)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Статус" if token else "Зарегистрироваться", 
                    callback_data="status" if token else "registration"
                ),
                InlineKeyboardButton(
                    text="Список товаров", 
                    callback_data="list"
                ) if token else None
            ],
            [
                InlineKeyboardButton(
                    text="Удалить аккаунт", 
                    callback_data="delete_account"
                ) if token else None
            ]
        ]
    )

    await message.answer(
        "Выберите действие:" if token else "Пожалуйста, зарегистрируйтесь для начала работы:",
        reply_markup=keyboard
    )

from bot.handlers.registration import router as registration_router
from bot.handlers.notifications import router as notifications_router

async def setup_routers():
    dp.include_router(registration_router)
    dp.include_router(notifications_router)

async def main():
    try:
        notification_service = NotificationService(bot=bot)
        price_checker = PriceChecker(
            redis_client=redis_client,
            notification_service=notification_service
        )

        await setup_routers()
        
        tasks = [
            asyncio.create_task(price_checker.start_monitoring()),
            asyncio.create_task(dp.start_polling(bot))
        ]

        done, pending = await asyncio.wait(
            tasks,
            return_when=asyncio.FIRST_COMPLETED
        )

        for task in pending:
            task.cancel()
            
    except Exception as e:
        logging.error(f"Critical error in main: {e}", exc_info=True)
    finally:
        await cleanup()

async def cleanup():
    try:
        await bot.session.close()
        tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    except Exception as e:
        logging.error(f"Error during cleanup: {e}")

def signal_handler(signum, frame):
    logging.info(f"Received signal {signum}")
    asyncio.get_event_loop().create_task(cleanup())

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Received KeyboardInterrupt")
    finally:
        logging.info("Application terminated")