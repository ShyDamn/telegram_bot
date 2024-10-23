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
        logging.debug(f"Проверка цены для пользователя {user_id}, товар '{product.get('title', 'No Title')}'")
        product_url = product.get('product_url')
        if not product_url:
            logging.error(f"Отсутствует 'product_url' для продукта: {product}")
            return
        try:
            # Таймаут для получения цены
            current_price = await asyncio.wait_for(self.parser.get_price(product_url), timeout=60)
            
            if current_price is None:
                logging.error(f"Не удалось получить цену для '{product.get('title', 'No Title')}'")
                return
            
            logging.debug(f"Текущая цена для '{product.get('title', 'No Title')}': {current_price}")
            
            target_price = float(product.get('target_price', 0))
            logging.debug(f"Целевая цена: {target_price}")

            # Проверка текущей цены с целевой
            if current_price <= target_price:
                logging.debug(f"Текущая цена {current_price} меньше или равна целевой {target_price}. Проверяем Redis...")

                # Проверка, было ли уведомление уже отправлено
                is_parsed = await self.redis_client.is_already_parsed(user_id, product_url)
                logging.debug(f"Статус Redis (уведомление уже отправлено?): {is_parsed}")

                if not is_parsed:
                    logging.info(f"Отправка уведомления для пользователя {user_id}, товар '{product.get('title', 'No Title')}'")
                    await self.notification_service.send_price_alert(
                        user_id=user_id,
                        product_title=product.get('title', 'No Title'),
                        current_price=current_price,
                        target_price=target_price,
                        product_url=product_url
                    )
                    logging.info(f"Уведомление отправлено пользователю {user_id} о продукте '{product.get('title', 'No Title')}'")
                    
                    await self.redis_client.mark_as_parsed(user_id, product_url)
                    logging.debug(f"Пометка товара как обработанного в Redis завершена для товара {product.get('title', 'No Title')}")
                else:
                    logging.debug(f"Уведомление для '{product.get('title', 'No Title')}' уже было отправлено")
            else:
                logging.debug(f"Текущая цена {current_price} выше целевой {target_price}. Уведомление не требуется.")

        except asyncio.TimeoutError:
            logging.error(f"Таймаут при проверке цены для '{product.get('title', 'No Title')}'")
        except Exception as e:
            logging.error(f"Ошибка при проверке цены для '{product.get('title', 'No Title')}': {e}")

    async def start_monitoring(self):
        logging.info("PriceChecker monitoring started")
        while True:
            try:
                users = await self.redis_client.get_all_users()
                for user_id in users:
                    products = await self.redis_client.get_products(user_id)
                    tasks = [self.check_price_for_product(user_id, product) for product in products]
                    if tasks:
                        await asyncio.gather(*tasks)
                await asyncio.sleep(300)  # Интервал проверки цен каждые 5 минут
            except Exception as e:
                logging.error(f"Ошибка в процессе мониторинга цен: {e}")
