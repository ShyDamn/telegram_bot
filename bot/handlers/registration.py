from aiogram import types, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from database.redis_client import RedisClient

router = Router()

def generate_token(user_id: int) -> str:
    import uuid
    return str(uuid.uuid4())

@router.message(Command(commands=['registration']))
async def registration(message: types.Message, redis_client: RedisClient):
    user_id = message.from_user.id
    existing_token = await redis_client.get_user_token(user_id)
    
    if existing_token:
        await message.answer("Вы уже зарегистрированы. Используйте /delete_account, чтобы удалить аккаунт.")
        return

    token = generate_token(user_id)
    await redis_client.save_user(user_id, token)

    instruction = (
        f"✅ Регистрация успешна! Ваш токен: <code>{token}</code>\n"
        "1. Откройте расширение в браузере.\n"
        "2. Введите ваш Telegram ID и токен в настройках расширения.\n"
        "3. Начните добавлять товары для отслеживания!"
    )

    # После регистрации отображаем кнопки для зарегистрированных пользователей
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

    await message.answer(instruction, parse_mode='HTML', reply_markup=keyboard)

# Обработчик для кнопки "Зарегистрироваться"
@router.callback_query(lambda c: c.data == 'registration')
async def registration_callback(callback_query: CallbackQuery, redis_client: RedisClient):
    user_id = callback_query.from_user.id
    existing_token = await redis_client.get_user_token(user_id)
    
    if existing_token:
        await callback_query.message.answer("Вы уже зарегистрированы. Используйте /delete_account, чтобы удалить аккаунт.")
        return

    token = generate_token(user_id)
    await redis_client.save_user(user_id, token)

    instruction = (
        f"✅ Регистрация успешна! Ваш токен: <code>{token}</code>\n"
        "1. Откройте расширение в браузере.\n"
        "2. Введите ваш Telegram ID и токен в настройках расширения.\n"
        "3. Начните добавлять товары для отслеживания!"
    )

    # После регистрации отображаем кнопки для зарегистрированных пользователей
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

    await callback_query.message.answer(instruction, parse_mode='HTML', reply_markup=keyboard)

@router.message(Command(commands=['delete_account']))
async def delete_account(message: types.Message, redis_client: RedisClient):
    user_id = message.from_user.id
    await redis_client.delete_user(user_id)

    # После удаления аккаунта отображаем кнопку регистрации
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Зарегистрироваться", callback_data="registration")
            ]
        ]
    )

    await message.answer("Ваш аккаунт и все данные были удалены. Вы можете зарегистрироваться снова.", reply_markup=keyboard)

# Обработчик для кнопки "Удалить аккаунт"
@router.callback_query(lambda c: c.data == 'delete_account')
async def delete_account_callback(callback_query: CallbackQuery, redis_client: RedisClient):
    user_id = callback_query.from_user.id
    await redis_client.delete_user(user_id)

    # После удаления аккаунта отображаем кнопку регистрации
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Зарегистрироваться", callback_data="registration")
            ]
        ]
    )

    await callback_query.message.answer("Ваш аккаунт и все данные были удалены. Вы можете зарегистрироваться снова.", reply_markup=keyboard)
