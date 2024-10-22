from aiogram import Bot
from bot.utils.helpers import format_price

class NotificationService:
    def __init__(self, bot: Bot):
        self.bot = bot

    async def send_price_alert(self, user_id: int, product_title: str, 
                             current_price: float, target_price: float, 
                             product_url: str):
        message = (
            f"🎯 Целевая цена достигнута!\n\n"
            f"📦 {product_title}\n"
            f"💰 Текущая цена: {format_price(current_price)}₽\n"
            f"🎯 Целевая цена: {format_price(target_price)}₽\n"
            f"🔗 {product_url}"
        )
        await self.bot.send_message(user_id, message)
