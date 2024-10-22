import asyncio
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from dotenv import load_dotenv
import os
from database.redis_client import RedisClient

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
async def start_command(message):
    await message.answer("Привет! Используйте команду /status для получения статуса или /list для списка товаров.")

from bot.handlers.registration import router as registration_router
from bot.handlers.notifications import router as notifications_router

dp.include_router(registration_router)
dp.include_router(notifications_router)

async def main():
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
