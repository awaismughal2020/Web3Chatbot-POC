import bcrypt
import jwt
import time
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Tuple
import secrets
from utils.typesense_client import TypesenseClient
from config import settings
import asyncio


class AuthService:
    def __init__(self):
        self.typesense = TypesenseClient()
        self.secret_key = settings.AUTH_SECRET_KEY if hasattr(settings,
                                                              'AUTH_SECRET_KEY') else self._generate_secret_key()
        self.token_expiry_hours = 24 * 7  # 7 days

    def _generate_secret_key(self):
        """Generate a secure secret key if not provided"""
        return secrets.token_urlsafe(32)

    async def initialize(self):
        """Initialize authentication collections in Typesense"""
        try:
            # Create users collection
            users_schema = {
                'name': 'users',
                'enable_nested_fields': True,
                'fields': [
                    {'name': 'id', 'type': 'string'},  # user_id
                    {'name': 'email', 'type': 'string', 'facet': True},
                    {'name': 'name', 'type': 'string'},
                    {'name': 'password_hash', 'type': 'string'},
                    {'name': 'created_at', 'type': 'int64'},
                    {'name': 'last_login', 'type': 'int64', 'optional': True},
                    {'name': 'is_active', 'type': 'bool'},
                    {'name': 'is_verified', 'type': 'bool', 'optional': True},
                    {'name': 'verification_token', 'type': 'string', 'optional': True},
                    {'name': 'reset_token', 'type': 'string', 'optional': True},
                    {'name': 'reset_token_expires', 'type': 'int64', 'optional': True},
                    {'name': 'metadata', 'type': 'object', 'optional': True}
                ],
                'default_sorting_field': 'created_at'
            }

            await self._create_or_update_collection(users_schema)

            # Create sessions collection for tracking active sessions
            sessions_schema = {
                'name': 'sessions',
                'fields': [
                    {'name': 'id', 'type': 'string'},  # session_id
                    {'name': 'user_id', 'type': 'string', 'facet': True},
                    {'name': 'token', 'type': 'string'},
                    {'name': 'ip_address', 'type': 'string', 'optional': True},
                    {'name': 'user_agent', 'type': 'string', 'optional': True},
                    {'name': 'created_at', 'type': 'int64'},
                    {'name': 'expires_at', 'type': 'int64'},
                    {'name': 'last_activity', 'type': 'int64'},
                    {'name': 'is_active', 'type': 'bool'}
                ],
                'default_sorting_field': 'created_at'
            }

            await self._create_or_update_collection(sessions_schema)

            print("✅ Authentication collections initialized")
            return True

        except Exception as e:
            print(f"❌ Error initializing auth collections: {e}")
            return False

    async def _create_or_update_collection(self, schema):
        """Create collection or update if exists"""
        try:
            await asyncio.to_thread(
                self.typesense.client.collections.create,
                schema
            )
            print(f"✅ Created collection: {schema['name']}")
        except Exception as e:
            if "already exists" in str(e):
                print(f"📋 Collection {schema['name']} already exists")
            else:
                raise

    def _hash_password(self, password: str) -> str:
        """Hash password using bcrypt"""
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

    def _verify_password(self, password: str, hashed: str) -> bool:
        """Verify password against hash"""
        return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

    def _generate_token(self, user_id: str, email: str, name: str) -> str:
        """Generate JWT token"""
        payload = {
            'user_id': user_id,
            'email': email,
            'name': name,
            'exp': datetime.now(timezone.utc) + timedelta(hours=self.token_expiry_hours),
            'iat': datetime.now(timezone.utc)
        }

        return jwt.encode(payload, self.secret_key, algorithm='HS256')

    def verify_token(self, token: str) -> Optional[Dict]:
        """Verify JWT token and return payload"""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=['HS256'])
            return payload
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None

    async def signup(self, name: str, email: str, password: str) -> Tuple[bool, Dict]:
        """Create new user account"""
        try:
            # Check if email already exists
            search_result = await asyncio.to_thread(
                self.typesense.client.collections['users'].documents.search,
                {
                    'q': email,
                    'query_by': 'email',
                    'filter_by': f'email:={email}'
                }
            )

            if search_result['found'] > 0:
                return False, {'error': 'Email already registered'}

            # Create user
            now = int(datetime.now(timezone.utc).timestamp())
            user_id = f"user_{email.replace('@', '_').replace('.', '_')}_{now}"

            user_doc = {
                'id': user_id,
                'email': email,
                'name': name,
                'password_hash': self._hash_password(password),
                'created_at': now,
                'is_active': True,
                'is_verified': False,
                'verification_token': secrets.token_urlsafe(32)
            }

            await asyncio.to_thread(
                self.typesense.client.collections['users'].documents.create,
                user_doc
            )

            # Create initial user profile in user_profiles collection
            profile_doc = {
                'id': user_id,
                'user_id': user_id,
                'username': name,
                'email': email,
                'created_at': now,
                'last_active': now,
                'total_conversations': 0,
                'total_messages': 0,
                'total_tokens_used': 0,
                'total_cost': 0.0,
                'favorite_cryptos': [],
                'common_intents': [],
                'common_topics': [],
                'subscription_tier': 'free',
                'account_status': 'active'
            }

            try:
                await asyncio.to_thread(
                    self.typesense.client.collections['user_profiles'].documents.create,
                    profile_doc
                )
            except Exception as e:
                print(f"Warning: Could not create user profile: {e}")

            return True, {
                'message': 'Account created successfully',
                'user_id': user_id,
                'email': email,
                'name': name
            }

        except Exception as e:
            print(f"Error creating user: {e}")
            return False, {'error': 'Failed to create account'}

    async def login(self, email: str, password: str, ip_address: str = None, user_agent: str = None) -> Tuple[
        bool, Dict]:
        """Authenticate user and create session"""
        try:
            # Find user by email
            search_result = await asyncio.to_thread(
                self.typesense.client.collections['users'].documents.search,
                {
                    'q': email,
                    'query_by': 'email',
                    'filter_by': f'email:={email}'
                }
            )

            if search_result['found'] == 0:
                return False, {'error': 'Invalid email or password'}

            user = search_result['hits'][0]['document']

            # Verify password
            if not self._verify_password(password, user['password_hash']):
                return False, {'error': 'Invalid email or password'}

            # Check if account is active
            if not user.get('is_active', True):
                return False, {'error': 'Account is disabled'}

            # Generate token
            token = self._generate_token(user['id'], user['email'], user['name'])

            # Create session
            now = int(datetime.now(timezone.utc).timestamp())
            session_id = f"session_{user['id']}_{now}"
            expires_at = now + (self.token_expiry_hours * 3600)

            session_doc = {
                'id': session_id,
                'user_id': user['id'],
                'token': token,
                'ip_address': ip_address or 'unknown',
                'user_agent': user_agent or 'unknown',
                'created_at': now,
                'expires_at': expires_at,
                'last_activity': now,
                'is_active': True
            }

            await asyncio.to_thread(
                self.typesense.client.collections['sessions'].documents.create,
                session_doc
            )

            # Update last login
            await asyncio.to_thread(
                self.typesense.client.collections['users'].documents[user['id']].update,
                {'last_login': now}
            )

            return True, {
                'token': token,
                'user': {
                    'id': user['id'],
                    'email': user['email'],
                    'name': user['name'],
                    'created_at': user['created_at']
                }
            }

        except Exception as e:
            print(f"Error during login: {e}")
            return False, {'error': 'Login failed'}

    async def logout(self, token: str) -> bool:
        """Logout user by invalidating session"""
        try:
            # Find session by token
            search_result = await asyncio.to_thread(
                self.typesense.client.collections['sessions'].documents.search,
                {
                    'q': token,
                    'query_by': 'token',
                    'filter_by': f'token:={token} && is_active:=true'
                }
            )

            if search_result['found'] > 0:
                session = search_result['hits'][0]['document']

                # Deactivate session
                await asyncio.to_thread(
                    self.typesense.client.collections['sessions'].documents[session['id']].update,
                    {'is_active': False}
                )

            return True

        except Exception as e:
            print(f"Error during logout: {e}")
            return False

    async def get_user_by_token(self, token: str) -> Optional[Dict]:
        """Get user info from token"""
        try:
            # Verify token
            payload = self.verify_token(token)
            if not payload:
                return None

            # Check if session is active
            search_result = await asyncio.to_thread(
                self.typesense.client.collections['sessions'].documents.search,
                {
                    'q': token,
                    'query_by': 'token',
                    'filter_by': f'token:={token} && is_active:=true'
                }
            )

            if search_result['found'] == 0:
                return None

            session = search_result['hits'][0]['document']

            # Check if session expired
            if session['expires_at'] < int(datetime.now(timezone.utc).timestamp()):
                # Deactivate expired session
                await asyncio.to_thread(
                    self.typesense.client.collections['sessions'].documents[session['id']].update,
                    {'is_active': False}
                )
                return None

            # Update last activity
            await asyncio.to_thread(
                self.typesense.client.collections['sessions'].documents[session['id']].update,
                {'last_activity': int(datetime.now(timezone.utc).timestamp())}
            )

            # Get user data
            user_doc = await asyncio.to_thread(
                self.typesense.client.collections['users'].documents[payload['user_id']].retrieve
            )

            return {
                'id': user_doc['id'],
                'email': user_doc['email'],
                'name': user_doc['name'],
                'created_at': user_doc['created_at']
            }

        except Exception as e:
            print(f"Error getting user by token: {e}")
            return None

    async def change_password(self, user_id: str, old_password: str, new_password: str) -> Tuple[bool, Dict]:
        """Change user password"""
        try:
            # Get user
            user = await asyncio.to_thread(
                self.typesense.client.collections['users'].documents[user_id].retrieve
            )

            # Verify old password
            if not self._verify_password(old_password, user['password_hash']):
                return False, {'error': 'Current password is incorrect'}

            # Update password
            new_hash = self._hash_password(new_password)
            await asyncio.to_thread(
                self.typesense.client.collections['users'].documents[user_id].update,
                {'password_hash': new_hash}
            )

            # Invalidate all existing sessions
            search_result = await asyncio.to_thread(
                self.typesense.client.collections['sessions'].documents.search,
                {
                    'q': '*',
                    'filter_by': f'user_id:={user_id} && is_active:=true',
                    'per_page': 100
                }
            )

            for hit in search_result['hits']:
                await asyncio.to_thread(
                    self.typesense.client.collections['sessions'].documents[hit['document']['id']].update,
                    {'is_active': False}
                )

            return True, {'message': 'Password changed successfully'}

        except Exception as e:
            print(f"Error changing password: {e}")
            return False, {'error': 'Failed to change password'}

    async def request_password_reset(self, email: str) -> Tuple[bool, Dict]:
        """Generate password reset token"""
        try:
            # Find user by email
            search_result = await asyncio.to_thread(
                self.typesense.client.collections['users'].documents.search,
                {
                    'q': email,
                    'query_by': 'email',
                    'filter_by': f'email:={email}'
                }
            )

            if search_result['found'] == 0:
                return False, {'error': 'Email not found'}

            user = search_result['hits'][0]['document']

            # Generate reset token
            reset_token = secrets.token_urlsafe(32)
            reset_expires = int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp())

            await asyncio.to_thread(
                self.typesense.client.collections['users'].documents[user['id']].update,
                {
                    'reset_token': reset_token,
                    'reset_token_expires': reset_expires
                }
            )

            return True, {
                'message': 'Password reset token generated',
                'token': reset_token,
                'email': email
            }

        except Exception as e:
            print(f"Error requesting password reset: {e}")
            return False, {'error': 'Failed to generate reset token'}

    async def reset_password(self, token: str, new_password: str) -> Tuple[bool, Dict]:
        """Reset password using token"""
        try:
            # Find user by reset token
            search_result = await asyncio.to_thread(
                self.typesense.client.collections['users'].documents.search,
                {
                    'q': token,
                    'query_by': 'reset_token',
                    'filter_by': f'reset_token:={token}'
                }
            )

            if search_result['found'] == 0:
                return False, {'error': 'Invalid reset token'}

            user = search_result['hits'][0]['document']

            # Check if token expired
            if user.get('reset_token_expires', 0) < int(datetime.now(timezone.utc).timestamp()):
                return False, {'error': 'Reset token has expired'}

            # Update password
            new_hash = self._hash_password(new_password)
            await asyncio.to_thread(
                self.typesense.client.collections['users'].documents[user['id']].update,
                {
                    'password_hash': new_hash,
                    'reset_token': None,
                    'reset_token_expires': None
                }
            )

            # Invalidate all sessions
            search_result = await asyncio.to_thread(
                self.typesense.client.collections['sessions'].documents.search,
                {
                    'q': '*',
                    'filter_by': f'user_id:={user["id"]} && is_active:=true',
                    'per_page': 100
                }
            )

            for hit in search_result['hits']:
                await asyncio.to_thread(
                    self.typesense.client.collections['sessions'].documents[hit['document']['id']].update,
                    {'is_active': False}
                )

            return True, {'message': 'Password reset successfully'}

        except Exception as e:
            print(f"Error resetting password: {e}")
            return False, {'error': 'Failed to reset password'}

    async def cleanup_expired_sessions(self):
        """Clean up expired sessions"""
        try:
            now = int(datetime.now(timezone.utc).timestamp())

            # Find expired sessions
            search_result = await asyncio.to_thread(
                self.typesense.client.collections['sessions'].documents.search,
                {
                    'q': '*',
                    'filter_by': f'expires_at:<{now} && is_active:=true',
                    'per_page': 100
                }
            )

            # Deactivate expired sessions
            for hit in search_result['hits']:
                await asyncio.to_thread(
                    self.typesense.client.collections['sessions'].documents[hit['document']['id']].update,
                    {'is_active': False}
                )

            print(f"Cleaned up {search_result['found']} expired sessions")

        except Exception as e:
            print(f"Error cleaning up sessions: {e}")
