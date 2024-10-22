from typing import Optional
import aiohttp
from bs4 import BeautifulSoup
import re

class PriceParser:
    async def get_price(self, url: str) -> Optional[float]:
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url) as response:
                    if response.status == 200:
                        html = await response.text()
                        return await self._parse_price(url, html)
            except Exception as e:
                print(f"Error fetching price: {e}")
                return None

    async def _parse_price(self, url: str, html: str) -> Optional[float]:
        soup = BeautifulSoup(html, 'html.parser')

        if 'ozon.ru' in url:
            price_elem = soup.select_one('span.s3m_27')
        elif 'wildberries.ru' in url:
            price_elem = soup.select_one('.price-block__final-price')
        elif 'market.yandex.ru' in url:
            price_elem = soup.select_one('div[data-tid="c3eaad93"]')
        else:
            return None

        if price_elem:
            price_text = price_elem.text
            price = float(re.sub(r'[^\d.]', '', price_text.replace(',', '.')))
            return price
        return None
