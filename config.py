"""
Ultra-simple configuration for Web3 Fast Chatbot
Use this if you're still having dataclass issues
"""
import os
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")
GROQ_MAX_TOKENS = int(os.getenv("GROQ_MAX_TOKENS", "1000"))
GROQ_TEMPERATURE = float(os.getenv("GROQ_TEMPERATURE", "0.7"))

COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY")
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD")
REDIS_DB = int(os.getenv("REDIS_DB", "0"))
REDIS_URL = os.getenv("REDIS_URL")

CACHE_PRICE_TTL = int(os.getenv("CACHE_PRICE_TTL", "30"))
CACHE_CHAT_TTL = int(os.getenv("CACHE_CHAT_TTL", "3600"))
CACHE_CONTEXT_TTL = int(os.getenv("CACHE_CONTEXT_TTL", "3600"))

APP_HOST = os.getenv("APP_HOST", "0.0.0.0")
APP_PORT = int(os.getenv("APP_PORT", "8000"))
APP_DEBUG = False
APP_RELOAD = False

MAX_CONCURRENT_REQUESTS = 100
REQUEST_TIMEOUT = 30
RESPONSE_STREAM_DELAY = 0.03

CORS_ORIGINS = ["*"]
API_KEY = os.getenv("API_KEY")
LOG_LEVEL = "INFO"
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
RATE_LIMIT_REQUESTS = 60
RATE_LIMIT_WINDOW = 60


class Settings:
    def __init__(self):
        for name in globals():
            if name.isupper():
                setattr(self, name, globals()[name])

    def validate(self):
        return bool(self.GROQ_API_KEY)

    def get_redis_config(self):
        if self.REDIS_URL:
            return {"from_url": self.REDIS_URL}
        return {
            "host": self.REDIS_HOST,
            "port": self.REDIS_PORT,
            "db": self.REDIS_DB,
            "decode_responses": True,
            "password": self.REDIS_PASSWORD
        }


settings = Settings()
