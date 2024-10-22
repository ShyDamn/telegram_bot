import hashlib
from datetime import datetime
from urllib.parse import urlparse
import re
from typing import Optional

def to_snake_case(s):
    return re.sub(r'(?<!^)(?=[A-Z])', '_', s).lower()

def normalize_keys(data):
    if isinstance(data, list):
        return [normalize_keys(item) for item in data]
    elif isinstance(data, dict):
        return {to_snake_case(key): normalize_keys(value) for key, value in data.items()}
    else:
        return data

def generate_token(user_id: int) -> str:
    # Генерация уникального токена для пользователя
    return hashlib.md5(f"{user_id}:{datetime.now().timestamp()}".encode()).hexdigest()

def format_price(price: float) -> str:
    # Форматирование цены с разделителями тысяч и двумя десятичными знаками
    return f"{price:,.2f}".replace(',', ' ')

def validate_url(url: str) -> Optional[str]:
    # Валидация URL и проверка, принадлежит ли он поддерживаемым магазинам
    try:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return None

        supported_domains = ['ozon.ru', 'wildberries.ru', 'market.yandex.ru']
        domain = parsed.netloc.replace('www.', '')

        return url if any(domain.endswith(d) for d in supported_domains) else None
    except Exception:
        return None

def extract_product_id(url: str) -> Optional[str]:
    # Извлечение ID продукта из URL магазина
    patterns = {
        'ozon.ru': r'/product/([^/?]+)',
        'wildberries.ru': r'/catalog/(\d+)',
        'market.yandex.ru': r'/product--([^/?]+)'
    }

    for domain, pattern in patterns.items():
        if domain in url:
            match = re.search(pattern, url)
            return match.group(1) if match else None
    return None
