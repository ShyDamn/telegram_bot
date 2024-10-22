import pytest
from unittest.mock import MagicMock, AsyncMock
from aiogram import types
from bot.handlers.notifications import router
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
async def test_check_status_active(redis_client, message):
    """Тест команды /status при активном отслеживании"""
    user_id = 12345
    message.from_user.id = user_id
    redis_client.get_user.return_value = {'is_active': '1'}

    await router.message.handlers[0].callback(message, redis_client=redis_client)

    message.answer.assert_called_once()
    assert '📊 Статус отслеживания' in message.answer.call_args[0][0]
    assert '✅ Активно' in message.answer.call_args[0][0]

@pytest.mark.asyncio
async def test_check_status_inactive(redis_client, message):
    """Тест команды /status при неактивном отслеживании"""
    user_id = 12345
    message.from_user.id = user_id
    redis_client.get_user.return_value = {'is_active': '0'}

    await router.message.handlers[0].callback(message, redis_client=redis_client)

    message.answer.assert_called_once()
    assert '📊 Статус отслеживания' in message.answer.call_args[0][0]
    assert '❌ Неактивно' in message.answer.call_args[0][0]

@pytest.mark.asyncio
async def test_check_status_unregistered(redis_client, message):
    """Тест команды /status для незарегистрированного пользователя"""
    user_id = 12345
    message.from_user.id = user_id
    redis_client.get_user.return_value = None

    await router.message.handlers[0].callback(message, redis_client=redis_client)

    message.answer.assert_called_once()
    assert 'Вы не зарегистрированы' in message.answer.call_args[0][0]

@pytest.mark.asyncio
async def test_list_products_with_products(redis_client, message):
    """Тест команды /list с товарами"""
    user_id = 12345
    message.from_user.id = user_id
    products = [
        {'title': 'Product 1', 'price': 1000.0, 'targetPrice': 950.0},
        {'title': 'Product 2', 'price': 2000.0, 'targetPrice': 1800.0}
    ]
    redis_client.get_products.return_value = products

    await router.message.handlers[1].callback(message, redis_client=redis_client)

    message.answer.assert_called_once()
    assert '📦 Ваши отслеживаемые товары' in message.answer.call_args[0][0]
    assert '🛍️ Product 1' in message.answer.call_args[0][0]
    assert '🛍️ Product 2' in message.answer.call_args[0][0]

@pytest.mark.asyncio
async def test_list_products_no_products(redis_client, message):
    """Тест команды /list без товаров"""
    user_id = 12345
    message.from_user.id = user_id
    redis_client.get_products.return_value = []

    await router.message.handlers[1].callback(message, redis_client=redis_client)

    message.answer.assert_called_once()
    assert 'У вас пока нет отслеживаемых товаров' in message.answer.call_args[0][0]
