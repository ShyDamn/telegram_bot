from aiogram import Bot
import logging

class NotificationService:
    def __init__(self, bot: Bot):
        self.bot = bot

    async def send_price_alert(self, user_id: int, product_title: str, current_price: float, target_price: float, product_url: str):
        message = (
            f"🎉 Цена на <b>{product_title}</b> снизилась!\n\n"
            f"Текущая цена: {current_price}₽\n"
            f"Целевая цена: {target_price}₽\n\n"
            f"Ссылка на товар: {product_url}"
        )
        try:
            await self.bot.send_message(chat_id=user_id, text=message, parse_mode='HTML')
            logging.info(f"Уведомление отправлено пользователю {user_id} о продукте '{product_title}'")
        except Exception as e:
            logging.error(f"Ошибка при отправке уведомления пользователю {user_id}: {e}")