import asyncio
import aiohttp
from typing import Dict, List, Optional
from config import settings


class CoinGeckoClient:
    def __init__(self):
        self.api_key = settings.COINGECKO_API_KEY
        self.base_url = "https://api.coingecko.com/api/v3"
        self.pro_url = "https://pro-api.coingecko.com/api/v3"
        self.session = None

        # Use pro API if key is available
        self.use_pro = bool(self.api_key)
        self.current_url = self.base_url #Update in case of Production

    async def _get_session(self):
        """Get or create HTTP session"""
        if not self.session:
            timeout = aiohttp.ClientTimeout(total=10, connect=5)
            headers = {"Accept": "application/json"}

            if self.api_key:
                headers["x-cg-pro-api-key"] = self.api_key

            self.session = aiohttp.ClientSession(
                timeout=timeout,
                headers=headers
            )
        return self.session

    async def get_price(self, crypto_id: str, vs_currency: str = "usd", include_24hr_change: bool = True) -> Optional[
        Dict]:
        """Get current price for a cryptocurrency"""
        try:
            session = await self._get_session()

            # First try to validate/correct the crypto_id
            validated_id = await self._validate_crypto_id(crypto_id)
            if not validated_id:
                print(f"Could not validate crypto ID: {crypto_id}")
                return None

            params = {
                "ids": validated_id,
                "vs_currencies": vs_currency,
                "include_market_cap": "true",
                "include_24hr_vol": "true"
            }

            if include_24hr_change:
                params["include_24hr_change"] = "true"

            url = f"{self.current_url}/simple/price"
            print(f"Fetching price for {validated_id} from {url}")

            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()

                    if validated_id in data:
                        return data[validated_id]
                    else:
                        print(f"Crypto ID '{validated_id}' not found in response")
                        print(f"Available keys: {list(data.keys())}")
                        return None

                elif response.status == 429:
                    print("CoinGecko rate limit exceeded")
                    return None
                else:
                    error_text = await response.text()
                    print(f"CoinGecko API error {response.status}: {error_text}")
                    print(f"URL: {url}")
                    print(f"Params: {params}")
                    return None

        except asyncio.TimeoutError:
            print("CoinGecko API timeout")
            return None
        except Exception as e:
            print(f"CoinGecko API error: {e}")
            return None

    async def get_multiple_prices(self, crypto_ids: List[str], vs_currency: str = "usd") -> Optional[Dict]:
        """Get prices for multiple cryptocurrencies"""
        try:
            session = await self._get_session()

            # Join crypto IDs with comma
            ids_param = ",".join(crypto_ids)

            params = {
                "ids": ids_param,
                "vs_currencies": vs_currency,
                "include_market_cap": "true",
                "include_24hr_vol": "true",
                "include_24hr_change": "true"
            }

            url = f"{self.current_url}/simple/price"

            async with session.get(url, params=params) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    error_text = await response.text()
                    print(f"CoinGecko multiple prices error {response.status}: {error_text}")
                    return None

        except Exception as e:
            print(f"CoinGecko multiple prices error: {e}")
            return None

    async def get_trending(self) -> Optional[List[Dict]]:
        """Get trending cryptocurrencies"""
        try:
            session = await self._get_session()
            url = f"{self.current_url}/search/trending"

            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()

                    # Extract trending coins
                    if "coins" in data:
                        trending_coins = []
                        for coin_data in data["coins"]:
                            coin = coin_data.get("item", {})
                            trending_coins.append({
                                "id": coin.get("id"),
                                "name": coin.get("name"),
                                "symbol": coin.get("symbol"),
                                "market_cap_rank": coin.get("market_cap_rank"),
                                "thumb": coin.get("thumb")
                            })
                        return trending_coins
                    return []
                else:
                    print(f"CoinGecko trending error {response.status}")
                    return None

        except Exception as e:
            print(f"CoinGecko trending error: {e}")
            return None

    async def get_coin_info(self, crypto_id: str) -> Optional[Dict]:
        """Get detailed information about a cryptocurrency"""
        try:
            session = await self._get_session()
            url = f"{self.current_url}/coins/{crypto_id}"

            params = {
                "localization": "false",
                "tickers": "false",
                "market_data": "true",
                "community_data": "false",
                "developer_data": "false"
            }

            async with session.get(url, params=params) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    print(f"CoinGecko coin info error {response.status}")
                    return None

        except Exception as e:
            print(f"CoinGecko coin info error: {e}")
            return None

    async def get_market_data(self, crypto_id: str, days: int = 7) -> Optional[Dict]:
        """Get historical market data"""
        try:
            session = await self._get_session()
            url = f"{self.current_url}/coins/{crypto_id}/market_chart"

            params = {
                "vs_currency": "usd",
                "days": str(days),
                "interval": "hourly" if days <= 1 else "daily"
            }

            async with session.get(url, params=params) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    print(f"CoinGecko market data error {response.status}")
                    return None

        except Exception as e:
            print(f"CoinGecko market data error: {e}")
            return None

    async def search_coins(self, query: str) -> Optional[List[Dict]]:
        """Search for cryptocurrencies by name or symbol"""
        try:
            session = await self._get_session()
            url = f"{self.current_url}/search"

            params = {"query": query}

            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("coins", [])
                else:
                    print(f"CoinGecko search error {response.status}")
                    return None

        except Exception as e:
            print(f"CoinGecko search error: {e}")
            return None

    async def get_global_data(self) -> Optional[Dict]:
        """Get global cryptocurrency market data"""
        try:
            session = await self._get_session()
            url = f"{self.current_url}/global"

            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("data", {})
                else:
                    print(f"CoinGecko global data error {response.status}")
                    return None

        except Exception as e:
            print(f"CoinGecko global data error: {e}")
            return None

    async def close(self):
        """Close the HTTP session"""
        if self.session:
            await self.session.close()
            self.session = None

    async def health_check(self) -> bool:
        """Check if CoinGecko API is accessible"""
        try:
            # Test with a simple ping endpoint
            session = await self._get_session()
            url = f"{self.current_url}/ping"

            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("gecko_says") == "(V3) To the Moon!"
                return False

        except Exception as e:
            print(f"CoinGecko health check failed: {e}")
            return False

    def get_rate_limits(self) -> Dict:
        """Get rate limit information"""
        if self.use_pro:
            return {
                "requests_per_minute": 500,
                "plan": "Pro",
                "features": ["Higher rate limits", "Priority support", "Additional endpoints"]
            }
        else:
            return {
                "requests_per_minute": 30,
                "plan": "Free",
                "features": ["Basic endpoints", "Community support"],
                "note": "Consider upgrading to Pro for higher limits"
            }

    async def _validate_crypto_id(self, crypto_id: str) -> Optional[str]:
        """Validate and potentially correct a cryptocurrency ID"""
        # Common mappings that might cause 404s
        id_mappings = {
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
            'polygon': 'matic-network',  # This was wrong before
            'matic': 'matic-network',
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
            'avax': 'avalanche-2',
            'avalanche': 'avalanche-2',
            'luna': 'terra-luna',
            'ust': 'terrausd',
            'shib': 'shiba-inu',
            'shiba': 'shiba-inu',
            'doge': 'dogecoin',
            'dogecoin': 'dogecoin'
        }

        # Normalize the input
        normalized_id = crypto_id.lower().strip()

        # Return the corrected ID if we have a mapping
        return id_mappings.get(normalized_id, normalized_id)

    async def validate_crypto_id(self, crypto_id: str) -> bool:
        """Validate if a crypto ID exists"""
        try:
            result = await self.get_price(crypto_id)
            return result is not None
        except Exception:
            return False
