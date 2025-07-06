import asyncio
import typesense
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timezone
import json
import uuid
import time
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings
from dotenv import load_dotenv

load_dotenv()


class TypesenseClient:
    def __init__(self):
        self.client = typesense.Client({
            "nodes": [
                {
                    "host": os.getenv("TYPESENSE_HOST"),
                    "port": os.getenv("TYPESENSE_PORT"),
                    "protocol": os.getenv("TYPESENSE_PROTOCOL")
                }
            ],
            "api_key": os.getenv("TYPESENSE_API_KEY"),
            "connection_timeout_seconds": 2
        })

        # Collection names
        self.conversations_collection = 'conversations'
        self.messages_collection = 'messages'
        self.user_profiles_collection = 'user_profiles'
        self.conversation_summaries_collection = 'conversation_summaries'
        self.user_preferences_collection = 'user_preferences'

    async def initialize_collections(self):
        """Create all Typesense collections for chat history"""
        max_retries = 5
        retry_delay = 2

        for attempt in range(max_retries):
            try:
                # Check if Typesense is reachable
                health = await asyncio.to_thread(self.client.operations.is_healthy)
                if not health:
                    print(f"⏳ Waiting for Typesense to be ready... (attempt {attempt + 1}/{max_retries})")
                    await asyncio.sleep(retry_delay)
                    continue

                # Create all collections
                await self._create_conversations_collection()
                await self._create_messages_collection()
                await self._create_user_profiles_collection()
                await self._create_conversation_summaries_collection()
                await self._create_user_preferences_collection()

                print("✅ All Typesense collections initialized successfully")
                return True

            except Exception as e:
                print(f"❌ Failed to initialize collections (attempt {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                else:
                    raise

        return False

    async def _create_conversations_collection(self):
        """Create conversations collection with all necessary fields"""
        schema = {
            'name': self.conversations_collection,
            'enable_nested_fields': True,
            'fields': [
                # Core fields
                {'name': 'id', 'type': 'string'},
                {'name': 'user_id', 'type': 'string', 'facet': True, 'index': True},
                {'name': 'title', 'type': 'string'},
                {'name': 'description', 'type': 'string', 'optional': True},

                # Timestamps
                {'name': 'created_at', 'type': 'int64'},
                {'name': 'updated_at', 'type': 'int64'},
                {'name': 'last_message_at', 'type': 'int64', 'optional': True},

                # Statistics
                {'name': 'message_count', 'type': 'int32'},
                {'name': 'user_message_count', 'type': 'int32', 'optional': True},
                {'name': 'assistant_message_count', 'type': 'int32', 'optional': True},
                {'name': 'total_tokens', 'type': 'int32', 'optional': True},
                {'name': 'total_cost', 'type': 'float', 'optional': True},

                # Status and metadata
                {'name': 'status', 'type': 'string', 'facet': True},  # active, archived, deleted
                {'name': 'pinned', 'type': 'bool', 'optional': True},
                {'name': 'starred', 'type': 'bool', 'optional': True},
                {'name': 'tags', 'type': 'string[]', 'optional': True, 'facet': True},

                # Preview and summary
                {'name': 'last_message_preview', 'type': 'string', 'optional': True},
                {'name': 'summary', 'type': 'string', 'optional': True},
                {'name': 'language', 'type': 'string', 'optional': True, 'facet': True},

                # Additional metadata
                {'name': 'metadata', 'type': 'object', 'optional': True}
            ],
            'default_sorting_field': 'updated_at'
        }

        await self._create_or_update_collection(schema)

    async def _create_messages_collection(self):
        """Create messages collection with all necessary fields"""
        schema = {
            'name': self.messages_collection,
            'enable_nested_fields': True,
            'fields': [
                # Core fields
                {'name': 'id', 'type': 'string'},
                {'name': 'conversation_id', 'type': 'string', 'facet': True, 'index': True},
                {'name': 'user_id', 'type': 'string', 'facet': True, 'index': True},
                {'name': 'parent_message_id', 'type': 'string', 'optional': True},  # For threading

                # Message content
                {'name': 'role', 'type': 'string', 'facet': True},  # user, assistant, system, error
                {'name': 'content', 'type': 'string'},
                {'name': 'content_type', 'type': 'string', 'optional': True, 'facet': True},  # text, code, markdown

                # Timestamps
                {'name': 'timestamp', 'type': 'int64'},
                {'name': 'edited_at', 'type': 'int64', 'optional': True},

                # Processing info
                {'name': 'intent', 'type': 'string', 'facet': True, 'optional': True},
                {'name': 'tokens', 'type': 'int32', 'optional': True},
                {'name': 'cost', 'type': 'float', 'optional': True},
                {'name': 'model', 'type': 'string', 'optional': True, 'facet': True},
                {'name': 'response_time_ms', 'type': 'int32', 'optional': True},

                # Cache and error handling
                {'name': 'cached', 'type': 'bool', 'optional': True},
                {'name': 'cache_hit', 'type': 'bool', 'optional': True},
                {'name': 'error', 'type': 'bool', 'optional': True},
                {'name': 'error_message', 'type': 'string', 'optional': True},

                # User feedback
                {'name': 'rating', 'type': 'int32', 'optional': True},  # 1-5 star rating
                {'name': 'feedback', 'type': 'string', 'optional': True},
                {'name': 'helpful', 'type': 'bool', 'optional': True},

                # Additional metadata
                {'name': 'attachments', 'type': 'object[]', 'optional': True},
                {'name': 'metadata', 'type': 'object', 'optional': True}
            ],
            'default_sorting_field': 'timestamp'
        }

        await self._create_or_update_collection(schema)

    async def _create_user_profiles_collection(self):
        """Create user profiles collection"""
        schema = {
            'name': self.user_profiles_collection,
            'enable_nested_fields': True,
            'fields': [
                # Core fields
                {'name': 'id', 'type': 'string'},  # Same as user_id
                {'name': 'user_id', 'type': 'string', 'facet': True},
                {'name': 'username', 'type': 'string', 'optional': True},
                {'name': 'email', 'type': 'string', 'optional': True},

                # Timestamps
                {'name': 'created_at', 'type': 'int64'},
                {'name': 'last_active', 'type': 'int64'},
                {'name': 'last_conversation_at', 'type': 'int64', 'optional': True},

                # Statistics
                {'name': 'total_conversations', 'type': 'int32'},
                {'name': 'active_conversations', 'type': 'int32', 'optional': True},
                {'name': 'archived_conversations', 'type': 'int32', 'optional': True},
                {'name': 'total_messages', 'type': 'int32'},
                {'name': 'total_tokens_used', 'type': 'int64', 'optional': True},
                {'name': 'total_cost', 'type': 'float', 'optional': True},

                # Usage patterns
                {'name': 'favorite_cryptos', 'type': 'string[]', 'optional': True, 'facet': True},
                {'name': 'common_intents', 'type': 'string[]', 'optional': True, 'facet': True},
                {'name': 'common_topics', 'type': 'string[]', 'optional': True, 'facet': True},
                {'name': 'preferred_language', 'type': 'string', 'optional': True},

                # Preferences
                {'name': 'preferences', 'type': 'object', 'optional': True},
                {'name': 'settings', 'type': 'object', 'optional': True},

                # Account info
                {'name': 'subscription_tier', 'type': 'string', 'optional': True, 'facet': True},
                {'name': 'account_status', 'type': 'string', 'optional': True, 'facet': True}
            ],
            'default_sorting_field': 'last_active'
        }

        await self._create_or_update_collection(schema)

    async def _create_conversation_summaries_collection(self):
        """Create conversation summaries collection for quick access"""
        schema = {
            'name': self.conversation_summaries_collection,
            'fields': [
                {'name': 'id', 'type': 'string'},
                {'name': 'conversation_id', 'type': 'string', 'facet': True},
                {'name': 'user_id', 'type': 'string', 'facet': True},
                {'name': 'summary', 'type': 'string'},
                {'name': 'key_points', 'type': 'string[]', 'optional': True},
                {'name': 'topics', 'type': 'string[]', 'optional': True, 'facet': True},
                {'name': 'sentiment', 'type': 'string', 'optional': True, 'facet': True},
                {'name': 'created_at', 'type': 'int64'},
                {'name': 'message_count_at_summary', 'type': 'int32', 'optional': True}
            ],
            'default_sorting_field': 'created_at'
        }

        await self._create_or_update_collection(schema)

    async def _create_user_preferences_collection(self):
        """Create user preferences collection"""
        schema = {
            'name': self.user_preferences_collection,
            'enable_nested_fields': True,
            'fields': [
                {'name': 'id', 'type': 'string'},
                {'name': 'user_id', 'type': 'string', 'facet': True},

                # UI Preferences
                {'name': 'theme', 'type': 'string', 'optional': True},
                {'name': 'language', 'type': 'string', 'optional': True},
                {'name': 'timezone', 'type': 'string', 'optional': True},
                {'name': 'date_format', 'type': 'string', 'optional': True},

                # Chat Preferences
                {'name': 'default_model', 'type': 'string', 'optional': True},
                {'name': 'response_style', 'type': 'string', 'optional': True},  # concise, detailed, etc.
                {'name': 'auto_save', 'type': 'bool', 'optional': True},
                {'name': 'show_timestamps', 'type': 'bool', 'optional': True},
                {'name': 'enable_markdown', 'type': 'bool', 'optional': True},

                # Notification Preferences
                {'name': 'notifications', 'type': 'object', 'optional': True},

                # Privacy Settings
                {'name': 'save_history', 'type': 'bool', 'optional': True},
                {'name': 'share_usage_data', 'type': 'bool', 'optional': True},

                # Custom settings
                {'name': 'custom_settings', 'type': 'object', 'optional': True},

                {'name': 'updated_at', 'type': 'int64'}
            ],
            'default_sorting_field': 'updated_at'
        }

        await self._create_or_update_collection(schema)

    async def _create_or_update_collection(self, schema):
        """Create collection or update if it exists"""
        collection_name = schema['name']

        try:
            # Try to create the collection
            await asyncio.to_thread(self.client.collections.create, schema)
            print(f"✅ Created collection: {collection_name}")

        except Exception as e:
            if "already exists" in str(e):
                print(f"📋 Collection {collection_name} already exists")

                # Optionally update the collection schema
                try:
                    # Get existing collection
                    existing = await asyncio.to_thread(
                        self.client.collections[collection_name].retrieve
                    )

                    # Check if update is needed
                    existing_fields = {f['name']: f for f in existing['fields']}
                    new_fields = {f['name']: f for f in schema['fields']}

                    # Add new fields that don't exist
                    for field_name, field_def in new_fields.items():
                        if field_name not in existing_fields:
                            print(f"📝 Adding new field '{field_name}' to {collection_name}")
                            # Note: Typesense doesn't support adding fields after creation
                            # You would need to recreate the collection with new schema

                except Exception as update_error:
                    print(f"⚠️ Could not check/update collection {collection_name}: {update_error}")

            else:
                print(f"❌ Error creating collection {collection_name}: {e}")
                raise

    # Enhanced methods for conversation management

    async def create_conversation(self, user_id: str, title: Optional[str] = None,
                                  metadata: Optional[Dict] = None) -> str:
        """Create a new conversation with enhanced metadata"""
        try:
            now = int(datetime.now(timezone.utc).timestamp())
            conversation_id = f"conv_{user_id}_{now}_{uuid.uuid4().hex[:6]}"

            if not title:
                title = f"Conversation {datetime.now().strftime('%Y-%m-%d %H:%M')}"

            document = {
                'id': conversation_id,
                'user_id': user_id,
                'title': title,
                'created_at': now,
                'updated_at': now,
                'message_count': 0,
                'user_message_count': 0,
                'assistant_message_count': 0,
                'total_tokens': 0,
                'total_cost': 0.0,
                'status': 'active',
                'pinned': False,
                'starred': False,
                'tags': [],
                'metadata': metadata or {}
            }

            await asyncio.to_thread(
                self.client.collections[self.conversations_collection].documents.create,
                document
            )

            # Update user profile
            await self._increment_user_conversations(user_id)

            return conversation_id

        except Exception as e:
            print(f"Error creating conversation: {e}")
            raise

    async def add_message(
            self,
            conversation_id: str,
            user_id: str,
            role: str,
            content: str,
            intent: Optional[str] = None,
            response_time_ms: Optional[int] = None,
            cached: bool = False,
            metadata: Optional[Dict] = None,
            model: Optional[str] = None,
            tokens: Optional[int] = None,
            cost: Optional[float] = None
    ) -> str:
        """Add a message with enhanced tracking"""
        try:
            now = int(datetime.now(timezone.utc).timestamp())
            message_id = f"msg_{now}_{uuid.uuid4().hex[:8]}"

            # Estimate tokens if not provided
            if tokens is None:
                tokens = len(content) // 4  # Rough estimate

            document = {
                'id': message_id,
                'conversation_id': conversation_id,
                'user_id': user_id,
                'role': role,
                'content': content,
                'content_type': 'text',
                'timestamp': now,
                'cached': cached,
                'error': False,
                'tokens': tokens,
                'metadata': metadata or {}
            }

            # Add optional fields
            if intent:
                document['intent'] = intent
            if response_time_ms:
                document['response_time_ms'] = response_time_ms
            if model:
                document['model'] = model
            if cost:
                document['cost'] = cost

            # Add message
            await asyncio.to_thread(
                self.client.collections[self.messages_collection].documents.create,
                document
            )

            # Update conversation stats and preview
            await self._update_conversation_after_message(
                conversation_id,
                role,
                content[:100],  # Preview
                tokens,
                cost
            )

            # Update user profile stats
            await self._update_user_profile(user_id, intent, tokens, cost)

            return message_id

        except Exception as e:
            print(f"Error adding message: {e}")
            raise

    async def _update_conversation_after_message(
            self,
            conversation_id: str,
            role: str,
            preview: str,
            tokens: int = 0,
            cost: float = 0.0
    ):
        """Update conversation statistics after adding a message"""
        try:
            # Get current conversation data
            conv = await asyncio.to_thread(
                self.client.collections[self.conversations_collection].documents[conversation_id].retrieve
            )

            now = int(datetime.now(timezone.utc).timestamp())

            # Prepare update
            update = {
                'updated_at': now,
                'last_message_at': now,
                'message_count': conv.get('message_count', 0) + 1,
                'last_message_preview': preview + '...' if len(preview) >= 100 else preview,
                'total_tokens': conv.get('total_tokens', 0) + tokens,
                'total_cost': conv.get('total_cost', 0.0) + cost
            }

            # Update role-specific counts
            if role == 'user':
                update['user_message_count'] = conv.get('user_message_count', 0) + 1
            elif role == 'assistant':
                update['assistant_message_count'] = conv.get('assistant_message_count', 0) + 1

            # Update conversation
            await asyncio.to_thread(
                self.client.collections[self.conversations_collection].documents[conversation_id].update,
                update
            )

        except Exception as e:
            print(f"Error updating conversation stats: {e}")

    async def _increment_user_conversations(self, user_id: str):
        """Increment user's conversation count"""
        try:
            # Try to get existing profile
            try:
                profile = await asyncio.to_thread(
                    self.client.collections[self.user_profiles_collection].documents[user_id].retrieve
                )

                # Update existing profile
                await asyncio.to_thread(
                    self.client.collections[self.user_profiles_collection].documents[user_id].update,
                    {
                        'total_conversations': profile.get('total_conversations', 0) + 1,
                        'active_conversations': profile.get('active_conversations', 0) + 1,
                        'last_conversation_at': int(datetime.now(timezone.utc).timestamp())
                    }
                )

            except:
                # Create new profile
                now = int(datetime.now(timezone.utc).timestamp())
                profile = {
                    'id': user_id,
                    'user_id': user_id,
                    'created_at': now,
                    'last_active': now,
                    'last_conversation_at': now,
                    'total_conversations': 1,
                    'active_conversations': 1,
                    'archived_conversations': 0,
                    'total_messages': 0,
                    'total_tokens_used': 0,
                    'total_cost': 0.0,
                    'favorite_cryptos': [],
                    'common_intents': [],
                    'common_topics': []
                }

                await asyncio.to_thread(
                    self.client.collections[self.user_profiles_collection].documents.create,
                    profile
                )

        except Exception as e:
            print(f"Error updating user conversations count: {e}")

    async def _update_user_profile(
            self,
            user_id: str,
            intent: Optional[str] = None,
            tokens: int = 0,
            cost: float = 0.0
    ):
        """Update user profile with usage statistics"""
        try:
            now = int(datetime.now(timezone.utc).timestamp())

            # Try to get existing profile
            try:
                profile = await asyncio.to_thread(
                    self.client.collections[self.user_profiles_collection].documents[user_id].retrieve
                )

                # Prepare update
                update = {
                    'last_active': now,
                    'total_messages': profile.get('total_messages', 0) + 1,
                    'total_tokens_used': profile.get('total_tokens_used', 0) + tokens,
                    'total_cost': profile.get('total_cost', 0.0) + cost
                }

                # Update common intents
                if intent:
                    common_intents = profile.get('common_intents', [])
                    if intent not in common_intents:
                        common_intents.append(intent)
                        # Keep only the last 20 unique intents
                        update['common_intents'] = common_intents[-20:]

                await asyncio.to_thread(
                    self.client.collections[self.user_profiles_collection].documents[user_id].update,
                    update
                )

            except:
                # Profile doesn't exist, will be created when conversation is created
                pass

        except Exception as e:
            print(f"Error updating user profile: {e}")

    # Additional utility methods

    async def update_conversation_title(self, conversation_id: str, title: str) -> bool:
        """Update conversation title"""
        try:
            await asyncio.to_thread(
                self.client.collections[self.conversations_collection].documents[conversation_id].update,
                {
                    'title': title,
                    'updated_at': int(datetime.now(timezone.utc).timestamp())
                }
            )
            return True
        except Exception as e:
            print(f"Error updating conversation title: {e}")
            return False

    async def pin_conversation(self, conversation_id: str, pinned: bool = True) -> bool:
        """Pin or unpin a conversation"""
        try:
            await asyncio.to_thread(
                self.client.collections[self.conversations_collection].documents[conversation_id].update,
                {
                    'pinned': pinned,
                    'updated_at': int(datetime.now(timezone.utc).timestamp())
                }
            )
            return True
        except Exception as e:
            print(f"Error pinning conversation: {e}")
            return False

    async def star_conversation(self, conversation_id: str, starred: bool = True) -> bool:
        """Star or unstar a conversation"""
        try:
            await asyncio.to_thread(
                self.client.collections[self.conversations_collection].documents[conversation_id].update,
                {
                    'starred': starred,
                    'updated_at': int(datetime.now(timezone.utc).timestamp())
                }
            )
            return True
        except Exception as e:
            print(f"Error starring conversation: {e}")
            return False

    async def add_conversation_tags(self, conversation_id: str, tags: List[str]) -> bool:
        """Add tags to a conversation"""
        try:
            # Get current tags
            conv = await asyncio.to_thread(
                self.client.collections[self.conversations_collection].documents[conversation_id].retrieve
            )

            current_tags = conv.get('tags', [])
            # Add new tags, avoiding duplicates
            updated_tags = list(set(current_tags + tags))

            await asyncio.to_thread(
                self.client.collections[self.conversations_collection].documents[conversation_id].update,
                {
                    'tags': updated_tags,
                    'updated_at': int(datetime.now(timezone.utc).timestamp())
                }
            )
            return True
        except Exception as e:
            print(f"Error adding conversation tags: {e}")
            return False

    async def rate_message(self, message_id: str, rating: int, feedback: Optional[str] = None) -> bool:
        """Rate a message (1-5 stars)"""
        try:
            update = {
                'rating': max(1, min(5, rating)),  # Ensure rating is between 1-5
                'helpful': rating >= 4
            }

            if feedback:
                update['feedback'] = feedback

            await asyncio.to_thread(
                self.client.collections[self.messages_collection].documents[message_id].update,
                update
            )
            return True
        except Exception as e:
            print(f"Error rating message: {e}")
            return False

    # Keep all the existing methods from the original implementation
    # (get_conversation_history, get_user_conversations, search_messages, etc.)
    # Just copy them here as they are already well-implemented

    async def get_conversation_history(
            self,
            conversation_id: str,
            limit: int = 50,
            offset: int = 0
    ) -> List[Dict]:
        """Get messages from a conversation"""
        try:
            search_parameters = {
                'q': '*',
                'filter_by': f'conversation_id:={conversation_id}',
                'sort_by': 'timestamp:asc',
                'per_page': limit,
                'page': (offset // limit) + 1
            }

            results = await asyncio.to_thread(
                self.client.collections[self.messages_collection].documents.search,
                search_parameters
            )

            return [hit['document'] for hit in results['hits']]

        except Exception as e:
            print(f"Error getting conversation history: {e}")
            return []

    async def get_user_conversations(
            self,
            user_id: str,
            limit: int = 10,
            offset: int = 0,
            status: str = 'active',
            sort_by: str = 'updated_at:desc'
    ) -> List[Dict]:
        """Get all conversations for a user with sorting options"""
        try:
            # Build filter
            filter_by = f'user_id:={user_id} && status:={status}'

            search_parameters = {
                'q': '*',
                'filter_by': filter_by,
                'sort_by': sort_by,
                'per_page': limit,
                'page': (offset // limit) + 1
            }

            results = await asyncio.to_thread(
                self.client.collections[self.conversations_collection].documents.search,
                search_parameters
            )

            return [hit['document'] for hit in results['hits']]

        except Exception as e:
            print(f"Error getting user conversations: {e}")
            return []

    async def search_messages(
            self,
            user_id: str,
            query: str,
            limit: int = 20,
            conversation_id: Optional[str] = None
    ) -> List[Dict]:
        """Search messages across conversations"""
        try:
            filter_by = f'user_id:={user_id}'
            if conversation_id:
                filter_by += f' && conversation_id:={conversation_id}'

            search_parameters = {
                'q': query,
                'query_by': 'content',
                'filter_by': filter_by,
                'sort_by': 'timestamp:desc',
                'per_page': limit
            }

            results = await asyncio.to_thread(
                self.client.collections[self.messages_collection].documents.search,
                search_parameters
            )

            return [hit['document'] for hit in results['hits']]

        except Exception as e:
            print(f"Error searching messages: {e}")
            return []

    async def get_conversation_context(
            self,
            conversation_id: str,
            limit: int = 10
    ) -> List[Dict]:
        """Get recent context for LLM from conversation"""
        try:
            messages = await self.get_conversation_history(
                conversation_id,
                limit=limit
            )

            # Format for LLM consumption
            context = []
            for msg in messages:
                if msg['role'] in ['user', 'assistant']:
                    context.append({
                        'role': msg['role'],
                        'content': msg['content']
                    })

            return context

        except Exception as e:
            print(f"Error getting conversation context: {e}")
            return []

    async def archive_conversation(self, conversation_id: str):
        """Archive a conversation"""
        try:
            # Get current conversation
            conv = await asyncio.to_thread(
                self.client.collections[self.conversations_collection].documents[conversation_id].retrieve
            )

            user_id = conv['user_id']

            # Update conversation status
            await asyncio.to_thread(
                self.client.collections[self.conversations_collection].documents[conversation_id].update,
                {
                    'status': 'archived',
                    'updated_at': int(datetime.now(timezone.utc).timestamp())
                }
            )

            # Update user profile counters
            await self._update_user_conversation_counts(user_id, -1, 1)  # -1 active, +1 archived

        except Exception as e:
            print(f"Error archiving conversation: {e}")

    async def delete_conversation(self, conversation_id: str):
        """Delete a conversation and all its messages"""
        try:
            # Get conversation details first
            conv = await asyncio.to_thread(
                self.client.collections[self.conversations_collection].documents[conversation_id].retrieve
            )
            user_id = conv['user_id']
            status = conv['status']

            # Delete all messages in batches
            deleted_count = 0
            batch_size = 250

            while True:
                search_parameters = {
                    'q': '*',
                    'filter_by': f'conversation_id:={conversation_id}',
                    'per_page': batch_size
                }

                results = await asyncio.to_thread(
                    self.client.collections[self.messages_collection].documents.search,
                    search_parameters
                )

                if not results['hits']:
                    break

                # Delete messages in this batch
                for hit in results['hits']:
                    await asyncio.to_thread(
                        self.client.collections[self.messages_collection].documents[hit['document']['id']].delete
                    )
                    deleted_count += 1

            # Delete conversation
            await asyncio.to_thread(
                self.client.collections[self.conversations_collection].documents[conversation_id].delete
            )

            # Update user profile counters
            if status == 'active':
                await self._update_user_conversation_counts(user_id, -1, 0)
            elif status == 'archived':
                await self._update_user_conversation_counts(user_id, 0, -1)

            print(f"Deleted conversation {conversation_id} with {deleted_count} messages")

        except Exception as e:
            print(f"Error deleting conversation: {e}")
            raise

    async def _update_user_conversation_counts(self, user_id: str, active_delta: int, archived_delta: int):
        """Update user's conversation counts"""
        try:
            profile = await asyncio.to_thread(
                self.client.collections[self.user_profiles_collection].documents[user_id].retrieve
            )

            update = {}
            if active_delta != 0:
                update['active_conversations'] = max(0, profile.get('active_conversations', 0) + active_delta)
            if archived_delta != 0:
                update['archived_conversations'] = max(0, profile.get('archived_conversations', 0) + archived_delta)

            if update:
                await asyncio.to_thread(
                    self.client.collections[self.user_profiles_collection].documents[user_id].update,
                    update
                )

        except Exception as e:
            print(f"Error updating user conversation counts: {e}")

    async def get_user_stats(self, user_id: str) -> Dict:
        """Get comprehensive user statistics"""
        try:
            # Get user profile
            try:
                profile = await asyncio.to_thread(
                    self.client.collections[self.user_profiles_collection].documents[user_id].retrieve
                )
            except:
                profile = {}

            # Get real-time counts
            conv_results = await asyncio.to_thread(
                self.client.collections[self.conversations_collection].documents.search,
                {
                    'q': '*',
                    'filter_by': f'user_id:={user_id}',
                    'per_page': 0
                }
            )

            msg_results = await asyncio.to_thread(
                self.client.collections[self.messages_collection].documents.search,
                {
                    'q': '*',
                    'filter_by': f'user_id:={user_id}',
                    'per_page': 0
                }
            )

            # Get additional statistics
            active_convs = await asyncio.to_thread(
                self.client.collections[self.conversations_collection].documents.search,
                {
                    'q': '*',
                    'filter_by': f'user_id:={user_id} && status:=active',
                    'per_page': 0
                }
            )

            archived_convs = await asyncio.to_thread(
                self.client.collections[self.conversations_collection].documents.search,
                {
                    'q': '*',
                    'filter_by': f'user_id:={user_id} && status:=archived',
                    'per_page': 0
                }
            )

            # Calculate average messages per conversation
            avg_messages = 0
            if conv_results['found'] > 0:
                avg_messages = msg_results['found'] / conv_results['found']

            return {
                'user_id': user_id,
                'created_at': profile.get('created_at'),
                'last_active': profile.get('last_active'),
                'total_conversations': conv_results['found'],
                'active_conversations': active_convs['found'],
                'archived_conversations': archived_convs['found'],
                'total_messages': msg_results['found'],
                'average_messages_per_conversation': round(avg_messages, 2),
                'total_tokens_used': profile.get('total_tokens_used', 0),
                'total_cost': profile.get('total_cost', 0.0),
                'favorite_cryptos': profile.get('favorite_cryptos', []),
                'common_intents': profile.get('common_intents', []),
                'common_topics': profile.get('common_topics', []),
                'subscription_tier': profile.get('subscription_tier', 'free'),
                'account_status': profile.get('account_status', 'active')
            }

        except Exception as e:
            print(f"Error getting user stats: {e}")
            return {}

    async def export_conversation(self, conversation_id: str) -> Dict:
        """Export a conversation with all messages and metadata"""
        try:
            # Get conversation details
            conversation = await asyncio.to_thread(
                self.client.collections[self.conversations_collection].documents[conversation_id].retrieve
            )

            # Get all messages (up to 10000)
            all_messages = []
            page = 1
            per_page = 250

            while len(all_messages) < 10000:  # Safety limit
                results = await asyncio.to_thread(
                    self.client.collections[self.messages_collection].documents.search,
                    {
                        'q': '*',
                        'filter_by': f'conversation_id:={conversation_id}',
                        'sort_by': 'timestamp:asc',
                        'per_page': per_page,
                        'page': page
                    }
                )

                if not results['hits']:
                    break

                all_messages.extend([hit['document'] for hit in results['hits']])

                if len(results['hits']) < per_page:
                    break

                page += 1

            # Get conversation summary if exists
            summary = None
            try:
                summary_results = await asyncio.to_thread(
                    self.client.collections[self.conversation_summaries_collection].documents.search,
                    {
                        'q': '*',
                        'filter_by': f'conversation_id:={conversation_id}',
                        'per_page': 1
                    }
                )
                if summary_results['hits']:
                    summary = summary_results['hits'][0]['document']
            except:
                pass

            return {
                'export_version': '2.0',
                'exported_at': datetime.now(timezone.utc).isoformat(),
                'conversation': conversation,
                'messages': all_messages,
                'message_count': len(all_messages),
                'summary': summary,
                'metadata': {
                    'export_format': 'json',
                    'includes_attachments': False,
                    'truncated': len(all_messages) >= 10000
                }
            }

        except Exception as e:
            print(f"Error exporting conversation: {e}")
            return {'error': str(e)}

    async def import_conversation(self, user_id: str, export_data: Dict) -> Optional[str]:
        """Import a previously exported conversation"""
        try:
            # Validate export format
            if export_data.get('export_version') not in ['1.0', '2.0']:
                raise ValueError("Unsupported export version")

            # Create new conversation with imported data
            conv_data = export_data['conversation']

            # Generate new conversation ID
            new_conv_id = f"conv_{user_id}_{int(time.time())}_{uuid.uuid4().hex[:6]}"

            # Create conversation
            conv_doc = {
                'id': new_conv_id,
                'user_id': user_id,
                'title': conv_data.get('title', 'Imported Conversation'),
                'description': f"Imported from {conv_data.get('id', 'unknown')}",
                'created_at': int(time.time()),
                'updated_at': int(time.time()),
                'message_count': len(export_data.get('messages', [])),
                'status': 'active',
                'tags': ['imported'] + conv_data.get('tags', []),
                'metadata': {
                    'imported': True,
                    'original_id': conv_data.get('id'),
                    'import_date': datetime.now(timezone.utc).isoformat()
                }
            }

            await asyncio.to_thread(
                self.client.collections[self.conversations_collection].documents.create,
                conv_doc
            )

            # Import messages
            for msg in export_data.get('messages', []):
                msg_doc = {
                    'id': f"msg_{int(time.time())}_{uuid.uuid4().hex[:8]}",
                    'conversation_id': new_conv_id,
                    'user_id': user_id,
                    'role': msg.get('role'),
                    'content': msg.get('content'),
                    'timestamp': msg.get('timestamp', int(time.time())),
                    'metadata': {
                        'imported': True,
                        'original_id': msg.get('id')
                    }
                }

                # Add optional fields
                for field in ['intent', 'tokens', 'response_time_ms', 'cached', 'error']:
                    if field in msg:
                        msg_doc[field] = msg[field]

                await asyncio.to_thread(
                    self.client.collections[self.messages_collection].documents.create,
                    msg_doc
                )

            return new_conv_id

        except Exception as e:
            print(f"Error importing conversation: {e}")
            return None

    async def generate_conversation_summary(self, conversation_id: str) -> Optional[str]:
        """Generate a summary for a conversation (placeholder for LLM integration)"""
        try:
            # Get recent messages
            messages = await self.get_conversation_history(conversation_id, limit=50)

            if len(messages) < 5:
                return None

            # This is a placeholder - in production, you'd use an LLM to generate a proper summary
            # For now, just extract key information
            topics = set()
            intents = set()

            for msg in messages:
                if msg.get('intent'):
                    intents.add(msg['intent'])
                # Simple keyword extraction (replace with proper NLP)
                if 'bitcoin' in msg['content'].lower():
                    topics.add('Bitcoin')
                if 'ethereum' in msg['content'].lower():
                    topics.add('Ethereum')
                if 'defi' in msg['content'].lower():
                    topics.add('DeFi')

            summary_doc = {
                'id': f"summary_{conversation_id}_{int(time.time())}",
                'conversation_id': conversation_id,
                'user_id': messages[0]['user_id'],
                'summary': f"Conversation about {', '.join(topics) if topics else 'cryptocurrency'}",
                'key_points': list(topics)[:5],
                'topics': list(topics),
                'sentiment': 'neutral',  # Placeholder
                'created_at': int(time.time()),
                'message_count_at_summary': len(messages)
            }

            await asyncio.to_thread(
                self.client.collections[self.conversation_summaries_collection].documents.create,
                summary_doc
            )

            return summary_doc['summary']

        except Exception as e:
            print(f"Error generating conversation summary: {e}")
            return None

    async def save_user_preferences(self, user_id: str, preferences: Dict) -> bool:
        """Save or update user preferences"""
        try:
            pref_doc = {
                'id': user_id,
                'user_id': user_id,
                'updated_at': int(time.time()),
                **preferences
            }

            # Try to update existing preferences
            try:
                await asyncio.to_thread(
                    self.client.collections[self.user_preferences_collection].documents[user_id].update,
                    pref_doc
                )
            except:
                # Create new preferences
                await asyncio.to_thread(
                    self.client.collections[self.user_preferences_collection].documents.create,
                    pref_doc
                )

            return True

        except Exception as e:
            print(f"Error saving user preferences: {e}")
            return False

    async def get_user_preferences(self, user_id: str) -> Dict:
        """Get user preferences"""
        try:
            prefs = await asyncio.to_thread(
                self.client.collections[self.user_preferences_collection].documents[user_id].retrieve
            )
            return prefs
        except:
            # Return default preferences
            return {
                'theme': 'dark',
                'language': 'en',
                'timezone': 'UTC',
                'auto_save': True,
                'show_timestamps': True,
                'enable_markdown': True,
                'save_history': True
            }

    async def health_check(self) -> bool:
        """Check if Typesense is accessible"""
        try:
            return await asyncio.to_thread(self.client.operations.is_healthy)
        except Exception as e:
            print(f"Typesense health check failed: {e}")
            return False

    async def get_collection_stats(self) -> Dict:
        """Get statistics about all collections"""
        try:
            stats = {}

            for collection_name in [
                self.conversations_collection,
                self.messages_collection,
                self.user_profiles_collection,
                self.conversation_summaries_collection,
                self.user_preferences_collection
            ]:
                try:
                    coll_info = await asyncio.to_thread(
                        self.client.collections[collection_name].retrieve
                    )
                    stats[collection_name] = {
                        'num_documents': coll_info.get('num_documents', 0),
                        'created_at': coll_info.get('created_at', 0)
                    }
                except:
                    stats[collection_name] = {'error': 'Collection not found'}

            return stats

        except Exception as e:
            print(f"Error getting collection stats: {e}")
            return {}
