from fastapi import FastAPI, HTTPException, Query, Request, Depends
from fastapi.responses import StreamingResponse, HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import json
import asyncio
import time
import uuid
from typing import AsyncGenerator, Optional, List, Dict
from datetime import datetime

from intent_detector import IntentDetector
from services.price_service import PriceService
from utils.cache import CacheManager
from utils.typesense_client import TypesenseClient
from config import settings
from services.auth_service import AuthService
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from services.enhanced_chat_service import EnhancedChatService

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
chat_service = EnhancedChatService(cache_manager)
price_service = PriceService(cache_manager)
auth_service = AuthService()
security = HTTPBearer()


class SignupRequest(BaseModel):
    name: str
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str
    remember_me: bool = False


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


class ResetPasswordRequest(BaseModel):
    email: str


class ResetPasswordConfirm(BaseModel):
    token: str
    new_password: str


# Dependency to get current user
async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Optional[Dict]:
    """Get current user from JWT token"""
    token = credentials.credentials
    user = await auth_service.get_user_by_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return user


# Optional authentication dependency
async def get_optional_user(request: Request) -> Optional[Dict]:
    """Get current user if authenticated, None otherwise"""
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return None

    token = auth_header.split(" ")[1]
    return await auth_service.get_user_by_token(token)

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

    # Initialize enhanced chat service with context handling
    global chat_service
    chat_service = EnhancedChatService(
        cache_manager,
        model_name="meta-llama/llama-4-maverick-17b-128e-instruct"  # Use the 128K model
    )

    # Initialize chat service (includes Typesense setup)
    await chat_service.initialize()

    await auth_service.initialize()

    print("Web3 Chatbot API started with Enhanced Context!")
    print(f"Cache: {'Connected' if cache_manager.redis else 'Disconnected'}")
    print(f"Typesense: {'Ready' if await typesense_client.health_check() else 'Not Ready'}")
    print(f"Context Model: meta-llama/llama-4-maverick-17b-128e-instruct (128K)")
    print(f"Context Optimization: {'Enabled' if chat_service.enable_context else 'Disabled'}")


@app.get("/api/context/stats")
async def get_context_stats():
    """Get context handling statistics"""
    try:
        stats = chat_service.get_context_stats()
        return {
            "status": "success",
            "stats": stats,
            "timestamp": time.time()
        }
    except Exception as e:
        print(f"Error getting context stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/context/toggle")
async def toggle_context_optimization(enabled: bool = True):
    """Toggle context optimization on/off"""
    try:
        chat_service.toggle_context_optimization(enabled)
        return {
            "status": "success",
            "context_enabled": enabled,
            "message": f"Context optimization {'enabled' if enabled else 'disabled'}"
        }
    except Exception as e:
        print(f"Error toggling context: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/context/settings")
async def update_context_settings(
        max_messages: Optional[int] = None,
        cache_duration: Optional[int] = None
):
    """Update context settings"""
    try:
        chat_service.update_context_settings(
            max_messages=max_messages,
            cache_duration=cache_duration
        )

        return {
            "status": "success",
            "settings": {
                "max_messages": chat_service.max_context_messages,
                "cache_duration": chat_service.context_cache_duration
            }
        }
    except Exception as e:
        print(f"Error updating context settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/context/clear-cache")
async def clear_context_cache():
    """Clear context cache"""
    try:
        chat_service.clear_context_cache()
        return {
            "status": "success",
            "message": "Context cache cleared"
        }
    except Exception as e:
        print(f"Error clearing context cache: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/context/debug")
async def debug_context(
        conversation_id: str,
        current_query: str,
        user_id: str = "default"
):
    """Debug context building for a specific query"""
    try:
        # Get conversation messages
        messages = await chat_service.get_conversation_messages(conversation_id)

        # Get context summary
        context_summary = chat_service.get_context_summary(messages, current_query)

        # Get built context
        context = chat_service.context_handler.build_optimized_context(messages, current_query)

        return {
            "status": "success",
            "conversation_id": conversation_id,
            "query": current_query,
            "summary": context_summary,
            "context_messages": len(context),
            "context_preview": context[:3] if context else [],  # Show first 3 context messages
            "debug_info": {
                "total_available_messages": len(messages),
                "context_messages_selected": len(context),
                "estimated_tokens": sum(
                    chat_service.context_handler.estimate_tokens(msg['content']) for msg in context),
                "token_budget": chat_service.context_handler.available_context_tokens
            }
        }
    except Exception as e:
        print(f"Error debugging context: {e}")
        raise HTTPException(status_code=500, detail=str(e))

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


# Authentication Routes
@app.post("/api/auth/signup")
async def signup(request: SignupRequest):
    """Create new user account"""
    success, result = await auth_service.signup(
        name=request.name,
        email=request.email,
        password=request.password
    )

    if not success:
        raise HTTPException(status_code=400, detail=result.get('error', 'Signup failed'))

    return result


