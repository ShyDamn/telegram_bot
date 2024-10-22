import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from database.redis_client import RedisClient
from bot.services.session_manager import SessionManager

@pytest.fixture
def redis_client():
    return MagicMock(spec=RedisClient)

@pytest.fixture
def session_manager(redis_client):
    return SessionManager(redis_client, session_api_url='http://testserver')

@pytest.mark.asyncio
async def test_fetch_user_data_from_backend_success(session_manager):
    """Тест успешного получения данных с бэкенда"""
    user_id = 12345
    token = 'test_token'
    response_data = {'products': [{'title': 'Product 1'}]}
    with patch('aiohttp.ClientSession.get') as mock_get:
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=response_data)
        mock_get.return_value.__aenter__.return_value = mock_response

        data = await session_manager.fetch_user_data_from_backend(user_id, token)
        assert data == response_data

@pytest.mark.asyncio
async def test_fetch_user_data_from_backend_error(session_manager):
    """Тест обработки ошибки при получении данных с бэкенда"""
    user_id = 12345
    token = 'test_token'
    with patch('aiohttp.ClientSession.get') as mock_get:
        mock_response = AsyncMock()
        mock_response.status = 500
        mock_get.return_value.__aenter__.return_value = mock_response

        data = await session_manager.fetch_user_data_from_backend(user_id, token)
        assert data == {}

@pytest.mark.asyncio
async def test_fetch_user_data_from_backend_exception(session_manager):
    """Тест обработки исключения при подключении к бэкенду"""
    user_id = 12345
    token = 'test_token'
    with patch('aiohttp.ClientSession.get', side_effect=Exception('Connection error')):
        data = await session_manager.fetch_user_data_from_backend(user_id, token)
        assert data == {}

@pytest.mark.asyncio
async def test_update_user_products(session_manager, redis_client):
    """Тест обновления продуктов пользователя"""
    user_id = 12345
    token = 'test_token'
    session_data = {'products': [{'title': 'Product 1'}]}
    with patch.object(session_manager, 'fetch_user_data_from_backend', return_value=session_data):
        with patch('json.dumps', side_effect=lambda x: '{"title": "Product 1"}'):
            await session_manager.update_user_products(user_id, token)
            redis_client.save_products.assert_called_once_with(user_id, ['{"title": "Product 1"}'])

@pytest.mark.asyncio
async def test_update_user_products_no_products(session_manager, redis_client):
    """Тест обновления продуктов при отсутствии данных"""
    user_id = 12345
    token = 'test_token'
    session_data = {}
    with patch.object(session_manager, 'fetch_user_data_from_backend', return_value=session_data):
        await session_manager.update_user_products(user_id, token)
        redis_client.save_products.assert_not_called()
