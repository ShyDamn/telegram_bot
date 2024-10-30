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

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('./logs/parser.log', encoding='UTF-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

class PriceParser:
    def __init__(self, max_concurrent_browsers: int = 10):
        """
        Инициализация парсера с пулом браузеров
        
        :param max_concurrent_browsers: Максимальное количество одновременно открытых браузеров
        """
        self.max_concurrent_browsers = max_concurrent_browsers
        self.browser_semaphore = asyncio.Semaphore(max_concurrent_browsers)
        self.session = None
        self.browser_pool = []
        self.available_browsers = asyncio.Queue()
        
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.77 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/12.1.1 Safari/605.1.15',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/67.0.3396.87 Safari/537.36'
        ]
        
        # Настройки браузера
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
        
        # Селекторы для разных магазинов
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
        
        # Инициализация пула браузеров
        self._initialize_browser_pool()

    def _initialize_browser_pool(self):
        """Инициализация пула браузеров"""
        logging.info(f"Инициализация пула из {self.max_concurrent_browsers} браузеров")
        for _ in range(self.max_concurrent_browsers):
            try:
                service = Service(self.driver_path)
                driver = webdriver.Chrome(service=service, options=self.chrome_options)
                driver.set_window_size(1920, 1080)
                driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
                self.browser_pool.append(driver)
                self.available_browsers.put_nowait(driver)
                logging.info(f"Браузер {_ + 1}/{self.max_concurrent_browsers} инициализирован")
            except Exception as e:
                logging.error(f"Ошибка при инициализации браузера: {e}")

    async def __aenter__(self):
        """Вход в контекстный менеджер"""
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Выход из контекстного менеджера"""
        if self.session:
            await self.session.close()
        for driver in self.browser_pool:
            try:
                driver.quit()
            except Exception as e:
                logging.error(f"Ошибка при закрытии браузера: {e}")

    async def get_browser(self):
        """Получение свободного браузера из пула"""
        return await self.available_browsers.get()

    def release_browser(self, driver):
        """Возврат браузера в пул"""
        self.available_browsers.put_nowait(driver)

    async def get_prices_batch(self, urls: List[str], timeout: int = 10) -> Dict[str, Optional[float]]:
        """
        Получение цен для списка URL-адресов параллельно
        
        :param urls: Список URL-адресов товаров
        :param timeout: Таймаут для каждого запроса
        :return: Словарь с ценами, где ключ - URL, значение - цена или None
        """
        # Группировка URL по магазинам
        wb_urls = [url for url in urls if 'wildberries.ru' in url]
        other_urls = [url for url in urls if 'wildberries.ru' not in url]
        
        results = {}
        
        # Обработка Wildberries URLs
        if wb_urls:
            wb_results = await self._get_wildberries_prices_batch(wb_urls)
            results.update(wb_results)

        # Обработка других магазинов
        if other_urls:
            other_results = await self._get_other_prices_batch(other_urls, timeout)
            results.update(other_results)

        return results

    async def _get_other_prices_batch(self, urls: List[str], timeout: int) -> Dict[str, Optional[float]]:
        """Получение цен для не-Wildberries магазинов"""
        async def process_url(url: str) -> tuple[str, Optional[float]]:
            browser = await self.get_browser()
            try:
                price = await self._get_price_with_selenium(browser, url, timeout)
                return url, price
            finally:
                self.release_browser(browser)

        tasks = [process_url(url) for url in urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        return {url: price for url, price in results if not isinstance(price, Exception)}

    async def _get_price_with_selenium(self, driver: WebDriver, url: str, timeout: int) -> Optional[float]:
        """Получение цены с использованием Selenium"""
        try:
            driver.execute_cdp_cmd('Network.setUserAgentOverride',
                                 {"userAgent": random.choice(self.user_agents)})
            driver.get(url)
            await asyncio.sleep(random.uniform(1, 2))

            if 'market.yandex.ru' in url:
                await self._handle_challenge(driver, 'market')
            elif 'ozon.ru' in url:
                await self._handle_challenge(driver, 'ozon')

            return await self._find_price(driver, url)

        except WebDriverException as e:
            logging.error(f"Ошибка WebDriver для URL {url}: {e}")
            return None
        except Exception as e:
            logging.error(f"Неожиданная ошибка при получении цены для {url}: {e}")
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
        return None

    async def _handle_challenge(self, driver: WebDriver, site: str):
        """Обработка антибот-защиты"""
        try:
            if site == 'ozon':
                wait = WebDriverWait(driver, 3)
                refresh_button = wait.until(EC.element_to_be_clickable(
                    (By.XPATH, "//button[contains(text(),'Обновить')]")))
                refresh_button.click()
                await asyncio.sleep(2)
            elif site == 'market':
                wait = WebDriverWait(driver, 2)
                captcha_checkbox = wait.until(
                    EC.element_to_be_clickable((By.ID, "js-button")))
                captcha_checkbox.click()
                await asyncio.sleep(2)
        except TimeoutException:
            logging.info(f"Антибот-защита не обнаружена для {site}")
        except Exception as e:
            logging.error(f"Ошибка при обработке антибот-защиты для {site}: {e}")

    async def _get_wildberries_prices_batch(self, urls: List[str]) -> Dict[str, Optional[float]]:
        """Получение цен с Wildberries через API для списка URLs"""
        results = {}
        product_ids = []
        url_map = {}

        # Извлечение ID товаров из URL
        for url in urls:
            product_id = self._extract_wildberries_product_id(url)
            if product_id:
                product_ids.append(product_id)
                url_map[product_id] = url

        if not product_ids:
            return {url: None for url in urls}

        # Формирование URL для batch-запроса
        api_url = f'https://card.wb.ru/cards/detail?dest=-1257786&nm={";".join(product_ids)}'
        headers = {'User-Agent': random.choice(self.user_agents)}

        if not self.session:
            self.session = aiohttp.ClientSession()

        try:
            async with self.session.get(api_url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    products = data.get('data', {}).get('products', [])
                    for product in products:
                        product_id = str(product.get('id'))
                        if product_id in url_map:
                            results[url_map[product_id]] = product.get('salePriceU', 0) / 100
                else:
                    logging.error(f"Ошибка Wildberries API, код: {response.status}")
        except Exception as e:
            logging.error(f"Ошибка при пакетном запросе к Wildberries API: {e}")

        # Добавление None для URL'ов без цен
        for url in urls:
            if url not in results:
                results[url] = None

        return results

    def _extract_price(self, price_text: str) -> Optional[float]:
        """Извлечение числового значения цены из текста"""
        try:
            price_text = price_text.replace('\xa0', '').replace(' ', '').replace(
                ' ', '').replace('₽', '').replace(',', '.').strip()
            return float(re.sub(r'[^0-9.]', '', price_text))
        except (ValueError, AttributeError):
            logging.error(f"Ошибка извлечения цены из текста: {price_text}")
            return None

    def _extract_wildberries_product_id(self, url: str) -> Optional[str]:
        """Извлечение ID товара из URL Wildberries"""
        match = re.search(r'/catalog/(\d+)/', url)
        return match.group(1) if match else None