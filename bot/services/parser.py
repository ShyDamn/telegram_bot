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
        logging.FileHandler('./logs/parser.log', encoding='UTF-8'),
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
            return await self._get_price_with_selenium(url)
        if 'wildberries.ru' in url:
            return await self._get_price_from_wildberries(url)
        return None

    async def _get_price_with_selenium(self, url: str) -> Optional[float]:
        """Получение цены с использованием Selenium для Ozon и Яндекс.Маркет"""
        driver = self.get_driver()
        
        try:
            driver.execute_cdp_cmd('Network.setUserAgentOverride', 
                                {"userAgent": random.choice(self.user_agents)})
            driver.get(url)
            await asyncio.sleep(random.uniform(2, 4))

            if 'market.yandex.ru' in url:
                await self._handle_challenge(driver, 'market')

            if 'ozon.ru' in url:
                await self._handle_challenge(driver, 'ozon')

            price = await self._find_price(driver, url)
            return price

        except WebDriverException as e:
            logging.error(f"Ошибка WebDriver при получении цены для URL {url}: {e}")
            return None
        finally:
            driver.quit()

    async def _find_price(self, driver, url: str) -> Optional[float]:
        """Универсальный метод поиска цены по селекторам"""
        marketplace = 'ozon' if 'ozon.ru' in url else 'market.yandex'
        selectors = self.selectors[marketplace]
        wait = WebDriverWait(driver, 15)

        for selector in selectors['css']:
            try:
                price_element = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
                price = self._extract_price(price_element.text)
                if price is not None:
                    return price
            except (TimeoutException, NoSuchElementException):
                continue

        driver.save_screenshot(f"./logs/debug_{marketplace}_screenshot.png")
        return None

    async def _handle_challenge(self, driver, site: str):
        """Обработка антибот страницы на Ozon или капчи на Яндекс.Маркете"""
        if site == 'ozon':
            try:
                wait = WebDriverWait(driver, 10)
                refresh_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(text(),'Обновить')]")))
                await asyncio.sleep(10)
                refresh_button.click()
                await asyncio.sleep(5)
            except TimeoutException:
                logging.info("Антибот-проблем не обнаружено.")
        elif site == 'market':
            try:
                wait = WebDriverWait(driver, 10)
                captcha_checkbox = wait.until(EC.element_to_be_clickable((By.ID, "js-button")))
                captcha_checkbox.click()
                await asyncio.sleep(5)
            except TimeoutException:
                logging.error("Не удалось пройти капчу на Яндекс.Маркете.")
                driver.save_screenshot("./logs/yandex_captcha_error.png")

    def _extract_price(self, price_text: str) -> Optional[float]:
        """Извлечение числового значения цены из текста"""
        try:
            price_text = price_text.replace('\xa0', '').replace(' ', '').replace(' ', '').replace('₽', '').replace(',', '.').strip()
            return float(re.sub(r'[^0-9.]', '', price_text))
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
        return match.group(1) if match else None

    async def get_wildberries_price(self, product_id):
        """Получение цены товара с Wildberries через API"""
        api_url = f'https://card.wb.ru/cards/detail?dest=-1257786&nm={product_id}'
        headers = {'User-Agent': random.choice(self.user_agents)}
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(api_url) as response:
                if response.status == 200:
                    data = await response.json()
                    try:
                        price = data['data']['products'][0].get('salePriceU') / 100
                        return price
                    except (KeyError, IndexError):
                        logging.error(f"Ошибка при парсинге данных Wildberries API")
                else:
                    logging.error(f"Ошибка Wildberries API, код: {response.status}")
        return None
