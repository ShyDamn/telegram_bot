import logging
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict
import redis
import json
from datetime import datetime, timedelta

app = FastAPI()

origins = [
    "chrome-extension://gpcindghocakhfbjmnamgnnjhgjjiijk",
    "http://localhost",
    "http://127.0.0.1",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "https://www.ozon.ru",
    "https://www.wildberries.ru",
    "https://market.yandex.ru"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"]
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

class SelectorsRequest(BaseModel):
    marketplace: str
    selectors: Dict[str, str]

@app.post("/api/selectors")
async def save_selectors(data: SelectorsRequest):
    try:
        marketplace = data.marketplace
        selectors = data.selectors
        required_selectors = {'title', 'price', 'image'}
        
        if not all(key in selectors for key in required_selectors):
            raise HTTPException(
                status_code=400, 
                detail=f"Missing required selectors. Required: {required_selectors}"
            )
        
        if not all(selectors.values()):
            raise HTTPException(
                status_code=400, 
                detail="All selectors must have non-empty values"
            )
        
        selector_data = {
            "selectors": selectors,
            "timestamp": {
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }
        }
        
        key = f"selectors:{marketplace}"
        redis_client.set(key, json.dumps(selector_data))
        
        history_key = f"selectors_history:{marketplace}"
        redis_client.rpush(history_key, json.dumps({
            "selectors": selectors,
            "timestamp": datetime.now().isoformat()
        }))
        
        redis_client.ltrim(history_key, -5, -1)
        
        return {
            "status": "success",
            "message": f"Selectors saved for {marketplace}",
            "data": selectors
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/selectors/{marketplace}")
async def get_selectors(marketplace: str):
    try:
        history_key = f"selectors_history:{marketplace}"
        stored_data = redis_client.lrange(history_key, 0, -1)
        
        if not stored_data:
            raise HTTPException(
                status_code=404, 
                detail=f"No selectors found for {marketplace}"
            )
            
        selectors_history = [json.loads(item) for item in stored_data]
        
        return {
            "marketplace": marketplace,
            "selectors_history": selectors_history
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/save-products")
async def save_products(data: SaveProductsRequest):
    try:
        user_id = data.telegram_id
        token = data.token
        products = [product.dict() for product in data.products]

        stored_token = redis_client.hget(f"user:{user_id}", "token")
        if stored_token != token:
            raise HTTPException(status_code=403, detail="Invalid token")

        products_key = f"products:{user_id}"
        old_products = redis_client.lrange(products_key, 0, -1)
        
        if old_products:
            history_key = f"products_history:{user_id}"
            redis_client.rpush(history_key, json.dumps({
                "products": [json.loads(p) for p in old_products],
                "timestamp": datetime.now().isoformat()
            }))
            redis_client.ltrim(history_key, -50, -1)

        redis_client.delete(products_key)
        for product in products:
            redis_client.rpush(products_key, json.dumps(product))

        return {
            "status": "success",
            "message": f"Saved {len(products)} products",
            "user_id": user_id
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/get-products")
async def get_products(telegram_id: int, token: str):
    try:
        stored_token = redis_client.hget(f"user:{telegram_id}", "token")
        if stored_token != token:
            raise HTTPException(status_code=403, detail="Invalid token")

        products_key = f"products:{telegram_id}"
        products = redis_client.lrange(products_key, 0, -1)
        products = [json.loads(p) for p in products]

        return {
            "products": products,
            "user_id": telegram_id,
            "count": len(products)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/price-history")
async def save_price_history(data: dict):
    try:
        product_url = data.get('product_url')
        price = data.get('price')
        timestamp = data.get('timestamp')

        if not all([product_url, price, timestamp]):
            raise HTTPException(status_code=400, detail="Missing required fields")

        history_key = f"price_history:{product_url}"
        
        history_data = {
            'price': price,
            'timestamp': timestamp
        }
        
        redis_client.rpush(history_key, json.dumps(history_data))
        
        month_ago = int((datetime.now() - timedelta(days=30)).timestamp())
        
        all_history = redis_client.lrange(history_key, 0, -1)
        filtered_history = [
            item for item in all_history 
            if json.loads(item)['timestamp'] >= month_ago
        ]
        
        redis_client.delete(history_key)
        for item in filtered_history:
            redis_client.rpush(history_key, item)

        return {"status": "success", "message": "Price history saved"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/user-activity/{token}")
async def get_user_activity(token: str):
    try:
        activity_key = f"user_activity:{token}"
        last_active = redis_client.get(activity_key)
        
        if not last_active:
            return {"last_active": 0}
            
        return {"last_active": int(last_active)}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/user-activity")
async def update_user_activity(data: dict):
    try:
        token = data.get('token')
        timestamp = data.get('time')

        if not all([token, timestamp]):
            raise HTTPException(status_code=400, detail="Missing required fields")

        activity_key = f"user_activity:{token}"
        redis_client.setex(activity_key, 700, timestamp)

        return {"status": "success", "message": "Activity updated"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/product-updates")
async def save_product_updates(data: dict):
    try:
        user_token = data.get('user_token')
        updates = data.get('updates')
        logging.info(f"Received updates for token {user_token}: {updates}")
        if not all([user_token, updates]):
            raise HTTPException(status_code=400, detail="Missing required fields")

        updates_key = f"product_updates:{user_token}"
        redis_client.setex(updates_key, 600, json.dumps(updates))
        logging.info(f"Successfully saved updates to Redis with key {updates_key}")
        return {"status": "success", "message": "Updates saved"}
    except Exception as e:
        logging.error(f"Error saving product updates: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/product-updates/{token}")
async def get_product_updates(token: str):
    try:
        updates_key = f"product_updates:{token}"
        updates_data = redis_client.get(updates_key)

        if not updates_data:
            return {"updates": []}

        updates = json.loads(updates_data)
        redis_client.delete(updates_key)

        return {"updates": updates}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/price-history/{product_url}")
async def get_price_history(product_url: str):
    try:
        history_key = f"price_history:{product_url}"
        history_data = redis_client.lrange(history_key, 0, -1)

        if not history_data:
            return {"history": []}

        history = [json.loads(item) for item in history_data]
        month_ago = int((datetime.now() - timedelta(days=30)).timestamp())
        filtered_history = [
            item for item in history 
            if item['timestamp'] >= month_ago
        ]

        return {"history": filtered_history}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))