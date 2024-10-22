import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from dotenv import load_dotenv
import os
from database.redis_client import RedisClient
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from bot.services.notification_service import NotificationService
from bot.services.price_checker import PriceChecker

import logging

# Настройка логирования
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

load_dotenv()
bot_token = os.getenv('TELEGRAM_TOKEN')

if not bot_token:
    print("Error: TELEGRAM_TOKEN not found in .env file.")
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
    token = await redis_client.get_user_token(user_id)

    if token:
        # Пользователь зарегистрирован
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="Статус", callback_data="status"),
                    InlineKeyboardButton(text="Список товаров", callback_data="list")
                ],
                [
                    InlineKeyboardButton(text="Удалить аккаунт", callback_data="delete_account")
                ]
            ]
        )
        await message.answer("Выберите действие:", reply_markup=keyboard)
    else:
        # Пользователь не зарегистрирован
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="Зарегистрироваться", callback_data="registration")
                ]
            ]
        )
        await message.answer("Пожалуйста, зарегистрируйтесь для начала работы:", reply_markup=keyboard)

from bot.handlers.registration import router as registration_router
from bot.handlers.notifications import router as notifications_router

dp.include_router(registration_router)
dp.include_router(notifications_router)

async def main():
    # Создаём экземпляры
    notification_service = NotificationService(bot=bot)
    price_checker = PriceChecker(redis_client=redis_client, notification_service=notification_service)

    # Создаём фоновую задачу
    asyncio.create_task(price_checker.start_monitoring())

    # Запускаем polling
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
