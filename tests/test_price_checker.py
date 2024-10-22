import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio
from bot.services.price_checker import PriceChecker
from bot.services.notification_service import NotificationService
from bot.services.parser import PriceParser
from database.redis_client import RedisClient

@pytest.fixture
def redis_client():
    mock_redis = MagicMock()
    mock_redis.get_all_users.return_value = [12345]
    mock_redis.get_products.return_value = []
    mock_redis.is_already_parsed.return_value = False
    mock_redis.mark_as_parsed = MagicMock()
    return mock_redis

@pytest.fixture
def notification_service():
    mock_notification = MagicMock()
    mock_notification.send_price_alert = AsyncMock()
    return mock_notification

@pytest.fixture
def price_checker(redis_client, notification_service):
    checker = PriceChecker(redis_client, notification_service)
    checker.parser = MagicMock()
    checker.parser.get_price = AsyncMock()
    return checker

@pytest.fixture
def test_product():
    return {
        'title': 'Test Product',
        'current_price': 1000.0,
        'target_price': 950.0,
        'product_url': 'https://test.com/product'
    }

@pytest.mark.asyncio
async def test_notification_sent_when_price_below_target(price_checker, test_product):
    """Тест отправки уведомления, когда цена ниже целевой"""
    price_checker.parser.get_price.return_value = 900.0
    
    await price_checker.check_price_for_product(12345, test_product)

    price_checker.notification_service.send_price_alert.assert_called_once_with(
        user_id=12345,
        product_title=test_product['title'],
        current_price=900.0,
        target_price=test_product['target_price'],
        product_url=test_product['product_url']
    )

@pytest.mark.asyncio
async def test_no_notification_when_price_above_target(price_checker, test_product):
    """Тест, что уведомление не отправляется, когда цена выше целевой"""
    price_checker.parser.get_price.return_value = 1000.0
    
    await price_checker.check_price_for_product(12345, test_product)

    price_checker.notification_service.send_price_alert.assert_not_called()

@pytest.mark.asyncio
async def test_notification_not_sent_twice_for_same_product(price_checker, test_product):
    """Тест, что уведомление не отправляется повторно для того же товара"""
    price_checker.parser.get_price.return_value = 900.0
    price_checker.redis_client.is_already_parsed.return_value = True
    
    await price_checker.check_price_for_product(12345, test_product)

    price_checker.notification_service.send_price_alert.assert_not_called()

@pytest.mark.asyncio
async def test_parser_error_handling(price_checker, test_product):
    """Тест обработки ошибок парсера"""
    price_checker.parser.get_price.return_value = None
    
    await price_checker.check_price_for_product(12345, test_product)

    price_checker.notification_service.send_price_alert.assert_not_called()

@pytest.mark.asyncio
async def test_notification_exactly_at_target_price(price_checker, test_product):
    """Тест отправки уведомления, когда цена равна целевой"""
    price_checker.parser.get_price.return_value = test_product['target_price']
    
    await price_checker.check_price_for_product(12345, test_product)

    price_checker.notification_service.send_price_alert.assert_called_once()

@pytest.mark.asyncio
async def test_multiple_products_monitoring(redis_client, notification_service):
    """Тест мониторинга нескольких товаров"""
    products = [
        {
            'title': 'Product 1',
            'current_price': 1000.0,
            'target_price': 950.0,
            'product_url': 'https://test.com/product1'
        },
        {
            'title': 'Product 2',
            'current_price': 2000.0,
            'target_price': 1800.0,
            'product_url': 'https://test.com/product2'
        }
    ]
    
    redis_client.get_products.return_value = products
    
    checker = PriceChecker(redis_client, notification_service)
    checker.parser = MagicMock()
    checker.parser.get_price = AsyncMock(side_effect=[900.0, 1900.0])
    
    tasks = [checker.check_price_for_product(12345, product) for product in products]
    await asyncio.gather(*tasks)

    assert notification_service.send_price_alert.call_count == 1

if __name__ == "__main__":
    pytest.main(["-v"])