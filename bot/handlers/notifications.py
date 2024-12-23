from aiogram import types, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery
from database.redis_client import RedisClient

router = Router()

# Команда для отображения статуса отслеживания
@router.message(Command('status'))
async def check_status(message: types.Message, redis_client: RedisClient):
    user_id = message.from_user.id
    user_data = await redis_client.get_user(user_id)

    if user_data:
        active = "✅ Активно" if user_data.get("is_active") == "1" else "❌ Неактивно"
        await message.answer(f"📊 Статус отслеживания:\n{active}")
    else:
        await message.answer("❌ Вы не зарегистрированы. Используйте /registration для регистрации.")

# Обработчик для кнопки "Статус"
@router.callback_query(lambda c: c.data == 'status')
async def check_status_callback(callback_query: CallbackQuery, redis_client: RedisClient):
    user_id = callback_query.from_user.id
    user_data = await redis_client.get_user(user_id)

    if user_data:
        active = "✅ Активно" if user_data.get("is_active") == "1" else "❌ Неактивно"
        await callback_query.message.answer(f"📊 Статус отслеживания:\n{active}")
    else:
        await callback_query.message.answer("❌ Вы не зарегистрированы. Используйте /registration для регистрации.")

# Команда для отображения списка отслеживаемых товаров
@router.message(Command('list'))
async def list_products(message: types.Message, redis_client: RedisClient):
    user_id = message.from_user.id
    products = await redis_client.get_products(user_id)

    if products:
        response = "📦 Ваши отслеживаемые товары:\n\n"
        for product in products:
            response += f"🛍️ {product.get('title', 'No Title')} — {product.get('price', 'N/A')}₽ (Лимит: {product.get('target_price', 'N/A')}₽)\n"
        await message.answer(response)
    else:
        await message.answer("📦 У вас пока нет отслеживаемых товаров.")

# Обработчик для кнопки "Список товаров"
@router.callback_query(lambda c: c.data == 'list')
async def list_products_callback(callback_query: CallbackQuery, redis_client: RedisClient):
    user_id = callback_query.from_user.id
    products = await redis_client.get_products(user_id)

    if products:
        response = "📦 Ваши отслеживаемые товары:\n\n"
        for product in products:
            response += f"🛍️ {product.get('title', 'No Title')} — {product.get('price', 'N/A')}₽ (Лимит: {product.get('target_price', 'N/A')}₽)\n"
        await callback_query.message.answer(response)
    else:
        await callback_query.message.answer("📦 У вас пока нет отслеживаемых товаров.")
