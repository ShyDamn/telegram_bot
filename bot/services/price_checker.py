import asyncio
from database.redis_client import RedisClient
from bot.services.parser import PriceParser
from bot.services.notification_service import NotificationService
import logging

class PriceChecker:
    def __init__(self, redis_client: RedisClient, notification_service: NotificationService):
        self.redis_client = redis_client
        self.parser = PriceParser()
        self.notification_service = notification_service

    async def check_price_for_product(self, user_id: int, product: dict):
        logging.debug(f"Проверка цены для пользователя {user_id}, товар '{product['title']}'")
        current_price = await self.parser.get_price(product['product_url'])
        logging.debug(f"Текущая цена для '{product['title']}': {current_price}")
        target_price = float(product['targetPrice'])
        if current_price and current_price <= target_price:
            if not self.redis_client.is_already_parsed(user_id, product['product_url']):
                logging.info(f"Отправка уведомления для пользователя {user_id}, товар '{product['title']}'")
                await self.notification_service.send_price_alert(
                    user_id=user_id,
                    product_title=product['title'],
                    current_price=current_price,
                    target_price=target_price,
                    product_url=product['product_url']
                )
                self.redis_client.mark_as_parsed(user_id, product['product_url'])
            else:
                logging.debug(f"Уведомление для '{product['title']}' уже было отправлено")
        else:
            logging.debug(f"Нет необходимости отправлять уведомление для '{product['title']}'. Текущая цена: {current_price}, Целевая цена: {target_price}")

    async def start_monitoring(self):
        logging.info("PriceChecker monitoring started")
        while True:
            users = self.redis_client.get_all_users()
            for user_id in users:
                products = self.redis_client.get_products(user_id)
                tasks = [self.check_price_for_product(user_id, product) for product in products]
                if tasks:
                    await asyncio.gather(*tasks)
            await asyncio.sleep(60)  # Проверка каждые 60 секунд
