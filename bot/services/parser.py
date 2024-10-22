import random
import logging
import re
import asyncio
from typing import Optional
from playwright.async_api import async_playwright
import aiohttp

class PriceParser:
    def __init__(self):
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.77 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/12.1.1 Safari/605.1.15',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/67.0.3396.87 Safari/537.36'
        ]

    async def get_price(self, url: str) -> Optional[float]:
        logging.info(f"Получение цены для URL: {url}")
        if 'ozon.ru' in url or 'market.yandex.ru' in url:
            return await self._get_price_with_playwright(url)
        
        retries = 3
        delay = 5  # Задержка между запросами в секундах
        headers = {
            'User-Agent': random.choice(self.user_agents)
        }
        
        async with aiohttp.ClientSession(headers=headers) as session:
            for attempt in range(retries):
                try:
                    async with session.get(url) as response:
                        if response.status == 200:
                            html_content = await response.text()
                            return await self._parse_price(url, html_content)
                        elif response.status == 403:
                            logging.error(f"Доступ запрещен (403) для URL: {url}")
                            await asyncio.sleep(delay)
                        elif response.status == 404:
                            logging.error(f"Страница не найдена (404): {url}")
                            return None
                        else:
                            logging.error(f"Ошибка при запросе страницы, код статуса: {response.status}")
                            await asyncio.sleep(delay)
                except Exception as e:
                    logging.error(f"Ошибка при получении цены: {e}")
                    await asyncio.sleep(delay)
            return None

    async def _get_price_with_playwright(self, url: str) -> Optional[float]:
        logging.info(f"Получение цены с использованием Playwright для URL: {url}")
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(user_agent=random.choice(self.user_agents))
            page = await context.new_page()

            try:
                await page.goto(url)
                await page.wait_for_timeout(3000)  # Ждем несколько секунд, чтобы страница полностью загрузилась

                if 'ozon.ru' in url:
                    price_element = await page.query_selector("[data-test-id='product-price']")
                elif 'market.yandex.ru' in url:
                    price_element = await page.query_selector("h3[data-auto='snippet-price-current']")
                
                if price_element:
                    price_text = await price_element.inner_text()
                    price_text = price_text.replace('\xa0', '').replace(' ', '').replace(',', '.').strip()
                    price = float(re.sub(r'[^0-9.]', '', price_text))
                    return price
                else:
                    logging.error(f"Цена не найдена для URL: {url}")
                    return None
            except Exception as e:
                logging.error(f"Ошибка при использовании Playwright для URL {url}: {e}")
                return None
            finally:
                await browser.close()

    async def _parse_price(self, url: str, html_content: str) -> Optional[float]:
        if 'wildberries.ru' in url:
            product_id = self.extract_wildberries_product_id(url)
            if not product_id:
                logging.error(f"Не удалось извлечь ID товара из URL: {url}")
                return None
            price = await self.get_wildberries_price(product_id)
            return price

        else:
            logging.error(f"Неизвестный домен в URL: {url}")
            return None

    def extract_wildberries_product_id(self, url):
        match = re.search(r'/catalog/(\d+)/', url)
        if match:
            return match.group(1)
        else:
            return None

    async def get_wildberries_price(self, product_id):
        api_url = f'https://card.wb.ru/cards/detail?dest=-1257786&nm={product_id}'
        headers = {
            'User-Agent': random.choice(self.user_agents)
        }
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(api_url) as response:
                if response.status == 200:
                    data = await response.json()
                    try:
                        product_data = data['data']['products'][0]
                        price = product_data.get('salePriceU')
                        if price is not None:
                            price = price / 100
                            return price
                    except (KeyError, IndexError) as e:
                        logging.error(f"Ошибка при парсинге ответа Wildberries API: {e}")
                        return None
                else:
                    logging.error(f"Ошибка при запросе Wildberries API, код статуса: {response.status}")
                    return None
