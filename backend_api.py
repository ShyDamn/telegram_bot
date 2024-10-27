from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
import redis
import json

app = FastAPI()

origins = [
    "chrome-extension://gpcindghocakhfbjmnamgnnjhgjjiijk",
    "http://localhost",
    "http://127.0.0.1",
    "http://localhost:8000",
    "http://127.0.0.1:8000"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

class Product(BaseModel):
    title: str
    price: float
    targetPrice: float
    imageUrl: str
    productUrl: str
    marketplace: str

class SaveProductsRequest(BaseModel):
    telegram_id: int
    token: str
    products: List[Product]

@app.post("/api/save-products")
async def save_products(data: SaveProductsRequest):
    user_id = data.telegram_id
    token = data.token
    products = [product.dict() for product in data.products]

    stored_token = redis_client.hget(f"user:{user_id}", "token")
    if stored_token != token:
        raise HTTPException(status_code=403, detail="Invalid token")

    # Сохраняем продукты в Redis
    products_key = f"products:{user_id}"
    redis_client.delete(products_key)
    for product in products:
        redis_client.rpush(products_key, json.dumps(product))

    print(f"Получены и сохранены продукты для пользователя {user_id}: {products}")

    return {"status": "success"}

@app.get("/api/get-products")
async def get_products(telegram_id: int, token: str):
    stored_token = redis_client.hget(f"user:{telegram_id}", "token")
    if stored_token != token:
        raise HTTPException(status_code=403, detail="Invalid token")

    # Получаем продукты
    products_key = f"products:{telegram_id}"
    products = redis_client.lrange(products_key, 0, -1)
    products = [json.loads(p) for p in products]

    print(f"Отправляем продукты для пользователя {telegram_id}: {products}")

    return {"products": products}
