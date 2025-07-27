# Updated intent_detector.py with Hugging Face model integration
import json
import torch
import os
import tempfile
import shutil
from pathlib import Path
from transformers import AutoTokenizer, AutoModelForSequenceClassification, pipeline
import asyncio
import re
import time
import gc


class IntentDetector:
    def __init__(self, use_fine_tuned=True, model_path="AwaisMughal1995/web3chatbot_fine_tuned_bart"):
        print("Initializing Intent Detector with storage optimization...")
        self.use_fine_tuned = use_fine_tuned
        self.model_path = model_path  # Now using Hugging Face model ID

        # Initialize model components
        self.classifier = None
        self.tokenizer = None
        self.model = None
        self.intent_to_id = {}
        self.id_to_intent = {}

        # Storage management
        self.temp_dir = None
        self.model_loaded_in_memory = False

        # Try to load fine-tuned model first, fallback to zero-shot
        if use_fine_tuned:
            try:
                self._load_fine_tuned_model()
            except Exception as e:
                print(f"Failed to load fine-tuned model: {e}")
                print("Falling back to zero-shot classification...")
                self.use_fine_tuned = False
                self._load_zero_shot_model()
        else:
            print("Using zero-shot classification...")
            self.use_fine_tuned = False
            self._load_zero_shot_model()

        # Keep your existing mappings and labels
        self.labels = [
            "asking for cryptocurrency price, market data, or current rates",
            "checking wallet balance, portfolio, or account information",
            "asking about web3 technology, blockchain, DeFi, NFTs, smart contracts, or cryptocurrency concepts",
            "general conversation, greetings, or casual chat",
            "asking about non-cryptocurrency topics like weather, food, sports, or entertainment"
        ]

        self.label_mapping = {
            "asking for cryptocurrency price, market data, or current rates": "price_query",
            "checking wallet balance, portfolio, or account information": "wallet_query",
            "asking about web3 technology, blockchain, DeFi, NFTs, smart contracts, or cryptocurrency concepts": "web3_chat",
            "general conversation, greetings, or casual chat": "general_chat",
            "asking about non-cryptocurrency topics like weather, food, sports, or entertainment": "non_web3"
        }

        # Your existing crypto mapping
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

    def _get_available_space(self, path="/tmp"):
        """Check available disk space"""
        try:
            statvfs = os.statvfs(path)
            # Available space in bytes
            available_space = statvfs.f_frsize * statvfs.f_bavail
            # Convert to GB
            available_gb = available_space / (1024 ** 3)
            return available_gb
        except Exception as e:
            print(f"Error checking disk space: {e}")
            return 0

    def _cleanup_temp_files(self):
        """Clean up temporary files"""
        try:
            if self.temp_dir and os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)
                print("✅ Cleaned up temporary files")
        except Exception as e:
            print(f"Warning: Could not clean up temp files: {e}")

    def _load_fine_tuned_model(self):
        """Load the fine-tuned model from Hugging Face Hub"""
        try:
            # Check available disk space
            available_space = self._get_available_space()
            print(f"Available disk space: {available_space:.2f} GB")

            print(f"Loading fine-tuned model from Hugging Face: {self.model_path}")

            if available_space < 2.0:  # Less than 2GB available
                print("⚠️ Low disk space detected, enabling memory-only loading...")
                # Load model directly into memory without caching
                self.tokenizer = AutoTokenizer.from_pretrained(
                    self.model_path,
                    cache_dir=None
                )
                self.model = AutoModelForSequenceClassification.from_pretrained(
                    self.model_path,
                    cache_dir=None,
                    torch_dtype=torch.float16,  # Use half precision to save memory
                    low_cpu_mem_usage=True
                )
            else:
                # Normal loading
                self.tokenizer = AutoTokenizer.from_pretrained(self.model_path)
                self.model = AutoModelForSequenceClassification.from_pretrained(self.model_path)

            self.model.eval()

            # Create intent mappings based on model's config
            # If the model doesn't have explicit intent mappings, create them from labels
            num_labels = self.model.config.num_labels

            # Create mappings based on your existing label system
            intent_labels = list(self.label_mapping.values())
            if num_labels == len(intent_labels):
                self.intent_to_id = {intent: i for i, intent in enumerate(intent_labels)}
                self.id_to_intent = {i: intent for i, intent in enumerate(intent_labels)}
            else:
                # Fallback mapping if model has different number of labels
                print(f"Model has {num_labels} labels, creating generic mapping")
                self.intent_to_id = {f"intent_{i}": i for i in range(num_labels)}
                self.id_to_intent = {i: f"intent_{i}" for i in range(num_labels)}

            print("✅ Fine-tuned model loaded successfully!")
            print(f"Model has {num_labels} output labels")
            print(f"Intent mappings: {self.id_to_intent}")

            self.model_loaded_in_memory = True

            # Force garbage collection
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

        except Exception as e:
            print(f"❌ Error loading fine-tuned model: {e}")
            # Clean up on failure
            self._cleanup_temp_files()
            raise

    def _load_zero_shot_model(self):
        """Load the original zero-shot model (your existing code)"""
        try:
            print("Loading zero-shot classification model...")
            # Check available space before loading
            available_space = self._get_available_space()
            if available_space < 1.0:  # Less than 1GB
                print("⚠️ Very low disk space, using minimal model configuration...")
                # Use a smaller model or disable caching
                self.classifier = pipeline(
                    "zero-shot-classification",
                    model="facebook/bart-base",  # Smaller model
                    device=-1,
                    return_all_scores=True,
                    model_kwargs={"cache_dir": None}
                )
            else:
                # Normal loading
                self.classifier = pipeline(
                    "zero-shot-classification",
                    model="facebook/bart-large-mnli",
                    device=-1,
                    return_all_scores=True
                )
            print("✅ Zero-shot model loaded successfully")
        except Exception as e:
            print(f"❌ Error loading zero-shot model: {e}")
            self.classifier = None

    async def detect_intent(self, message: str) -> str:
        """
        Detect intent using fine-tuned model if available, otherwise zero-shot
        """
        if self.use_fine_tuned and self.model:
            return await self._detect_with_fine_tuned(message)
        else:
            return await self._detect_with_zero_shot(message)

    async def _detect_with_fine_tuned(self, message: str) -> str:
        """Detect intent using fine-tuned model"""
        try:
            # Tokenize input with memory optimization
            inputs = self.tokenizer(
                message,
                return_tensors="pt",
                truncation=True,
                padding=True,
                max_length=512  # Adjust based on your model's max length
            )

            # Get prediction
            with torch.no_grad():
                outputs = self.model(**inputs)
                predictions = torch.nn.functional.softmax(outputs.logits, dim=-1)
                predicted_class_id = predictions.argmax().item()
                confidence = predictions.max().item()

                # Clean up tensors immediately
                del outputs, predictions

            # Map back to intent
            detected_intent = self.id_to_intent.get(predicted_class_id, "web3_chat")

            # Apply your existing post-processing rules
            final_intent = self._apply_post_processing_rules(message, detected_intent, confidence)

            print(f"Fine-tuned Intent Detected: {final_intent} (confidence: {confidence:.4f})")
            return final_intent

        except Exception as e:
            print(f"Error in fine-tuned detection: {e}")
            return self._fallback_intent_detection(message)

    async def _detect_with_zero_shot(self, message: str) -> str:
        """Your existing zero-shot detection method"""
        if not self.classifier:
            print("Classifier not available, using fallback")
            return self._fallback_intent_detection(message)

        try:
            processed_message = self._preprocess_message(message)
            result = self.classifier(processed_message, self.labels)

            top_label = result['labels'][0]
            top_score = result['scores'][0]

            detected_intent = self.label_mapping.get(top_label, 'web3_chat')
            final_intent = self._apply_post_processing_rules(message, detected_intent, top_score)

            print(f"Zero-shot Intent Detected: {final_intent}")
            return final_intent

        except Exception as e:
            print(f"Error in zero-shot classification: {e}")
            return self._fallback_intent_detection(message)

    def get_intent_confidence(self, message: str):
        """Return confidence scores using appropriate model"""
        if self.use_fine_tuned and self.model:
            return self._get_fine_tuned_confidence(message)
        else:
            return self._get_zero_shot_confidence(message)

    def _get_fine_tuned_confidence(self, message: str):
        """Get confidence scores from fine-tuned model"""
        if not self.model or not self.tokenizer:
            return self._get_fallback_confidence(message)

        try:
            inputs = self.tokenizer(
                message,
                return_tensors="pt",
                truncation=True,
                padding=True,
                max_length=512
            )

            with torch.no_grad():
                outputs = self.model(**inputs)
                predictions = torch.nn.functional.softmax(outputs.logits, dim=-1)

            confidence_scores = {}
            for intent_id, confidence in enumerate(predictions[0].tolist()):
                intent_name = self.id_to_intent.get(intent_id, f"unknown_{intent_id}")
                confidence_scores[intent_name] = confidence

            return confidence_scores

        except Exception as e:
            print(f"Error getting fine-tuned confidence scores: {e}")
            return self._get_fallback_confidence(message)

    def _get_zero_shot_confidence(self, message: str):
        """Your existing zero-shot confidence method"""
        if not self.classifier:
            return self._get_fallback_confidence(message)

        try:
            processed_message = self._preprocess_message(message)
            result = self.classifier(processed_message, self.labels)

            confidence_scores = {}
            for i, label in enumerate(result["labels"]):
                original_intent = self.label_mapping.get(label, 'unknown')
                confidence_scores[original_intent] = result["scores"][i]

            return confidence_scores

        except Exception as e:
            print(f"Error getting zero-shot confidence scores: {e}")
            return self._get_fallback_confidence(message)

    # Keep all your existing methods unchanged
    def _preprocess_message(self, message: str) -> str:
        """Your existing preprocessing method"""
        message_lower = message.lower().strip()
        enhanced_message = message_lower

        crypto_found = []
        for crypto in self.crypto_mapping.keys():
            if crypto in message_lower:
                crypto_found.append(crypto)

        if crypto_found:
            enhanced_message += f" (mentioning cryptocurrency: {', '.join(crypto_found)})"

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
        """Your existing post-processing rules"""
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
            r'\bdefi\b', r'decentralized\s+finance', r'yield\s+farming',
            r'liquidity\s+pool', r'smart\s+contract', r'\bnft\b',
            r'non.fungible\s+token', r'\bdao\b', r'web3',
            r'blockchain\s+technology', r'what\s+(?:is|are)\s+(?:defi|nft|dao|blockchain)',
            r'explain\s+(?:defi|nft|dao|blockchain)', r'how\s+(?:does|do)\s+(?:defi|nft|dao|blockchain)'
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

        if detected_intent == 'general_chat' and confidence < 0.5:
            return 'web3_chat'

        return detected_intent

    def _fallback_intent_detection(self, message: str) -> str:
        """Your existing fallback method"""
        message_lower = message.lower()

        if (any(word in message_lower for word in ['price', 'cost', 'worth', 'value', 'how much']) and
                any(crypto in message_lower for crypto in self.crypto_mapping.keys())):
            return 'price_query'

        if any(word in message_lower for word in ['wallet', 'balance', 'portfolio', 'account']):
            return 'wallet_query'

        web3_keywords = ['defi', 'decentralized finance', 'blockchain', 'web3', 'nft', 'smart contract',
                         'dao', 'yield farming', 'staking', 'liquidity', 'amm']
        if any(keyword in message_lower for keyword in web3_keywords):
            return 'web3_chat'

        non_crypto_keywords = ['weather', 'food', 'movie', 'music', 'sports', 'health', 'travel']
        if (any(keyword in message_lower for keyword in non_crypto_keywords) and
                not any(crypto in message_lower for crypto in self.crypto_mapping.keys())):
            return 'non_web3'

        return 'web3_chat'

    def extract_crypto_symbol(self, message: str) -> str:
        """Your existing crypto extraction method"""
        message_lower = message.lower()

        for crypto_key in self.crypto_mapping.keys():
            if crypto_key in message_lower:
                return crypto_key

        patterns = [
            r'price\s+of\s+(\w+)', r'(\w+)\s+price',
            r'how\s+much\s+is\s+(\w+)', r'(\w+)\s+(?:cost|value|worth)',
            r'current\s+(\w+)'
        ]

        for pattern in patterns:
            match = re.search(pattern, message_lower)
            if match:
                potential_crypto = match.group(1)
                if potential_crypto in self.crypto_mapping:
                    return potential_crypto

        return 'bitcoin'

    def _get_fallback_confidence(self, message: str):
        """Your existing fallback confidence method"""
        fallback_intent = self._fallback_intent_detection(message)
        scores = {
            "price_query": 0.1, "wallet_query": 0.1, "web3_chat": 0.1,
            "general_chat": 0.1, "non_web3": 0.1, fallback_intent: 0.6
        }
        return scores

    def get_model_info(self):
        """Get information about the currently loaded model"""
        return {
            "using_fine_tuned": self.use_fine_tuned,
            "model_path": self.model_path,
            "model_loaded": self.model_loaded_in_memory if self.use_fine_tuned else (self.classifier is not None),
            "available_intents": list(self.id_to_intent.values()) if self.use_fine_tuned else list(
                self.label_mapping.values()),
            "temp_dir": self.temp_dir,
            "available_disk_space_gb": self._get_available_space()
        }

    def __del__(self):
        """Cleanup when object is destroyed"""
        try:
            self._cleanup_temp_files()
        except:
            pass
