import asyncio
import json
import time
import uuid
from typing import AsyncGenerator, List, Dict, Optional
from datetime import datetime, timezone
from utils.groq_client import GroqClient
from utils.cache import CacheManager
from utils.typesense_client import TypesenseClient


class ChatService:
    def __init__(self, cache_manager: CacheManager):
        self.groq_client = GroqClient()
        self.cache = cache_manager
        self.typesense = TypesenseClient()
        self.active_conversations = {}  # user_id -> conversation_id mapping
        self.conversation_locks = {}  # Prevent concurrent updates

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
        """Initialize Typesense collections with better error handling"""
        max_retries = 5
        retry_delay = 2

        for attempt in range(max_retries):
            try:
                await self.typesense.initialize_collections()
                print("✅ Chat history storage initialized")
                return True
            except Exception as e:
                print(f"❌ Attempt {attempt + 1}/{max_retries} failed: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                else:
                    print("⚠️ Chat history initialization failed, continuing without history")
                    return False

    async def get_or_create_conversation(self, user_id: str, title: Optional[str] = None) -> str:
        """Get existing active conversation or create new one"""
        # Check if user has an active conversation in memory
        if user_id in self.active_conversations:
            conv_id = self.active_conversations[user_id]

            # Verify it still exists and is recent
            try:
                conversations = await self.typesense.get_user_conversations(user_id, limit=1, status='active')
                if conversations and conversations[0]['id'] == conv_id:
                    last_updated = conversations[0].get('updated_at', 0)
                    if time.time() - last_updated < 3600:  # Active within last hour
                        return conv_id
            except:
                pass

        # Create new conversation
        try:
            if not title:
                title = f"Chat {datetime.now().strftime('%Y-%m-%d %H:%M')}"

            conversation_id = await self.typesense.create_conversation(user_id, title)
            self.active_conversations[user_id] = conversation_id
            return conversation_id

        except Exception as e:
            # Fallback to UUID if Typesense fails
            print(f"Error creating conversation: {e}")
            conversation_id = f"conv_{user_id}_{uuid.uuid4().hex[:8]}"
            self.active_conversations[user_id] = conversation_id
            return conversation_id

    async def handle_chat(self, message: str, user_id: str = "default", conversation_id: Optional[str] = None) -> str:
        """Handle general chat queries with improved conversation management"""
        start_time = time.time()

        try:
            # Use provided conversation ID or get/create one
            if not conversation_id:
                conversation_id = await self.get_or_create_conversation(user_id)
            else:
                # Update active conversation mapping
                self.active_conversations[user_id] = conversation_id

            # Acquire lock for this conversation to prevent race conditions
            if conversation_id not in self.conversation_locks:
                self.conversation_locks[conversation_id] = asyncio.Lock()

            async with self.conversation_locks[conversation_id]:
                # Add user message to history
                try:
                    await self.typesense.add_message(
                        conversation_id=conversation_id,
                        user_id=user_id,
                        role="user",
                        content=message
                    )
                except Exception as e:
                    print(f"Error saving user message: {e}")

                # Check cache for common questions
                cache_key = f"chat:{hash(message.lower().strip())}"
                cached_response = await self.cache.get(cache_key)

                if cached_response:
                    response_time_ms = int((time.time() - start_time) * 1000)

                    # Save cached response to history
                    try:
                        await self.typesense.add_message(
                            conversation_id=conversation_id,
                            user_id=user_id,
                            role="assistant",
                            content=cached_response,
                            response_time_ms=response_time_ms,
                            cached=True
                        )
                    except:
                        pass

                    return cached_response

                # Get conversation context with error handling
                context = []
                try:
                    context = await self.typesense.get_conversation_context(
                        conversation_id,
                        limit=10  # Last 10 messages for context
                    )
                except Exception as e:
                    print(f"Error getting context: {e}")
                    # Continue without context if Typesense fails

                # Prepare messages for Groq
                messages = [
                    {"role": "system", "content": self.system_prompt},
                    *context,
                    {"role": "user", "content": message}
                ]

                # Get response from Groq
                response = await self.groq_client.chat_completion(messages)
                response_time_ms = int((time.time() - start_time) * 1000)

                # Cache if appropriate
                if self._is_cacheable_question(message):
                    await self.cache.set(cache_key, response, expire=3600)

                # Save assistant response to history
                try:
                    await self.typesense.add_message(
                        conversation_id=conversation_id,
                        user_id=user_id,
                        role="assistant",
                        content=response,
                        response_time_ms=response_time_ms,
                        cached=False
                    )
                except Exception as e:
                    print(f"Error saving assistant response: {e}")

                return response

        except Exception as e:
            print(f"Error in chat service: {e}")
            return "I'm sorry, I'm having trouble processing your request right now. Please try again."

    async def stream_chat_response(self, message: str, user_id: str = "default",
                                   conversation_id: Optional[str] = None) -> AsyncGenerator[str, None]:
        """Stream chat responses with improved error handling"""
        start_time = time.time()

        try:
            # Use provided conversation ID or get/create one
            if not conversation_id:
                conversation_id = await self.get_or_create_conversation(user_id)
            else:
                self.active_conversations[user_id] = conversation_id

            # Yield conversation ID first
            yield f"CONVERSATION_ID:{conversation_id}"

            # Add user message to history
            try:
                await self.typesense.add_message(
                    conversation_id=conversation_id,
                    user_id=user_id,
                    role="user",
                    content=message
                )
            except Exception as e:
                print(f"Error saving user message: {e}")

            # Check cache
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
                    await asyncio.sleep(0.02)

                # Save to history
                try:
                    await self.typesense.add_message(
                        conversation_id=conversation_id,
                        user_id=user_id,
                        role="assistant",
                        content=cached_response,
                        response_time_ms=int((time.time() - start_time) * 1000),
                        cached=True
                    )
                except:
                    pass

                return

            # Get context
            context = []
            try:
                context = await self.typesense.get_conversation_context(conversation_id, limit=10)
            except:
                pass

            # Prepare messages
            messages = [
                {"role": "system", "content": self.system_prompt},
                *context,
                {"role": "user", "content": message}
            ]

            # Stream response
            full_response = ""
            async for chunk in self.groq_client.stream_chat_completion(messages):
                full_response += chunk
                yield chunk

            response_time_ms = int((time.time() - start_time) * 1000)

            # Cache if appropriate
            if self._is_cacheable_question(message):
                await self.cache.set(cache_key, full_response, expire=3600)

            # Save to history
            try:
                await self.typesense.add_message(
                    conversation_id=conversation_id,
                    user_id=user_id,
                    role="assistant",
                    content=full_response,
                    response_time_ms=response_time_ms,
                    cached=False
                )
            except Exception as e:
                print(f"Error saving assistant response: {e}")

        except Exception as e:
            print(f"Error in streaming chat: {e}")
            yield "I'm sorry, I'm having trouble processing your request right now."

    async def handle_non_web3_query(self, message: str, user_id: str = "default") -> str:
        """Handle non-Web3 queries with conversation tracking"""
        start_time = time.time()

        try:
            conversation_id = await self.get_or_create_conversation(user_id)

            # Add user message
            try:
                await self.typesense.add_message(
                    conversation_id=conversation_id,
                    user_id=user_id,
                    role="user",
                    content=message,
                    intent="non_web3"
                )
            except:
                pass

            response = "I only provide information about Web3, cryptocurrency, and blockchain technology. I cannot help with this topic."

            # Add response
            try:
                await self.typesense.add_message(
                    conversation_id=conversation_id,
                    user_id=user_id,
                    role="assistant",
                    content=response,
                    intent="non_web3_decline",
                    response_time_ms=int((time.time() - start_time) * 1000)
                )
            except:
                pass

            return response

        except Exception as e:
            print(f"Error handling non-web3 query: {e}")
            return "I only provide information about Web3, cryptocurrency, and blockchain technology. I cannot help with this topic."

    async def get_user_conversations(self, user_id: str, limit: int = 20, offset: int = 0) -> List[Dict]:
        """Get user's conversations with error handling"""
        try:
            return await self.typesense.get_user_conversations(user_id, limit=limit, offset=offset)
        except Exception as e:
            print(f"Error getting conversations: {e}")
            return []

    async def get_conversation_messages(self, conversation_id: str, limit: int = 100) -> List[Dict]:
        """Get messages from a conversation"""
        try:
            return await self.typesense.get_conversation_history(conversation_id, limit=limit)
        except Exception as e:
            print(f"Error getting messages: {e}")
            return []

    async def update_conversation_title(self, conversation_id: str, title: str) -> bool:
        """Update conversation title"""
        try:
            # This would need to be implemented in TypesenseClient
            # For now, return True as placeholder
            return True
        except Exception as e:
            print(f"Error updating conversation title: {e}")
            return False

    async def search_user_history(self, user_id: str, query: str, conversation_id: Optional[str] = None) -> List[Dict]:
        """Search through user's chat history"""
        try:
            return await self.typesense.search_messages(user_id, query, conversation_id=conversation_id)
        except Exception as e:
            print(f"Error searching history: {e}")
            return []

    async def export_conversation(self, conversation_id: str) -> Dict:
        """Export a conversation"""
        try:
            return await self.typesense.export_conversation(conversation_id)
        except Exception as e:
            print(f"Error exporting conversation: {e}")
            return {"error": str(e)}

    async def delete_conversation(self, conversation_id: str) -> bool:
        """Delete a conversation"""
        try:
            await self.typesense.delete_conversation(conversation_id)

            # Remove from active conversations
            for user_id, conv_id in list(self.active_conversations.items()):
                if conv_id == conversation_id:
                    del self.active_conversations[user_id]

            return True
        except Exception as e:
            print(f"Error deleting conversation: {e}")
            return False

    async def get_user_stats(self, user_id: str) -> Dict:
        """Get user statistics"""
        try:
            return await self.typesense.get_user_stats(user_id)
        except Exception as e:
            print(f"Error getting user stats: {e}")
            return {}

    def _is_cacheable_question(self, message: str) -> bool:
        """Determine if a question should be cached"""
        message_lower = message.lower().strip()

        cacheable_patterns = [
            'what is', 'what are', 'how does', 'explain', 'define',
            'difference between', 'benefits of', 'risks of', 'tell me about'
        ]

        return any(pattern in message_lower for pattern in cacheable_patterns)

    async def cleanup_old_conversations(self, user_id: str, keep_recent: int = 10):
        """Archive old conversations to keep the list manageable"""
        try:
            conversations = await self.typesense.get_user_conversations(user_id, limit=100)

            if len(conversations) > keep_recent:
                # Archive older conversations
                for conv in conversations[keep_recent:]:
                    await self.typesense.archive_conversation(conv['id'])

        except Exception as e:
            print(f"Error cleaning up conversations: {e}")

    async def get_chat_stats(self) -> Dict:
        """Get service statistics"""
        try:
            return {
                "service": "chat_service",
                "status": "active",
                "active_conversations": len(self.active_conversations),
                "cache_enabled": True,
                "history_enabled": True,
                "groq_connected": await self.groq_client.health_check(),
                "typesense_healthy": await self.typesense.health_check()
            }
        except Exception as e:
            return {"error": str(e)}
