import random
import logging
import re
import asyncio
import sys
from typing import Optional
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
import aiohttp

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('./logs/parser.log', encoding='windows-1251'),
        logging.StreamHandler(sys.stdout)
    ]
)

class PriceParser:
    def __init__(self):
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

        self.selectors = {
            'ozon': {
                'css': [
                    "div.m3s_27.sm2_27 span.s5m_27.ms4_27",
                    "span[data-widget='webPrice']",
                    "span.price-number",
                    "span[data-rating-name='price']",
                    "span.rq4 span"
                ],
                'xpath': [
                    "//span[contains(@class, 'price-number')]",
                    "//div[contains(@class, 'price')]/span[contains(text(),'₽')]",
                    "//span[contains(@class, 'rq4')]//span[contains(text(),'₽')]"
                ]
            },
            'market.yandex': {
                'css': [
                    "h3[data-auto='snippet-price-current']"
                ]
            }
        }

    def get_driver(self):
        """Создание настроенного экземпляра веб-драйвера"""
        service = Service(self.driver_path)
        driver = webdriver.Chrome(service=service, options=self.chrome_options)
        
        driver.set_window_size(1920, 1080)
        
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        return driver

    async def get_price(self, url: str) -> Optional[float]:
        """Основной метод получения цены"""
        if 'ozon.ru' in url or 'market.yandex.ru' in url:
            price = await self._get_price_with_selenium(url)
            logging.debug(f"Полученная цена через Selenium: {price} для URL: {url}")
            return price

        if 'wildberries.ru' in url:
            price = await self._get_price_from_wildberries(url)
            logging.debug(f"Полученная цена через Wildberries API: {price} для URL: {url}")
            return price

        price = await self._get_price_with_aiohttp(url)
        logging.debug(f"Полученная цена через aiohttp: {price} для URL: {url}")
        return price

    async def _get_price_with_selenium(self, url: str) -> Optional[float]:
        """Получение цены с использованием Selenium для Ozon и Яндекс.Маркет"""
        driver = self.get_driver()
        
        try:
            driver.execute_cdp_cmd('Network.setUserAgentOverride', 
                                {"userAgent": random.choice(self.user_agents)})
            
            driver.get(url)
            
            await asyncio.sleep(random.uniform(2, 4))

            # Проверяем наличие капчи на Яндекс.Маркете
            if 'market.yandex.ru' in url:
                await self._solve_yandex_captcha(driver)

            marketplace = 'ozon' if 'ozon.ru' in url else 'market.yandex'
            selectors = self.selectors[marketplace]

            # Проверяем на наличие антибот страницы на Ozon
            if 'ozon.ru' in url:
                await self._handle_ozon_antibot_challenge(driver)

            price = None
            wait = WebDriverWait(driver, 15)

            # Извлекаем цену с использованием CSS-селекторов
            for selector in selectors['css']:
                try:
                    price_element = wait.until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    price = self._extract_price(price_element.text)
                    logging.debug(f"Найдена цена с селектором {selector}: {price}")
                    if price is not None:
                        break
                except (TimeoutException, NoSuchElementException) as e:
                    logging.warning(f"Селектор {selector} не сработал: {e}")
                    continue

            if price is None:
                logging.error(f"Цена не найдена для URL: {url}")
                driver.save_screenshot(f"./logs/debug_{marketplace}_screenshot.png")
                return None

            logging.info(f"Найдена цена {price} для URL: {url}")
            return price

        except WebDriverException as e:
            logging.error(f"Ошибка WebDriver при получении цены для URL {url}: {e}")
            return None
        finally:
            driver.quit()

    async def _handle_ozon_antibot_challenge(self, driver):
        """Обработка антибот страницы на Ozon"""
        try:
            wait = WebDriverWait(driver, 10)
            refresh_button = wait.until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(text(),'Обновить')]"))
            )
            logging.info("Antibot page detected, waiting and clicking refresh...")
            await asyncio.sleep(10)  # Ждем 10 секунд перед нажатием
            refresh_button.click()  # Нажимаем на кнопку "Обновить"
            await asyncio.sleep(5)  # Ждем загрузки страницы после обновления
        except TimeoutException:
            logging.info("Antibot challenge page not detected or refresh failed.")

    async def _solve_yandex_captcha(self, driver):
        """Прохождение капчи на Яндекс.Маркете"""
        try:
            wait = WebDriverWait(driver, 10)
            captcha_checkbox = wait.until(
                EC.element_to_be_clickable((By.ID, "js-button"))
            )
            captcha_checkbox.click()
            logging.info("Капча Яндекс.Маркета пройдена.")
            await asyncio.sleep(5)  # Ждем загрузки страницы после прохождения капчи
        except TimeoutException:
            logging.error("Не удалось пройти капчу на Яндекс.Маркете.")
            driver.save_screenshot("yandex_captcha_error.png")

    def _extract_price(self, price_text: str) -> Optional[float]:
        """Извлечение числового значения цены из текста"""
        try:
            price_text = price_text.replace('\xa0', '').replace(' ', '').replace(' ', '').replace('₽', '').replace(',', '.').strip()
            price = float(re.sub(r'[^0-9.]', '', price_text))
            return price
        except (ValueError, AttributeError):
            logging.error(f"Ошибка извлечения цены из текста: {price_text}")
            return None

    async def _get_price_from_wildberries(self, url: str) -> Optional[float]:
        """Получение цены с Wildberries через API"""
        product_id = self.extract_wildberries_product_id(url)
        if not product_id:
            logging.error(f"Не удалось извлечь ID товара из URL: {url}")
            return None

        return await self.get_wildberries_price(product_id)

    def extract_wildberries_product_id(self, url):
        """Извлечение ID товара из URL Wildberries"""
        match = re.search(r'/catalog/(\d+)/', url)
        if match:
            return match.group(1)
        else:
            return None

    async def get_wildberries_price(self, product_id):
        """Получение цены товара с Wildberries через API"""
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
                            price = price / 100  # Цена в API указана в копейках
                            logging.info(f"Цена для Wildberries, ID {product_id}: {price}")
                            return price
                        else:
                            logging.error(f"Цена не найдена в данных Wildberries для товара {product_id}")
                            return None
                    except (KeyError, IndexError) as e:
                        logging.error(f"Ошибка при парсинге ответа Wildberries API: {e}")
                        return None
                else:
                    logging.error(f"Ошибка при запросе Wildberries API, код статуса: {response.status}")
                    return None

    async def _get_price_with_aiohttp(self, url: str) -> Optional[float]:
        """Получение цены с использованием aiohttp для остальных сайтов"""
        retries = 3
        delay = 5
        headers = {'User-Agent': random.choice(self.user_agents)}

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
                        else:
                            await asyncio.sleep(delay)
                except Exception as e:
                    logging.error(f"Ошибка при получении цены: {e}")
                    await asyncio.sleep(delay)
            return None

    async def _parse_price(self, url: str, html_content: str) -> Optional[float]:
        """Парсинг цены для других сайтов"""
        logging.error(f"Парсинг для сайта не поддерживается: {url}")
        return None
