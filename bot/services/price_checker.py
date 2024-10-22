import asyncio
from database.redis_client import RedisClient
from bot.services.parser import PriceParser
from bot.services.notification_service import NotificationService
from bot.utils.helpers import format_price

class PriceChecker:
    def __init__(self, redis_client: RedisClient, notification_service: NotificationService):
        self.redis_client = redis_client
        self.parser = PriceParser()
        self.notification_service = notification_service

    async def check_price_for_product(self, user_id: int, product: dict):
        current_price = await self.parser.get_price(product['product_url'])
        if current_price and current_price <= product['target_price']:
            if not self.redis_client.is_already_parsed(user_id, product['product_url']):
                await self.notification_service.send_price_alert(
                    user_id=user_id,
                    product_title=product['title'],
                    current_price=current_price,
                    target_price=product['target_price'],
                    product_url=product['product_url']
                )
                self.redis_client.mark_as_parsed(user_id, product['product_url'])

    async def start_monitoring(self):
        while True:
            users = self.redis_client.get_all_users()
            for user_id in users:
                products = self.redis_client.get_products(user_id)
                tasks = [self.check_price_for_product(user_id, product) for product in products]
                await asyncio.gather(*tasks)
            await asyncio.sleep(3600)  # Проверка раз в час
