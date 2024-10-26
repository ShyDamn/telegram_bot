import asyncio
from typing import List
from database.redis_client import RedisClient
from bot.services.parser import PriceParser
from bot.services.notification_service import NotificationService
import logging
from dataclasses import dataclass

@dataclass
class ProductInfo:
    user_id: int
    url: str
    title: str
    target_price: float

class PriceChecker:
    def __init__(self, redis_client: RedisClient, notification_service: NotificationService, batch_size: int = 50, concurrent_workers: int = 5):
        self.redis_client = redis_client
        self.notification_service = notification_service
        self.parser = PriceParser(concurrent_workers=concurrent_workers)
        self.batch_size = batch_size
        logging.info(f"PriceChecker инициализирован (batch_size={batch_size}, workers={concurrent_workers})")

    async def initialize(self):
        await self.parser.setup()
        logging.info("Parser initialization completed")

    async def check_prices_batch(self, products_info: List[ProductInfo]):
        urls = [p.url for p in products_info]
        url_to_product = {p.url: p for p in products_info}
        
        try:
            results = await self.parser.parse_urls(urls)
            
            notifications = []
            for result in results:
                product = url_to_product[result.url]
                
                if result.error:
                    logging.error(f"Ошибка парсинга для '{product.title}': {result.error}")
                    continue
                    
                if result.price is None:
                    logging.error(f"Не удалось получить цену для '{product.title}'")
                    continue

                if result.price <= product.target_price:
                    is_parsed = await self.redis_client.is_already_parsed(
                        product.user_id, 
                        product.url
                    )
                    
                    if not is_parsed:
                        notifications.append(self.notification_service.send_price_alert(
                            user_id=product.user_id,
                            product_title=product.title,
                            current_price=result.price,
                            target_price=product.target_price,
                            product_url=product.url
                        ))
                        await self.redis_client.mark_as_parsed(product.user_id, product.url)
                        logging.info(f"Товар помечен для пользователя {product.user_id}: {product.title}")

            if notifications:
                await asyncio.gather(*notifications)
                
        except Exception as e:
            logging.error(f"Ошибка при обработке пакета товаров: {e}", exc_info=True)

    async def start_monitoring(self):
        try:
            await self.initialize()
            logging.info("Запуск оптимизированного мониторинга цен")
            
            while True:
                try:
                    users = await self.redis_client.get_all_users()
                    all_products_info = []

                    for user_id in users:
                        products = await self.redis_client.get_products(user_id)
                        
                        if not products:
                            logging.warning(f"Нет товаров для пользователя {user_id}")
                            continue
                            
                        for product in products:
                            url = product.get('product_url')
                            if url:
                                all_products_info.append(ProductInfo(
                                    user_id=user_id,
                                    url=url,
                                    title=product.get('title', 'No Title'),
                                    target_price=float(product.get('target_price', 0))
                                ))

                    for i in range(0, len(all_products_info), self.batch_size):
                        batch = all_products_info[i:i + self.batch_size]
                        await self.check_prices_batch(batch)
                        await asyncio.sleep(2)

                    logging.info("Ожидание следующей итерации (600 секунд)")
                    await asyncio.sleep(600)
                    
                except Exception as e:
                    logging.error(f"Ошибка в цикле мониторинга: {e}", exc_info=True)
                    await asyncio.sleep(60)
                    
        finally:
            await self.parser.cleanup()