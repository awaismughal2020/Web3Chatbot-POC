from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import StreamingResponse, HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import json
import asyncio
import time
import uuid
from typing import AsyncGenerator, Optional, List
from datetime import datetime

from intent_detector import IntentDetector
from services.chat_service import ChatService  # Use the improved version
from services.price_service import PriceService
from utils.cache import CacheManager
from utils.typesense_client import TypesenseClient
from config import settings

app = FastAPI(
    title="Web3 Fast Chatbot API",
    version="2.0.0",
    description="Cryptocurrency chatbot with complete chat history management"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Initialize services
cache_manager = CacheManager()
typesense_client = TypesenseClient()
intent_detector = IntentDetector()
chat_service = ChatService(cache_manager)
price_service = PriceService(cache_manager)


# Request/Response Models
class ChatRequest(BaseModel):
    message: str
    user_id: str = "default"
    conversation_id: Optional[str] = None


class StreamChatRequest(BaseModel):
    message: str
    user_id: str = "default"
    conversation_id: Optional[str] = None


class ChatResponse(BaseModel):
    response: str
    intent: str
    response_time: float
    conversation_id: str


class SearchRequest(BaseModel):
    user_id: str
    query: str
    conversation_id: Optional[str] = None


class ConversationUpdate(BaseModel):
    title: Optional[str] = None
    status: Optional[str] = None


# Startup/Shutdown Events
@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    # Connect to cache
    await cache_manager.connect()

    # Initialize chat service (includes Typesense setup)
    await chat_service.initialize()

    print("🚀 Web3 Chatbot API started!")
    print(f"📊 Cache: {'✅ Connected' if cache_manager.redis else '❌ Disconnected'}")
    print(f"🔍 Typesense: {'✅ Ready' if await typesense_client.health_check() else '❌ Not Ready'}")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    await cache_manager.disconnect()
    await chat_service.groq_client.close()
    await price_service.coingecko.close()


# Main Routes
@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    """Serve the enhanced chat frontend"""
    return FileResponse("static/index.html")


# This is a partial update for main.py - just the chat endpoint

@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    """Synchronous chat endpoint with conversation management"""
    start_time = time.time()

    try:
        # Detect intent
        intent = await intent_detector.detect_intent(request.message)

        # Handle conversation creation/selection
        conversation_id = request.conversation_id

        # If no conversation_id is provided, let the chat service handle it
        if not conversation_id:
            # For initial greeting messages that create new conversations
            if "ready to help" in request.message.lower():
                conversation_id = await chat_service.get_or_create_conversation(
                    request.user_id,
                    force_new=True  # Force new conversation for greeting
                )
            else:
                conversation_id = await chat_service.get_or_create_conversation(request.user_id)

        # Store the conversation_id for response
        final_conversation_id = conversation_id

        # Route based on intent
        if intent == "price_query":
            response = await price_service.handle_price_query(request.message)

            # Save price queries to history too
            await typesense_client.add_message(
                conversation_id=final_conversation_id,
                user_id=request.user_id,
                role="user",
                content=request.message,
                intent=intent
            )
            await typesense_client.add_message(
                conversation_id=final_conversation_id,
                user_id=request.user_id,
                role="assistant",
                content=response,
                intent=intent,
                response_time_ms=int((time.time() - start_time) * 1000)
            )

        elif intent == "wallet_query":
            response = "🔒 Wallet features are coming soon! For now, I can help with cryptocurrency prices and Web3 concepts."

            # Save to history
            await typesense_client.add_message(
                conversation_id=final_conversation_id,
                user_id=request.user_id,
                role="user",
                content=request.message,
                intent=intent
            )
            await typesense_client.add_message(
                conversation_id=final_conversation_id,
                user_id=request.user_id,
                role="assistant",
                content=response,
                intent=intent,
                response_time_ms=int((time.time() - start_time) * 1000)
            )

        elif intent == "non_web3":
            response = await chat_service.handle_non_web3_query(request.message, request.user_id)

        else:  # web3_chat or general_chat
            response = await chat_service.handle_chat(
                request.message,
                request.user_id,
                final_conversation_id
            )

        response_time = time.time() - start_time

        return ChatResponse(
            response=response,
            intent=intent,
            response_time=round(response_time, 3),
            conversation_id=final_conversation_id
        )

    except Exception as e:
        print(f"Chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat/stream")
async def chat_stream_endpoint(request: StreamChatRequest):
    """Streaming chat endpoint with conversation support"""

    async def generate_response() -> AsyncGenerator[str, None]:
        start_time = time.time()

        try:
            # Send initial acknowledgment
            yield f"data: {json.dumps({'type': 'start', 'message': 'Processing...'})}\n\n"

            # Detect intent
            intent = await intent_detector.detect_intent(request.message)
            yield f"data: {json.dumps({'type': 'intent', 'intent': intent})}\n\n"

            # Handle conversation creation/selection
            conversation_id = request.conversation_id

            # If this is a greeting message for new chat, force new conversation
            if not conversation_id and "ready to help" in request.message.lower():
                conversation_id = await chat_service.get_or_create_conversation(
                    request.user_id,
                    force_new=True
                )
            elif not conversation_id:
                conversation_id = await chat_service.get_or_create_conversation(request.user_id)

            yield f"data: {json.dumps({'type': 'conversation_id', 'conversation_id': conversation_id})}\n\n"

            # Route based on intent
            if intent == "price_query":
                # Save user message
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

                # Save user message
                await typesense_client.add_message(
                    conversation_id=conversation_id,
                    user_id=request.user_id,
                    role="user",
                    content=request.message,
                    intent=intent
                )

                # Stream the response
                for word in wallet_msg.split():
                    yield f"data: {json.dumps({'type': 'content', 'content': word + ' '})}\n\n"
                    await asyncio.sleep(0.03)

                # Save assistant response
                await typesense_client.add_message(
                    conversation_id=conversation_id,
                    user_id=request.user_id,
                    role="assistant",
                    content=wallet_msg,
                    intent=intent,
                    response_time_ms=int((time.time() - start_time) * 1000)
                )

            elif intent == "non_web3":
                response = await chat_service.handle_non_web3_query(request.message, request.user_id)
                for word in response.split():
                    yield f"data: {json.dumps({'type': 'content', 'content': word + ' '})}\n\n"
                    await asyncio.sleep(0.03)

            else:  # web3_chat or general_chat
                conversation_sent = False
                async for chunk in chat_service.stream_chat_response(
                        request.message,
                        request.user_id,
                        conversation_id
                ):
                    # Handle special conversation ID marker
                    if chunk.startswith("CONVERSATION_ID:"):
                        conv_id = chunk.split(":", 1)[1]
                        if not conversation_sent:
                            yield f"data: {json.dumps({'type': 'conversation_id', 'conversation_id': conv_id})}\n\n"
                            conversation_sent = True
                    else:
                        yield f"data: {json.dumps({'type': 'content', 'content': chunk})}\n\n"

            # Send completion
            response_time = time.time() - start_time
            yield f"data: {json.dumps({'type': 'complete', 'response_time': round(response_time, 3)})}\n\n"

        except Exception as e:
            print(f"Streaming error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        generate_response(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Content-Type": "text/event-stream",
            "X-Accel-Buffering": "no"
        }
    )


