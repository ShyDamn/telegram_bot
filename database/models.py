from dataclasses import dataclass
from typing import List, Optional

@dataclass
class Product:
    title: str
    current_price: float
    target_price: float
    image_url: Optional[str] = None
    product_url: str = ""

@dataclass
class User:
    telegram_id: int
    token: str
    is_active: bool
    products: List[Product]
