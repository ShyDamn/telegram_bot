import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from aiogram import types
from bot.handlers.registration import router
from database.redis_client import RedisClient

@pytest.fixture
def redis_client():
    return MagicMock(spec=RedisClient)

@pytest.fixture
def message():
    msg = MagicMock(spec=types.Message)
    msg.from_user = MagicMock()
    msg.answer = AsyncMock()
    return msg

@pytest.mark.asyncio
async def test_registration_new_user(redis_client, message):
    """Тест регистрации нового пользователя"""
    user_id = 12345
    message.from_user.id = user_id
    redis_client.get_user_token.return_value = None

    with patch('bot.handlers.registration.generate_token', return_value='test_token'):
        await router.message.handlers[0].callback(message, redis_client=redis_client)

    redis_client.save_user.assert_called_once_with(user_id, 'test_token')
    message.answer.assert_called_once()
    assert 'Ваш токен' in message.answer.call_args[0][0]

@pytest.mark.asyncio
async def test_registration_existing_user(redis_client, message):
    """Тест регистрации уже существующего пользователя"""
    user_id = 12345
    message.from_user.id = user_id
    redis_client.get_user_token.return_value = 'existing_token'

    await router.message.handlers[0].callback(message, redis_client=redis_client)

    redis_client.save_user.assert_not_called()
    message.answer.assert_called_once()
    assert 'Вы уже зарегистрированы' in message.answer.call_args[0][0]

@pytest.mark.asyncio
async def test_delete_account(redis_client, message):
    """Тест удаления аккаунта"""
    user_id = 12345
    message.from_user.id = user_id

    await router.message.handlers[1].callback(message, redis_client=redis_client)

    redis_client.delete_user.assert_called_once_with(user_id)
    message.answer.assert_called_once()
    assert 'Ваш аккаунт и все данные были удалены' in message.answer.call_args[0][0]
