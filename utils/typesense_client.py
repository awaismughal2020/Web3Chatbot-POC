import asyncio
import typesense
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone
import json
import hashlib
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from config import settings


class TypesenseClient:
    def __init__(self):
        self.client = typesense.Client({
            'nodes': [{
                'host': settings.TYPESENSE_HOST,
                'port': settings.TYPESENSE_PORT,
                'protocol': settings.TYPESENSE_PROTOCOL
            }],
            'api_key': settings.TYPESENSE_API_KEY,
            'connection_timeout_seconds': 5.0
        })

        if self.client:
            self.client.operations.is_healthy()

        self.conversations_collection = 'conversations'
        self.messages_collection = 'messages'
        self.user_profiles_collection = 'user_profiles'

    async def initialize_collections(self):
        """Create Typesense collections for chat history"""
        max_retries = 5
        retry_delay = 2

        for attempt in range(max_retries):
            try:
                # Check if Typesense is reachable
                health = self.client.operations.is_healthy()
                if not health:
                    print(f"⏳ Waiting for Typesense to be ready... (attempt {attempt + 1}/{max_retries})")
                    await asyncio.sleep(retry_delay)
                    continue

                # Create conversations collection
                conversations_schema = {
                    'name': self.conversations_collection,
                    'fields': [
                        {'name': 'id', 'type': 'string'},
                        {'name': 'user_id', 'type': 'string', 'facet': True},
                        {'name': 'title', 'type': 'string'},
                        {'name': 'summary', 'type': 'string', 'optional': True},
                        {'name': 'created_at', 'type': 'int64'},
                        {'name': 'updated_at', 'type': 'int64'},
                        {'name': 'message_count', 'type': 'int32'},
                        {'name': 'total_tokens', 'type': 'int32', 'optional': True},
                        {'name': 'tags', 'type': 'string[]', 'optional': True, 'facet': True},
                        {'name': 'status', 'type': 'string', 'facet': True}  # active, archived
                    ],
                    'default_sorting_field': 'updated_at'
                }

                # Create messages collection
                messages_schema = {
                    'name': self.messages_collection,
                    'enable_nested_fields': True,
                    'fields': [
                        {'name': 'id', 'type': 'string'},
                        {'name': 'conversation_id', 'type': 'string', 'facet': True},
                        {'name': 'user_id', 'type': 'string', 'facet': True},
                        {'name': 'role', 'type': 'string', 'facet': True},  # user, assistant, system
                        {'name': 'content', 'type': 'string'},
                        {'name': 'intent', 'type': 'string', 'facet': True, 'optional': True},
                        {'name': 'timestamp', 'type': 'int64'},
                        {'name': 'tokens', 'type': 'int32', 'optional': True},
                        {'name': 'response_time_ms', 'type': 'int32', 'optional': True},
                        {'name': 'cached', 'type': 'bool', 'optional': True},
                        {'name': 'error', 'type': 'bool', 'optional': True},
                        {'name': 'metadata', 'type': 'object', 'optional': True}
                    ],
                    'default_sorting_field': 'timestamp'
                }

                # Create user profiles collection
                user_profiles_schema = {
                    'name': self.user_profiles_collection,
                    'enable_nested_fields': True,
                    'fields': [
                        {'name': 'id', 'type': 'string'},
                        {'name': 'user_id', 'type': 'string', 'facet': True},
                        {'name': 'created_at', 'type': 'int64'},
                        {'name': 'last_active', 'type': 'int64'},
                        {'name': 'total_messages', 'type': 'int32'},
                        {'name': 'total_conversations', 'type': 'int32'},
                        {'name': 'preferences', 'type': 'object', 'optional': True},
                        {'name': 'favorite_cryptos', 'type': 'string[]', 'optional': True, 'facet': True},
                        {'name': 'common_intents', 'type': 'string[]', 'optional': True, 'facet': True}
                    ],
                    'default_sorting_field': 'last_active'
                }

                # Try to create collections
                for schema in [conversations_schema, messages_schema, user_profiles_schema]:
                    try:
                        await asyncio.to_thread(self.client.collections.create, schema)
                        print(f"✅ Created Typesense collection: {schema['name']}")
                    except Exception as e:
                        if "already exists" in str(e):
                            print(f"📋 Collection {schema['name']} already exists")
                        else:
                            print(f"❌ Error creating collection {schema['name']}: {e}")

            except Exception as e:
                print(f"❌ Failed to initialize Typesense collections: {e}")
                raise

    async def create_conversation(self, user_id: str, title: str = None) -> str:
        """Create a new conversation"""
        try:
            now = int(datetime.now(timezone.utc).timestamp())
            conversation_id = f"conv_{user_id}_{now}"

            if not title:
                title = f"Conversation {datetime.now().strftime('%Y-%m-%d %H:%M')}"

            document = {
                'id': conversation_id,
                'user_id': user_id,
                'title': title,
                'created_at': now,
                'updated_at': now,
                'message_count': 0,
                'status': 'active'
            }

            await asyncio.to_thread(
                self.client.collections[self.conversations_collection].documents.create,
                document
            )

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
            metadata: Optional[Dict] = None
    ) -> str:
        """Add a message to the conversation"""
        try:
            now = int(datetime.now(timezone.utc).timestamp())
            message_id = f"msg_{conversation_id}_{now}_{role}"

            document = {
                'id': message_id,
                'conversation_id': conversation_id,
                'user_id': user_id,
                'role': role,
                'content': content,
                'timestamp': now,
                'cached': cached,
                'error': False
            }

            if intent:
                document['intent'] = intent
            if response_time_ms:
                document['response_time_ms'] = response_time_ms
            if metadata:
                document['metadata'] = metadata

            # Estimate tokens (rough approximation)
            document['tokens'] = len(content) // 4

            # Add message
            await asyncio.to_thread(
                self.client.collections[self.messages_collection].documents.create,
                document
            )

            # Update conversation
            await self._update_conversation_stats(conversation_id)

            # Update user profile
            await self._update_user_profile(user_id, intent)

            return message_id

        except Exception as e:
            print(f"Error adding message: {e}")
            raise


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
            status: str = 'active'
    ) -> List[Dict]:
        """Get all conversations for a user"""
        try:
            search_parameters = {
                'q': '*',
                'filter_by': f'user_id:={user_id} && status:={status}',
                'sort_by': 'updated_at:desc',
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


    async def _update_conversation_stats(self, conversation_id: str):
        """Update conversation statistics"""
        try:
            # Get message count
            search_parameters = {
                'q': '*',
                'filter_by': f'conversation_id:={conversation_id}',
                'per_page': 0  # Just get count
            }

            results = await asyncio.to_thread(
                self.client.collections[self.messages_collection].documents.search,
                search_parameters
            )

            message_count = results['found']
            now = int(datetime.now(timezone.utc).timestamp())

            # Update conversation
            update = {
                'updated_at': now,
                'message_count': message_count
            }

            await asyncio.to_thread(
                self.client.collections[self.conversations_collection].documents[conversation_id].update,
                update
            )

        except Exception as e:
            print(f"Error updating conversation stats: {e}")


    async def _update_user_profile(self, user_id: str, intent: Optional[str] = None):
        """Update user profile statistics"""
        try:
            now = int(datetime.now(timezone.utc).timestamp())

            # Try to get existing profile
            try:
                profile = await asyncio.to_thread(
                    self.client.collections[self.user_profiles_collection].documents[user_id].retrieve
                )

                # Update existing profile
                update = {
                    'last_active': now,
                    'total_messages': profile.get('total_messages', 0) + 1
                }

                if intent:
                    common_intents = profile.get('common_intents', [])
                    if intent not in common_intents:
                        common_intents.append(intent)
                        update['common_intents'] = common_intents[-10:]  # Keep last 10

                await asyncio.to_thread(
                    self.client.collections[self.user_profiles_collection].documents[user_id].update,
                    update
                )

            except Exception:
                # Create new profile
                profile = {
                    'id': user_id,
                    'user_id': user_id,
                    'created_at': now,
                    'last_active': now,
                    'total_messages': 1,
                    'total_conversations': 1
                }

                if intent:
                    profile['common_intents'] = [intent]

                await asyncio.to_thread(
                    self.client.collections[self.user_profiles_collection].documents.create,
                    profile
                )

        except Exception as e:
            print(f"Error updating user profile: {e}")


    async def archive_conversation(self, conversation_id: str):
        """Archive a conversation"""
        try:
            update = {
                'status': 'archived',
                'updated_at': int(datetime.now(timezone.utc).timestamp())
            }

            await asyncio.to_thread(
                self.client.collections[self.conversations_collection].documents[conversation_id].update,
                update
            )

        except Exception as e:
            print(f"Error archiving conversation: {e}")


    async def delete_conversation(self, conversation_id: str):
        """Delete a conversation and all its messages"""
        try:
            # Delete all messages
            search_parameters = {
                'q': '*',
                'filter_by': f'conversation_id:={conversation_id}',
                'per_page': 250
            }

            while True:
                results = await asyncio.to_thread(
                    self.client.collections[self.messages_collection].documents.search,
                    search_parameters
                )

                if not results['hits']:
                    break

                for hit in results['hits']:
                    await asyncio.to_thread(
                        self.client.collections[self.messages_collection].documents[hit['document']['id']].delete
                    )

            # Delete conversation
            await asyncio.to_thread(
                self.client.collections[self.conversations_collection].documents[conversation_id].delete
            )

        except Exception as e:
            print(f"Error deleting conversation: {e}")


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

            # Get conversation count
            conv_results = await asyncio.to_thread(
                self.client.collections[self.conversations_collection].documents.search,
                {
                    'q': '*',
                    'filter_by': f'user_id:={user_id}',
                    'per_page': 0
                }
            )

            # Get message count
            msg_results = await asyncio.to_thread(
                self.client.collections[self.messages_collection].documents.search,
                {
                    'q': '*',
                    'filter_by': f'user_id:={user_id}',
                    'per_page': 0
                }
            )

            return {
                'user_id': user_id,
                'created_at': profile.get('created_at'),
                'last_active': profile.get('last_active'),
                'total_conversations': conv_results['found'],
                'total_messages': msg_results['found'],
                'favorite_cryptos': profile.get('favorite_cryptos', []),
                'common_intents': profile.get('common_intents', [])
            }

        except Exception as e:
            print(f"Error getting user stats: {e}")
            return {}


    async def export_conversation(self, conversation_id: str) -> Dict:
        """Export a conversation with all messages"""
        try:
            # Get conversation details
            conversation = await asyncio.to_thread(
                self.client.collections[self.conversations_collection].documents[conversation_id].retrieve
            )

            # Get all messages
            messages = await self.get_conversation_history(conversation_id, limit=1000)

            return {
                'conversation': conversation,
                'messages': messages,
                'exported_at': datetime.now(timezone.utc).isoformat()
            }

        except Exception as e:
            print(f"Error exporting conversation: {e}")
            return {}


    async def health_check(self) -> bool:
        """Check if Typesense is accessible"""
        try:
            return await asyncio.to_thread(self.client.operations.is_healthy)
        except Exception as e:
            print(f"Typesense health check failed: {e}")
            return False
