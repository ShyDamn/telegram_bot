import random
import logging
import re
import asyncio
import sys
from typing import Optional, List, Dict
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
import aiohttp
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager

@dataclass
class ParseResult:
    url: str
    price: Optional[float]
    error: Optional[str] = None

class DriverPool:
    def __init__(self, pool_size: int = 5):
        self.pool_size = pool_size
        self.drivers: List[webdriver.Chrome] = []
        self.available_drivers = asyncio.Queue()
        self.setup_complete = False
        
    async def setup(self):
        if self.setup_complete:
            return
            
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument('--enable-logging')
        chrome_options.add_argument('--log-level=3')
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)

        with ThreadPoolExecutor(max_workers=self.pool_size) as executor:
            futures = []
            for _ in range(self.pool_size):
                futures.append(executor.submit(self._create_driver, chrome_options))
            
            for future in futures:
                driver = future.result()
                await self.available_drivers.put(driver)
                self.drivers.append(driver)
        
        self.setup_complete = True

    def _create_driver(self, options):
        service = Service("./chromedriver.exe")
        driver = webdriver.Chrome(service=service, options=options)
        driver.set_window_size(1920, 1080)
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        return driver

    @asynccontextmanager
    async def get_driver(self):
        driver = await self.available_drivers.get()
        try:
            yield driver
        finally:
            await self.available_drivers.put(driver)

    async def cleanup(self):
        for driver in self.drivers:
            driver.quit()
        self.drivers.clear()
        self.setup_complete = False

class PriceParser:
    def __init__(self, concurrent_workers: int = 5):
        self.driver_pool = DriverPool(pool_size=concurrent_workers)
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.77 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/12.1.1 Safari/605.1.15',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/67.0.3396.87 Safari/537.36'
        ]
        self.selectors = {
            'ozon': {
                'css': [
                    "div.m3s_27.sm2_27 span.s5m_27.ms4_27",
                    "span[data-widget='webPrice']",
                    "span.price-number",
                    "span[data-rating-name='price']",
                    "span.rq4 span"
                ]
            },
            'market.yandex': {
                'css': [
                    "h3[data-auto='snippet-price-current']"
                ]
            }
        }
        self.wb_session: Optional[aiohttp.ClientSession] = None
        
    async def setup(self):
        await self.driver_pool.setup()
        self.wb_session = aiohttp.ClientSession(
            headers={'User-Agent': random.choice(self.user_agents)},
            timeout=aiohttp.ClientTimeout(total=30)
        )

    async def parse_urls(self, urls: List[str]) -> List[ParseResult]:
        tasks = []
        for url in urls:
            if 'wildberries.ru' in url:
                tasks.append(self._get_price_from_wildberries(url))
            else:
                tasks.append(self._get_price_with_selenium(url))
        
        results = await asyncio.gather(*tasks)
        return results

    async def _get_price_with_selenium(self, url: str) -> ParseResult:
        async with self.driver_pool.get_driver() as driver:
            try:
                driver.execute_cdp_cmd('Network.setUserAgentOverride', 
                                    {"userAgent": random.choice(self.user_agents)})
                driver.get(url)
                await asyncio.sleep(random.uniform(1, 2))

                if 'market.yandex.ru' in url:
                    await self._handle_challenge(driver, 'market')
                elif 'ozon.ru' in url:
                    await self._handle_challenge(driver, 'ozon')

                price = await self._find_price(driver, url)
                return ParseResult(url=url, price=price)

            except WebDriverException as e:
                logging.error(f"Ошибка WebDriver для URL {url}: {e}")
                return ParseResult(url=url, price=None, error=str(e))

    async def _handle_challenge(self, driver, site: str):
        if site == 'ozon':
            try:
                wait = WebDriverWait(driver, 3)
                refresh_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(text(),'Обновить')]")))
                await asyncio.sleep(3)
                refresh_button.click()
                await asyncio.sleep(2)
            except TimeoutException:
                logging.info("Антибот-проблем не обнаружено.")
        elif site == 'market':
            try:
                wait = WebDriverWait(driver, 10)
                captcha_checkbox = wait.until(EC.element_to_be_clickable((By.ID, "js-button")))
                captcha_checkbox.click()
                await asyncio.sleep(2)
            except TimeoutException:
                logging.error("Не удалось пройти капчу на Яндекс.Маркете.")

    async def _find_price(self, driver, url: str) -> Optional[float]:
        marketplace = 'ozon' if 'ozon.ru' in url else 'market.yandex'
        selectors = self.selectors[marketplace]
        wait = WebDriverWait(driver, 10)

        for selector in selectors['css']:
            try:
                price_element = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
                price = self._extract_price(price_element.text)
                if price is not None:
                    return price
            except (TimeoutException, NoSuchElementException):
                continue
        return None

    async def _get_price_from_wildberries(self, url: str) -> ParseResult:
        product_id = self.extract_wildberries_product_id(url)
        if not product_id:
            return ParseResult(url=url, price=None, error="Invalid URL format")

        api_url = f'https://card.wb.ru/cards/detail?dest=-1257786&nm={product_id}'
        try:
            async with self.wb_session.get(api_url) as response:
                if response.status == 200:
                    data = await response.json()
                    try:
                        price = data['data']['products'][0].get('salePriceU') / 100
                        return ParseResult(url=url, price=price)
                    except (KeyError, IndexError):
                        return ParseResult(url=url, price=None, error="Failed to parse API response")
                else:
                    return ParseResult(url=url, price=None, error=f"API error: {response.status}")
        except Exception as e:
            return ParseResult(url=url, price=None, error=str(e))

    def extract_wildberries_product_id(self, url: str) -> Optional[str]:
        match = re.search(r'/catalog/(\d+)/', url)
        return match.group(1) if match else None

    async def cleanup(self):
        await self.driver_pool.cleanup()
        if self.wb_session:
            await self.wb_session.close()

    @staticmethod
    def _extract_price(price_text: str) -> Optional[float]:
        try:
            price_text = price_text.replace('\xa0', '').replace(' ', '').replace('₽', '').replace(',', '.').strip()
            return float(re.sub(r'[^0-9.]', '', price_text))
        except (ValueError, AttributeError):
            return None