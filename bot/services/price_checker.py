import asyncio
import logging
from datetime import datetime
from typing import Dict, List
from bot.services.parser import PriceParser

class PriceChecker:
    def __init__(self, redis_client, notification_service, batch_size: int = 50):
        self.redis_client = redis_client
        self.notification_service = notification_service
        self.batch_size = batch_size
        self.parser = None
        self.monitoring_interval = 600
        self.retry_interval = 60
        self.pending_updates = {}
        logging.info("PriceChecker initialized")

    async def process_batch(self, batch_urls: List[str], user_product_map: Dict[str, list]):
        try:
            logging.info(f"Processing batch of {len(batch_urls)} URLs")
            prices = await self.parser.get_prices_batch(batch_urls)
            
            updates_by_user = {}
            
            for url, price in prices.items():
                if price is not None and url in user_product_map:
                    for user_id, product in user_product_map[url]:
                        current_price = float(product.get('price', 0))
                        user_token = await self.redis_client.get_user_token(user_id)
                        
                        if not user_token:
                            continue

                        update = {
                            'product_url': url,
                            'current_price': price
                        }

                        if user_token not in updates_by_user:
                            updates_by_user[user_token] = []
                        updates_by_user[user_token].append(update)

                        target_price = float(product.get('target_price', 0))
                        if price <= target_price:
                            is_parsed = await self.redis_client.is_already_parsed(user_id, url)
                            if not is_parsed:
                                await self.notification_service.send_price_alert(
                                    user_id=user_id,
                                    product_title=product.get('title', 'Unknown'),
                                    current_price=price,
                                    target_price=target_price,
                                    product_url=url
                                )
                                await self.redis_client.mark_as_parsed(user_id, url)
                                logging.info(f"Price alert sent for user {user_id}, product: {product.get('title')}")

            for user_token, updates in updates_by_user.items():
                is_active = await self.parser.check_user_activity(user_token)
                
                if is_active:
                    await self.parser.send_price_updates(user_token, updates)
                    if user_token in self.pending_updates:
                        await self.parser.send_price_updates(user_token, self.pending_updates[user_token])
                        del self.pending_updates[user_token]
                else:
                    if user_token not in self.pending_updates:
                        self.pending_updates[user_token] = []
                    self.pending_updates[user_token].extend(updates)
                    
        except Exception as e:
            logging.error(f"Error processing batch: {e}", exc_info=True)

    async def start_monitoring(self):
        self.parser = PriceParser()
        
        async with self.parser:
            while True:
                try:
                    users = await self.redis_client.get_all_users()
                    all_products = []
                    user_product_map = {}

                    for user_id in users:
                        products = await self.redis_client.get_products(user_id)
                        if not products:
                            continue

                        for product in products:
                            url = product.get('product_url')
                            if url and not await self.redis_client.is_already_parsed(user_id, url):
                                all_products.append(url)
                                if url not in user_product_map:
                                    user_product_map[url] = []
                                user_product_map[url].append((user_id, product))

                    if not all_products:
                        logging.info("No products to check, waiting...")
                        await asyncio.sleep(self.retry_interval)
                        continue

                    batches = [all_products[i:i + self.batch_size] 
                             for i in range(0, len(all_products), self.batch_size)]
                    
                    logging.info(f"Processing {len(batches)} batches ({len(all_products)} products total)")
                    start_time = datetime.now()
                    
                    tasks = []
                    for batch in batches:
                        task = asyncio.create_task(self.process_batch(batch, user_product_map))
                        tasks.append(task)
                    
                    await asyncio.gather(*tasks)
                    
                    end_time = datetime.now()
                    processing_time = (end_time - start_time).total_seconds()
                    logging.info(f"Batch processing completed in {processing_time:.2f} seconds")
                    
                    await asyncio.sleep(self.monitoring_interval)

                except Exception as e:
                    logging.error(f"Error in monitoring loop: {e}", exc_info=True)
                    await asyncio.sleep(self.retry_interval)