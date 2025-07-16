"""
Context Handler Utility - utils/context_handler.py
Place this file in utils/context_handler.py
"""

import asyncio
import json
import time
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timezone
import re
from dataclasses import dataclass
from enum import Enum


class MessagePriority(Enum):
    CRITICAL = 1  # System messages, current query
    HIGH = 2  # Recent messages, price queries
    MEDIUM = 3  # Relevant context, similar topics
    LOW = 4  # Older messages, general chat


@dataclass
class ContextMessage:
    role: str
    content: str
    timestamp: int
    priority: MessagePriority
    tokens: int
    intent: Optional[str] = None
    relevance_score: float = 0.0
    message_id: Optional[str] = None


class ContextHandler:
    def __init__(self, model_name: str = "meta-llama/llama-4-maverick-17b-128e-instruct"):
        self.model_name = model_name

        # Model-specific configurations
        self.model_configs = {
            "meta-llama/llama-4-maverick-17b-128e-instruct": {
                "max_context_tokens": 128000,  # 128K context window
                "max_output_tokens": 4096,  # Reserve for response
                "chars_per_token": 4,  # Rough estimate
                "speed_optimized": True
            },
            "meta-llama/llama-4-scout-17b-16e-instruct": {
                "max_context_tokens": 16000,
                "max_output_tokens": 1000,
                "chars_per_token": 4,
                "speed_optimized": True
            }
        }

        self.config = self.model_configs.get(model_name,
                                             self.model_configs["meta-llama/llama-4-maverick-17b-128e-instruct"])

        # Context management settings
        self.max_input_tokens = self.config["max_context_tokens"] - self.config["max_output_tokens"]
        self.system_prompt_tokens = 200  # Estimate for system prompt
        self.safety_buffer = 500  # Token buffer for safety

        # Available tokens for conversation history
        self.available_context_tokens = self.max_input_tokens - self.system_prompt_tokens - self.safety_buffer

        # Context optimization settings
        self.min_recent_messages = 6  # Always include last 6 messages
        self.max_recent_messages = 20  # Don't exceed 20 recent messages
        self.relevance_threshold = 0.3  # Minimum relevance score to include

        # Performance tracking
        self.context_stats = {
            'total_requests': 0,
            'avg_context_tokens': 0,
            'avg_processing_time': 0,
            'cache_hits': 0
        }

        # Simple cache for context chunks
        self.context_cache = {}
        self.cache_ttl = 300  # 5 minutes

    def estimate_tokens(self, text: str) -> int:
        """Fast token estimation"""
        return max(1, len(text) // self.config["chars_per_token"])

    def calculate_relevance_score(self, message: Dict, current_query: str, conversation_topics: List[str]) -> float:
        """Calculate relevance score for context inclusion"""
        score = 0.0
        content = message.get('content', '').lower()
        current_query_lower = current_query.lower()

        # Time-based relevance (recent messages are more relevant)
        message_age = time.time() - message.get('timestamp', 0)
        if message_age < 300:  # Last 5 minutes
            score += 0.4
        elif message_age < 3600:  # Last hour
            score += 0.3
        elif message_age < 86400:  # Last day
            score += 0.2
        else:
            score += 0.1

        # Content similarity (simple keyword matching)
        query_words = set(current_query_lower.split())
        content_words = set(content.split())

        if query_words & content_words:
            overlap = len(query_words & content_words) / len(query_words | content_words)
            score += overlap * 0.5

        # Intent-based relevance
        message_intent = message.get('intent', '')
        if message_intent in ['price_query', 'web3_chat']:
            score += 0.3

        # Topic continuity
        for topic in conversation_topics:
            if topic.lower() in content:
                score += 0.2

        # Prioritize user questions and assistant responses
        if message.get('role') == 'user':
            score += 0.1
        elif message.get('role') == 'assistant' and len(content) > 50:
            score += 0.1

        return min(1.0, score)

    def extract_conversation_topics(self, messages: List[Dict]) -> List[str]:
        """Extract main topics from conversation"""
        topics = []
        crypto_keywords = ['bitcoin', 'ethereum', 'btc', 'eth', 'defi', 'nft', 'crypto', 'blockchain']

        for message in messages[-10:]:  # Look at recent messages
            content = message.get('content', '').lower()
            for keyword in crypto_keywords:
                if keyword in content and keyword not in topics:
                    topics.append(keyword)

        return topics[:5]  # Return top 5 topics

    def prioritize_messages(self, messages: List[Dict], current_query: str) -> List[ContextMessage]:
        """Convert and prioritize messages for context"""
        conversation_topics = self.extract_conversation_topics(messages)
        context_messages = []

        for msg in messages:
            if not msg.get('content'):
                continue

            # Calculate relevance
            relevance = self.calculate_relevance_score(msg, current_query, conversation_topics)

            # Determine priority
            priority = MessagePriority.MEDIUM

            # Recent messages get higher priority
            if len(messages) - messages.index(msg) <= 3:
                priority = MessagePriority.HIGH

            # Price queries and Web3 topics get higher priority
            if msg.get('intent') in ['price_query', 'web3_chat']:
                priority = MessagePriority.HIGH

            # Very relevant messages get high priority
            if relevance > 0.7:
                priority = MessagePriority.HIGH

            context_msg = ContextMessage(
                role=msg.get('role'),
                content=msg.get('content'),
                timestamp=msg.get('timestamp', 0),
                priority=priority,
                tokens=self.estimate_tokens(msg.get('content', '')),
                intent=msg.get('intent'),
                relevance_score=relevance,
                message_id=msg.get('id')
            )

            context_messages.append(context_msg)

        # Sort by priority and relevance
        context_messages.sort(key=lambda x: (x.priority.value, -x.relevance_score, -x.timestamp))

        return context_messages

    def build_optimized_context(self, messages: List[Dict], current_query: str) -> List[Dict]:
        """Build optimized context that fits within token limits"""
        start_time = time.time()

        # Quick return for empty messages
        if not messages:
            return []

        # Check cache first
        cache_key = f"{hash(str(messages[-5:]))}{hash(current_query)}"
        if cache_key in self.context_cache:
            cache_entry = self.context_cache[cache_key]
            if time.time() - cache_entry['timestamp'] < self.cache_ttl:
                self.context_stats['cache_hits'] += 1
                return cache_entry['context']

        # Prioritize messages
        prioritized_messages = self.prioritize_messages(messages, current_query)

        # Build context with token budget
        selected_messages = []
        total_tokens = 0

        # Always include the most recent messages (for continuity)
        recent_count = 0
        for msg in reversed(prioritized_messages):
            if recent_count >= self.min_recent_messages:
                break

            if msg.priority in [MessagePriority.HIGH, MessagePriority.CRITICAL]:
                if total_tokens + msg.tokens <= self.available_context_tokens:
                    selected_messages.append(msg)
                    total_tokens += msg.tokens
                    recent_count += 1

        # Add more messages based on relevance and priority
        for msg in prioritized_messages:
            if msg in selected_messages:
                continue

            if len(selected_messages) >= self.max_recent_messages:
                break

            if msg.relevance_score < self.relevance_threshold:
                continue

            if total_tokens + msg.tokens <= self.available_context_tokens:
                selected_messages.append(msg)
                total_tokens += msg.tokens

        # Sort selected messages by timestamp for chronological order
        selected_messages.sort(key=lambda x: x.timestamp)

        # Convert to LLM format
        context = []
        for msg in selected_messages:
            if msg.role in ['user', 'assistant']:
                context.append({
                    'role': msg.role,
                    'content': msg.content
                })

        # Update stats
        processing_time = time.time() - start_time
        self.context_stats['total_requests'] += 1
        self.context_stats['avg_context_tokens'] = (
                (self.context_stats['avg_context_tokens'] * (self.context_stats['total_requests'] - 1) + total_tokens)
                / self.context_stats['total_requests']
        )
        self.context_stats['avg_processing_time'] = (
                (self.context_stats['avg_processing_time'] * (
                            self.context_stats['total_requests'] - 1) + processing_time)
                / self.context_stats['total_requests']
        )

        # Cache the result
        self.context_cache[cache_key] = {
            'context': context,
            'timestamp': time.time(),
            'tokens': total_tokens
        }

        # Clean old cache entries
        if len(self.context_cache) > 100:
            self.clean_cache()

        return context

    def clean_cache(self):
        """Clean old cache entries"""
        current_time = time.time()
        to_remove = []

        for key, entry in self.context_cache.items():
            if current_time - entry['timestamp'] > self.cache_ttl:
                to_remove.append(key)

        for key in to_remove:
            del self.context_cache[key]

    def build_smart_context(self, messages: List[Dict], current_query: str, system_prompt: str) -> List[Dict]:
        """Build smart context with system prompt optimization"""
        # Get optimized conversation context
        context = self.build_optimized_context(messages, current_query)

        # Build final message list
        final_messages = [
            {"role": "system", "content": system_prompt}
        ]

        # Add conversation context
        final_messages.extend(context)

        # Add current query
        final_messages.append({
            "role": "user",
            "content": current_query
        })

        # Final token check and truncation if needed
        total_tokens = sum(self.estimate_tokens(msg['content']) for msg in final_messages)

        if total_tokens > self.max_input_tokens:
            # Emergency truncation - remove oldest context messages
            while len(final_messages) > 2 and total_tokens > self.max_input_tokens:
                # Remove the oldest context message (keep system and current query)
                if len(final_messages) > 2:
                    removed = final_messages.pop(1)
                    total_tokens -= self.estimate_tokens(removed['content'])

        return final_messages

    def get_context_summary(self, messages: List[Dict], current_query: str) -> Dict:
        """Get summary of context building process"""
        context = self.build_optimized_context(messages, current_query)

        total_tokens = sum(self.estimate_tokens(msg['content']) for msg in context)

        return {
            'total_messages_available': len(messages),
            'messages_selected': len(context),
            'estimated_tokens': total_tokens,
            'token_budget': self.available_context_tokens,
            'utilization_percent': (total_tokens / self.available_context_tokens) * 100,
            'processing_stats': self.context_stats.copy()
        }

    def clear_cache(self):
        """Clear context cache"""
        self.context_cache.clear()

    def get_performance_stats(self) -> Dict:
        """Get performance statistics"""
        return {
            'context_stats': self.context_stats.copy(),
            'cache_size': len(self.context_cache),
            'model_config': self.config.copy(),
            'available_context_tokens': self.available_context_tokens
        }
    