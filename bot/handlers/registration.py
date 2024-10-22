from aiogram import types, Router
from aiogram.filters import Command
from database.redis_client import RedisClient

router = Router()

def generate_token(user_id: int) -> str:
    import uuid
    return str(uuid.uuid4())

@router.message(Command(commands=['registration']))
async def registration(message: types.Message, redis_client: RedisClient):
    user_id = message.from_user.id
    existing_token = redis_client.get_user_token(user_id)
    
    if existing_token:
        await message.answer("Вы уже зарегистрированы. Используйте /delete_account, чтобы удалить аккаунт.")
        return

    token = generate_token(user_id)
    redis_client.save_user(user_id, token)

    instruction = (
        f"✅ Регистрация успешна! Ваш токен: <code>{token}</code>\n"
        "1. Откройте расширение в браузере.\n"
        "2. Введите ваш Telegram ID и токен в настройках расширения.\n"
        "3. Начните добавлять товары для отслеживания!"
    )

    await message.answer(instruction, parse_mode='HTML')

@router.message(Command(commands=['delete_account']))
async def delete_account(message: types.Message, redis_client: RedisClient):
    user_id = message.from_user.id
    redis_client.delete_user(user_id)
    await message.answer("Ваш аккаунт и все данные были удалены. Вы можете зарегистрироваться снова с помощью /registration.")
