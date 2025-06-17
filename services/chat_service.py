import asyncio
import json
import time
from typing import AsyncGenerator, List, Dict
from utils.groq_client import GroqClient
from utils.cache import CacheManager


class ChatService:
    def __init__(self, cache_manager: CacheManager):
        self.groq_client = GroqClient()
        self.cache = cache_manager

        # System prompt for Web3/Crypto chatbot (ULTRA RESTRICTIVE)
        self.system_prompt = """You are an EXTREMELY specialized Web3 and cryptocurrency assistant. You have ABSOLUTE RESTRICTIONS:

🚫 CRITICAL INSTRUCTION: If ANY question is about non-Web3 topics, you MUST respond with EXACTLY this:
"I only provide information about Web3, cryptocurrency, and blockchain technology. I cannot help with this topic."

✅ ONLY answer questions about:
- Cryptocurrency (Bitcoin, Ethereum, altcoins, trading, market analysis)
- Blockchain technology and protocols
- DeFi (Decentralized Finance) - yield farming, liquidity pools, lending, AMMs
- NFTs (Non-Fungible Tokens) and digital assets
- Smart contracts and dApps development
- DAOs and governance tokens
- Web3 platforms, news, and developments
- Crypto wallets and security best practices
- Staking, mining, and consensus mechanisms
- Latest Web3 trends, updates, and industry news
- Layer 2 solutions and blockchain scaling

✅ For Web3 news/information requests:
- Provide educational information about Web3 concepts and trends
- Explain recent developments in DeFi, NFTs, and blockchain technology
- Share knowledge about emerging Web3 protocols and platforms
- Discuss Web3 adoption and industry developments

🚫 NEVER answer questions about:
- Geography, countries, capitals, cities
- Weather, general news, current events (non-crypto)
- Entertainment (movies, music, sports)
- Traditional finance (stocks, bonds, banking)
- Food, recipes, cooking, restaurants
- Health, medicine, fitness
- Travel, hotels, transportation
- General technology (non-blockchain)
- Academic subjects (math, science, history)
- Personal advice (relationships, career)
- ANY topic not directly related to Web3/crypto/blockchain

REMINDER: If it's not Web3/crypto/blockchain, respond with the exact decline message above. DO NOT provide any non-Web3 information even if you know the answer."""

    async def handle_chat(self, message: str, user_id: str = "default") -> str:
        """Handle general chat queries using Groq"""
        try:
            # Check cache first for common questions
            cache_key = f"chat:{hash(message.lower().strip())}"
            cached_response = await self.cache.get(cache_key)

            if cached_response:
                return cached_response

            # Get conversation context
            context = await self._get_conversation_context(user_id)

            # Prepare messages for Groq
            messages = [
                {"role": "system", "content": self.system_prompt},
                *context,
                {"role": "user", "content": message}
            ]

            # Get response from Groq
            response = await self.groq_client.chat_completion(messages)

            # Cache response for common questions (expire in 1 hour)
            if self._is_cacheable_question(message):
                await self.cache.set(cache_key, response, expire=3600)

            # Store in conversation context
            await self._update_conversation_context(user_id, message, response)

            return response

        except Exception as e:
            print(f"Error in chat service: {e}")
            return "I'm sorry, I'm having trouble processing your request right now. Please try again."

    async def handle_non_web3_query(self, message: str) -> str:
        """Handle non-Web3 queries with STRICT decline (no Groq call)"""

        # Strict decline responses - NO information about the actual question
        decline_responses = [
            "I only provide information about Web3, cryptocurrency, and blockchain technology. I cannot help with this topic.",

            "I'm specialized exclusively in Web3 and crypto. I can only assist with blockchain, DeFi, NFTs, and cryptocurrency questions.",

            "This is outside my scope. I focus solely on Web3, cryptocurrency, and blockchain-related topics.",

            "I cannot help with that topic. I'm designed specifically for Web3, crypto, and blockchain assistance only.",

            "That's not something I can assist with. I only handle Web3, cryptocurrency, and blockchain technology questions."
        ]

        # Choose a response (rotate based on message hash)
        base_response = decline_responses[hash(message) % len(decline_responses)]

        return f"{base_response}"

    async def stream_chat_response(self, message: str, user_id: str = "default") -> AsyncGenerator[str, None]:
        """Stream chat responses for real-time feel"""
        try:
            # Check cache first
            cache_key = f"chat:{hash(message.lower().strip())}"
            cached_response = await self.cache.get(cache_key)

            if cached_response:
                # Stream cached response word by word for consistency
                words = cached_response.split()
                for i, word in enumerate(words):
                    if i == 0:
                        yield word
                    else:
                        yield f" {word}"
                    await asyncio.sleep(0.05)  # Small delay for streaming effect
                return

            # Get conversation context
            context = await self._get_conversation_context(user_id)

            # Prepare messages for Groq
            messages = [
                {"role": "system", "content": self.system_prompt},
                *context,
                {"role": "user", "content": message}
            ]

            # Stream response from Groq
            full_response = ""
            async for chunk in self.groq_client.stream_chat_completion(messages):
                full_response += chunk
                yield chunk

            # Cache and store in context
            if self._is_cacheable_question(message):
                await self.cache.set(cache_key, full_response, expire=3600)

            await self._update_conversation_context(user_id, message, full_response)

        except Exception as e:
            print(f"Error in streaming chat: {e}")
            yield "I'm sorry, I'm having trouble processing your request right now."

    async def _get_conversation_context(self, user_id: str) -> List[Dict]:
        """Get recent conversation context for the user"""
        try:
            context_key = f"context:{user_id}"
            context_data = await self.cache.get(context_key)

            if context_data:
                return json.loads(context_data)
            return []

        except Exception as e:
            print(f"Error getting context: {e}")
            return []

    async def _update_conversation_context(self, user_id: str, user_message: str, bot_response: str):
        """Update conversation context with new exchange"""
        try:
            context = await self._get_conversation_context(user_id)

            # Add new exchange
            context.extend([
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": bot_response}
            ])

            # Keep only last 10 messages (5 exchanges) for performance
            context = context[-10:]

            # Store updated context (expire in 1 hour)
            context_key = f"context:{user_id}"
            await self.cache.set(context_key, json.dumps(context), expire=3600)

        except Exception as e:
            print(f"Error updating context: {e}")

    def _is_cacheable_question(self, message: str) -> bool:
        """Determine if a question is common enough to cache"""
        message_lower = message.lower().strip()

        # Cache common questions about Web3/crypto concepts
        cacheable_patterns = [
            'what is', 'what are', 'how does', 'explain', 'define',
            'difference between', 'benefits of', 'risks of', 'how to'
        ]

        return any(pattern in message_lower for pattern in cacheable_patterns)

    async def get_chat_stats(self) -> Dict:
        """Get statistics about chat service usage"""
        try:
            # This could be enhanced with proper metrics collection
            return {
                "service": "chat_service",
                "status": "active",
                "cache_enabled": True,
                "groq_client": "connected"
            }
        except Exception as e:
            return {"error": str(e)}
