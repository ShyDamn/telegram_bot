import random
import logging
import re
import asyncio
import sys
from typing import Optional, Dict, List
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
import aiohttp
from selenium.webdriver.chrome.webdriver import WebDriver
from contextlib import asynccontextmanager

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('./logs/parser.log', encoding='UTF-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

class PriceParser:
    def __init__(self, max_concurrent_browsers: int = 5):
        """
        Инициализация парсера с ограничением количества одновременных браузеров
        
        :param max_concurrent_browsers: Максимальное количество одновременно открытых браузеров
        """
        self.max_concurrent_browsers = max_concurrent_browsers
        self.browser_semaphore = asyncio.Semaphore(max_concurrent_browsers)
        
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.77 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/12.1.1 Safari/605.1.15',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/67.0.3396.87 Safari/537.36'
        ]
        
        self.chrome_options = Options()
        self.chrome_options.add_argument("--headless")
        self.chrome_options.add_argument("--no-sandbox")
        self.chrome_options.add_argument("--disable-dev-shm-usage")
        self.chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        self.chrome_options.add_argument("--disable-gpu")
        self.chrome_options.add_argument('--enable-logging')
        self.chrome_options.add_argument('--log-level=3')
        self.chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        self.chrome_options.add_experimental_option('useAutomationExtension', False)

        self.driver_path = "./chromedriver.exe"
        
        # Пул соединений aiohttp для Wildberries API
        self.session: Optional[aiohttp.ClientSession] = None
        
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

    async def __aenter__(self):
        """Инициализация aiohttp сессии при входе в контекстный менеджер"""
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Закрытие aiohttp сессии при выходе из контекстного менеджера"""
        if self.session:
            await self.session.close()
            self.session = None

    @asynccontextmanager
    async def get_driver(self):
        """Контекстный менеджер для работы с браузером"""
        async with self.browser_semaphore:  # Ограничиваем количество одновременных браузеров
            service = Service(self.driver_path)
            driver = webdriver.Chrome(service=service, options=self.chrome_options)
            try:
                driver.set_window_size(1920, 1080)
                driver.execute_script(
                    "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
                yield driver
            finally:
                driver.quit()

    async def get_prices_batch(self, urls: List[str]) -> Dict[str, Optional[float]]:
        """
        Получение цен для списка URL-адресов параллельно
        
        :param urls: Список URL-адресов товаров
        :return: Словарь с ценами, где ключ - URL, значение - цена или None
        """
        async with self:  # Инициализируем aiohttp сессию
            tasks = [self.get_price(url) for url in urls]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            return {url: price if not isinstance(price, Exception) else None 
                   for url, price in zip(urls, results)}

    async def get_price(self, url: str) -> Optional[float]:
        """
        Получение цены товара в зависимости от магазина
        
        :param url: URL товара
        :return: Цена товара или None в случае ошибки
        """
        try:
            if 'wildberries.ru' in url:
                return await self._get_price_from_wildberries(url)
            else:
                return await self._get_price_with_selenium(url)
        except Exception as e:
            logging.error(f"Ошибка при получении цены для {url}: {e}")
            return None

    async def _get_price_with_selenium(self, url: str) -> Optional[float]:
        """Получение цены с использованием Selenium"""
        async with self.get_driver() as driver:
            try:
                driver.execute_cdp_cmd('Network.setUserAgentOverride',
                                     {"userAgent": random.choice(self.user_agents)})
                driver.get(url)
                await asyncio.sleep(random.uniform(2, 4))

                if 'market.yandex.ru' in url:
                    await self._handle_challenge(driver, 'market')
                elif 'ozon.ru' in url:
                    await self._handle_challenge(driver, 'ozon')

                return await self._find_price(driver, url)

            except WebDriverException as e:
                logging.error(f"Ошибка WebDriver для URL {url}: {e}")
                return None

    async def _find_price(self, driver: WebDriver, url: str) -> Optional[float]:
        """Поиск цены на странице по селекторам"""
        marketplace = 'ozon' if 'ozon.ru' in url else 'market.yandex'
        selectors = self.selectors[marketplace]
        wait = WebDriverWait(driver, 3)

        for selector in selectors['css']:
            try:
                price_element = wait.until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
                price = self._extract_price(price_element.text)
                if price is not None:
                    return price
            except (TimeoutException, NoSuchElementException):
                continue

        logging.error(f"Цена не найдена для {url}")
        driver.save_screenshot(f"./logs/debug_{marketplace}_screenshot.png")
        return None

    async def _handle_challenge(self, driver: WebDriver, site: str):
        """Обработка антибот-защиты"""
        if site == 'ozon':
            try:
                wait = WebDriverWait(driver, 3)
                refresh_button = wait.until(EC.element_to_be_clickable(
                    (By.XPATH, "//button[contains(text(),'Обновить')]")))
                await asyncio.sleep(3)
                refresh_button.click()
                await asyncio.sleep(2)
            except TimeoutException:
                logging.info("Антибот-защита не обнаружена")
        elif site == 'market':
            try:
                wait = WebDriverWait(driver, 2)
                captcha_checkbox = wait.until(
                    EC.element_to_be_clickable((By.ID, "js-button")))
                captcha_checkbox.click()
                await asyncio.sleep(3)
            except TimeoutException:
                logging.error("Не удалось пройти капчу на Яндекс.Маркете")
                driver.save_screenshot("./logs/yandex_captcha_error.png")

    def _extract_price(self, price_text: str) -> Optional[float]:
        """Извлечение числового значения цены из текста"""
        try:
            price_text = price_text.replace('\xa0', '').replace(' ', '').replace(
                ' ', '').replace('₽', '').replace(',', '.').strip()
            return float(re.sub(r'[^0-9.]', '', price_text))
        except (ValueError, AttributeError):
            logging.error(f"Ошибка извлечения цены из текста: {price_text}")
            return None

    async def _get_price_from_wildberries(self, url: str) -> Optional[float]:
        """Получение цены с Wildberries через API"""
        product_id = self._extract_wildberries_product_id(url)
        if not product_id:
            logging.error(f"Не удалось извлечь ID товара из URL: {url}")
            return None

        api_url = f'https://card.wb.ru/cards/detail?dest=-1257786&nm={product_id}'
        headers = {'User-Agent': random.choice(self.user_agents)}

        if not self.session:
            self.session = aiohttp.ClientSession()

        try:
            async with self.session.get(api_url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    try:
                        price = data['data']['products'][0].get('salePriceU', 0) / 100
                        return price
                    except (KeyError, IndexError):
                        logging.error("Ошибка при парсинге данных Wildberries API")
                else:
                    logging.error(f"Ошибка Wildberries API, код: {response.status}")
        except Exception as e:
            logging.error(f"Ошибка при запросе к Wildberries API: {e}")
        
        return None

    def _extract_wildberries_product_id(self, url: str) -> Optional[str]:
        """Извлечение ID товара из URL Wildberries"""
        match = re.search(r'/catalog/(\d+)/', url)
        return match.group(1) if match else None