from transformers import pipeline
import asyncio

class IntentDetector:
    def __init__(self):
        # Load zero-shot classification model
        self.classifier = pipeline("zero-shot-classification", model="facebook/bart-large-mnli")

        # Intents to classify against (keep consistent with previous behavior)
        self.labels = [
            "price_query",
            "wallet_query",
            "web3_chat",
            "general_chat",
            "non_web3"
        ]

    async def detect_intent(self, message: str) -> str:
        """
        Detect the intent of a user message using zero-shot classification.
        Returns one of: 'price_query', 'wallet_query', 'web3_chat', 'general_chat', 'non_web3'
        """
        result = self.classifier(message, self.labels)
        top_intent = result['labels'][0]
        return top_intent

    def extract_crypto_symbol(self, message: str) -> str:
        """
        Placeholder for symbol extraction — optional.
        This version always returns 'bitcoin' as fallback.
        """
        return 'bitcoin'

    def get_intent_confidence(self, message: str):
        """
        Optional: return confidence scores for each intent
        """
        result = self.classifier(message, self.labels)
        return dict(zip(result["labels"], result["scores"]))
