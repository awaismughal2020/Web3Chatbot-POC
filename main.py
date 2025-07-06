from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import json
import asyncio
import time
from typing import AsyncGenerator, Optional, List

from intent_detector import IntentDetector
from services.chat_service import ChatService
from services.price_service import PriceService
from utils.cache import CacheManager
from utils.typesense_client import TypesenseClient
from config import settings

app = FastAPI(title="Web3 Fast Chatbot with History", version="2.0.0")

# Mount static files for frontend
app.mount("/static", StaticFiles(directory="static"), name="static")

# Initialize services
cache_manager = CacheManager()
typesense_client = TypesenseClient()
intent_detector = IntentDetector()
chat_service = ChatService(cache_manager)
price_service = PriceService(cache_manager)


class ChatRequest(BaseModel):
    message: str
    user_id: str = "default"
    conversation_id: Optional[str] = None


class ChatResponse(BaseModel):
    response: str
    intent: str
    response_time: float
    conversation_id: Optional[str] = None


class HistoryRequest(BaseModel):
    user_id: str
    limit: int = 50
    offset: int = 0


class SearchRequest(BaseModel):
    user_id: str
    query: str
    conversation_id: Optional[str] = None


@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    await cache_manager.connect()
    await chat_service.initialize()
    print("🚀 Fast Web3 Chatbot with History started!")
    print(f"Cache: {'✅ Connected' if cache_manager.redis else '❌ Disconnected'}")
    print(f"Typesense: {'✅ Ready' if await typesense_client.health_check() else '❌ Not Ready'}")


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
    """Single entry point for all chat interactions with history"""
    start_time = time.time()

    try:
        # Detect intent
        intent = await intent_detector.detect_intent(request.message)

        # Route to appropriate service based on intent
        if intent == "price_query":
            response = await price_service.handle_price_query(request.message)

            # Also save price queries to history
            conversation_id = await chat_service._get_or_create_conversation(request.user_id)
            await typesense_client.add_message(
                conversation_id=conversation_id,
                user_id=request.user_id,
                role="user",
                content=request.message,
                intent=intent
            )
            await typesense_client.add_message(
                conversation_id=conversation_id,
                user_id=request.user_id,
                role="assistant",
                content=response,
                intent=intent,
                response_time_ms=int((time.time() - start_time) * 1000)
            )

        elif intent == "wallet_query":
            response = "🔒 Wallet features are coming soon! For now, I can help with cryptocurrency prices and Web3 concepts."
        elif intent == "non_web3":
            response = await chat_service.handle_non_web3_query(request.message, request.user_id)
        elif intent == "web3_chat":
            response = await chat_service.handle_chat(request.message, request.user_id)
        elif intent == "general_chat":
            response = await chat_service.handle_chat(request.message, request.user_id)
        else:
            response = await chat_service.handle_non_web3_query(request.message, request.user_id)

        response_time = time.time() - start_time

        # Get current conversation ID
        conversation_id = chat_service.active_conversations.get(request.user_id)

        return ChatResponse(
            response=response,
            intent=intent,
            response_time=round(response_time, 3),
            conversation_id=conversation_id
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
    """Streaming chat endpoint with history"""

    async def generate_response() -> AsyncGenerator[str, None]:
        start_time = time.time()

        try:
            yield f"data: {json.dumps({'type': 'start', 'message': 'Processing your request...'})}\n\n"

            # Detect intent
            intent = await intent_detector.detect_intent(request.message)
            yield f"data: {json.dumps({'type': 'intent', 'intent': intent})}\n\n"

            # Get conversation ID
            conversation_id = await chat_service._get_or_create_conversation(request.user_id)
            yield f"data: {json.dumps({'type': 'conversation_id', 'conversation_id': conversation_id})}\n\n"

            # Route to appropriate service
            if intent == "price_query":
                # Save user message to history
                await typesense_client.add_message(
                    conversation_id=conversation_id,
                    user_id=request.user_id,
                    role="user",
                    content=request.message,
                    intent=intent
                )

                full_response = ""
                async for chunk in price_service.stream_price_response(request.message):
                    full_response += chunk
                    yield f"data: {json.dumps({'type': 'content', 'content': chunk})}\n\n"

                # Save assistant response
                await typesense_client.add_message(
                    conversation_id=conversation_id,
                    user_id=request.user_id,
                    role="assistant",
                    content=full_response,
                    intent=intent,
                    response_time_ms=int((time.time() - start_time) * 1000)
                )

            elif intent == "wallet_query":
                wallet_msg = "🔒 Wallet features are coming soon! For now, I can help with cryptocurrency prices and Web3 concepts."
                for word in wallet_msg.split():
                    yield f"data: {json.dumps({'type': 'content', 'content': word + ' '})}\n\n"
                    await asyncio.sleep(0.05)

            elif intent == "non_web3":
                decline_response = await chat_service.handle_non_web3_query(request.message, request.user_id)
                words = decline_response.split()
                for word in words:
                    yield f"data: {json.dumps({'type': 'content', 'content': word + ' '})}\n\n"
                    await asyncio.sleep(0.03)

            elif intent in ["web3_chat", "general_chat"]:
                async for chunk in chat_service.stream_chat_response(request.message, request.user_id):
                    yield f"data: {json.dumps({'type': 'content', 'content': chunk})}\n\n"
            else:
                decline_response = await chat_service.handle_non_web3_query(request.message, request.user_id)
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


# Chat History Endpoints

@app.get("/api/conversations")
async def get_user_conversations(
        user_id: str = Query(..., description="User ID"),
        limit: int = Query(10, ge=1, le=100),
        offset: int = Query(0, ge=0),
        status: str = Query("active", regex="^(active|archived)$")
):
    """Get user's conversation list"""
    try:
        conversations = await typesense_client.get_user_conversations(
            user_id=user_id,
            limit=limit,
            offset=offset,
            status=status
        )

        return {
            "conversations": conversations,
            "total": len(conversations),
            "limit": limit,
            "offset": offset
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/conversations/{conversation_id}/messages")
async def get_conversation_messages(
        conversation_id: str,
        limit: int = Query(50, ge=1, le=500),
        offset: int = Query(0, ge=0)
):
    """Get messages from a specific conversation"""
    try:
        messages = await typesense_client.get_conversation_history(
            conversation_id=conversation_id,
            limit=limit,
            offset=offset
        )

        return {
            "conversation_id": conversation_id,
            "messages": messages,
            "total": len(messages),
            "limit": limit,
            "offset": offset
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/search")
async def search_messages(request: SearchRequest):
    """Search through user's chat history"""
    try:
        results = await typesense_client.search_messages(
            user_id=request.user_id,
            query=request.query,
            conversation_id=request.conversation_id
        )

        return {
            "query": request.query,
            "results": results,
            "total": len(results)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/users/{user_id}/stats")
async def get_user_statistics(user_id: str):
    """Get user statistics"""
    try:
        stats = await typesense_client.get_user_stats(user_id)
        return stats

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/conversations/{conversation_id}/archive")
async def archive_conversation(conversation_id: str):
    """Archive a conversation"""
    try:
        await typesense_client.archive_conversation(conversation_id)
        return {"status": "archived", "conversation_id": conversation_id}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str):
    """Delete a conversation and all its messages"""
    try:
        await typesense_client.delete_conversation(conversation_id)
        return {"status": "deleted", "conversation_id": conversation_id}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/export/user/{user_id}")
async def export_user_history(user_id: str):
    """Export all user's chat history"""
    try:
        export_data = await chat_service.export_chat_history(user_id)

        return JSONResponse(
            content=export_data,
            headers={
                "Content-Disposition": f"attachment; filename=chat_history_{user_id}.json"
            }
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/export/conversation/{conversation_id}")
async def export_conversation(conversation_id: str):
    """Export a specific conversation"""
    try:
        export_data = await typesense_client.export_conversation(conversation_id)

        return JSONResponse(
            content=export_data,
            headers={
                "Content-Disposition": f"attachment; filename=conversation_{conversation_id}.json"
            }
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "cache_connected": cache_manager.redis is not None,
        "typesense_connected": await typesense_client.health_check(),
        "timestamp": time.time()
    }


@app.get("/metrics")
async def get_metrics():
    """Enhanced metrics endpoint"""
    cache_stats = await cache_manager.get_stats()
    chat_stats = await chat_service.get_chat_stats()

    return {
        "cache_stats": cache_stats,
        "chat_stats": chat_stats,
        "services": {
            "chat_service": "active",
            "price_service": "active",
            "intent_detector": "active",
            "typesense": "active" if await typesense_client.health_check() else "inactive"
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
