import aiohttp
from database.redis_client import RedisClient
import json

class SessionManager:
    def __init__(self, redis_client: RedisClient, session_api_url: str):
        self.redis_client = redis_client
        self.session_api_url = session_api_url

    async def fetch_user_data_from_backend(self, user_id: int, token: str) -> dict:
        # Получение списка товаров из бэкенд-сервера
        session_api_url = f"{self.session_api_url}/api/get-products?telegram_id={user_id}&token={token}"
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(session_api_url) as response:
                    if response.status == 200:
                        data = await response.json()
                        print(f"Получены данные с бэкенда для пользователя {user_id}: {data}")
                        return data
                    else:
                        print(f"Ошибка при получении данных: {response.status}")
                        return {}
            except Exception as e:
                print(f"Не удалось подключиться к бэкенд-серверу: {e}")
                return {}

    async def update_user_products(self, user_id: int, token: str):
        # Обновление списка товаров пользователя из бэкенд-сервера
        session_data = await self.fetch_user_data_from_backend(user_id, token)
        if 'products' in session_data:
            self.redis_client.save_products(user_id, [json.dumps(p) for p in session_data['products']])
        else:
            print("Нет данных о продуктах или бэкенд-сервер недоступен.")
