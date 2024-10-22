import pytest
from unittest.mock import AsyncMock, patch
from bot.services.parser import PriceParser

@pytest.mark.asyncio
async def test_get_price_ozon():
    """Тест получения цены для Ozon"""
    url = 'https://www.ozon.ru/product/test-product'
    html = '<span class="s3m_27">1 000 ₽</span>'
    parser = PriceParser()
    with patch('aiohttp.ClientSession.get') as mock_get:
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value=html)
        mock_get.return_value.__aenter__.return_value = mock_response

        price = await parser.get_price(url)
        assert price == 1000.0

@pytest.mark.asyncio
async def test_get_price_wildberries():
    """Тест получения цены для Wildberries"""
    url = 'https://www.wildberries.ru/product/test-product'
    html = '<span class="price-block__final-price">2 000 ₽</span>'
    parser = PriceParser()
    with patch('aiohttp.ClientSession.get') as mock_get:
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value=html)
        mock_get.return_value.__aenter__.return_value = mock_response

        price = await parser.get_price(url)
        assert price == 2000.0

@pytest.mark.asyncio
async def test_get_price_yandex_market():
    """Тест получения цены для Яндекс.Маркета"""
    url = 'https://market.yandex.ru/product--test-product'
    html = '<div data-tid="c3eaad93">3 000 ₽</div>'
    parser = PriceParser()
    with patch('aiohttp.ClientSession.get') as mock_get:
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value=html)
        mock_get.return_value.__aenter__.return_value = mock_response

        price = await parser.get_price(url)
        assert price == 3000.0

@pytest.mark.asyncio
async def test_get_price_unknown_site():
    """Тест получения цены для неизвестного сайта"""
    url = 'https://unknownsite.com/product/test-product'
    parser = PriceParser()
    with patch('aiohttp.ClientSession.get') as mock_get:
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value='')
        mock_get.return_value.__aenter__.return_value = mock_response

        price = await parser.get_price(url)
        assert price is None

@pytest.mark.asyncio
async def test_get_price_request_error():
    """Тест обработки ошибки при запросе"""
    url = 'https://www.ozon.ru/product/test-product'
    parser = PriceParser()
    with patch('aiohttp.ClientSession.get', side_effect=Exception('Network error')):
        price = await parser.get_price(url)
        assert price is None
