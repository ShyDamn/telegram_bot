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
        logging.info("PriceChecker инициализирован")

    async def check_price_for_product(self, user_id: int, product: dict):
        
        product_url = product.get('product_url')
        if not product_url:
            logging.error(f"Отсутствует 'product_url' для продукта: {product}")
            return

        try:
            current_price = await asyncio.wait_for(self.parser.get_price(product_url), timeout=240)
            
            if current_price is None:
                logging.error(f"Не удалось получить цену для '{product.get('title', 'No Title')}'")
                return
            
            target_price = float(product.get('target_price', 0))

            if current_price <= target_price:
                is_parsed = await self.redis_client.is_already_parsed(user_id, product_url)

                if not is_parsed:
                    await self.notification_service.send_price_alert(
                        user_id=user_id,
                        product_title=product.get('title', 'No Title'),
                        current_price=current_price,
                        target_price=target_price,
                        product_url=product_url
                    )
                    await self.redis_client.mark_as_parsed(user_id, product_url)
                    logging.info(f"Уведомление отправлено и товар помечен для пользователя {user_id}")

        except asyncio.TimeoutError:
            logging.error(f"Таймаут при проверке цены для '{product.get('title', 'No Title')}'")
        except Exception as e:
            logging.error(f"Ошибка при проверке цены для '{product.get('title', 'No Title')}': {e}", exc_info=True)

    async def start_monitoring(self):
        logging.info("Запуск мониторинга цен")
        while True:
            try:
                users = await self.redis_client.get_all_users()

                for user_id in users:
                    products = await self.redis_client.get_products(user_id)

                    if not products:
                        logging.warning(f"Нет товаров для пользователя {user_id}")
                        continue

                    tasks = [self.check_price_for_product(user_id, product) for product in products]

                    if tasks:
                        await asyncio.gather(*tasks)

                logging.info("Ожидание следующей итерации (600 секунд)")
                await asyncio.sleep(600)
            except Exception as e:
                logging.error(f"Ошибка в цикле мониторинга: {e}", exc_info=True)
                await asyncio.sleep(60)