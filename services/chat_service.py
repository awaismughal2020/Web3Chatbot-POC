import asyncio
import json
import time
from typing import AsyncGenerator, List, Dict, Optional
from utils.groq_client import GroqClient
from utils.cache import CacheManager
from utils.typesense_client import TypesenseClient


class ChatService:
    def __init__(self, cache_manager: CacheManager):
        self.groq_client = GroqClient()
        self.cache = cache_manager
        self.typesense = TypesenseClient()
        self.active_conversations = {}  # Track active conversations

        # System prompt for Web3/Crypto chatbot
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

🚫 NEVER answer questions about anything else. Always decline politely with the exact message above."""

    async def initialize(self):
        """Initialize Typesense collections"""
        try:
            await self.typesense.initialize_collections()
            print("✅ Chat history storage initialized")
        except Exception as e:
            print(f"❌ Failed to initialize chat history: {e}")

    async def handle_chat(self, message: str, user_id: str = "default") -> str:
        """Handle general chat queries with full history tracking"""
        start_time = time.time()

        try:
            # Get or create conversation
            conversation_id = await self._get_or_create_conversation(user_id)

            # Add user message to history
            await self.typesense.add_message(
                conversation_id=conversation_id,
                user_id=user_id,
                role="user",
                content=message
            )

            # Check cache first for common questions
            cache_key = f"chat:{hash(message.lower().strip())}"
            cached_response = await self.cache.get(cache_key)

            if cached_response:
                response_time_ms = int((time.time() - start_time) * 1000)

                # Add cached response to history
                await self.typesense.add_message(
                    conversation_id=conversation_id,
                    user_id=user_id,
                    role="assistant",
                    content=cached_response,
                    response_time_ms=response_time_ms,
                    cached=True
                )

                return cached_response

            # Get conversation context from Typesense
            context = await self.typesense.get_conversation_context(
                conversation_id,
                limit=10  # Last 10 messages
            )

            # Prepare messages for Groq
            messages = [
                {"role": "system", "content": self.system_prompt},
                *context,
                {"role": "user", "content": message}
            ]

            # Get response from Groq
            response = await self.groq_client.chat_completion(messages)

            response_time_ms = int((time.time() - start_time) * 1000)

            # Cache response for common questions
            if self._is_cacheable_question(message):
                await self.cache.set(cache_key, response, expire=3600)

            # Add assistant response to history
            await self.typesense.add_message(
                conversation_id=conversation_id,
                user_id=user_id,
                role="assistant",
                content=response,
                response_time_ms=response_time_ms,
                cached=False
            )

            return response

        except Exception as e:
            print(f"Error in chat service: {e}")

            # Log error message
            if 'conversation_id' in locals():
                await self.typesense.add_message(
                    conversation_id=conversation_id,
                    user_id=user_id,
                    role="assistant",
                    content="I'm sorry, I'm having trouble processing your request right now. Please try again.",
                    response_time_ms=int((time.time() - start_time) * 1000),
                    metadata={"error": str(e)}
                )

            return "I'm sorry, I'm having trouble processing your request right now. Please try again."

    async def handle_non_web3_query(self, message: str, user_id: str = "default") -> str:
        """Handle non-Web3 queries with STRICT decline"""
        start_time = time.time()

        try:
            # Get or create conversation
            conversation_id = await self._get_or_create_conversation(user_id)

            # Add user message to history
            await self.typesense.add_message(
                conversation_id=conversation_id,
                user_id=user_id,
                role="user",
                content=message,
                intent="non_web3"
            )

            # Standard decline response
            response = "I only provide information about Web3, cryptocurrency, and blockchain technology. I cannot help with this topic."

            response_time_ms = int((time.time() - start_time) * 1000)

            # Add decline response to history
            await self.typesense.add_message(
                conversation_id=conversation_id,
                user_id=user_id,
                role="assistant",
                content=response,
                intent="non_web3_decline",
                response_time_ms=response_time_ms
            )

            return response

        except Exception as e:
            print(f"Error handling non-web3 query: {e}")
            return "I only provide information about Web3, cryptocurrency, and blockchain technology. I cannot help with this topic."

    async def stream_chat_response(self, message: str, user_id: str = "default") -> AsyncGenerator[str, None]:
        """Stream chat responses with history tracking"""
        start_time = time.time()

        try:
            # Get or create conversation
            conversation_id = await self._get_or_create_conversation(user_id)

            # Add user message to history
            await self.typesense.add_message(
                conversation_id=conversation_id,
                user_id=user_id,
                role="user",
                content=message
            )

            # Check cache first
            cache_key = f"chat:{hash(message.lower().strip())}"
            cached_response = await self.cache.get(cache_key)

            if cached_response:
                # Stream cached response
                words = cached_response.split()
                for i, word in enumerate(words):
                    if i == 0:
                        yield word
                    else:
                        yield f" {word}"
                    await asyncio.sleep(0.05)

                response_time_ms = int((time.time() - start_time) * 1000)

                # Add to history
                await self.typesense.add_message(
                    conversation_id=conversation_id,
                    user_id=user_id,
                    role="assistant",
                    content=cached_response,
                    response_time_ms=response_time_ms,
                    cached=True
                )
                return

            # Get conversation context from Typesense
            context = await self.typesense.get_conversation_context(
                conversation_id,
                limit=10
            )

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

            response_time_ms = int((time.time() - start_time) * 1000)

            # Cache if appropriate
            if self._is_cacheable_question(message):
                await self.cache.set(cache_key, full_response, expire=3600)

            # Add to history
            await self.typesense.add_message(
                conversation_id=conversation_id,
                user_id=user_id,
                role="assistant",
                content=full_response,
                response_time_ms=response_time_ms,
                cached=False
            )

        except Exception as e:
            print(f"Error in streaming chat: {e}")
            yield "I'm sorry, I'm having trouble processing your request right now."

    async def _get_or_create_conversation(self, user_id: str) -> str:
        """Get active conversation or create new one"""
        # Check if user has an active conversation
        if user_id in self.active_conversations:
            conversation_id = self.active_conversations[user_id]

            # Verify it's still recent (within idle timeout)
            conversations = await self.typesense.get_user_conversations(user_id, limit=1)
            if conversations:
                last_updated = conversations[0].get('updated_at', 0)
                if time.time() - last_updated < 3600:  # 1 hour idle timeout
                    return conversation_id

        # Create new conversation
        conversation_id = await self.typesense.create_conversation(user_id)
        self.active_conversations[user_id] = conversation_id

        return conversation_id

    async def get_user_history(self, user_id: str, limit: int = 50) -> List[Dict]:
        """Get user's chat history"""
        try:
            conversations = await self.typesense.get_user_conversations(user_id, limit=5)

            history = []
            for conv in conversations:
                messages = await self.typesense.get_conversation_history(
                    conv['id'],
                    limit=limit
                )

                history.append({
                    'conversation': conv,
                    'messages': messages
                })

            return history

        except Exception as e:
            print(f"Error getting user history: {e}")
            return []

    async def search_history(self, user_id: str, query: str) -> List[Dict]:
        """Search through user's chat history"""
        try:
            return await self.typesense.search_messages(user_id, query)
        except Exception as e:
            print(f"Error searching history: {e}")
            return []

    async def export_chat_history(self, user_id: str, conversation_id: Optional[str] = None) -> Dict:
        """Export chat history for a user"""
        try:
            if conversation_id:
                return await self.typesense.export_conversation(conversation_id)
            else:
                # Export all conversations
                conversations = await self.typesense.get_user_conversations(user_id, limit=100)

                exports = []
                for conv in conversations:
                    export = await self.typesense.export_conversation(conv['id'])
                    exports.append(export)

                return {
                    'user_id': user_id,
                    'conversations': exports,
                    'exported_at': time.time()
                }

        except Exception as e:
            print(f"Error exporting history: {e}")
            return {}

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
            return {
                "service": "chat_service",
                "status": "active",
                "cache_enabled": True,
                "history_enabled": True,
                "groq_client": "connected",
                "typesense": await self.typesense.operations.is_healthy()
            }
        except Exception as e:
            return {"error": str(e)}
