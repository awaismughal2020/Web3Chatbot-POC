import asyncio
import json
import time
from typing import Optional, Any, Dict
import redis.asyncio as redis
from config import settings


class CacheManager:
    def __init__(self):
        self.redis: Optional[redis.Redis] = None
        self.stats = {
            'hits': 0,
            'misses': 0,
            'sets': 0,
            'errors': 0
        }

    async def connect(self):
        """Connect to Redis"""
        try:
            self.redis = redis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                password=settings.REDIS_PASSWORD,
                db=settings.REDIS_DB,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True,
                health_check_interval=30
            )

            # Test connection
            await self.redis.ping()
            print(f"✅ Connected to Redis at {settings.REDIS_HOST}:{settings.REDIS_PORT}")

        except Exception as e:
            print(f"❌ Failed to connect to Redis: {e}")
            print("🔄 Running without cache (in-memory fallback)")
            self.redis = None

    async def disconnect(self):
        """Disconnect from Redis"""
        if self.redis:
            await self.redis.close()
            print("✅ Disconnected from Redis")

    async def get(self, key: str) -> Optional[str]:
        """Get value from cache"""
        try:
            if not self.redis:
                return None

            value = await self.redis.get(key)

            if value is not None:
                self.stats['hits'] += 1
                return value
            else:
                self.stats['misses'] += 1
                return None

        except Exception as e:
            self.stats['errors'] += 1
            print(f"Cache GET error for key {key}: {e}")
            return None

    async def set(self, key: str, value: str, expire: int = 3600) -> bool:
        """Set value in cache with expiration"""
        try:
            if not self.redis:
                return False

            await self.redis.setex(key, expire, value)
            self.stats['sets'] += 1
            return True

        except Exception as e:
            self.stats['errors'] += 1
            print(f"Cache SET error for key {key}: {e}")
            return False

    async def delete(self, key: str) -> bool:
        """Delete key from cache"""
        try:
            if not self.redis:
                return False

            result = await self.redis.delete(key)
            return result > 0

        except Exception as e:
            self.stats['errors'] += 1
            print(f"Cache DELETE error for key {key}: {e}")
            return False

    async def exists(self, key: str) -> bool:
        """Check if key exists in cache"""
        try:
            if not self.redis:
                return False

            result = await self.redis.exists(key)
            return result > 0

        except Exception as e:
            self.stats['errors'] += 1
            print(f"Cache EXISTS error for key {key}: {e}")
            return False

    async def increment(self, key: str, amount: int = 1, expire: int = 3600) -> Optional[int]:
        """Increment a counter in cache"""
        try:
            if not self.redis:
                return None

            # Use pipeline for atomic operations
            pipe = self.redis.pipeline()
            pipe.incr(key, amount)
            pipe.expire(key, expire)
            results = await pipe.execute()

            return results[0]

        except Exception as e:
            self.stats['errors'] += 1
            print(f"Cache INCREMENT error for key {key}: {e}")
            return None

    async def get_json(self, key: str) -> Optional[Dict]:
        """Get JSON value from cache"""
        try:
            value = await self.get(key)
            if value:
                return json.loads(value)
            return None

        except json.JSONDecodeError as e:
            print(f"JSON decode error for key {key}: {e}")
            return None
        except Exception as e:
            print(f"Cache GET_JSON error for key {key}: {e}")
            return None

    async def set_json(self, key: str, value: Dict, expire: int = 3600) -> bool:
        """Set JSON value in cache"""
        try:
            json_value = json.dumps(value)
            return await self.set(key, json_value, expire)

        except json.JSONEncodeError as e:
            print(f"JSON encode error for key {key}: {e}")
            return False
        except Exception as e:
            print(f"Cache SET_JSON error for key {key}: {e}")
            return False

    async def get_or_set(self, key: str, fetch_function, expire: int = 3600) -> Optional[str]:
        """Get from cache or fetch and set if not exists"""
        try:
            # Try to get from cache first
            value = await self.get(key)
            if value is not None:
                return value

            # Fetch the value
            if asyncio.iscoroutinefunction(fetch_function):
                fresh_value = await fetch_function()
            else:
                fresh_value = fetch_function()

            if fresh_value is not None:
                # Set in cache for future use
                await self.set(key, fresh_value, expire)
                return fresh_value

            return None

        except Exception as e:
            print(f"Cache GET_OR_SET error for key {key}: {e}")
            return None

    async def clear_pattern(self, pattern: str) -> int:
        """Clear all keys matching a pattern"""
        try:
            if not self.redis:
                return 0

            keys = await self.redis.keys(pattern)
            if keys:
                return await self.redis.delete(*keys)
            return 0

        except Exception as e:
            self.stats['errors'] += 1
            print(f"Cache CLEAR_PATTERN error for pattern {pattern}: {e}")
            return 0

    async def get_stats(self) -> Dict:
        """Get cache statistics"""
        total_operations = self.stats['hits'] + self.stats['misses']
        hit_rate = (self.stats['hits'] / total_operations * 100) if total_operations > 0 else 0

        cache_info = {
            'connected': self.redis is not None,
            'hit_rate_percent': round(hit_rate, 2),
            'total_hits': self.stats['hits'],
            'total_misses': self.stats['misses'],
            'total_sets': self.stats['sets'],
            'total_errors': self.stats['errors']
        }

        if self.redis:
            try:
                info = await self.redis.info()
                cache_info.update({
                    'redis_memory_used': info.get('used_memory_human', 'Unknown'),
                    'redis_connected_clients': info.get('connected_clients', 0),
                    'redis_uptime_seconds': info.get('uptime_in_seconds', 0)
                })
            except Exception as e:
                cache_info['redis_info_error'] = str(e)

        return cache_info

    async def health_check(self) -> bool:
        """Check if Redis is healthy"""
        try:
            if not self.redis:
                return False

            # Test with a simple ping
            response = await self.redis.ping()
            return response is True

        except Exception as e:
            print(f"Redis health check failed: {e}")
            return False

    def reset_stats(self):
        """Reset cache statistics"""
        self.stats = {
            'hits': 0,
            'misses': 0,
            'sets': 0,
            'errors': 0
        }
