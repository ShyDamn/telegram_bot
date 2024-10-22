import pytest
from database.redis_client import RedisClient
from unittest.mock import MagicMock, patch, call, ANY

@pytest.fixture
def redis_mock():
    with patch('redis.Redis') as mock_redis:
        yield mock_redis.return_value

@pytest.fixture
def redis_client(redis_mock):
    return RedisClient()

def test_save_user(redis_client, redis_mock):
    """Тест сохранения пользователя в Redis"""
    user_id = 12345
    token = 'test_token'
    redis_client.save_user(user_id, token)
    redis_mock.hset.assert_any_call(f"user:{user_id}", "token", token)
    redis_mock.hset.assert_any_call(f"user:{user_id}", "is_active", "1")

def test_get_user_token(redis_client, redis_mock):
    """Тест получения токена пользователя"""
    user_id = 12345
    redis_mock.hget.return_value = 'test_token'
    token = redis_client.get_user_token(user_id)
    redis_mock.hget.assert_called_once_with(f"user:{user_id}", "token")
    assert token == 'test_token'

def test_delete_user(redis_client, redis_mock):
    """Тест удаления пользователя"""
    user_id = 12345
    redis_client.delete_user(user_id)
    redis_mock.delete.assert_any_call(f"user:{user_id}")
    redis_mock.delete.assert_any_call(f"products:{user_id}")

def test_save_products(redis_client, redis_mock):
    """Тест сохранения товаров пользователя"""
    user_id = 12345
    products = [{'title': 'Product 1'}, {'title': 'Product 2'}]
    redis_client.save_products(user_id, products)
    redis_mock.delete.assert_called_once_with(f"products:{user_id}")
    calls = [call(f"products:{user_id}", ANY) for _ in products]
    redis_mock.rpush.assert_has_calls(calls, any_order=True)

def test_get_products(redis_client, redis_mock):
    """Тест получения списка товаров пользователя"""
    user_id = 12345
    products_data = ['{"title": "Product 1"}', '{"title": "Product 2"}']
    redis_mock.lrange.return_value = products_data
    products = redis_client.get_products(user_id)
    redis_mock.lrange.assert_called_once_with(f"products:{user_id}", 0, -1)
    assert products == [{'title': 'Product 1'}, {'title': 'Product 2'}]

def test_get_user(redis_client, redis_mock):
    """Тест получения данных пользователя"""
    user_id = 12345
    user_data = {'token': 'test_token', 'is_active': '1'}
    redis_mock.hgetall.return_value = user_data
    user = redis_client.get_user(user_id)
    redis_mock.hgetall.assert_called_once_with(f"user:{user_id}")
    assert user == user_data

def test_get_all_users(redis_client, redis_mock):
    """Тест получения всех пользователей"""
    redis_mock.scan.side_effect = [('1', [f"user:12345"]), ('0', [f"user:67890"])]
    user_ids = redis_client.get_all_users()
    redis_mock.scan.assert_any_call(cursor='0', match='user:*', count=100)
    redis_mock.scan.assert_any_call(cursor='1', match='user:*', count=100)
    assert user_ids == [12345, 67890]

def test_is_already_parsed(redis_client, redis_mock):
    """Тест проверки, был ли товар уже обработан"""
    user_id = 12345
    product_url = 'http://example.com/product'
    redis_mock.sismember.return_value = True
    result = redis_client.is_already_parsed(user_id, product_url)
    redis_mock.sismember.assert_called_once_with(f"parsed:{user_id}", product_url)
    assert result is True

def test_mark_as_parsed(redis_client, redis_mock):
    """Тест отметки товара как обработанного"""
    user_id = 12345
    product_url = 'http://example.com/product'
    redis_client.mark_as_parsed(user_id, product_url)
    redis_mock.sadd.assert_called_once_with(f"parsed:{user_id}", product_url)
