from aiogram import types, Router
from aiogram.filters import Command
from database.redis_client import RedisClient

router = Router()

# Команда для отображения статуса отслеживания
@router.message(Command('status'))
async def check_status(message: types.Message, redis_client: RedisClient):
    user_id = message.from_user.id
    user_data = redis_client.get_user(user_id)

    if user_data:
        active = "✅ Активно" if user_data.get("is_active") == "1" else "❌ Неактивно"
        await message.answer(f"📊 Статус отслеживания:\n{active}")
    else:
        await message.answer("❌ Вы не зарегистрированы. Используйте /registration для регистрации.")

# Команда для отображения списка отслеживаемых товаров
@router.message(Command('list'))
async def list_products(message: types.Message, redis_client: RedisClient):
    user_id = message.from_user.id
    products = redis_client.get_products(user_id)

    if products:
        response = "📦 Ваши отслеживаемые товары:\n\n"
        for product in products:
            response += f"🛍️ {product['title']} — {product['price']}₽ (Лимит: {product['targetPrice']}₽)\n"
        await message.answer(response)
    else:
        await message.answer("📦 У вас пока нет отслеживаемых товаров.")
