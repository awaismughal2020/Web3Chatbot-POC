import re
import asyncio
from typing import Dict, List


class IntentDetector:
    def __init__(self):
        # Price-specific keywords that clearly indicate price queries
        self.price_keywords = [
            'price', 'cost', 'value', 'worth', 'rate', 'quote', 'how much',
            'current price', 'live price', 'real-time price', 'market price',
            'trading price', 'usd', 'dollar', 'euro', '$'
        ]

        # Wallet-related keywords
        self.wallet_keywords = [
            'wallet', 'balance', 'portfolio', 'holdings', 'assets',
            'transfer', 'send', 'receive', 'transaction', 'address',
            'private key', 'public key', 'metamask', 'trust wallet',
            'cold storage', 'hardware wallet', 'seed phrase'
        ]

        # General greetings and polite conversation
        self.general_chat_keywords = [
            'hello', 'hi', 'hey', 'good morning', 'good evening', 'good afternoon',
            'thanks', 'thank you', 'bye', 'goodbye', 'help', 'who are you',
            'what can you do', 'how are you'
        ]

        # Web3/Crypto specific topics and information requests
        self.web3_keywords = [
            # Core blockchain concepts
            'blockchain', 'decentralized', 'distributed ledger', 'consensus',
            'proof of stake', 'proof of work', 'mining', 'staking', 'validator',
            'node', 'network', 'protocol', 'smart contract', 'dapp', 'dapps',
            'web3', 'web3.0', 'web 3', 'web 3.0',

            # DeFi terms
            'defi', 'decentralized finance', 'yield farming', 'liquidity pool',
            'amm', 'automated market maker', 'swap', 'lending', 'borrowing',
            'flash loan', 'governance token', 'dao', 'treasury', 'vault',
            'impermanent loss', 'slippage', 'arbitrage', 'composability',

            # NFT and digital assets
            'nft', 'non-fungible token', 'non fungible token', 'marketplace',
            'opensea', 'metadata', 'erc-721', 'erc-1155', 'mint', 'minting',
            'collection', 'trait', 'rarity', 'floor price', 'royalty',

            # Cryptocurrency general
            'cryptocurrency', 'crypto', 'digital currency', 'token', 'coin',
            'altcoin', 'stablecoin', 'cbdc', 'digital asset', 'market cap',
            'volume', 'trading', 'exchange', 'cold storage',

            # Layer 2 and scaling
            'layer 2', 'l2', 'rollup', 'optimistic rollup', 'zk rollup',
            'plasma', 'state channel', 'sidechain', 'bridge', 'cross-chain',
            'interoperability', 'scaling', 'throughput', 'gas fees', 'gas',

            # Governance and tokenomics
            'tokenomics', 'governance', 'voting', 'proposal', 'delegate',
            'inflation', 'deflation', 'burn', 'supply', 'circulating supply',
            'total supply', 'emission', 'halving', 'fork', 'upgrade',

            # Technical concepts
            'hash', 'merkle tree', 'cryptography', 'public key', 'private key',
            'seed phrase', 'mnemonic', 'signature', 'transaction', 'block',
            'gwei', 'wei', 'satoshi', 'finality', 'immutable',

            # Information and news keywords
            'news', 'latest', 'recent', 'developments', 'updates', 'trends',
            'information', 'share', 'tell me about', 'explain', 'what is',
            'how does', 'what are'
        ]

        # Non-Web3 topics that should be declined
        self.non_web3_keywords = [
            # Geography and places
            'capital', 'country', 'city', 'geography', 'continent', 'location',
            'paris', 'london', 'islamabad', 'pakistan', 'france', 'europe',

            # Weather
            'weather', 'temperature', 'rain', 'sunny', 'cloudy', 'storm',
            'forecast', 'climate', 'degrees', 'celsius', 'fahrenheit',

            # Entertainment
            'movie', 'film', 'cinema', 'music', 'song', 'artist', 'sports',
            'football', 'basketball', 'game', 'celebrity', 'actor', 'director',

            # Food and cooking
            'recipe', 'cooking', 'food', 'restaurant', 'pizza', 'pasta',
            'ingredients', 'cook', 'bake', 'oven', 'dinner', 'lunch',

            # Health and medicine
            'health', 'doctor', 'medicine', 'symptom', 'headache', 'fitness',
            'exercise', 'diet', 'weight loss', 'medical',

            # Travel
            'travel', 'vacation', 'hotel', 'flight', 'destination', 'tourism',
            'book', 'reservation', 'trip',

            # Traditional finance
            'stock market', 'stocks', 'bonds', 'mutual funds', 'traditional banking',
            'credit card', 'mortgage', 'insurance', 'forex', 'real estate',

            # Technology (non-blockchain)
            'facebook', 'google', 'amazon', 'netflix', 'spotify', 'youtube',
            'instagram', 'twitter', 'programming', 'python', 'javascript',
            'mobile app', 'smartphone', 'wifi',

            # Academic subjects
            'mathematics', 'physics', 'chemistry', 'biology', 'history',
            'geography', 'literature', 'psychology', 'photosynthesis', 'gravity',

            # Personal topics
            'relationship', 'dating', 'family', 'parenting', 'career advice',
            'job interview', 'resume', 'personal development'
        ]

        # Cryptocurrency symbols and names
        self.crypto_symbols = {
            'btc', 'bitcoin', 'eth', 'ethereum', 'ada', 'cardano',
            'sol', 'solana', 'dot', 'polkadot', 'matic', 'polygon',
            'link', 'chainlink', 'uni', 'uniswap', 'aave', 'comp',
            'mkr', 'maker', 'snx', 'synthetix', 'bnb', 'binance',
            'xrp', 'ripple', 'ltc', 'litecoin', 'bch', 'bitcoin cash',
            'eos', 'trx', 'tron', 'xlm', 'stellar', 'icp', 'doge', 'dogecoin'
        }

    async def detect_intent(self, message: str) -> str:
        """
        Detect the intent of a user message
        Returns: 'price_query', 'wallet_query', 'web3_chat', 'non_web3', 'general_chat'
        """
        message_lower = message.lower().strip()

        # 1. Check for price-related queries first (most specific)
        if self._is_price_query(message_lower):
            return "price_query"

        # 2. Check for wallet-related queries
        if self._is_wallet_query(message_lower):
            return "wallet_query"

        # 3. Check if it's clearly non-Web3 related
        if self._is_non_web3_query(message_lower):
            return "non_web3"

        # 4. Check for general greetings/polite conversation
        if self._is_general_greeting(message_lower):
            return "general_chat"

        # 5. Check if it's Web3 related
        if self._is_web3_related(message_lower):
            return "web3_chat"

        # 6. Default: treat unclear messages as non-Web3 to be safe
        return "non_web3"

    def _is_price_query(self, message: str) -> bool:
        """Check if message is asking for price information"""

        # Must have explicit price-related keywords
        has_price_keyword = False
        for keyword in self.price_keywords:
            if keyword in message:
                has_price_keyword = True
                break

        # If no price keywords, definitely not a price query
        if not has_price_keyword:
            return False

        # Check for cryptocurrency mentions combined with price context
        has_crypto = any(symbol in message for symbol in self.crypto_symbols)

        # Pattern matching for price query formats
        price_patterns = [
            r'\b(price|cost|value|worth)\s+of\s+\w+',
            r'\bhow\s+much\s+(is|does|cost)',
            r'\bcurrent\s+\w+\s+(price|value|cost)',
            r'\w+\s+(price|cost|value|worth)',
            r'\$\d+',
            r'\b\w+\s+to\s+usd\b'
        ]

        has_price_pattern = any(re.search(pattern, message, re.IGNORECASE) for pattern in price_patterns)

        # Return True only if we have both price keywords AND (crypto mention OR price pattern)
        return has_price_keyword and (has_crypto or has_price_pattern)

    def _is_wallet_query(self, message: str) -> bool:
        """Check if message is asking for wallet information"""

        # Check for wallet keywords
        for keyword in self.wallet_keywords:
            if keyword in message:
                return True

        # Pattern matching for wallet-related queries
        wallet_patterns = [
            r'\bmy\s+(wallet|balance|portfolio|holdings)',
            r'\bwallet\s+(address|balance|setup)',
            r'\btransfer\s+\w+',
            r'\bsend\s+(crypto|token|coin)',
            r'\breceive\s+(crypto|token|coin)'
        ]

        for pattern in wallet_patterns:
            if re.search(pattern, message, re.IGNORECASE):
                return True

        return False

    def _is_web3_related(self, message: str) -> bool:
        """Check if message is related to Web3/crypto topics"""

        web3_score = 0

        # Check for Web3 keywords
        for keyword in self.web3_keywords:
            if keyword in message:
                web3_score += 1

        # Check for cryptocurrency mentions (not for price)
        has_crypto = any(symbol in message for symbol in self.crypto_symbols)
        if has_crypto:
            web3_score += 1

        # Pattern matching for Web3 concepts and information requests
        web3_patterns = [
            r'\bweb3\b',
            r'\bweb3\.0\b',
            r'\bblockchain\b',
            r'\bdefi\b',
            r'\bnft\b',
            r'\bsmart\s+contract\b',
            r'\bdapp\b',
            r'\bdao\b',
            r'\bstaking\b',
            r'\byield\s+farming\b',
            r'\bliquidity\b',
            r'\bgas\s+fees?\b',
            r'\bdecentralized\b',
            r'\bcrypto\b',
            r'\bcryptocurrency\b',
            r'\bdigital\s+asset\b',
            # Information request patterns
            r'\blatest\s+(news|updates?|developments?|trends?)\b',
            r'\bnews\s+about\b',
            r'\brecent\s+(developments?|updates?|news|trends?)\b',
            r'\bshare\s+(news|updates?|information|latest)\b',
            r'\bwhat\'?s\s+(new|latest|happening)\b',
            r'\btell\s+me\s+about\b',
            r'\bexplain\b',
            r'\bhow\s+does\b',
            r'\bwhat\s+(is|are)\b'
        ]

        for pattern in web3_patterns:
            if re.search(pattern, message, re.IGNORECASE):
                web3_score += 1

        return web3_score >= 1

    def _is_non_web3_query(self, message: str) -> bool:
        """Check if message is clearly non-Web3 related"""

        # Check for explicit non-Web3 keywords
        for keyword in self.non_web3_keywords:
            if keyword in message:
                return True

        # Pattern matching for clearly non-Web3 topics
        non_web3_patterns = [
            r'\bcapital\s+of\s+\w+',
            r'\bweather\s+(today|tomorrow|forecast)',
            r'\bmovie\s+(recommendation|review)',
            r'\brecipe\s+for\b',
            r'\bhow\s+to\s+(cook|bake|make)\b',
            r'\bhealth\s+(advice|tip)',
            r'\bstock\s+(market|price|recommendation)',
            r'\bwhat\s+is\s+\d+\s*[\+\-\*\/]\s*\d+',  # Math questions
            r'\btravel\s+(to|destination|hotel)',
            r'\brelationship\s+advice\b'
        ]

        for pattern in non_web3_patterns:
            if re.search(pattern, message, re.IGNORECASE):
                return True

        return False

    def _is_general_greeting(self, message: str) -> bool:
        """Check if message is a general greeting or polite conversation"""

        # Exact matches for simple greetings
        simple_greetings = [
            'hi', 'hello', 'hey', 'good morning', 'good evening', 'good afternoon',
            'thank you', 'thanks', 'bye', 'goodbye', 'help', 'who are you',
            'what can you do', 'how are you'
        ]

        # Check if the entire message (trimmed) is just a greeting
        message_clean = message.strip().lower()
        if message_clean in simple_greetings:
            return True

        # Pattern matching for greeting-like messages
        greeting_patterns = [
            r'^\s*(hi|hello|hey)\s*[!\.]*\s*$',
            r'^\s*(good\s+(morning|evening|afternoon))\s*[!\.]*\s*$',
            r'^\s*(thank\s+you|thanks)\s*[!\.]*\s*$',
            r'^\s*(bye|goodbye)\s*[!\.]*\s*$',
            r'^\s*(help|what\s+can\s+you\s+do)\s*[!\.]*\s*$'
        ]

        for pattern in greeting_patterns:
            if re.search(pattern, message, re.IGNORECASE):
                return True

        return False

    def extract_crypto_symbol(self, message: str) -> str:
        """Extract cryptocurrency symbol from message"""
        message_lower = message.lower()

        # Direct symbol matches with standardization
        symbol_mapping = {
            'btc': 'bitcoin',
            'bitcoin': 'bitcoin',
            'eth': 'ethereum',
            'ethereum': 'ethereum',
            'ada': 'cardano',
            'cardano': 'cardano',
            'sol': 'solana',
            'solana': 'solana',
            'dot': 'polkadot',
            'polkadot': 'polkadot',
            'matic': 'matic-network',
            'polygon': 'matic-network',
            'link': 'chainlink',
            'chainlink': 'chainlink'
        }

        for symbol in symbol_mapping:
            if symbol in message_lower:
                return symbol_mapping[symbol]

        # Default fallback
        return 'bitcoin'

    def get_intent_confidence(self, message: str) -> Dict[str, float]:
        """Get confidence scores for each intent (useful for debugging)"""
        message_lower = message.lower().strip()

        scores = {
            'price_query': 0.0,
            'wallet_query': 0.0,
            'web3_chat': 0.0,
            'non_web3': 0.0,
            'general_chat': 0.0
        }

        # Price query confidence
        price_score = 0
        for keyword in self.price_keywords:
            if keyword in message_lower:
                price_score += 1
        has_crypto = any(symbol in message_lower for symbol in self.crypto_symbols)
        if has_crypto:
            price_score += 1
        scores['price_query'] = min(price_score / 4.0, 1.0)

        # Wallet query confidence
        wallet_score = 0
        for keyword in self.wallet_keywords:
            if keyword in message_lower:
                wallet_score += 1
        scores['wallet_query'] = min(wallet_score / 3.0, 1.0)

        # Web3 confidence
        web3_score = 0
        for keyword in self.web3_keywords:
            if keyword in message_lower:
                web3_score += 1
        scores['web3_chat'] = min(web3_score / 5.0, 1.0)

        # Non-Web3 confidence
        non_web3_score = 0
        for keyword in self.non_web3_keywords:
            if keyword in message_lower:
                non_web3_score += 1
        scores['non_web3'] = min(non_web3_score / 3.0, 1.0)

        # General chat confidence
        chat_score = 0
        for keyword in self.general_chat_keywords:
            if keyword in message_lower:
                chat_score += 1
        scores['general_chat'] = min(chat_score / 2.0, 1.0)

        return scores