# Conversation Management Endpoints
@app.get("/api/conversations")
async def get_conversations(
        user_id: str = Query(..., description="User ID"),
        limit: int = Query(20, ge=1, le=100),
        offset: int = Query(0, ge=0),
        status: str = Query("active", regex="^(active|archived)$")
):
    """Get user's conversations"""
    try:
        conversations = await chat_service.get_user_conversations(user_id, limit, offset)

        # Filter by status if needed
        if status != "active":
            conversations = [c for c in conversations if c.get('status') == status]

        return {
            "conversations": conversations,
            "total": len(conversations),
            "limit": limit,
            "offset": offset,
            "user_id": user_id
        }

    except Exception as e:
        print(f"Error getting conversations: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/conversations/{conversation_id}/messages")
async def get_conversation_messages(
        conversation_id: str,
        limit: int = Query(100, ge=1, le=500),
        offset: int = Query(0, ge=0)
):
    """Get messages from a specific conversation"""
    try:
        messages = await chat_service.get_conversation_messages(conversation_id, limit)

        return {
            "conversation_id": conversation_id,
            "messages": messages,
            "total": len(messages),
            "limit": limit,
            "offset": offset
        }

    except Exception as e:
        print(f"Error getting messages: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.patch("/api/conversations/{conversation_id}")
async def update_conversation(conversation_id: str, update: ConversationUpdate):
    """Update conversation metadata"""
    try:
        success = True

        if update.title:
            success = await chat_service.update_conversation_title(conversation_id, update.title)

        if update.status:
            if update.status == "archived":
                await typesense_client.archive_conversation(conversation_id)

        return {"success": success, "conversation_id": conversation_id}

    except Exception as e:
        print(f"Error updating conversation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str):
    """Delete a conversation and all its messages"""
    try:
        success = await chat_service.delete_conversation(conversation_id)

        if success:
            return {"status": "deleted", "conversation_id": conversation_id}
        else:
            raise HTTPException(status_code=404, detail="Conversation not found")

    except Exception as e:
        print(f"Error deleting conversation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Search Endpoints
@app.post("/api/search")
async def search_messages(request: SearchRequest):
    """Search through user's chat history"""
    try:
        results = await chat_service.search_user_history(
            request.user_id,
            request.query,
            request.conversation_id
        )

        return {
            "query": request.query,
            "results": results,
            "total": len(results),
            "user_id": request.user_id
        }

    except Exception as e:
        print(f"Error searching: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Statistics Endpoints
@app.get("/api/users/{user_id}/stats")
async def get_user_statistics(user_id: str):
    """Get comprehensive user statistics"""
    try:
        stats = await chat_service.get_user_stats(user_id)

        # Calculate additional stats
        if stats.get('created_at'):
            days_active = (time.time() - stats['created_at']) / 86400
            stats['days_active'] = int(days_active)

        return stats

    except Exception as e:
        print(f"Error getting stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Export Endpoints
@app.get("/api/export/conversation/{conversation_id}")
async def export_conversation(conversation_id: str):
    """Export a specific conversation"""
    try:
        export_data = await chat_service.export_conversation(conversation_id)

        if "error" in export_data:
            raise HTTPException(status_code=404, detail=export_data["error"])

        return JSONResponse(
            content=export_data,
            headers={
                "Content-Disposition": f"attachment; filename=conversation_{conversation_id}_{int(time.time())}.json"
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error exporting conversation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/export/user/{user_id}")
async def export_user_history(user_id: str, limit: int = Query(100, le=1000)):
    """Export all user's chat history"""
    try:
        conversations = await chat_service.get_user_conversations(user_id, limit=limit)

        export_data = {
            "user_id": user_id,
            "export_date": datetime.now().isoformat(),
            "total_conversations": len(conversations),
            "conversations": []
        }

        # Export each conversation
        for conv in conversations[:10]:  # Limit to prevent timeout
            conv_export = await chat_service.export_conversation(conv['id'])
            if "error" not in conv_export:
                export_data["conversations"].append(conv_export)

        return JSONResponse(
            content=export_data,
            headers={
                "Content-Disposition": f"attachment; filename=chat_history_{user_id}_{int(time.time())}.json"
            }
        )

    except Exception as e:
        print(f"Error exporting user history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Health & Monitoring Endpoints
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    health_status = {
        "status": "healthy",
        "timestamp": time.time(),
        "services": {
            "cache": await cache_manager.health_check(),
            "typesense": await typesense_client.health_check(),
            "groq": await chat_service.groq_client.health_check(),
            "coingecko": await price_service.coingecko.health_check()
        }
    }

    # Determine overall health
    all_healthy = all(health_status["services"].values())
    health_status["status"] = "healthy" if all_healthy else "degraded"

    return health_status


@app.get("/metrics")
async def get_metrics():
    """Get application metrics"""
    try:
        cache_stats = await cache_manager.get_stats()
        chat_stats = await chat_service.get_chat_stats()

        return {
            "timestamp": time.time(),
            "cache": cache_stats,
            "chat": chat_stats,
            "uptime": time.time() - startup_time if 'startup_time' in globals() else 0
        }

    except Exception as e:
        print(f"Error getting metrics: {e}")
        return {"error": str(e)}


# Error Handlers
@app.exception_handler(404)
async def not_found_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=404,
        content={"error": "Not found", "path": request.url.path}
    )


@app.exception_handler(500)
async def internal_error_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "detail": str(exc)}
    )


# Store startup time
startup_time = time.time()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.APP_HOST,
        port=settings.APP_PORT,
        reload=settings.APP_RELOAD,
        log_level=settings.LOG_LEVEL.lower()
    )
    