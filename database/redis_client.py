import redis.asyncio as redis
import json
from bot.utils.helpers import normalize_keys 

class RedisClient:
    def __init__(self, host='localhost', port=6379, db=0):
        self.client = redis.Redis(host=host, port=port, db=db, decode_responses=True)

    async def save_user(self, user_id: int, token: str):
        await self.client.hset(f"user:{user_id}", mapping={"token": token, "is_active": "1"})

    async def get_user_token(self, user_id: int) -> str:
        return await self.client.hget(f"user:{user_id}", "token")

    async def delete_user(self, user_id: int):
        await self.client.delete(f"user:{user_id}")
        await self.client.delete(f"products:{user_id}")

    async def save_products(self, user_id: int, products: list):
        await self.client.delete(f"products:{user_id}")
        for product in products:
            await self.client.rpush(f"products:{user_id}", json.dumps(product))

    async def get_products(self, user_id: int) -> list:
        products_data = await self.client.lrange(f"products:{user_id}", 0, -1)
        if products_data:
            products = [json.loads(p) for p in products_data]
            # Нормализуем ключи
            products = normalize_keys(products)
            return products
        return []

    async def get_user(self, user_id: int) -> dict:
        user_data = await self.client.hgetall(f"user:{user_id}")
        if user_data:
            return user_data
        else:
            return {}

    async def get_all_users(self) -> list:
        user_ids = []
        cursor = 0
        while True:
            cursor, keys = await self.client.scan(cursor=cursor, match='user:*', count=100)
            for key in keys:
                user_id = key.split(':')[1]
                user_ids.append(int(user_id))
            if cursor == 0:
                break
        return user_ids

    async def is_already_parsed(self, user_id: int, product_url: str) -> bool:
        return await self.client.sismember(f"parsed:{user_id}", product_url)

    async def mark_as_parsed(self, user_id: int, product_url: str):
        await self.client.sadd(f"parsed:{user_id}", product_url)