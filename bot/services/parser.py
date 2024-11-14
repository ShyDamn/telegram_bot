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
    def __init__(self):
        self.session: Optional[ClientSession] = None
        self.browser: Optional[Browser] = None
        self.context = None
        self.timeout = ClientTimeout(total=30)

        # Актуальные селекторы для OZON
        self.ozon_selectors = [
            'span.sm4_27.s2m_27',
            'span.m9s_27.sm9_27.t2m_27',
            'div.sm5_27'
        ]

        # Актуальные селекторы для Яндекс.Маркет
        self.market_selectors = [
            'h3[data-auto="snippet-price-current"]',
            'span[class*="2r9lI"]',
            'div._3q55J span[data-auto="price-value"]'
        ]

    async def __aenter__(self):
        self.session = ClientSession(timeout=self.timeout)
        playwright = await async_playwright().start()
        self.browser = await playwright.chromium.launch(headless=True)
        
        self.context = await self.browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/119.0.0.0 Safari/537.36'
        )
        
        # Настройка обработчика cookies
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
            
        # Очищаем текст от всех символов кроме цифр и разделителей
        clean_text = re.sub(r'[^\d.,]', '', text.replace('\xa0', '').replace('\u2009', ''))
        
        # Ищем первое число с возможной десятичной частью
        match = re.search(r'\d+[.,]?\d*', clean_text)
        if match:
            try:
                price_str = match.group(0).replace(',', '.')
                price = float(price_str)
                return price if price > 0 else None
            except (ValueError, TypeError):
                return None
        return None

    async def _get_marketplace_price(self, url: str) -> Optional[float]:
        page = None
        try:
            page = await self.context.new_page()
            await page.route("**/*", lambda route: route.continue_())
            
            # Устанавливаем более короткие таймауты
            await page.goto(url, wait_until='domcontentloaded', timeout=15000)
            
            if 'ozon.ru' in url:
                logging.info(f"Processing OZON URL: {url}")
                # Проверяем наличие капчи
                try:
                    refresh_button = await page.wait_for_selector('button:has-text("Обновить")', timeout=3000)
                    if refresh_button:
                        await refresh_button.click()
                        await page.wait_for_load_state('networkidle', timeout=5000)
                except:
                    pass

                # Получаем HTML и ищем цену
                content = await page.content()
                soup = BeautifulSoup(content, 'html.parser')
                
                for selector in self.ozon_selectors:
                    if element := soup.select_one(selector):
                        if price := self._extract_price(element.text):
                            logging.info(f"Found OZON price {price} for {url}")
                            return price

            elif 'market.yandex.ru' in url:
                logging.info(f"Processing Yandex.Market URL: {url}")
                # Проверяем наличие капчи
                try:
                    captcha = await page.wait_for_selector('#js-button', timeout=3000)
                    if captcha:
                        await captcha.click()
                        await asyncio.sleep(2)
                        await page.wait_for_load_state('networkidle')
                except:
                    pass

                # Получаем HTML и ищем цену
                content = await page.content()
                soup = BeautifulSoup(content, 'html.parser')
                
                for selector in self.market_selectors:
                    if element := soup.select_one(selector):
                        if price := self._extract_price(element.text):
                            logging.info(f"Found Market price {price} for {url}")
                            return price

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
                            price = product.get('salePriceU', 0) / 100
                            results[url_map[product_id]] = price
                            logging.info(f"Got WB price {price} for {url_map[product_id]}")
                else:
                    logging.error(f"WB API error: {response.status}")
                    
        except Exception as e:
            logging.error(f"Error fetching WB prices: {e}")

        return results

    async def get_prices_batch(self, urls: List[str]) -> Dict[str, Optional[float]]:
        if not urls:
            return {}

        # Разделяем URLs по маркетплейсам
        wb_urls = []
        other_urls = []
        
        for url in urls:
            if 'wildberries.ru' in url:
                wb_urls.append(url)
            else:
                other_urls.append(url)

        results = {}
        
        # Обработка Wildberries
        if wb_urls:
            logging.info(f"Processing {len(wb_urls)} Wildberries URLs")
            wb_results = await self._get_wb_prices(wb_urls)
            results.update(wb_results)

        # Обработка других маркетплейсов
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
                if price is not None:
                    results[url] = price

        logging.info(f"Completed processing {len(urls)} URLs with {len(results)} successful results")
        return results