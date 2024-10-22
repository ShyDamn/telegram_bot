import redis
import json

class RedisClient:
    def __init__(self, host='localhost', port=6379, db=0):
        self.client = redis.Redis(host=host, port=port, db=db, decode_responses=True)

    def save_user(self, user_id: int, token: str):
        self.client.hset(f"user:{user_id}", "token", token)
        self.client.hset(f"user:{user_id}", "is_active", "1")

    def get_user_token(self, user_id: int) -> str:
        return self.client.hget(f"user:{user_id}", "token")

    def delete_user(self, user_id: int):
        self.client.delete(f"user:{user_id}")
        self.client.delete(f"products:{user_id}")

    def save_products(self, user_id: int, products: list):
        self.client.delete(f"products:{user_id}")
        for product in products:
            self.client.rpush(f"products:{user_id}", json.dumps(product))

    def get_products(self, user_id: int) -> list:
        products_data = self.client.lrange(f"products:{user_id}", 0, -1)
        if products_data:
            return [json.loads(p) for p in products_data]
        return []

    def get_user(self, user_id: int) -> dict:
        return self.client.hgetall(f"user:{user_id}")

    def get_all_users(self) -> list:
        user_ids = []
        cursor = '0'
        while True:
            cursor, keys = self.client.scan(cursor=cursor, match='user:*', count=100)
            for key in keys:
                user_id = key.split(':')[1]
                user_ids.append(int(user_id))
            if cursor == '0':
                break
        return user_ids
