from transformers import pipeline
import asyncio
import re
import time


class IntentDetector:
    def __init__(self):
        print("Initializing Intent Detector...")
        try:
            # Load zero-shot classification model with proper configuration
            self.classifier = pipeline(
                "zero-shot-classification",
                model="facebook/bart-large-mnli",
                device=-1,  # Use CPU (set to 0 for GPU if available)
                return_all_scores=True  # Get all confidence scores
            )
            print("Model loaded successfully")
        except Exception as e:
            print(f"Error loading model: {e}")
            self.classifier = None

        # Enhanced labels with clear, specific descriptions
        self.labels = [
            "asking for cryptocurrency price, market data, or current rates",
            "checking wallet balance, portfolio, or account information",
            "asking about web3 technology, blockchain, DeFi, NFTs, smart contracts, or cryptocurrency concepts",
            "general conversation, greetings, or casual chat",
            "asking about non-cryptocurrency topics like weather, food, sports, or entertainment"
        ]

        # Map enhanced labels back to original intent names
        self.label_mapping = {
            "asking for cryptocurrency price, market data, or current rates": "price_query",
            "checking wallet balance, portfolio, or account information": "wallet_query",
            "asking about web3 technology, blockchain, DeFi, NFTs, smart contracts, or cryptocurrency concepts": "web3_chat",
            "general conversation, greetings, or casual chat": "general_chat",
            "asking about non-cryptocurrency topics like weather, food, sports, or entertainment": "non_web3"
        }

        # Cryptocurrency mapping
        self.crypto_mapping = {
            'bitcoin': 'bitcoin', 'btc': 'bitcoin',
            'ethereum': 'ethereum', 'eth': 'ethereum',
            'cardano': 'cardano', 'ada': 'cardano',
            'solana': 'solana', 'sol': 'solana',
            'polkadot': 'polkadot', 'dot': 'polkadot',
            'polygon': 'matic-network', 'matic': 'matic-network',
            'chainlink': 'chainlink', 'link': 'chainlink',
            'uniswap': 'uniswap', 'uni': 'uniswap',
            'litecoin': 'litecoin', 'ltc': 'litecoin',
            'ripple': 'ripple', 'xrp': 'ripple',
            'binancecoin': 'binancecoin', 'bnb': 'binancecoin',
            'dogecoin': 'dogecoin', 'doge': 'dogecoin',
            'defi': 'defi', 'nft': 'nft', 'dao': 'dao'
        }

    async def detect_intent(self, message: str) -> str:
        """
        Detect the intent of a user message using zero-shot classification.
        Returns one of: 'price_query', 'wallet_query', 'web3_chat', 'general_chat', 'non_web3'
        """
        if not self.classifier:
            print("Classifier not available, using fallback")
            return self._fallback_intent_detection(message)

        try:
            # Preprocess message for better classification
            processed_message = self._preprocess_message(message)

            # Get classification result
            result = self.classifier(processed_message, self.labels)

            # Extract top prediction
            top_label = result['labels'][0]
            top_score = result['scores'][0]

            # Map back to original intent
            detected_intent = self.label_mapping.get(top_label, 'web3_chat')

            # Apply post-processing rules
            final_intent = self._apply_post_processing_rules(message, detected_intent, top_score)
            print(f"\nFinal Intent Detected: {final_intent}")

            return final_intent

        except Exception as e:
            print(f"Error in classification: {e}")
            return self._fallback_intent_detection(message)

    def _preprocess_message(self, message: str) -> str:
        """Enhance message with context for better classification"""
        message_lower = message.lower().strip()

        # Add relevant context based on content
        enhanced_message = message_lower

        # Add crypto context
        crypto_found = []
        for crypto in self.crypto_mapping.keys():
            if crypto in message_lower:
                crypto_found.append(crypto)

        if crypto_found:
            enhanced_message += f" (mentioning cryptocurrency: {', '.join(crypto_found)})"

        # Add specific domain context
        if any(term in message_lower for term in ['defi', 'decentralized finance']):
            enhanced_message += " (about decentralized finance DeFi)"
        if any(term in message_lower for term in ['nft', 'non-fungible']):
            enhanced_message += " (about NFT non-fungible tokens)"
        if any(term in message_lower for term in ['blockchain', 'smart contract']):
            enhanced_message += " (about blockchain technology)"
        if any(term in message_lower for term in ['price', 'cost', 'worth', 'value', 'how much']):
            enhanced_message += " (asking about price or value)"

        return enhanced_message

    def _apply_post_processing_rules(self, original_message: str, detected_intent: str, confidence: float) -> str:
        """Apply rule-based corrections for better accuracy"""
        message_lower = original_message.lower()

        # Strong price query indicators
        price_patterns = [
            r'(?:price|cost|worth|value).{0,10}(?:of|for).{0,10}(?:bitcoin|btc|ethereum|eth|solana|cardano)',
            r'(?:bitcoin|btc|ethereum|eth|solana|cardano).{0,10}(?:price|cost|worth|value)',
            r'how\s+much\s+(?:is|does).{0,10}(?:bitcoin|btc|ethereum|eth|solana|cardano)',
            r'current\s+(?:bitcoin|btc|ethereum|eth|solana|cardano)\s+(?:price|rate)'
        ]

        for pattern in price_patterns:
            if re.search(pattern, message_lower):
                return 'price_query'

        # Strong Web3/DeFi indicators
        web3_patterns = [
            r'\bdefi\b',
            r'decentralized\s+finance',
            r'yield\s+farming',
            r'liquidity\s+pool',
            r'smart\s+contract',
            r'\bnft\b',
            r'non.fungible\s+token',
            r'\bdao\b',
            r'web3',
            r'blockchain\s+technology',
            r'what\s+(?:is|are)\s+(?:defi|nft|dao|blockchain)',
            r'explain\s+(?:defi|nft|dao|blockchain)',
            r'how\s+(?:does|do)\s+(?:defi|nft|dao|blockchain)'
        ]

        for pattern in web3_patterns:
            if re.search(pattern, message_lower):
                if detected_intent in ['general_chat', 'non_web3'] and confidence < 0.8:
                    return 'web3_chat'

        # Wallet indicators
        if any(term in message_lower for term in ['wallet', 'balance', 'portfolio', 'my account']):
            if confidence > 0.3:
                return 'wallet_query'

        # Conservative non-web3 classification
        non_crypto_terms = ['weather', 'food', 'movie', 'music', 'sports', 'health']
        crypto_terms = list(self.crypto_mapping.keys()) + ['crypto', 'blockchain', 'defi', 'web3']

        has_non_crypto = any(term in message_lower for term in non_crypto_terms)
        has_crypto = any(term in message_lower for term in crypto_terms)

        if has_non_crypto and not has_crypto and confidence > 0.7:
            return 'non_web3'

        # Default to web3_chat for ambiguous cases in a crypto bot
        if detected_intent == 'general_chat' and confidence < 0.5:
            return 'web3_chat'

        return detected_intent

    def _fallback_intent_detection(self, message: str) -> str:
        """Simple rule-based fallback when ML model fails"""
        message_lower = message.lower()

        # Price queries
        if (any(word in message_lower for word in ['price', 'cost', 'worth', 'value', 'how much']) and
                any(crypto in message_lower for crypto in self.crypto_mapping.keys())):
            return 'price_query'

        # Wallet queries
        if any(word in message_lower for word in ['wallet', 'balance', 'portfolio', 'account']):
            return 'wallet_query'

        # Web3 topics
        web3_keywords = ['defi', 'decentralized finance', 'blockchain', 'web3', 'nft', 'smart contract',
                         'dao', 'yield farming', 'staking', 'liquidity', 'amm']
        if any(keyword in message_lower for keyword in web3_keywords):
            return 'web3_chat'

        # Non-crypto topics
        non_crypto_keywords = ['weather', 'food', 'movie', 'music', 'sports', 'health', 'travel']
        if (any(keyword in message_lower for keyword in non_crypto_keywords) and
                not any(crypto in message_lower for crypto in self.crypto_mapping.keys())):
            return 'non_web3'

        return 'web3_chat'  # Default for crypto bot

    def extract_crypto_symbol(self, message: str) -> str:
        """Extract cryptocurrency symbol from message"""
        message_lower = message.lower()

        # Direct matches first
        for crypto_key in self.crypto_mapping.keys():
            if crypto_key in message_lower:
                return crypto_key

        # Regex patterns for price queries
        patterns = [
            r'price\s+of\s+(\w+)',
            r'(\w+)\s+price',
            r'how\s+much\s+is\s+(\w+)',
            r'(\w+)\s+(?:cost|value|worth)',
            r'current\s+(\w+)'
        ]

        for pattern in patterns:
            match = re.search(pattern, message_lower)
            if match:
                potential_crypto = match.group(1)
                if potential_crypto in self.crypto_mapping:
                    return potential_crypto

        return 'bitcoin'

    def get_intent_confidence(self, message: str):
        """Return confidence scores for each intent"""
        if not self.classifier:
            return self._get_fallback_confidence(message)

        try:
            processed_message = self._preprocess_message(message)
            result = self.classifier(processed_message, self.labels)

            # Map enhanced labels back to original intents
            confidence_scores = {}
            for i, label in enumerate(result["labels"]):
                original_intent = self.label_mapping.get(label, 'unknown')
                confidence_scores[original_intent] = result["scores"][i]

            return confidence_scores

        except Exception as e:
            print(f"Error getting confidence scores: {e}")
            return self._get_fallback_confidence(message)

    def _get_fallback_confidence(self, message: str):
        """Fallback confidence scores when model fails"""
        fallback_intent = self._fallback_intent_detection(message)
        scores = {"price_query": 0.1, "wallet_query": 0.1, "web3_chat": 0.1, "general_chat": 0.1, "non_web3": 0.1,
                  fallback_intent: 0.6}
        return scores
