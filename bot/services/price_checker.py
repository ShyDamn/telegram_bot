import asyncio
from database.redis_client import RedisClient
from bot.services.parser import PriceParser
from bot.services.notification_service import NotificationService
import logging

class PriceChecker:
    def __init__(self, redis_client: RedisClient, notification_service: NotificationService, batch_size: int = 50, timeout: int = 10):
        self.redis_client = redis_client
        self.parser = PriceParser(max_concurrent_browsers=10)
        self.notification_service = notification_service
        self.batch_size = batch_size
        self.timeout = timeout
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
        async with self.parser:  # Используем контекстный менеджер для управления сессией
            while True:
                try:
                    users = await self.redis_client.get_all_users()
                    all_products = []
                    user_product_map = {}  # Для хранения соответствия URL и информации о товаре/пользователе

                    # Собираем все товары со всех пользователей
                    for user_id in users:
                        products = await self.redis_client.get_products(user_id)
                        if not products:
                            continue

                        for product in products:
                            url = product.get('product_url')
                            if url and not await self.redis_client.is_already_parsed(user_id, url):
                                all_products.append(url)
                                user_product_map[url] = (user_id, product)

                    if not all_products:
                        logging.info("Нет товаров для проверки")
                        await asyncio.sleep(600)
                        continue

                    # Разбиваем все товары на пакеты
                    for i in range(0, len(all_products), self.batch_size):
                        batch_urls = all_products[i:i + self.batch_size]
                        
                        try:
                            # Получаем цены для всего пакета
                            prices = await self.parser.get_prices_batch(batch_urls, timeout=self.timeout)

                            # Обрабатываем результаты
                            for url, price in prices.items():
                                if price is not None and url in user_product_map:
                                    user_id, product = user_product_map[url]
                                    target_price = float(product.get('target_price', 0))

                                    if price <= target_price:
                                        await self.notification_service.send_price_alert(
                                            user_id=user_id,
                                            product_title=product.get('title', 'No Title'),
                                            current_price=price,
                                            target_price=target_price,
                                            product_url=url
                                        )
                                        await self.redis_client.mark_as_parsed(user_id, url)
                                        logging.info(f"Уведомление отправлено для пользователя {user_id}, товар: {product.get('title')}")

                        except Exception as e:
                            logging.error(f"Ошибка при обработке пакета товаров: {e}", exc_info=True)

                        # Небольшая пауза между пакетами
                        await asyncio.sleep(1)

                    logging.info("Завершена проверка всех товаров, ожидание следующей итерации (600 секунд)")
                    await asyncio.sleep(600)

                except Exception as e:
                    logging.error(f"Ошибка в цикле мониторинга: {e}", exc_info=True)
                    await asyncio.sleep(60)