import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from aiogram import Bot
from bot.services.notification_service import NotificationService

@pytest.fixture
def bot_mock():
    mock_bot = MagicMock(spec=Bot)
    mock_bot.send_message = AsyncMock()
    return mock_bot

@pytest.mark.asyncio
async def test_send_price_alert(bot_mock):
    """Тест отправки уведомления о достижении целевой цены"""
    with patch('bot.services.notification_service.format_price', side_effect=lambda x: f"{x:.2f}"):
        notification_service = NotificationService(bot_mock)
        user_id = 12345
        product_title = 'Test Product'
        current_price = 900.0
        target_price = 950.0
        product_url = 'https://example.com/product'

        await notification_service.send_price_alert(
            user_id=user_id,
            product_title=product_title,
            current_price=current_price,
            target_price=target_price,
            product_url=product_url
        )

        expected_message = (
            f"🎯 Целевая цена достигнута!\n\n"
            f"📦 {product_title}\n"
            f"💰 Текущая цена: {current_price:.2f}₽\n"
            f"🎯 Целевая цена: {target_price:.2f}₽\n"
            f"🔗 {product_url}"
        )

        bot_mock.send_message.assert_called_once_with(user_id, expected_message)
