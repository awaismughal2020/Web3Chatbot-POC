#!/usr/bin/env python3
"""
Web3 Fast Chatbot - Startup Script
Run this file to start the chatbot server
"""

import os
import sys
import asyncio
import uvicorn
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Add current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import settings


def check_requirements():
    """Check if all required environment variables are set"""
    missing = []

    if not settings.GROQ_API_KEY:
        missing.append("GROQ_API_KEY")

    if missing:
        print("❌ Missing required environment variables:")
        for var in missing:
            print(f"   - {var}")
        print("\n📝 Please copy .env.template to .env and fill in the values")
        print("   Or set the environment variables directly")
        return False

    print("✅ All required environment variables are set")
    return True


def print_startup_info():
    """Print startup information"""
    print("=" * 50)
    print("🚀 Web3 Fast Chatbot Starting Up")
    print("=" * 50)
    print(f"Environment: {os.getenv('ENVIRONMENT', 'development')}")
    print(f"Host: {settings.APP_HOST}")
    print(f"Port: {settings.APP_PORT}")
    print(f"Debug: {settings.APP_DEBUG}")
    print(f"Reload: {settings.APP_RELOAD}")
    print()
    print("📊 Services Configuration:")
    print(f"   Groq Model: {settings.GROQ_MODEL}")
    print(f"   CoinGecko: {'Pro' if settings.COINGECKO_API_KEY else 'Free Tier'}")
    print(f"   Redis: {settings.REDIS_HOST}:{settings.REDIS_PORT}")
    print()
    print("⚡ Cache Settings:")
    print(f"   Price TTL: {settings.CACHE_PRICE_TTL}s")
    print(f"   Chat TTL: {settings.CACHE_CHAT_TTL}s")
    print()
    print("🌐 URLs:")
    print(f"   Frontend: http://{settings.APP_HOST}:{settings.APP_PORT}")
    print(f"   Health: http://{settings.APP_HOST}:{settings.APP_PORT}/health")
    print(f"   Metrics: http://{settings.APP_HOST}:{settings.APP_PORT}/metrics")
    print("=" * 50)


async def check_services():
    """Check if external services are accessible"""
    print("🔍 Checking external services...")

    # Check Redis
    try:
        from utils.cache import CacheManager
        cache = CacheManager()
        await cache.connect()
        if await cache.health_check():
            print("   ✅ Redis: Connected")
        else:
            print("   ⚠️ Redis: Connection issues")
        await cache.disconnect()
    except Exception as e:
        print(f"   ❌ Redis: Failed to connect ({e})")

    # Check Groq
    try:
        from utils.groq_client import GroqClient
        groq = GroqClient()
        if await groq.health_check():
            print("   ✅ Groq: Connected")
        else:
            print("   ⚠️ Groq: Connection issues")
        await groq.close()
    except Exception as e:
        print(f"   ❌ Groq: Failed to connect ({e})")

    # Check CoinGecko
    try:
        from utils.coingecko_client import CoinGeckoClient
        coingecko = CoinGeckoClient()
        if await coingecko.health_check():
            print("   ✅ CoinGecko: Connected")
        else:
            print("   ⚠️ CoinGecko: Connection issues")
        await coingecko.close()
    except Exception as e:
        print(f"   ❌ CoinGecko: Failed to connect ({e})")

    print()


def create_directories():
    """Create necessary directories"""
    directories = ["logs", "static"]

    for directory in directories:
        if not os.path.exists(directory):
            os.makedirs(directory)
            print(f"📁 Created directory: {directory}")


def main():
    """Main function to start the server"""
    print("🤖 Web3 Fast Chatbot - Starting...")

    # Check requirements
    if not check_requirements():
        sys.exit(1)

    # Create directories
    create_directories()

    # Print startup info
    print_startup_info()

    # Check services (optional, don't fail if services are down)
    try:
        asyncio.run(check_services())
    except Exception as e:
        print(f"⚠️ Service check failed: {e}")
        print("Continuing with startup anyway...")

    # Start the server
    try:
        print("🚀 Starting FastAPI server...")
        print("💡 Tip: Try asking 'What is the price of Bitcoin?' for a quick test")
        print("📱 Open your browser and go to the Frontend URL above")
        print()

        uvicorn.run(
            "main:app",
            host=settings.APP_HOST,
            port=settings.APP_PORT,
            reload=settings.APP_RELOAD,
            log_level=settings.LOG_LEVEL.lower(),
            access_log=True,
            reload_dirs=["./"] if settings.APP_RELOAD else None
        )

    except KeyboardInterrupt:
        print("\n🛑 Server stopped by user")
    except Exception as e:
        print(f"❌ Server error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
