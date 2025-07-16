"""
Complete Enhanced ChatService - services/enhanced_chat_service.py
Clean version without duplicates and with proper error handling
"""

import asyncio
import json
import time
import uuid
from typing import AsyncGenerator, List, Dict, Optional
from datetime import datetime, timezone
from utils.groq_client import GroqClient
from utils.cache import CacheManager
from utils.typesense_client import TypesenseClient

# Import the context handler
from utils.context_handler import ContextHandler


class EnhancedChatService:
    def __init__(self, cache_manager: CacheManager, model_name: str = "meta-llama/llama-4-maverick-17b-128e-instruct"):
        self.groq_client = GroqClient()
        self.cache = cache_manager
        self.typesense = TypesenseClient()
        self.active_conversations = {}
        self.conversation_locks = {}

        # Initialize context handler
        self.context_handler = ContextHandler(model_name)

        # Update Groq client model
        self.groq_client.model = model_name

        # Context settings
        self.enable_context = True
        self.max_context_messages = 50
        self.context_cache_duration = 300  # 5 minutes

        # System prompt optimized for context
        self.system_prompt = """You are a HIGHLY specialized Web3 and cryptocurrency assistant with access to conversation history for context.

🚫 CRITICAL INSTRUCTION: If ANY question is about non-Web3 topics, respond with EXACTLY:
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

📝 CONTEXT USAGE: Use the conversation history to:
- Provide consistent, contextual responses
- Reference previous discussions when relevant
- Build on prior explanations
- Maintain conversation flow
- Avoid repeating information unnecessarily

🚫 DO NOT answer questions about anything else. Always decline politely."""

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

    async def get_or_create_conversation(self, user_id: str, title: Optional[str] = None,
                                         force_new: bool = False) -> str:
        """Get existing active conversation or create new one"""
        if force_new:
            return await self._create_new_conversation(user_id, title)

        if user_id in self.active_conversations:
            conv_id = self.active_conversations[user_id]
            try:
                conversations = await self.typesense.get_user_conversations(user_id, limit=1, status='active')
                if conversations and conversations[0]['id'] == conv_id:
                    last_updated = conversations[0].get('updated_at', 0)
                    if time.time() - last_updated < 3600:
                        return conv_id
            except:
                pass

        return await self._create_new_conversation(user_id, title)

    async def _create_new_conversation(self, user_id: str, title: Optional[str] = None) -> str:
        """Create a new conversation"""
        try:
            if not title:
                title = f"Chat {datetime.now().strftime('%Y-%m-%d %H:%M')}"

            conversation_id = await self.typesense.create_conversation(user_id, title)
            self.active_conversations[user_id] = conversation_id
            await self.cleanup_old_conversations(user_id)
            return conversation_id

        except Exception as e:
            print(f"Error creating conversation: {e}")
            conversation_id = f"conv_{user_id}_{uuid.uuid4().hex[:8]}"
            self.active_conversations[user_id] = conversation_id
            return conversation_id

    async def handle_chat(self, message: str, user_id: str = "default", conversation_id: Optional[str] = None) -> str:
        """Handle chat with optimized context"""
        start_time = time.time()

        try:
            # Get or create conversation
            if not conversation_id:
                conversation_id = await self.get_or_create_conversation(user_id)
            else:
                try:
                    conversations = await self.typesense.get_user_conversations(user_id, limit=100)
                    if not any(c['id'] == conversation_id for c in conversations):
                        conversation_id = await self.get_or_create_conversation(user_id, force_new=True)
                except:
                    conversation_id = await self.get_or_create_conversation(user_id, force_new=True)

                self.active_conversations[user_id] = conversation_id

            # Acquire lock for this conversation
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
                cache_key = f"chat_context:{hash(message.lower().strip())}:{conversation_id}"
                cached_response = await self.cache.get(cache_key)

                if cached_response:
                    response_time_ms = int((time.time() - start_time) * 1000)

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

                # Get conversation context with optimization
                messages = []
                if self.enable_context:
                    try:
                        # Get recent conversation history
                        recent_messages = await self.typesense.get_conversation_history(
                            conversation_id,
                            limit=self.max_context_messages
                        )

                        # Build optimized context
                        if recent_messages:
                            messages = self.context_handler.build_smart_context(
                                recent_messages,
                                message,
                                self.system_prompt
                            )
                        else:
                            messages = [
                                {"role": "system", "content": self.system_prompt},
                                {"role": "user", "content": message}
                            ]

                    except Exception as e:
                        print(f"Error building context: {e}")
                        # Fallback to simple context
                        messages = [
                            {"role": "system", "content": self.system_prompt},
                            {"role": "user", "content": message}
                        ]
                else:
                    # Simple context without optimization
                    messages = [
                        {"role": "system", "content": self.system_prompt},
                        {"role": "user", "content": message}
                    ]

                # Get response from Groq
                response = await self.groq_client.chat_completion(messages)
                response_time_ms = int((time.time() - start_time) * 1000)

                # Cache if appropriate
                if self._is_cacheable_question(message):
                    await self.cache.set(cache_key, response, expire=self.context_cache_duration)

                # Save assistant response
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
        """Stream chat responses with optimized context"""
        start_time = time.time()

        try:
            # Get or create conversation
            if not conversation_id:
                conversation_id = await self.get_or_create_conversation(user_id)
            else:
                try:
                    conversations = await self.typesense.get_user_conversations(user_id, limit=100)
                    if not any(c['id'] == conversation_id for c in conversations):
                        conversation_id = await self.get_or_create_conversation(user_id, force_new=True)
                except:
                    conversation_id = await self.get_or_create_conversation(user_id, force_new=True)

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

            # Check cache for streaming responses
            cache_key = f"stream_context:{hash(message.lower().strip())}:{conversation_id}"
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

            # Build optimized context
            messages = []
            if self.enable_context:
                try:
                    # Get recent conversation history
                    recent_messages = await self.typesense.get_conversation_history(
                        conversation_id,
                        limit=self.max_context_messages
                    )

                    # Build optimized context
                    if recent_messages:
                        messages = self.context_handler.build_smart_context(
                            recent_messages,
                            message,
                            self.system_prompt
                        )
                    else:
                        messages = [
                            {"role": "system", "content": self.system_prompt},
                            {"role": "user", "content": message}
                        ]

                except Exception as e:
                    print(f"Error building context: {e}")
                    # Fallback to simple context
                    messages = [
                        {"role": "system", "content": self.system_prompt},
                        {"role": "user", "content": message}
                    ]
            else:
                # Simple context without optimization
                messages = [
                    {"role": "system", "content": self.system_prompt},
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
                await self.cache.set(cache_key, full_response, expire=self.context_cache_duration)

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

    # Context management methods
    def toggle_context_optimization(self, enabled: bool):
        """Enable/disable context optimization"""
        self.enable_context = enabled
        print(f"Context optimization {'enabled' if enabled else 'disabled'}")

    def update_context_settings(self, max_messages: int = None, cache_duration: int = None):
        """Update context settings"""
        if max_messages is not None:
            self.max_context_messages = max_messages
            print(f"Max context messages set to {max_messages}")

        if cache_duration is not None:
            self.context_cache_duration = cache_duration
            print(f"Context cache duration set to {cache_duration} seconds")

    def clear_context_cache(self):
        """Clear context cache"""
        try:
            self.context_handler.clear_cache()
            print("Context cache cleared")
        except Exception as e:
            print(f"Error clearing context cache: {e}")

    def get_context_stats(self) -> Dict:
        """Get context handling statistics - FIXED VERSION"""
        try:
            # Safely get handler stats
            handler_stats = {}
            if hasattr(self, 'context_handler') and self.context_handler:
                try:
                    handler_stats = self.context_handler.get_performance_stats()
                except Exception as e:
                    print(f"Error getting handler stats: {e}")
                    handler_stats = {"error": str(e)}

            return {
                'context_enabled': getattr(self, 'enable_context', False),
                'max_context_messages': getattr(self, 'max_context_messages', 50),
                'cache_duration': getattr(self, 'context_cache_duration', 300),
                'handler_stats': handler_stats,
                'active_conversations': len(getattr(self, 'active_conversations', {})),
                'conversation_locks': len(getattr(self, 'conversation_locks', {}))
            }
        except Exception as e:
            print(f"Error getting context stats: {e}")
            return {
                'context_enabled': False,
                'max_context_messages': 50,
                'cache_duration': 300,
                'error': str(e)
            }

    def get_context_summary(self, messages: List[Dict], current_query: str) -> Dict:
        """Get context summary for debugging"""
        try:
            if hasattr(self, 'context_handler') and self.context_handler:
                return self.context_handler.get_context_summary(messages, current_query)
            else:
                return {
                    'total_messages_available': len(messages),
                    'messages_selected': 0,
                    'estimated_tokens': 0,
                    'token_budget': 0,
                    'utilization_percent': 0,
                    'error': 'Context handler not available'
                }
        except Exception as e:
            print(f"Error getting context summary: {e}")
            return {
                'total_messages_available': len(messages),
                'messages_selected': 0,
                'estimated_tokens': 0,
                'token_budget': 0,
                'utilization_percent': 0,
                'error': str(e)
            }

    async def handle_enhanced_context_query(self, message: str, user_id: str, conversation_id: str = None) -> Dict:
        """Handle query with detailed context information"""
        try:
            if not conversation_id:
                conversation_id = await self.get_or_create_conversation(user_id)

            # Get conversation history
            recent_messages = await self.typesense.get_conversation_history(
                conversation_id,
                limit=self.max_context_messages
            )

            # Build context summary
            context_summary = self.get_context_summary(recent_messages, message)

            # Get the actual response
            response = await self.handle_chat(message, user_id, conversation_id)

            return {
                "response": response,
                "context_info": context_summary,
                "conversation_id": conversation_id,
                "context_enabled": self.enable_context
            }

        except Exception as e:
            print(f"Error in enhanced context query: {e}")
            return {
                "response": "I'm sorry, I'm having trouble processing your request.",
                "error": str(e)
            }

    # Standard conversation management methods
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
            return await self.typesense.update_conversation_title(conversation_id, title)
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
        try:
            message_lower = message.lower().strip()

            cacheable_patterns = [
                'what is', 'what are', 'how does', 'explain', 'define',
                'difference between', 'benefits of', 'risks of', 'tell me about'
            ]

            return any(pattern in message_lower for pattern in cacheable_patterns)
        except Exception as e:
            print(f"Error checking cacheable question: {e}")
            return False

    async def cleanup_old_conversations(self, user_id: str, keep_recent: int = 10):
        """Archive old conversations to keep the list manageable"""
        try:
            conversations = await self.typesense.get_user_conversations(user_id, limit=100)

            if len(conversations) > keep_recent:
                for conv in conversations[keep_recent:]:
                    await self.typesense.archive_conversation(conv['id'])

        except Exception as e:
            print(f"Error cleaning up conversations: {e}")

    async def get_chat_stats(self) -> Dict:
        """Get service statistics - FIXED VERSION"""
        try:
            # Get context stats safely
            context_stats = self.get_context_stats()

            # Check service health safely
            groq_healthy = False
            typesense_healthy = False

            try:
                if hasattr(self, 'groq_client') and self.groq_client:
                    groq_healthy = await self.groq_client.health_check()
            except Exception as e:
                print(f"Groq health check failed: {e}")

            try:
                if hasattr(self, 'typesense') and self.typesense:
                    typesense_healthy = await self.typesense.health_check()
            except Exception as e:
                print(f"Typesense health check failed: {e}")

            base_stats = {
                "service": "enhanced_chat_service",
                "status": "active",
                "active_conversations": len(getattr(self, 'active_conversations', {})),
                "context_enabled": getattr(self, 'enable_context', False),
                "groq_connected": groq_healthy,
                "typesense_healthy": typesense_healthy,
                "context_stats": context_stats
            }

            return base_stats

        except Exception as e:
            print(f"Error getting chat stats: {e}")
            return {
                "service": "enhanced_chat_service",
                "status": "error",
                "error": str(e),
                "active_conversations": len(getattr(self, 'active_conversations', {}))
            }


# Factory function to create the enhanced chat service
def create_enhanced_chat_service(cache_manager: CacheManager,
                                 model_name: str = "meta-llama/llama-4-maverick-17b-128e-instruct"):
    """Create enhanced chat service with context handling"""
    return EnhancedChatService(cache_manager, model_name)


# Safe utility functions for debugging and monitoring
async def debug_context_performance(chat_service: EnhancedChatService, test_queries: List[str],
                                    user_id: str = "test_user"):
    """Debug context performance with test queries - SAFE VERSION"""
    print("🔍 Context Performance Debug")
    print("=" * 50)

    try:
        conv_id = await chat_service.get_or_create_conversation(user_id)

        for i, query in enumerate(test_queries):
            print(f"\n📝 Test Query {i + 1}: {query[:50]}...")
            start_time = time.time()

            # Get context summary safely
            try:
                recent_messages = await chat_service.typesense.get_conversation_history(conv_id, limit=50)
                context_summary = chat_service.get_context_summary(recent_messages, query)

                messages_selected = context_summary.get('messages_selected', 0)
                total_messages = context_summary.get('total_messages_available', 0)
                estimated_tokens = context_summary.get('estimated_tokens', 0)
                token_budget = context_summary.get('token_budget', 0)
                utilization = context_summary.get('utilization_percent', 0)

                print(f"   📊 Context: {messages_selected}/{total_messages} messages")
                print(f"   🎯 Tokens: {estimated_tokens}/{token_budget} ({utilization:.1f}%)")

            except Exception as e:
                print(f"   ❌ Context error: {e}")

            # Test response safely
            try:
                response = await chat_service.handle_chat(query, user_id, conv_id)
                response_time = time.time() - start_time

                print(f"   ⚡ Response time: {response_time:.2f}s")
                print(f"   💬 Response: {response[:100]}...")

            except Exception as e:
                print(f"   ❌ Response error: {e}")

        # Print final stats safely
        print(f"\n📈 Final Context Stats:")
        try:
            stats = chat_service.get_context_stats()
            for key, value in stats.items():
                if isinstance(value, dict):
                    print(f"   {key}:")
                    for sub_key, sub_value in value.items():
                        print(f"     {sub_key}: {sub_value}")
                else:
                    print(f"   {key}: {value}")
        except Exception as e:
            print(f"   ❌ Error getting final stats: {e}")

    except Exception as e:
        print(f"❌ Debug session failed: {e}")