@app.post("/api/auth/login")
async def login(request: LoginRequest, req: Request):
    """Login user"""
    # Get IP and user agent for session tracking
    ip_address = req.client.host if req.client else None
    user_agent = req.headers.get('user-agent')

    success, result = await auth_service.login(
        email=request.email,
        password=request.password,
        ip_address=ip_address,
        user_agent=user_agent
    )

    if not success:
        raise HTTPException(status_code=401, detail=result.get('error', 'Login failed'))

    return result


@app.post("/api/auth/logout")
async def logout(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Logout user"""
    token = credentials.credentials
    success = await auth_service.logout(token)

    if not success:
        raise HTTPException(status_code=400, detail="Logout failed")

    return {"message": "Logged out successfully"}


@app.get("/api/auth/verify")
async def verify_token(user: Dict = Depends(get_current_user)):
    """Verify if token is valid"""
    return {"valid": True, "user": user}


@app.get("/api/auth/me")
async def get_me(user: Dict = Depends(get_current_user)):
    """Get current user info"""
    return user


@app.post("/api/auth/change-password")
async def change_password(request: ChangePasswordRequest, user: Dict = Depends(get_current_user)):
    """Change user password"""
    success, result = await auth_service.change_password(
        user_id=user['id'],
        old_password=request.old_password,
        new_password=request.new_password
    )

    if not success:
        raise HTTPException(status_code=400, detail=result.get('error', 'Failed to change password'))

    return result


@app.post("/api/auth/reset-password")
async def request_reset_password(request: ResetPasswordRequest):
    """Request password reset"""
    success, result = await auth_service.request_password_reset(email=request.email)

    if not success:
        raise HTTPException(status_code=400, detail=result.get('error', 'Failed to request reset'))

    # In production, send email with reset link
    # For now, return the token (don't do this in production!)
    return {"message": "Reset link sent to email", "debug_token": result.get('token')}


@app.post("/api/auth/reset-password/confirm")
async def reset_password_confirm(request: ResetPasswordConfirm):
    """Reset password with token"""
    success, result = await auth_service.reset_password(
        token=request.token,
        new_password=request.new_password
    )

    if not success:
        raise HTTPException(status_code=400, detail=result.get('error', 'Failed to reset password'))

    return result


@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest, user: Optional[Dict] = Depends(get_optional_user)):
    """Synchronous chat endpoint with enhanced context handling"""
    start_time = time.time()

    # Use authenticated user ID or fall back to provided user_id
    if user:
        actual_user_id = user['id']
        user_name = user['name']
    else:
        actual_user_id = request.user_id
        user_name = "Guest"

    try:
        # Detect intent
        intent = await intent_detector.detect_intent(request.message)

        # Handle conversation creation/selection
        conversation_id = request.conversation_id

        if not conversation_id:
            if "ready to help" in request.message.lower():
                conversation_id = await chat_service.get_or_create_conversation(
                    actual_user_id,
                    force_new=True
                )
            else:
                conversation_id = await chat_service.get_or_create_conversation(actual_user_id)

        final_conversation_id = conversation_id

        # Route based on intent
        if intent == "price_query":
            response = await price_service.handle_price_query(request.message)

            # Note: Price queries might not need full context, but we still track them
            await typesense_client.add_message(
                conversation_id=final_conversation_id,
                user_id=actual_user_id,
                role="user",
                content=request.message,
                intent=intent
            )
            await typesense_client.add_message(
                conversation_id=final_conversation_id,
                user_id=actual_user_id,
                role="assistant",
                content=response,
                intent=intent,
                response_time_ms=int((time.time() - start_time) * 1000)
            )

        elif intent == "wallet_query":
            response = f"🔒 {user_name}, wallet features are coming soon! For now, I can help with cryptocurrency prices and Web3 concepts."

            await typesense_client.add_message(
                conversation_id=final_conversation_id,
                user_id=actual_user_id,
                role="user",
                content=request.message,
                intent=intent
            )
            await typesense_client.add_message(
                conversation_id=final_conversation_id,
                user_id=actual_user_id,
                role="assistant",
                content=response,
                intent=intent,
                response_time_ms=int((time.time() - start_time) * 1000)
            )

        elif intent == "non_web3":
            response = await chat_service.handle_non_web3_query(request.message, actual_user_id)

        else:  # web3_chat or general_chat - Use enhanced context here
            response = await chat_service.handle_chat(
                request.message,
                actual_user_id,
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


# Update the streaming chat endpoint:
@app.post("/chat/stream")
async def chat_stream_endpoint(request: StreamChatRequest, user: Optional[Dict] = Depends(get_optional_user)):
    """Streaming chat endpoint with enhanced context handling"""

    async def generate_response() -> AsyncGenerator[str, None]:
        start_time = time.time()

        # Use authenticated user ID or fall back to provided user_id
        if user:
            actual_user_id = user['id']
            user_name = user['name']
        else:
            actual_user_id = request.user_id
            user_name = "Guest"

        try:
            yield f"data: {json.dumps({'type': 'start', 'message': 'Processing with enhanced context...'})}\n\n"

            # Detect intent
            intent = await intent_detector.detect_intent(request.message)
            yield f"data: {json.dumps({'type': 'intent', 'intent': intent})}\n\n"

            # Handle conversation creation/selection
            conversation_id = request.conversation_id

            if not conversation_id and "ready to help" in request.message.lower():
                conversation_id = await chat_service.get_or_create_conversation(
                    actual_user_id,
                    force_new=True
                )
            elif not conversation_id:
                conversation_id = await chat_service.get_or_create_conversation(actual_user_id)

            yield f"data: {json.dumps({'type': 'conversation_id', 'conversation_id': conversation_id})}\n\n"
            yield f"data: {json.dumps({'type': 'user_info', 'user_name': user_name})}\n\n"

            # Route based on intent
            if intent == "price_query":
                # Handle price queries (no context needed)
                await typesense_client.add_message(
                    conversation_id=conversation_id,
                    user_id=actual_user_id,
                    role="user",
                    content=request.message,
                    intent=intent
                )

                full_response = ""
                async for chunk in price_service.stream_price_response(request.message):
                    full_response += chunk
                    yield f"data: {json.dumps({'type': 'content', 'content': chunk})}\n\n"

                await typesense_client.add_message(
                    conversation_id=conversation_id,
                    user_id=actual_user_id,
                    role="assistant",
                    content=full_response,
                    intent=intent,
                    response_time_ms=int((time.time() - start_time) * 1000)
                )

            elif intent == "wallet_query":
                wallet_msg = f"🔒 {user_name}, wallet features are coming soon! For now, I can help with cryptocurrency prices and Web3 concepts."

                await typesense_client.add_message(
                    conversation_id=conversation_id,
                    user_id=actual_user_id,
                    role="user",
                    content=request.message,
                    intent=intent
                )

                # Stream the response
                for word in wallet_msg.split():
                    yield f"data: {json.dumps({'type': 'content', 'content': word + ' '})}\n\n"
                    await asyncio.sleep(0.03)

                await typesense_client.add_message(
                    conversation_id=conversation_id,
                    user_id=actual_user_id,
                    role="assistant",
                    content=wallet_msg,
                    intent=intent,
                    response_time_ms=int((time.time() - start_time) * 1000)
                )

            elif intent == "non_web3":
                response = await chat_service.handle_non_web3_query(request.message, actual_user_id)
                for word in response.split():
                    yield f"data: {json.dumps({'type': 'content', 'content': word + ' '})}\n\n"
                    await asyncio.sleep(0.03)

            else:  # web3_chat or general_chat - Use enhanced streaming context
                conversation_sent = False

                # Add context info to stream
                try:
                    # Get context summary for debugging
                    recent_messages = await chat_service.get_conversation_messages(conversation_id, limit=50)
                    if recent_messages:
                        context_summary = chat_service.get_context_summary(recent_messages, request.message)
                        yield f"data: {json.dumps({'type': 'context_info', 'context_summary': context_summary})}\n\n"
                except:
                    pass  # Don't fail if context info unavailable

                async for chunk in chat_service.stream_chat_response(
                        request.message,
                        actual_user_id,
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

            # Send completion with context stats
            response_time = time.time() - start_time
            completion_data = {
                'type': 'complete',
                'response_time': round(response_time, 3)
            }

            # Add context stats for web3 queries
            if intent in ['web3_chat', 'general_chat']:
                try:
                    context_stats = chat_service.get_context_stats()
                    completion_data['context_stats'] = context_stats
                except:
                    pass

            yield f"data: {json.dumps(completion_data)}\n\n"

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


# Update the health check to include context information:
@app.get("/health")
async def health_check():
    """Health check endpoint with context information"""
    health_status = {
        "status": "healthy",
        "timestamp": time.time(),
        "services": {
            "cache": await cache_manager.health_check(),
            "typesense": await typesense_client.health_check(),
            "groq": await chat_service.groq_client.health_check(),
            "coingecko": await price_service.coingecko.health_check()
        },
        "context": {
            "model": chat_service.context_handler.model_name,
            "context_enabled": chat_service.enable_context,
            "max_context_tokens": chat_service.context_handler.available_context_tokens,
            "cache_size": len(chat_service.context_handler.context_cache)
        }
    }

    # Determine overall health
    all_healthy = all(health_status["services"].values())
    health_status["status"] = "healthy" if all_healthy else "degraded"

    return health_status


# Update metrics endpoint:
@app.get("/metrics")
async def get_metrics():
    """Get application metrics including context performance"""
    try:
        cache_stats = await cache_manager.get_stats()
        chat_stats = await chat_service.get_chat_stats()
        context_stats = chat_service.get_context_stats()

        return {
            "timestamp": time.time(),
            "cache": cache_stats,
            "chat": chat_stats,
            "context": context_stats,
            "uptime": time.time() - startup_time if 'startup_time' in globals() else 0
        }

    except Exception as e:
        print(f"Error getting metrics: {e}")
        return {"error": str(e)}

@app.get("/auth", response_class=HTMLResponse)
async def serve_auth():
    """Serve the authentication page"""
    return FileResponse("static/auth.html")

@app.get("/chat", response_class=HTMLResponse)
async def serve_chat():
    """Serve the main chat interface"""
    return FileResponse("static/index.html")

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
    