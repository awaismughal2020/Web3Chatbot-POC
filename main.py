from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import json
import asyncio
import time
from typing import AsyncGenerator

from intent_detector import IntentDetector
from services.chat_service import ChatService
from services.price_service import PriceService
from utils.cache import CacheManager
from config import settings

app = FastAPI(title="Web3 Fast Chatbot", version="1.0.0")

# Mount static files for frontend
app.mount("/static", StaticFiles(directory="static"), name="static")

# Initialize services
cache_manager = CacheManager()
intent_detector = IntentDetector()
chat_service = ChatService(cache_manager)
price_service = PriceService(cache_manager)


class ChatRequest(BaseModel):
    message: str
    user_id: str = "default"


class ChatResponse(BaseModel):
    response: str
    intent: str
    response_time: float


@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    await cache_manager.connect()
    print("🚀 Fast Web3 Chatbot started!")
    print(f"Cache: {'✅ Connected' if cache_manager.redis else '❌ Disconnected'}")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    await cache_manager.disconnect()


@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    """Serve the chat frontend"""
    with open("static/index.html", "r") as f:
        return HTMLResponse(content=f.read())


@app.post("/chat")
async def chat_endpoint(request: ChatRequest):
    """Single entry point for all chat interactions"""
    start_time = time.time()

    try:
        # Detect intent
        intent = await intent_detector.detect_intent(request.message)

        # Route to appropriate service based on intent
        if intent == "price_query":
            response = await price_service.handle_price_query(request.message)
        elif intent == "wallet_query":
            response = "🔒 Wallet features are coming soon! For now, I can help with cryptocurrency prices and Web3 concepts."
        elif intent == "non_web3":
            # CRITICAL: Non-Web3 queries handled locally, NEVER sent to Groq
            response = await chat_service.handle_non_web3_query(request.message)
        elif intent == "web3_chat":
            response = await chat_service.handle_chat(request.message, request.user_id)
        elif intent == "general_chat":
            # Only handle polite greetings, everything else goes to non_web3
            response = await chat_service.handle_chat(request.message, request.user_id)
        else:
            # Default: treat unknown intents as non-Web3
            response = await chat_service.handle_non_web3_query(request.message)

        response_time = time.time() - start_time

        return ChatResponse(
            response=response,
            intent=intent,
            response_time=round(response_time, 3)
        )

    except Exception as e:
        response_time = time.time() - start_time
        return ChatResponse(
            response=f"Sorry, I encountered an error: {str(e)}",
            intent="error",
            response_time=round(response_time, 3)
        )


@app.post("/chat/stream")
async def chat_stream_endpoint(request: ChatRequest):
    """Streaming chat endpoint for real-time responses"""

    async def generate_response() -> AsyncGenerator[str, None]:
        start_time = time.time()

        try:
            # Send immediate acknowledgment
            yield f"data: {json.dumps({'type': 'start', 'message': 'Processing your request...'})}\n\n"

            # Detect intent quickly
            intent = await intent_detector.detect_intent(request.message)
            yield f"data: {json.dumps({'type': 'intent', 'intent': intent})}\n\n"

            # Route to appropriate service and stream response
            if intent == "price_query":
                async for chunk in price_service.stream_price_response(request.message):
                    yield f"data: {json.dumps({'type': 'content', 'content': chunk})}\n\n"
            elif intent == "wallet_query":
                # For wallet queries, send a simple message
                wallet_msg = "🔒 Wallet features are coming soon! For now, I can help with cryptocurrency prices and Web3 concepts."
                for word in wallet_msg.split():
                    yield f"data: {json.dumps({'type': 'content', 'content': word + ' '})}\n\n"
                    await asyncio.sleep(0.05)
            elif intent == "non_web3":
                # CRITICAL: Non-Web3 queries handled locally, NEVER sent to Groq
                decline_response = await chat_service.handle_non_web3_query(request.message)
                words = decline_response.split()
                for word in words:
                    yield f"data: {json.dumps({'type': 'content', 'content': word + ' '})}\n\n"
                    await asyncio.sleep(0.03)
            elif intent == "web3_chat":
                # Only Web3 topics go to Groq
                async for chunk in chat_service.stream_chat_response(request.message, request.user_id):
                    yield f"data: {json.dumps({'type': 'content', 'content': chunk})}\n\n"
            elif intent == "general_chat":
                # Only polite greetings go to Groq
                async for chunk in chat_service.stream_chat_response(request.message, request.user_id):
                    yield f"data: {json.dumps({'type': 'content', 'content': chunk})}\n\n"
            else:
                # Default: treat unknown intents as non-Web3
                decline_response = await chat_service.handle_non_web3_query(request.message)
                words = decline_response.split()
                for word in words:
                    yield f"data: {json.dumps({'type': 'content', 'content': word + ' '})}\n\n"
                    await asyncio.sleep(0.03)

            # Send completion signal
            response_time = time.time() - start_time
            yield f"data: {json.dumps({'type': 'complete', 'response_time': round(response_time, 3)})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        generate_response(),
        media_type="text/plain",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Content-Type": "text/event-stream"
        }
    )


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "cache_connected": cache_manager.redis is not None,
        "timestamp": time.time()
    }


@app.get("/metrics")
async def get_metrics():
    """Simple metrics endpoint"""
    cache_stats = await cache_manager.get_stats()
    return {
        "cache_stats": cache_stats,
        "services": {
            "chat_service": "active",
            "price_service": "active",
            "intent_detector": "active"
        }
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
