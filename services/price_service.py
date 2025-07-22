import asyncio
import json
import re
from typing import AsyncGenerator, Dict, List, Optional
from datetime import datetime
from utils.coingecko_client import CoinGeckoClient
from utils.cache import CacheManager
from intent_detector import IntentDetector


class PriceService:
    def __init__(self, cache_manager: CacheManager):
        self.coingecko = CoinGeckoClient()
        self.cache = cache_manager
        self.intent_detector = IntentDetector()

        # Popular cryptocurrencies with their CoinGecko IDs (CORRECTED)
        self.crypto_mapping = {
            'bitcoin': 'bitcoin',
            'btc': 'bitcoin',
            'ethereum': 'ethereum',
            'eth': 'ethereum',
            'cardano': 'cardano',
            'ada': 'cardano',
            'solana': 'solana',
            'sol': 'solana',
            'polkadot': 'polkadot',
            'dot': 'polkadot',
            'polygon': 'matic-network',  # FIXED: was 'polygon-ecosystem-token'
            'matic': 'matic-network',  # FIXED: was 'polygon-ecosystem-token'
            'chainlink': 'chainlink',
            'link': 'chainlink',
            'uniswap': 'uniswap',
            'uni': 'uniswap',
            'litecoin': 'litecoin',
            'ltc': 'litecoin',
            'ripple': 'ripple',
            'xrp': 'ripple',
            'binancecoin': 'binancecoin',
            'bnb': 'binancecoin',
            'dogecoin': 'dogecoin',
            'doge': 'dogecoin',
            'shiba-inu': 'shiba-inu',
            'shib': 'shiba-inu',
            'avalanche': 'avalanche-2',
            'avax': 'avalanche-2'
        }

    async def handle_price_query(self, message: str) -> str:
        """Handle price-related queries"""
        try:
            # Extract cryptocurrency from message
            crypto_symbol = self._extract_crypto_from_message(message)
            crypto_id = self.crypto_mapping.get(crypto_symbol.lower(), crypto_symbol.lower())

            print(f"Price query: '{message}' -> symbol: '{crypto_symbol}' -> id: '{crypto_id}'")

            # Check cache first (30-second cache for prices)
            cache_key = f"price:{crypto_id}"
            cached_price = await self.cache.get(cache_key)

            if cached_price:
                price_data = json.loads(cached_price)
                return self._format_price_response(crypto_symbol, price_data, from_cache=True)

            # Fetch fresh data from CoinGecko
            price_data = await self.coingecko.get_price(crypto_id)

            if price_data:
                # Cache the price data for 30 seconds
                await self.cache.set(cache_key, json.dumps(price_data), expire=30)
                return self._format_price_response(crypto_symbol, price_data)
            else:
                # Try alternative approaches if the first one fails
                return await self._handle_price_query_fallback(crypto_symbol, message)

        except Exception as e:
            print(f"Error in price service: {e}")
            return f"I'm having trouble fetching price information right now. Please try again or ask about a specific cryptocurrency like Bitcoin or Ethereum."

    async def _handle_price_query_fallback(self, crypto_symbol: str, original_message: str) -> str:
        """Handle fallback when primary price query fails"""

        # Try common alternative names
        alternatives = {
            'bitcoin': ['btc', 'bitcoin'],
            'ethereum': ['eth', 'ethereum'],
            'cardano': ['ada', 'cardano'],
            'solana': ['sol', 'solana'],
            'polygon': ['matic', 'matic-network'],
            'dogecoin': ['doge', 'dogecoin']
        }

        # Find alternatives for the requested crypto
        for main_name, alts in alternatives.items():
            if crypto_symbol.lower() in alts:
                for alt in alts:
                    if alt != crypto_symbol.lower():
                        try:
                            alt_id = self.crypto_mapping.get(alt, alt)
                            price_data = await self.coingecko.get_price(alt_id)
                            if price_data:
                                await self.cache.set(f"price:{alt_id}", json.dumps(price_data), expire=30)
                                return self._format_price_response(crypto_symbol, price_data)
                        except:
                            continue

        # If no alternatives work, provide helpful message
        available_cryptos = list(set([k for k in self.crypto_mapping.keys() if len(k) <= 8]))[:10]

        return f"""Sorry, I couldn't find price information for "{crypto_symbol}". 

🔍 **Try asking for:**
• Bitcoin (BTC)
• Ethereum (ETH) 
• Cardano (ADA)
• Solana (SOL)
• Dogecoin (DOGE)

📝 **Examples:**
• "What's the price of Bitcoin?"
• "Current ETH price"
• "How much is Solana worth?"

Available cryptocurrencies: {', '.join(available_cryptos[:5])}..."""

    async def stream_price_response(self, message: str) -> AsyncGenerator[str, None]:
        """Stream price response for real-time feel"""
        try:
            # Extract cryptocurrency
            crypto_symbol = self._extract_crypto_from_message(message)
            crypto_id = self.crypto_mapping.get(crypto_symbol.lower(), crypto_symbol)

            # Initial acknowledgment
            yield f"Fetching {crypto_symbol.upper()} price data..."
            await asyncio.sleep(0.1)

            # Check cache first
            cache_key = f"price:{crypto_id}"
            cached_price = await self.cache.get(cache_key)

            if cached_price:
                yield "\n\n"
                price_data = json.loads(cached_price)
                response = self._format_price_response(crypto_symbol, price_data, from_cache=True)

                # Stream the response word by word
                words = response.split()
                for i, word in enumerate(words):
                    if i == 0:
                        yield word
                    else:
                        yield f" {word}"
                    await asyncio.sleep(0.03)
                return

            # Fetch fresh data
            yield "\n\nConnecting to CoinGecko API..."
            await asyncio.sleep(0.1)

            price_data = await self.coingecko.get_price(crypto_id)

            if price_data:
                yield "\n\n"
                # Cache the data
                await self.cache.set(cache_key, json.dumps(price_data), expire=30)

                # Stream formatted response
                response = self._format_price_response(crypto_symbol, price_data)
                words = response.split()
                for i, word in enumerate(words):
                    if i == 0:
                        yield word
                    else:
                        yield f" {word}"
                    await asyncio.sleep(0.03)
            else:
                yield f"\n\nSorry, I couldn't find price information for {crypto_symbol}."

        except Exception as e:
            yield f"\n\nError fetching price data: {str(e)}"

    def _extract_crypto_from_message(self, message: str) -> str:
        """Extract cryptocurrency symbol from user message"""
        message_lower = message.lower()

        # Check for direct matches in our mapping
        for key in self.crypto_mapping.keys():
            if key in message_lower:
                return key

        # Try to extract using regex patterns
        # Pattern for common formats like "price of BTC", "BTC price", etc.
        patterns = [
            r'\bprice\s+of\s+(\w+)',
            r'\b(\w+)\s+price',
            r'\bhow\s+much\s+is\s+(\w+)',
            r'\b(\w+)\s+cost',
            r'\bcurrent\s+(\w+)',
            r'\b(\w+)\s+value'
        ]

        for pattern in patterns:
            match = re.search(pattern, message_lower)
            if match:
                potential_crypto = match.group(1)
                if potential_crypto in self.crypto_mapping:
                    return potential_crypto

        # Default to Bitcoin if no specific crypto found
        return 'bitcoin'

    def _format_price_response(self, crypto_symbol: str, price_data: Dict, from_cache: bool = False) -> str:
        """Format price data into a user-friendly response"""
        try:
            symbol = crypto_symbol.upper()
            price = price_data.get('usd', 0)
            change_24h = price_data.get('usd_24h_change', 0)
            market_cap = price_data.get('usd_market_cap', 0)
            volume = price_data.get('usd_24h_vol', 0)

            # Format price with appropriate decimal places
            if price >= 1:
                price_str = f"${price:,.2f}"
            else:
                price_str = f"${price:.6f}"

            # Format change with emoji indicator
            if change_24h > 0:
                change_emoji = "📈"
                change_str = f"+{change_24h:.2f}%"
            elif change_24h < 0:
                change_emoji = "📉"
                change_str = f"{change_24h:.2f}%"
            else:
                change_emoji = "➡️"
                change_str = "0.00%"

            response = f"💰 {symbol} Price Update\n\n"
            response += f"Current Price: {price_str}\n"
            response += f"24h Change: {change_str} {change_emoji}\n"

            if market_cap:
                response += f"Market Cap: ${market_cap:,.0f}\n"

            if volume:
                response += f"24h Volume: ${volume:,.0f}\n"

            # Add timestamp
            timestamp = datetime.now().strftime("%H:%M:%S")
            # cache_indicator = " (cached)" if from_cache else " (live)"
            #response += f"\nUpdated: {timestamp}"

            return response

        except Exception as e:
            return f"Error formatting price data for {crypto_symbol}: {str(e)}"

    async def get_multiple_prices(self, crypto_list: List[str]) -> Dict:
        """Get prices for multiple cryptocurrencies"""
        try:
            results = {}

            for crypto in crypto_list:
                crypto_id = self.crypto_mapping.get(crypto.lower(), crypto)
                cache_key = f"price:{crypto_id}"

                # Try cache first
                cached_price = await self.cache.get(cache_key)
                if cached_price:
                    results[crypto] = json.loads(cached_price)
                else:
                    # Fetch from API
                    price_data = await self.coingecko.get_price(crypto_id)
                    if price_data:
                        results[crypto] = price_data
                        await self.cache.set(cache_key, json.dumps(price_data), expire=30)

            return results

        except Exception as e:
            print(f"Error getting multiple prices: {e}")
            return {}

    async def get_trending_cryptos(self) -> str:
        """Get trending cryptocurrencies"""
        try:
            cache_key = "trending_cryptos"
            cached_trending = await self.cache.get(cache_key)

            if cached_trending:
                return cached_trending

            # This would call CoinGecko's trending endpoint
            trending_data = await self.coingecko.get_trending()

            if trending_data:
                response = "🔥 Trending Cryptocurrencies:\n\n"
                for i, coin in enumerate(trending_data[:5], 1):
                    response += f"{i}. {coin.get('name', 'Unknown')} ({coin.get('symbol', '').upper()})\n"

                # Cache for 5 minutes
                await self.cache.set(cache_key, response, expire=300)
                return response

            return "Unable to fetch trending cryptocurrencies at the moment."

        except Exception as e:
            return f"Error fetching trending data: {str(e)}"

    async def get_price_stats(self) -> Dict:
        """Get statistics about price service usage"""
        try:
            return {
                "service": "price_service",
                "status": "active",
                "cache_enabled": True,
                "supported_cryptos": len(self.crypto_mapping),
                "coingecko_client": "connected"
            }
        except Exception as e:
            return {"error": str(e)}
