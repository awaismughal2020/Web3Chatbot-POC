"""
Configuration for Web3 Fast Chatbot with Typesense integration
"""
import os
from dotenv import load_dotenv

load_dotenv()

# Groq Configuration
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")
GROQ_MAX_TOKENS = int(os.getenv("GROQ_MAX_TOKENS", "1000"))
GROQ_TEMPERATURE = float(os.getenv("GROQ_TEMPERATURE", "0.7"))

# CoinGecko Configuration
COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY")

# Redis Configuration
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD")
REDIS_DB = int(os.getenv("REDIS_DB", "0"))
REDIS_URL = os.getenv("REDIS_URL")

# Typesense Configuration
TYPESENSE_HOST = os.getenv("TYPESENSE_HOST", "localhost")
TYPESENSE_PORT = os.getenv("TYPESENSE_PORT", "8108")
TYPESENSE_PROTOCOL = os.getenv("TYPESENSE_PROTOCOL", "http")
TYPESENSE_API_KEY = os.getenv("TYPESENSE_API_KEY", "xyz")

# Cache Configuration (seconds)
CACHE_PRICE_TTL = int(os.getenv("CACHE_PRICE_TTL", "30"))
CACHE_CHAT_TTL = int(os.getenv("CACHE_CHAT_TTL", "3600"))
CACHE_CONTEXT_TTL = int(os.getenv("CACHE_CONTEXT_TTL", "3600"))

# Application Configuration
APP_HOST = os.getenv("APP_HOST", "0.0.0.0")
APP_PORT = int(os.getenv("APP_PORT", "8000"))
APP_DEBUG = os.getenv("APP_DEBUG", "true").lower() == "true"
APP_RELOAD = os.getenv("APP_RELOAD", "true").lower() == "true"

# Performance Settings
MAX_CONCURRENT_REQUESTS = int(os.getenv("MAX_CONCURRENT_REQUESTS", "100"))
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "30"))
RESPONSE_STREAM_DELAY = float(os.getenv("RESPONSE_STREAM_DELAY", "0.03"))

# Chat History Settings
MAX_CONTEXT_MESSAGES = int(os.getenv("MAX_CONTEXT_MESSAGES", "10"))
CONVERSATION_IDLE_TIMEOUT = int(os.getenv("CONVERSATION_IDLE_TIMEOUT", "3600"))  # 1 hour

# Security
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")
API_KEY = os.getenv("API_KEY")

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FORMAT = os.getenv("LOG_FORMAT", "%(asctime)s - %(name)s - %(levelname)s - %(message)s")

# Rate Limiting
RATE_LIMIT_REQUESTS = int(os.getenv("RATE_LIMIT_REQUESTS", "60"))
RATE_LIMIT_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW", "60"))


class Settings:
    def __init__(self):
        for name in globals():
            if name.isupper():
                setattr(self, name, globals()[name])

    def validate(self):
        """Validate required settings"""
        if not self.GROQ_API_KEY:
            print("⚠️ GROQ_API_KEY is not set")
            return False

        if not self.TYPESENSE_API_KEY:
            print("⚠️ TYPESENSE_API_KEY is not set")
            return False

        return True

    def get_redis_config(self):
        """Get Redis configuration"""
        if self.REDIS_URL:
            return {"from_url": self.REDIS_URL}
        return {
            "host": self.REDIS_HOST,
            "port": self.REDIS_PORT,
            "db": self.REDIS_DB,
            "decode_responses": True,
            "password": self.REDIS_PASSWORD
        }

    def get_typesense_config(self):
        """Get Typesense configuration"""
        return {
            'nodes': [{
                'host': self.TYPESENSE_HOST,
                'port': self.TYPESENSE_PORT,
                'protocol': self.TYPESENSE_PROTOCOL
            }],
            'api_key': self.TYPESENSE_API_KEY,
            'connection_timeout_seconds': 5.0
        }


settings = Settings()
