from typing import Optional
import aiohttp
from bs4 import BeautifulSoup
import re
import logging

class PriceParser:
    async def get_price(self, url: str) -> Optional[float]:
        logging.debug(f"Получение цены для URL: {url}")
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url) as response:
                    if response.status == 200:
                        html = await response.text()
                        return await self._parse_price(url, html)
                    else:
                        logging.error(f"Ошибка при запросе страницы, код статуса: {response.status}")
                        return None
            except Exception as e:
                logging.error(f"Ошибка при получении цены: {e}")
                return None

    async def _parse_price(self, url: str, html: str) -> Optional[float]:
        logging.debug(f"Парсинг цены из HTML для URL: {url}")
        soup = BeautifulSoup(html, 'html.parser')

        if 'ozon.ru' in url:
            price_elem = soup.select_one('span.s3m_27')
        elif 'wildberries.ru' in url:
            price_elem = soup.select_one('.price-block__final-price')
        elif 'market.yandex.ru' in url:
            price_elem = soup.select_one('div[data-tid="c3eaad93"]')
        else:
            logging.error(f"Неизвестный домен в URL: {url}")
            return None

        if price_elem:
            price_text = price_elem.text
            logging.debug(f"Найден текст цены: {price_text}")
            price = float(re.sub(r'[^\d.]', '', price_text.replace(',', '.')))
            logging.debug(f"Распознанная цена: {price}")
            return price
        else:
            logging.error(f"Элемент цены не найден для URL: {url}")
        return None
