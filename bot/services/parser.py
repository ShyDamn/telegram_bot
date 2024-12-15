import aiohttp
import asyncio
import logging
import re
from typing import Dict, List, Optional
from aiohttp import ClientTimeout, ClientSession
from urllib.parse import urlencode
import random
from bs4 import BeautifulSoup
import sys
from playwright.async_api import async_playwright, Page, Browser
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('parser.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

class PriceParser:
    def __init__(self, api_url: str = 'http://localhost:8000'):
        self.session: Optional[ClientSession] = None
        self.browser: Optional[Browser] = None
        self.context = None
        self.timeout = ClientTimeout(total=30)
        self.api_url = api_url

    async def __aenter__(self):
        self.session = ClientSession(timeout=self.timeout)
        playwright = await async_playwright().start()
        self.browser = await playwright.chromium.launch(headless=True)
        
        self.context = await self.browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/119.0.0.0 Safari/537.36'
        )
        
        await self.context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        """)
        
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()

    def _extract_price(self, text: str) -> Optional[float]:
        if not text:
            return None
            
        if 'без:' in text:
            # Извлекаем первую цену после 'без:'
            match = re.search(r'без:.*?(\d[\d\s]*[.,]?\d*)\s*₽', text)
            if match:
                clean_text = match.group(1).replace('\xa0', '').replace('\u2009', '')
                try:
                    price_str = re.sub(r'[^\d.,]', '', clean_text).replace(',', '.')
                    price = float(price_str)
                    return price if price > 0 else None
                except (ValueError, TypeError):
                    return None
            return None
            
        clean_text = re.sub(r'[^\d.,]', '', text.replace('\xa0', '').replace('\u2009', ''))
        match = re.search(r'\d+[.,]?\d*', clean_text)
        if match:
            try:
                price_str = match.group(0).replace(',', '.')
                price = float(price_str)
                return price if price > 0 else None
            except (ValueError, TypeError):
                return None
        return None

    async def get_selectors(self, marketplace: str) -> List[Dict[str, str]]:
        try:
            async with self.session.get(f'{self.api_url}/api/selectors/{marketplace}') as response:
                if response.status == 200:
                    data = await response.json()
                    return [item['selectors'] for item in data.get('selectors_history', [])]
                return []
        except Exception as e:
            logging.error(f"Error fetching selectors for {marketplace}: {e}")
            return []

    async def save_price_history(self, product_url: str, price: float):
        try:
            async with self.session.post(
                f'{self.api_url}/api/price-history',
                json={
                    'product_url': product_url,
                    'price': price,
                    'timestamp': int(datetime.now().timestamp())
                }
            ) as response:
                if response.status != 200:
                    logging.error(f"Failed to save price history for {product_url}")
        except Exception as e:
            logging.error(f"Error saving price history: {e}")

    async def check_user_activity(self, token: str) -> bool:
        try:
            async with self.session.get(
                f'{self.api_url}/api/user-activity/{token}'
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    last_active = data.get('last_active', 0)
                    return (datetime.now().timestamp() - last_active) <= 600
                return False
        except Exception as e:
            logging.error(f"Error checking user activity: {e}")
            return False

    async def send_price_updates(self, user_token: str, updates: List[Dict]):
        try:
            async with self.session.post(
                f'{self.api_url}/api/product-updates',
                json={
                    'user_token': user_token,
                    'updates': [{
                        'product_url': update['product_url'],
                        'current_price': update['current_price']
                    } for update in updates]
                }
            ) as response:
                if response.status != 200:
                    logging.error(f"Failed to send price updates for user {user_token}")
        except Exception as e:
            logging.error(f"Error sending price updates: {e}")

    async def _get_marketplace_price(self, url: str) -> Optional[float]:
        page = None
        try:
            page = await self.context.new_page()
            await page.route("**/*", lambda route: route.continue_())
            
            await page.goto(url, wait_until='domcontentloaded', timeout=15000)
            marketplace = 'ozon' if 'ozon.ru' in url else 'yandex_market'
            selectors = await self.get_selectors(marketplace)
            
            if not selectors:
                return None

            for selector_set in selectors:
                try:
                    price_selector = selector_set.get('price')
                    if not price_selector:
                        continue

                    if marketplace == 'ozon':
                        try:
                            refresh_button = await page.wait_for_selector('button:has-text("Обновить")', timeout=3000)
                            if refresh_button:
                                await refresh_button.click()
                                await page.wait_for_load_state('networkidle', timeout=5000)
                        except:
                            pass
                    elif marketplace == 'yandex_market':
                        try:
                            captcha = await page.wait_for_selector('#js-button', timeout=3000)
                            if captcha:
                                await captcha.click()
                                await asyncio.sleep(2)
                                await page.wait_for_load_state('networkidle')
                        except:
                            pass

                    content = await page.content()
                    soup = BeautifulSoup(content, 'html.parser')
                    
                    if element := soup.select_one(price_selector):
                        if price := self._extract_price(element.text):
                            await self.save_price_history(url, price)
                            logging.info(f"Found price {price} for {url}")
                            return price
                except Exception as e:
                    logging.error(f"Error with selector {selector_set}: {e}")
                    continue

            return None
            
        except Exception as e:
            logging.error(f"Error processing {url}: {e}")
            return None
        finally:
            if page:
                await page.close()

    async def _get_wb_prices(self, urls: List[str]) -> Dict[str, Optional[float]]:
        results = {}
        product_ids = []
        url_map = {}

        for url in urls:
            if match := re.search(r'/catalog/(\d+)/', url):
                product_id = match.group(1)
                product_ids.append(product_id)
                url_map[product_id] = url

        if not product_ids:
            return {}

        try:
            api_url = f'https://card.wb.ru/cards/detail?curr=rub&dest=-1257786&nm={";".join(product_ids)}'
            
            async with self.session.get(api_url) as response:
                if response.status == 200:
                    data = await response.json()
                    products = data.get('data', {}).get('products', [])
                    
                    for product in products:
                        product_id = str(product.get('id'))
                        if product_id in url_map:
                            url = url_map[product_id]
                            price = product.get('salePriceU', 0) / 100
                            if price > 0:
                                await self.save_price_history(url, price)
                                results[url] = price
                                logging.info(f"Got WB price {price} for {url}")
                            else:
                                results[url] = None
                else:
                    for url in url_map.values():
                        results[url] = None
                    
        except Exception as e:
            logging.error(f"Error fetching WB prices: {e}")
            for url in url_map.values():
                results[url] = None

        return results

    async def get_prices_batch(self, urls: List[str]) -> Dict[str, Optional[float]]:
        if not urls:
            return {}

        wb_urls = []
        other_urls = []
        
        for url in urls:
            if 'wildberries.ru' in url:
                wb_urls.append(url)
            else:
                other_urls.append(url)

        results = {}
        
        if wb_urls:
            logging.info(f"Processing {len(wb_urls)} Wildberries URLs")
            wb_results = await self._get_wb_prices(wb_urls)
            results.update(wb_results)

        if other_urls:
            logging.info(f"Processing {len(other_urls)} marketplace URLs")
            semaphore = asyncio.Semaphore(5)
            
            async def process_url(url: str):
                async with semaphore:
                    price = await self._get_marketplace_price(url)
                    return url, price

            tasks = [process_url(url) for url in other_urls]
            marketplace_results = await asyncio.gather(*tasks)
            
            for url, price in marketplace_results:
                results[url] = price

        return results