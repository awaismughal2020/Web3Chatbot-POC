import asyncio
import aiohttp
import json
from typing import List, Dict, AsyncGenerator
from config import settings


class GroqClient:
    def __init__(self):
        self.api_key = settings.GROQ_API_KEY
        self.base_url = "https://api.groq.com/openai/v1"
        self.model = "meta-llama/llama-4-scout-17b-16e-instruct"  # Fast Groq model
        self.session = None

    async def _get_session(self):
        """Get or create HTTP session"""
        if not self.session:
            timeout = aiohttp.ClientTimeout(total=30, connect=10)
            self.session = aiohttp.ClientSession(
                timeout=timeout,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }
            )
        return self.session

    async def chat_completion(self, messages: List[Dict], max_tokens: int = 1000, temperature: float = 0.7) -> str:
        """Get chat completion from Groq"""
        try:
            session = await self._get_session()

            payload = {
                "model": self.model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "stream": False
            }

            async with session.post(f"{self.base_url}/chat/completions", json=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    return data["choices"][0]["message"]["content"].strip()
                else:
                    error_text = await response.text()
                    print(f"Groq API error {response.status}: {error_text}")
                    return "I'm having trouble processing your request right now."

        except asyncio.TimeoutError:
            print("Groq API timeout")
            return "Response timeout. Please try again."
        except Exception as e:
            print(f"Groq API error: {e}")
            return "I'm experiencing technical difficulties. Please try again."

    async def stream_chat_completion(self, messages: List[Dict], max_tokens: int = 1000, temperature: float = 0.7) -> \
    AsyncGenerator[str, None]:
        """Stream chat completion from Groq"""
        try:
            session = await self._get_session()

            payload = {
                "model": self.model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "stream": True
            }

            async with session.post(f"{self.base_url}/chat/completions", json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    print(f"Groq API error {response.status}: {error_text}")
                    yield "I'm having trouble processing your request right now."
                    return

                async for line in response.content:
                    line_str = line.decode('utf-8').strip()

                    if not line_str:
                        continue

                    if line_str.startswith('data: '):
                        data_str = line_str[6:]  # Remove 'data: ' prefix

                        if data_str == '[DONE]':
                            break

                        try:
                            data = json.loads(data_str)
                            if 'choices' in data and len(data['choices']) > 0:
                                delta = data['choices'][0].get('delta', {})
                                if 'content' in delta:
                                    yield delta['content']
                        except json.JSONDecodeError:
                            continue

        except asyncio.TimeoutError:
            yield "Response timeout. Please try again."
        except Exception as e:
            print(f"Groq streaming error: {e}")
            yield "I'm experiencing technical difficulties."

    async def get_embedding(self, text: str) -> List[float]:
        """Get text embedding from Groq (if available)"""
        # Note: Groq might not have embedding endpoints yet
        # This is a placeholder for future functionality
        try:
            # For now, return a simple hash-based pseudo-embedding
            import hashlib
            hash_obj = hashlib.md5(text.encode())
            hash_hex = hash_obj.hexdigest()

            # Convert to pseudo-embedding vector
            embedding = []
            for i in range(0, len(hash_hex), 2):
                val = int(hash_hex[i:i + 2], 16) / 255.0
                embedding.append(val)

            # Pad to 384 dimensions
            while len(embedding) < 384:
                embedding.append(0.0)

            return embedding[:384]

        except Exception as e:
            print(f"Embedding error: {e}")
            return [0.0] * 384

    async def close(self):
        """Close the HTTP session"""
        if self.session:
            await self.session.close()
            self.session = None

    async def health_check(self) -> bool:
        """Check if Groq API is accessible"""
        try:
            test_messages = [
                {"role": "user", "content": "Hello"}
            ]

            response = await self.chat_completion(test_messages, max_tokens=10)
            return len(response) > 0

        except Exception as e:
            print(f"Groq health check failed: {e}")
            return False

    def get_available_models(self) -> List[str]:
        """Get list of available Groq models"""
        return [
            "meta-llama/llama-4-scout-17b-16e-instruct",  # Very fast, good quality
            "llama2-70b-4096",  # Good quality, moderate speed
            "gemma-7b-it"  # Lightweight, very fast
        ]

    async def list_models(self) -> Dict:
        """List available models from Groq API"""
        try:
            session = await self._get_session()

            async with session.get(f"{self.base_url}/models") as response:
                if response.status == 200:
                    return await response.json()
                else:
                    return {"error": f"HTTP {response.status}"}

        except Exception as e:
            return {"error": str(e)}

    def estimate_tokens(self, text: str) -> int:
        """Rough estimation of token count"""
        # Simple approximation: ~4 characters per token
        return len(text) // 4

    def truncate_messages(self, messages: List[Dict], max_tokens: int = 30000) -> List[Dict]:
        """Truncate messages to fit within token limit"""
        total_tokens = 0
        truncated_messages = []

        # Always keep system message
        if messages and messages[0].get("role") == "system":
            truncated_messages.append(messages[0])
            total_tokens += self.estimate_tokens(messages[0]["content"])
            messages = messages[1:]

        # Add messages from the end (most recent first)
        for message in reversed(messages):
            message_tokens = self.estimate_tokens(message["content"])
            if total_tokens + message_tokens > max_tokens:
                break

            truncated_messages.insert(-1 if truncated_messages and truncated_messages[0].get("role") == "system" else 0,
                                      message)
            total_tokens += message_tokens

        return truncated_messages
