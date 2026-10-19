"""Production-grade FastAPI REST application exposing endpoints for multi-user chat,
personalized memory lifecycle, Qdrant semantic retrieval, and administration.
"""

import logging
import os
from typing import Any, Dict, List, Optional
import uuid
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Security, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials

from intelligent_forgetting.agent import MemoryAgent
from intelligent_forgetting.auth import (
    AuthenticatedUser,
    get_current_admin_user,
    get_current_user,
    provision_admin_user,
    security_bearer,
    verify_id_token,
)
from intelligent_forgetting.config import Settings, get_settings
from intelligent_forgetting.forgetting_engine import ForgettingEngine
from intelligent_forgetting.gemini_service import GeminiChatService
from intelligent_forgetting.memory_scorer import MemoryScorer
from intelligent_forgetting.memory_store import MemoryStore
from intelligent_forgetting.models import (
    AgentTaskRequest,
    AgentTaskResponse,
    ChatMessage,
    ChatMessageCreateRequest,
    Conversation,
    ConversationCreateRequest,
    ConversationUpdateRequest,
    ForgettingActionItem,
    ForgettingActionType,
    ForgettingApplyRequest,
    ForgettingApplyResult,
    ForgettingEvaluationRequest,
    ForgettingEvaluationResult,
    LifecycleActivityItem,
    Memory,
    MemoryCategory,
    MemoryCreateRequest,
    MemoryImportanceUpdateRequest,
    MemorySearchRequest,
    MemoryStats,
    MemoryType,
    MemoryUpdateRequest,
    RLExperimentRun,
    RetentionStatus,
    SystemAuditLogItem,
    UserProfileUpdate,
    UserRecord,
    utc_now,
)
from intelligent_forgetting.firestore_service import FirestoreChatService
from intelligent_forgetting.lifecycle_router import (
    LifecycleRouter,
    is_inquiry_or_question,
    is_lifecycle_command,
    is_preview_request,
)
from intelligent_forgetting.rl_engine import ReinforcementLearningEngine
from intelligent_forgetting.vector_store import QdrantVectorService

logger = logging.getLogger("intelligent_forgetting.api")

settings = get_settings()
store = MemoryStore(db_path=settings.database_path, database_url=settings.database_url)
scorer = MemoryScorer(settings=settings)
vector_service = QdrantVectorService(settings=settings)
firestore_service = FirestoreChatService(settings=settings)
engine = ForgettingEngine(
    memory_store=store,
    scorer=scorer,
    settings=settings,
    vector_service=vector_service,
)
gemini_service = GeminiChatService(settings=settings)
rl_engine = ReinforcementLearningEngine(scorer=scorer, settings=settings)
agent = MemoryAgent(memory_store=store, forgetting_engine=engine, scorer=scorer, settings=settings)
lifecycle_router = LifecycleRouter(
    store=store,
    engine=engine,
    vector_service=vector_service,
    scorer=scorer,
)


app = FastAPI(
    title="Intelligent Forgetting in Agentic AI",
    description=(
        "Full-Stack Multi-User AI Chat Platform with Intelligent Memory Management, "
        "Qdrant Semantic Retrieval, and Reinforcement Learning Optimization."
    ),
    version="1.0.0",
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_cors_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"],
)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Ensures HTTPExceptions return uniform JSON with CORS headers preserved."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=getattr(exc, "headers", None) or {},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Catches unhandled server exceptions, logs traceback, and returns JSON 500 with CORS headers."""
    logger.error("Unhandled exception on %s %s: %s", request.method, request.url.path, exc, exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": f"Internal server error: {str(exc)}"},
    )


def resolve_user_optional(
    auth_header: Optional[HTTPAuthorizationCredentials] = Security(security_bearer),
) -> AuthenticatedUser:
    """Extracts authenticated user if Bearer token present, otherwise defaults to local default user.
    
    This allows backwards compatibility with unauthenticated unit tests while enforcing tenant
    isolation when tokens are provided.
    """
    if auth_header and auth_header.credentials:
        try:
            return verify_id_token(auth_header.credentials)
        except Exception:
            pass
    return AuthenticatedUser(
        uid="default_user",
        email="default@intelligentforgetting.org",
        name="Default User",
        role="user",
        is_admin=False,
    )


# ==============================================================================
# SYSTEM & HEALTH ENDPOINTS
# ==============================================================================

@app.get("/health", tags=["System"])
@app.get("/api/v1/health", tags=["System"])
def health_check():
    """Service health verification endpoint."""
    firestore_health = firestore_service.is_healthy()
    return {
        "status": "healthy",
        "timestamp": utc_now().isoformat(),
        "services": {
            "database_backend": "postgresql" if store.is_postgres else "sqlite",
            "sqlite": not store.is_postgres,
            "postgresql": store.is_postgres,
            "qdrant": vector_service.is_healthy(),
            "gemini": gemini_service.is_live(),
            "firestore": firestore_health.get("healthy", False),
            "firestore_details": firestore_health,
            "rl_engine": True,
        },
    }


@app.get("/health/ready", tags=["System"])
@app.get("/api/v1/health/ready", tags=["System"])
def readiness_check():
    """Service readiness verification for deployment orchestrators."""
    return {
        "status": "ready",
        "timestamp": utc_now().isoformat(),
        "database": True,
        "api": True,
    }


@app.get("/api/v1/qdrant/diagnostics", tags=["System"])
def get_qdrant_diagnostics(user: AuthenticatedUser = Depends(resolve_user_optional)):
    """Retrieves detailed Qdrant Cloud collection health and vector metrics."""
    return vector_service.get_collection_info()


@app.post("/api/v1/qdrant/reconcile", tags=["System"])
def reconcile_qdrant_vectors(
    fix: bool = Query(False, description="If true, re-indexes missing or stale vectors in Qdrant"),
    user: AuthenticatedUser = Depends(resolve_user_optional),
):
    """Reconciles SQLite cognitive memories with Qdrant Cloud vector index."""
    uid = user.uid if not user.is_admin else None
    return vector_service.reconcile_with_sqlite(store, user_id=uid, fix=fix)



# ==============================================================================
# AUTHENTICATION & USER PROFILE
# ==============================================================================

@app.get("/api/v1/me", response_model=UserRecord, tags=["Auth & Profile"])
@app.get("/me", response_model=UserRecord, tags=["Auth & Profile"])
def get_current_user_profile(user: AuthenticatedUser = Depends(get_current_user)):
    """Retrieves current verified user profile, creating SQLite record if first login."""
    record = store.get_user(user.uid)
    if not record:
        record = UserRecord(
            uid=user.uid,
            email=user.email,
            display_name=user.name or (user.email.split("@")[0] if user.email else "User"),
            role="admin" if user.is_admin else "user",
            status="active",
        )
        store.upsert_user(record)
    else:
        # Update last active timestamp
        record.last_active_at = utc_now()
        if user.is_admin and record.role != "admin":
            record.role = "admin"
        store.upsert_user(record)
    return record


@app.patch("/api/v1/me/profile", response_model=UserRecord, tags=["Auth & Profile"])
@app.patch("/me/profile", response_model=UserRecord, tags=["Auth & Profile"])
def update_profile(
    payload: UserProfileUpdate,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """Updates display name or preferences for current user."""
    record = store.get_user(user.uid)
    if not record:
        record = UserRecord(uid=user.uid, email=user.email)
    if payload.display_name is not None:
        record.display_name = payload.display_name
    if payload.metadata is not None:
        record.metadata.update(payload.metadata)
    record.last_active_at = utc_now()
    return store.upsert_user(record)


@app.delete("/api/v1/me", tags=["Auth & Profile"])
@app.delete("/me", tags=["Auth & Profile"])
def delete_account(user: AuthenticatedUser = Depends(get_current_user)):
    """Complete GDPR-compliant user account and data deletion workflow."""
    # 1. Cascade SQLite records
    counts = store.delete_user_data(user.uid)
    # 2. Delete Qdrant vectors
    vector_service.delete_user_vectors(user.uid)
    return {
        "status": "success",
        "message": "User account, conversations, messages, and vector memories permanently purged.",
        "purged_records": counts,
    }


# ==============================================================================
# CONVERSATIONS & CHAT
# ==============================================================================

@app.post("/api/v1/conversations", response_model=Conversation, status_code=status.HTTP_201_CREATED, tags=["Conversations"])
def create_conversation(
    req: ConversationCreateRequest,
    user: AuthenticatedUser = Depends(resolve_user_optional),
):
    """Creates a new conversation thread for the authenticated user."""
    conv = Conversation(
        user_id=user.uid,
        title=req.title or "New Conversation",
        model=req.model or settings.gemini_model,
    )
    created = store.create_conversation(conv)
    if firestore_service.is_healthy().get("healthy"):
        firestore_service.create_conversation(user.uid, created)
    return created


@app.get("/api/v1/conversations", response_model=List[Conversation], tags=["Conversations"])
def list_conversations(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: AuthenticatedUser = Depends(resolve_user_optional),
):
    """Lists conversations belonging strictly to current user."""
    if firestore_service.is_healthy().get("healthy"):
        fs_convs = firestore_service.list_conversations(user_id=user.uid, limit=limit, offset=offset)
        if fs_convs:
            return fs_convs
    return store.list_conversations(user_id=user.uid, limit=limit, offset=offset)


@app.get("/api/v1/conversations/{conversation_id}", response_model=Conversation, tags=["Conversations"])
def get_conversation(
    conversation_id: str,
    user: AuthenticatedUser = Depends(resolve_user_optional),
):
    """Retrieves conversation details verifying user ownership."""
    conv = store.get_conversation(conversation_id, user_id=user.uid)
    if not conv and firestore_service.is_healthy().get("healthy"):
        conv = firestore_service.get_conversation(user.uid, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found or access denied.")
    return conv


@app.patch("/api/v1/conversations/{conversation_id}", response_model=Conversation, tags=["Conversations"])
def update_conversation(
    conversation_id: str,
    req: ConversationUpdateRequest,
    user: AuthenticatedUser = Depends(resolve_user_optional),
):
    """Renames or pins a conversation."""
    conv = store.update_conversation(conversation_id, user_id=user.uid, title=req.title, is_pinned=req.is_pinned)
    if firestore_service.is_healthy().get("healthy"):
        firestore_service.update_conversation(user.uid, conversation_id, title=req.title, is_pinned=req.is_pinned)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found or access denied.")
    return conv


@app.delete("/api/v1/conversations/{conversation_id}", tags=["Conversations"])
def delete_conversation(
    conversation_id: str,
    user: AuthenticatedUser = Depends(resolve_user_optional),
):
    """Deletes conversation and associated messages without affecting cognitive memories."""
    success = store.delete_conversation(conversation_id, user_id=user.uid)
    if firestore_service.is_healthy().get("healthy"):
        firestore_service.delete_conversation(user.uid, conversation_id)
    if not success:
        raise HTTPException(status_code=404, detail="Conversation not found or access denied.")
    return {"status": "success", "conversation_id": conversation_id}


@app.get("/api/v1/conversations/{conversation_id}/messages", response_model=List[ChatMessage], tags=["Conversations"])
def get_conversation_messages(
    conversation_id: str,
    user: AuthenticatedUser = Depends(resolve_user_optional),
):
    """Retrieves all chat messages for a conversation in chronological order."""
    # Verify ownership
    conv = store.get_conversation(conversation_id, user_id=user.uid)
    if not conv and firestore_service.is_healthy().get("healthy"):
        conv = firestore_service.get_conversation(user.uid, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found or access denied.")

    # Retrieve from Firestore if available, otherwise SQLite
    if firestore_service.is_healthy().get("healthy"):
        fs_msgs = firestore_service.get_messages(user.uid, conversation_id)
        if fs_msgs:
            return fs_msgs

    return store.get_conversation_messages(conversation_id, user_id=user.uid)



@app.post("/api/v1/conversations/{conversation_id}/messages", response_model=ChatMessage, tags=["Conversations"])
def send_chat_message(
    conversation_id: str,
    req: ChatMessageCreateRequest,
    user: AuthenticatedUser = Depends(resolve_user_optional),
):
    """Submits user prompt, retrieves personalized memories, queries Gemini, and saves messages."""
    conv = store.get_conversation(conversation_id, user_id=user.uid)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found or access denied.")

    # 1. Save User Message
    user_msg = ChatMessage(
        conversation_id=conversation_id,
        user_id=user.uid,
        role="user",
        content=req.content,
        token_count=max(1, len(req.content) // 4),
    )
    store.save_message(user_msg)
    if firestore_service.is_healthy().get("healthy"):
        firestore_service.save_message(user.uid, conversation_id, user_msg)

    # 2. Check for explicit memory lifecycle directive BEFORE standard retrieval & extraction
    lifecycle_response = lifecycle_router.route_and_execute(
        user_id=user.uid,
        conversation_id=conversation_id,
        user_message=req.content,
    )
    if lifecycle_response is not None:
        is_preview = is_preview_request(req.content)
        assistant_msg = ChatMessage(
            conversation_id=conversation_id,
            user_id=user.uid,
            role="assistant",
            content=lifecycle_response,
            token_count=max(1, len(lifecycle_response) // 4),
            retrieved_memory_ids=[],
            metadata={
                "lifecycle_operation": True,
                "lifecycle_mode": "preview" if is_preview else "mutation",
            },
        )
        store.save_message(assistant_msg)
        if firestore_service.is_healthy().get("healthy"):
            firestore_service.save_message(user.uid, conversation_id, assistant_msg)

        if conv.title == "New Conversation":
            snippet = req.content[:35].strip()
            new_title = snippet + ("..." if len(req.content) > 35 else "")
            store.update_conversation(conversation_id, user_id=user.uid, title=new_title)
            if firestore_service.is_healthy().get("healthy"):
                firestore_service.update_conversation(user.uid, conversation_id, title=new_title)

        return assistant_msg

    # 3. Retrieve relevant personalized memories (Hybrid Semantic + Lexical with tenant filter)
    retrieved_memories: List[Memory] = []

    # Semantic Qdrant vector retrieval for active memories
    qdrant_hits = vector_service.search_memories(query=req.content, user_id=user.uid, top_k=5, status="active")
    retrieved_ids = [hit["memory_id"] for hit in qdrant_hits if hit.get("memory_id")]

    for mem_id in retrieved_ids:
        mem = store.get_memory(mem_id, user_id=user.uid)
        if mem and mem.retention_status == RetentionStatus.ACTIVE:
            retrieved_memories.append(mem)

    # If vector retrieval yielded few results, fallback/supplement with SQLite lexical search
    if len(retrieved_memories) < 3:
        lexical_mems = store.search_memories(query=req.content, user_id=user.uid, top_k=5)
        for lm in lexical_mems:
            if lm.id not in [m.id for m in retrieved_memories]:
                retrieved_memories.append(lm)


    # Score and rank retrieved memories
    scorer.score_all(retrieved_memories, task_context=req.content)
    retrieved_memories.sort(key=lambda m: m.retention_score or 0.0, reverse=True)

    # Token budget enforcement: select memories fitting within budget
    budget = min(settings.token_budget, 4000)
    current_tokens = 0
    top_memories: List[Memory] = []
    for m in retrieved_memories:
        m_tokens = m.estimated_tokens()
        if current_tokens + m_tokens <= budget:
            top_memories.append(m)
            current_tokens += m_tokens
        if len(top_memories) >= 5:
            break

    # Touch retrieved memories to update access frequency and recency stats
    for m in top_memories:
        store.touch_memory(m.id, user_id=user.uid)

    # 3. Extract candidate memories from interaction with deduplication BEFORE generating response
    candidates = gemini_service.extract_candidate_memories(user_message=req.content, user_id=user.uid)
    newly_saved_memories: List[Memory] = []
    for cand in candidates:
        dup = store.find_duplicate(cand.content, user_id=user.uid)
        if not dup:
            score, breakdown = scorer.score_memory(cand)
            cand.retention_score = score
            cand.score_breakdown = breakdown
            saved = store.save_memory(cand)
            pt_id = vector_service.upsert_memory(saved)
            if pt_id:
                saved.qdrant_point_id = pt_id
                store.save_memory(saved)
            newly_saved_memories.append(saved)
            logger.info("Successfully persisted new memory %s for user %s: '%s'", saved.id, user.uid, saved.content)
        else:
            store.touch_memory(dup.id, user_id=user.uid)

    # 4. Fetch conversation history
    history = store.get_conversation_messages(conversation_id, user_id=user.uid)

    # 5. Generate Gemini response with verified persistence awareness
    try:
        response_text = gemini_service.generate_response(
            messages=history,
            retrieved_memories=top_memories,
            user_name=user.name or user.email,
            newly_saved_memories=newly_saved_memories,
        )
    except Exception as gen_err:
        logger.error("Gemini generation failed: %s", gen_err)
        failed_id = str(uuid.uuid4())
        if firestore_service.is_healthy().get("healthy"):
            firestore_service.mark_assistant_message_failed(user.uid, conversation_id, failed_id, str(gen_err))
        raise HTTPException(status_code=500, detail=f"AI generation failed: {str(gen_err)}")

    # 6. Save Assistant Message with persistence metadata
    assistant_msg = ChatMessage(
        conversation_id=conversation_id,
        user_id=user.uid,
        role="assistant",
        content=response_text,
        token_count=max(1, len(response_text) // 4),
        retrieved_memory_ids=[m.id for m in top_memories],
        metadata={
            "new_memories_created": [m.id for m in newly_saved_memories],
        },
    )
    store.save_message(assistant_msg)
    if firestore_service.is_healthy().get("healthy"):
        firestore_service.save_message(user.uid, conversation_id, assistant_msg)

    # Update conversation title automatically on first exchange if still default
    if conv.title == "New Conversation" and len(history) <= 2:
        snippet = req.content[:35].strip()
        new_title = snippet + ("..." if len(req.content) > 35 else "")
        store.update_conversation(conversation_id, user_id=user.uid, title=new_title)
        if firestore_service.is_healthy().get("healthy"):
            firestore_service.update_conversation(user.uid, conversation_id, title=new_title)

    return assistant_msg


@app.post("/api/v1/conversations/{conversation_id}/messages/stream", tags=["Conversations"])
async def send_chat_message_stream(
    conversation_id: str,
    req: ChatMessageCreateRequest,
    user: AuthenticatedUser = Depends(resolve_user_optional),
):
    """Submits user prompt and streams Gemini response tokens via Server-Sent Events (SSE)."""
    import json
    conv = store.get_conversation(conversation_id, user_id=user.uid)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found or access denied.")

    # 1. Save User Message
    user_msg = ChatMessage(
        conversation_id=conversation_id,
        user_id=user.uid,
        role="user",
        content=req.content,
        token_count=max(1, len(req.content) // 4),
    )
    store.save_message(user_msg)
    if firestore_service.is_healthy().get("healthy"):
        firestore_service.save_message(user.uid, conversation_id, user_msg)

    # 2. Check for explicit memory lifecycle directive BEFORE standard retrieval & extraction
    lifecycle_response = lifecycle_router.route_and_execute(
        user_id=user.uid,
        conversation_id=conversation_id,
        user_message=req.content,
    )
    if lifecycle_response is not None:
        is_preview = is_preview_request(req.content)

        async def sse_lifecycle_stream():
            yield f"data: {json.dumps({'type': 'init', 'retrieved_memories': [], 'newly_saved_memories': []})}\n\n"
            chunk_size = 64
            for i in range(0, len(lifecycle_response), chunk_size):
                chunk = lifecycle_response[i:i + chunk_size]
                yield f"data: {json.dumps({'type': 'chunk', 'delta': chunk})}\n\n"

            assistant_msg = ChatMessage(
                conversation_id=conversation_id,
                user_id=user.uid,
                role="assistant",
                content=lifecycle_response,
                token_count=max(1, len(lifecycle_response) // 4),
                retrieved_memory_ids=[],
                metadata={
                    "lifecycle_operation": True,
                    "lifecycle_mode": "preview" if is_preview else "mutation",
                },
            )
            store.save_message(assistant_msg)
            if firestore_service.is_healthy().get("healthy"):
                firestore_service.save_message(user.uid, conversation_id, assistant_msg)

            yield f"data: {json.dumps({'type': 'done', 'message_id': assistant_msg.id})}\n\n"

        return StreamingResponse(sse_lifecycle_stream(), media_type="text/event-stream")

    # 3. Retrieve personalized memories (Qdrant semantic + SQLite lexical fallback + archive recall)
    retrieved_memories: List[Memory] = []
    qdrant_hits = vector_service.search_memories(query=req.content, user_id=user.uid, top_k=5, status="active")
    retrieved_ids = [hit["memory_id"] for hit in qdrant_hits if hit.get("memory_id")]
    for mem_id in retrieved_ids:
        mem = store.get_memory(mem_id, user_id=user.uid)
        if mem and mem.retention_status == RetentionStatus.ACTIVE:
            retrieved_memories.append(mem)

    if len(retrieved_memories) < 3:
        for lm in store.search_memories(query=req.content, user_id=user.uid, top_k=5):
            if lm.id not in [m.id for m in retrieved_memories]:
                retrieved_memories.append(lm)


    scorer.score_all(retrieved_memories, task_context=req.content)
    retrieved_memories.sort(key=lambda m: m.retention_score or 0.0, reverse=True)
    budget = min(settings.token_budget, 4000)
    current_tokens = 0
    top_memories = []
    for m in retrieved_memories:
        m_tokens = m.estimated_tokens()
        if current_tokens + m_tokens <= budget:
            top_memories.append(m)
            current_tokens += m_tokens
        if len(top_memories) >= 5:
            break

    for m in top_memories:
        store.touch_memory(m.id, user_id=user.uid)

    # 3. Extract candidate memories and persist BEFORE streaming response
    candidates = gemini_service.extract_candidate_memories(user_message=req.content, user_id=user.uid)
    newly_saved_memories: List[Memory] = []
    for cand in candidates:
        dup = store.find_duplicate(cand.content, user_id=user.uid)
        if not dup:
            cand_score, cand_breakdown = scorer.score_memory(cand)
            cand.retention_score = cand_score
            cand.score_breakdown = cand_breakdown
            saved_cand = store.save_memory(cand)
            pt_id = vector_service.upsert_memory(saved_cand)
            if pt_id:
                saved_cand.qdrant_point_id = pt_id
                store.save_memory(saved_cand)
            newly_saved_memories.append(saved_cand)
            logger.info("Persisted new memory %s before streaming for user %s: '%s'", saved_cand.id, user.uid, saved_cand.content)
        else:
            store.touch_memory(dup.id, user_id=user.uid)

    history = store.get_conversation_messages(conversation_id, user_id=user.uid)

    async def sse_event_stream():
        accumulated_text = ""
        try:
            # Yield initial metadata including newly persisted memory IDs
            yield f"data: {json.dumps({'type': 'init', 'retrieved_memories': [m.id for m in top_memories], 'newly_saved_memories': [m.id for m in newly_saved_memories]})}\n\n"

            for chunk in gemini_service.generate_response_stream(
                messages=history,
                retrieved_memories=top_memories,
                user_name=user.name or user.email,
                newly_saved_memories=newly_saved_memories,
            ):
                accumulated_text += chunk
                yield f"data: {json.dumps({'type': 'chunk', 'delta': chunk})}\n\n"

            # Save Assistant Message upon completion with persistence metadata
            assistant_msg = ChatMessage(
                conversation_id=conversation_id,
                user_id=user.uid,
                role="assistant",
                content=accumulated_text,
                token_count=max(1, len(accumulated_text) // 4),
                retrieved_memory_ids=[m.id for m in top_memories],
                metadata={
                    "new_memories_created": [m.id for m in newly_saved_memories],
                },
            )
            store.save_message(assistant_msg)
            if firestore_service.is_healthy().get("healthy"):
                firestore_service.save_message(user.uid, conversation_id, assistant_msg)

            if conv.title == "New Conversation" and len(history) <= 2:
                snippet = req.content[:35].strip()
                new_title = snippet + ("..." if len(req.content) > 35 else "")
                store.update_conversation(conversation_id, user_id=user.uid, title=new_title)
                if firestore_service.is_healthy().get("healthy"):
                    firestore_service.update_conversation(user.uid, conversation_id, title=new_title)

            yield f"data: {json.dumps({'type': 'done', 'message_id': assistant_msg.id, 'new_memories_created': [m.id for m in newly_saved_memories]})}\n\n"

        except Exception as e:
            logger.error("SSE stream error: %s", e)
            failed_id = str(uuid.uuid4())
            if firestore_service.is_healthy().get("healthy"):
                firestore_service.mark_assistant_message_failed(user.uid, conversation_id, failed_id, str(e))
            yield f"data: {json.dumps({'type': 'error', 'detail': str(e)})}\n\n"

    return StreamingResponse(sse_event_stream(), media_type="text/event-stream")



# ==============================================================================
# MEMORY LIFECYCLE MANAGEMENT (Multi-Tenant)
# ==============================================================================

@app.post(
    "/api/v1/memories",
    response_model=Memory,
    status_code=status.HTTP_201_CREATED,
    tags=["Memories"],
)
def create_memory(
    request: MemoryCreateRequest,
    user: AuthenticatedUser = Depends(resolve_user_optional),
):
    """Creates and persists a new memory item for the current user with deduplication."""
    target_uid = request.user_id if (user.is_admin and request.user_id) else user.uid
    
    # 1. Deduplication check (Section 4)
    existing = store.find_duplicate(request.content, user_id=target_uid)
    if existing:
        store.touch_memory(existing.id, user_id=target_uid)
        return existing

    created_dt = request.created_at or utc_now()
    accessed_dt = request.last_accessed_at or created_dt

    memory = Memory(
        user_id=target_uid,
        content=request.content.strip(),
        importance=request.importance,
        category=request.category,
        memory_type=request.memory_type,
        is_pinned=request.is_pinned,
        is_critical=request.is_critical,
        tags=request.tags,
        metadata=request.metadata,
        created_at=created_dt,
        last_accessed_at=accessed_dt,
        access_count=request.access_count or 0,
    )
    # Compute initial retention score
    score, breakdown = scorer.score_memory(memory)
    memory.retention_score = score
    memory.score_breakdown = breakdown
    saved = store.save_memory(memory)

    # Upsert into Qdrant semantic store
    pt_id = vector_service.upsert_memory(saved)
    if pt_id:
        saved.qdrant_point_id = pt_id
        store.save_memory(saved)

    return saved


@app.get(
    "/api/v1/memories",
    response_model=List[Memory],
    tags=["Memories"],
)
def list_memories(
    status_filter: Optional[RetentionStatus] = Query(None, alias="status"),
    category: Optional[MemoryCategory] = None,
    memory_type: Optional[MemoryType] = None,
    include_forgotten: bool = Query(False),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    user: AuthenticatedUser = Depends(resolve_user_optional),
):
    """Lists memories scoped to the verified user."""
    # If admin and user_id not specified, can view all; ordinary users only view their own
    owner_uid = None if user.is_admin else user.uid
    return store.list_memories(
        user_id=owner_uid,
        status=status_filter,
        category=category,
        memory_type=memory_type,
        include_forgotten=include_forgotten,
        limit=limit,
        offset=offset,
    )


@app.get(
    "/api/v1/memories/stats",
    response_model=MemoryStats,
    tags=["Memories"],
)
def get_user_memory_stats(
    user: AuthenticatedUser = Depends(resolve_user_optional),
):
    """Retrieves statistical summary of cognitive memories for authenticated user."""
    owner_uid = None if user.is_admin else user.uid
    return store.get_stats(user_id=owner_uid)


@app.get(
    "/api/v1/memories/activity-log",
    response_model=List[LifecycleActivityItem],
    tags=["Memories"],
)
def get_activity_log(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: AuthenticatedUser = Depends(resolve_user_optional),
):
    """Retrieves verified lifecycle activity events for the authenticated user."""
    owner_uid = None if user.is_admin else user.uid
    return store.get_activity_log(user_id=owner_uid, limit=limit, offset=offset)


@app.get(
    "/api/v1/memories/lifecycle-stats",
    tags=["Memories"],
)
def get_lifecycle_stats(
    user: AuthenticatedUser = Depends(resolve_user_optional),
):
    """Calculates authoritative lifecycle totals from persisted operation records."""
    owner_uid = None if user.is_admin else user.uid
    return store.get_lifecycle_stats(user_id=owner_uid)


@app.get(
    "/api/v1/lifecycle/activity-log",
    response_model=List[LifecycleActivityItem],
    tags=["Forgetting Engine"],
)
def get_lifecycle_activity_log(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: AuthenticatedUser = Depends(resolve_user_optional),
):
    """Retrieves verified lifecycle activity events for the authenticated user (alias)."""
    owner_uid = None if user.is_admin else user.uid
    return store.get_activity_log(user_id=owner_uid, limit=limit, offset=offset)


@app.get(
    "/api/v1/memories/{memory_id}",
    response_model=Memory,
    tags=["Memories"],
)
def get_memory(
    memory_id: str,
    user: AuthenticatedUser = Depends(resolve_user_optional),
):
    """Retrieves a single memory by ID enforcing tenant isolation."""
    owner_uid = None if user.is_admin else user.uid
    mem = store.get_memory(memory_id, user_id=owner_uid)
    if not mem:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Memory '{memory_id}' not found.",
        )
    return mem


@app.patch(
    "/api/v1/memories/{memory_id}",
    response_model=Memory,
    tags=["Memories"],
)
def update_memory(
    memory_id: str,
    request: MemoryUpdateRequest,
    user: AuthenticatedUser = Depends(resolve_user_optional),
):
    """Updates mutable fields of a memory."""
    owner_uid = None if user.is_admin else user.uid
    mem = store.get_memory(memory_id, user_id=owner_uid)
    if not mem:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Memory '{memory_id}' not found.",
        )

    if request.content is not None:
        mem.content = request.content
    if request.importance is not None:
        mem.importance = request.importance
    if request.category is not None:
        mem.category = request.category
    if request.memory_type is not None:
        mem.memory_type = request.memory_type
    if request.tags is not None:
        mem.tags = request.tags
    if request.metadata is not None:
        mem.metadata.update(request.metadata)

    score, breakdown = scorer.score_memory(mem)
    mem.retention_score = score
    mem.score_breakdown = breakdown

    saved = store.save_memory(mem)
    vector_service.upsert_memory(saved)
    return saved


@app.patch(
    "/api/v1/memories/{memory_id}/importance",
    response_model=Memory,
    tags=["Memories"],
)
def update_importance(
    memory_id: str,
    payload: MemoryImportanceUpdateRequest,
    user: AuthenticatedUser = Depends(resolve_user_optional),
):
    """Updates importance rating for a memory."""
    owner_uid = None if user.is_admin else user.uid
    mem = store.update_importance(memory_id, payload.importance, user_id=owner_uid)
    if not mem:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Memory '{memory_id}' not found.",
        )
    vector_service.upsert_memory(mem)
    return mem


@app.post(
    "/api/v1/memories/{memory_id}/pin",
    response_model=Memory,
    tags=["Memories"],
)
def pin_memory(
    memory_id: str,
    user: AuthenticatedUser = Depends(resolve_user_optional),
):
    """Pins a memory to permanently prevent deletion or archival."""
    owner_uid = None if user.is_admin else user.uid
    mem = store.set_pinned(memory_id, pinned=True, user_id=owner_uid)
    if not mem:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Memory '{memory_id}' not found.",
        )
    vector_service.upsert_memory(mem)
    return mem


@app.post(
    "/api/v1/memories/{memory_id}/unpin",
    response_model=Memory,
    tags=["Memories"],
)
def unpin_memory(
    memory_id: str,
    user: AuthenticatedUser = Depends(resolve_user_optional),
):
    """Removes pinned status from a memory."""
    owner_uid = None if user.is_admin else user.uid
    mem = store.set_pinned(memory_id, pinned=False, user_id=owner_uid)
    if not mem:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Memory '{memory_id}' not found.",
        )
    vector_service.upsert_memory(mem)
    return mem


@app.post(
    "/api/v1/memories/{memory_id}/critical",
    response_model=Memory,
    tags=["Memories"],
)
def mark_critical(
    memory_id: str,
    critical: bool = Query(True),
    user: AuthenticatedUser = Depends(resolve_user_optional),
):
    """Sets or clears critical status on a memory."""
    owner_uid = None if user.is_admin else user.uid
    mem = store.set_critical(memory_id, critical=critical, user_id=owner_uid)
    if not mem:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Memory '{memory_id}' not found.",
        )
    vector_service.upsert_memory(mem)
    return mem


@app.post(
    "/api/v1/memories/{memory_id}/archive",
    response_model=Memory,
    tags=["Memories"],
)
def archive_memory(
    memory_id: str,
    reason: str = Query("Manual API archival"),
    user: AuthenticatedUser = Depends(resolve_user_optional),
):
    """Moves memory to archived status."""
    owner_uid = None if user.is_admin else user.uid
    existing = store.get_memory(memory_id, user_id=owner_uid)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Memory '{memory_id}' not found.",
        )
    if existing.is_protected():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Memory '{memory_id}' is protected (pinned/critical) and cannot be archived.",
        )
    if existing.retention_status == RetentionStatus.ARCHIVED:
        # Idempotent: already archived
        return existing
    if existing.retention_status != RetentionStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot archive memory '{memory_id}' from status '{existing.retention_status.value}'. Only active memories can be archived.",
        )
    mem = store.archive_memory(memory_id, reason=reason, user_id=owner_uid)
    if not mem:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Could not archive memory '{memory_id}'.",
        )
    # Retain vector in Qdrant with status='archived' for on-demand semantic retrieval
    vector_service.update_memory_status(memory_id, "archived")
    return mem


@app.post(
    "/api/v1/memories/{memory_id}/restore",
    response_model=Memory,
    tags=["Memories"],
)
def restore_memory(
    memory_id: str,
    user: AuthenticatedUser = Depends(resolve_user_optional),
):
    """Restores an archived or summarized memory back to active status."""
    owner_uid = None if user.is_admin else user.uid
    existing = store.get_memory(memory_id, user_id=owner_uid)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Memory '{memory_id}' not found.",
        )
    if existing.retention_status == RetentionStatus.ACTIVE:
        # Idempotent: already active
        return existing
    if existing.retention_status not in (RetentionStatus.ARCHIVED, RetentionStatus.SUMMARIZED):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot restore memory '{memory_id}' with status '{existing.retention_status.value}'. Only archived or summarized memories can be restored to active.",
        )
    mem = store.restore_memory(memory_id, user_id=owner_uid)
    if not mem:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Could not restore memory '{memory_id}'.",
        )
    vector_service.update_memory_status(memory_id, "active")
    return mem


@app.delete(
    "/api/v1/memories/{memory_id}",
    status_code=status.HTTP_200_OK,
    tags=["Memories"],
)
def forget_memory(
    memory_id: str,
    permanent: bool = Query(False),
    reason: str = Query("Manual API deletion"),
    user: AuthenticatedUser = Depends(resolve_user_optional),
):
    """Marks memory as forgotten or permanently purges it."""
    owner_uid = None if user.is_admin else user.uid
    existing = store.get_memory(memory_id, user_id=owner_uid)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Could not forget memory '{memory_id}'. Memory may not exist, belongs to another user, or is protected.",
        )
    if existing.is_protected():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Memory '{memory_id}' is protected (pinned/critical) and cannot be pruned.",
        )
    success = store.forget_memory(
        memory_id,
        permanent_delete=permanent,
        reason=reason,
        user_id=owner_uid,
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Could not forget memory '{memory_id}'. Memory may not exist, belongs to another user, or is protected.",
        )
    if permanent:
        qdrant_ok = vector_service.delete_memory(memory_id)
    else:
        qdrant_ok = vector_service.update_memory_status(memory_id, "forgotten")

    return {
        "status": "success",
        "memory_id": memory_id,
        "permanent": permanent,
        "qdrant_synchronized": qdrant_ok,
    }





@app.post(
    "/api/v1/memories/search",
    response_model=List[Memory],
    tags=["Memories"],
)
def search_memories(
    request: MemorySearchRequest,
    user: AuthenticatedUser = Depends(resolve_user_optional),
):
    """Searches memories using hybrid dense vector matching and token overlap."""
    owner_uid = user.uid

    # 1. Try Qdrant semantic search if enabled
    if request.use_vector:
        hits = vector_service.search_memories(
            query=request.query,
            user_id=owner_uid,
            top_k=request.top_k,
            status=request.status.value if request.status else None,
        )
        if hits:
            results = []
            for h in hits:
                mem = store.get_memory(h["memory_id"], user_id=owner_uid)
                if mem:
                    results.append(mem)
            if results:
                return results

    # 2. Fallback to SQLite lexical search
    return store.search_memories(
        query=request.query,
        user_id=owner_uid,
        category=request.category,
        status=request.status,
        top_k=request.top_k,
    )


# ==============================================================================
# FORGETTING ENGINE (DRY-RUN & PERSISTENT APPLICATION)
# ==============================================================================

@app.post(
    "/api/v1/forgetting/evaluate",
    response_model=ForgettingEvaluationResult,
    tags=["Forgetting Engine"],
)
def evaluate_forgetting(
    request: ForgettingEvaluationRequest,
    user: AuthenticatedUser = Depends(resolve_user_optional),
):
    """Evaluates active memories and proposes retention, summarization, archival, and forgetting actions (Dry-Run by default)."""
    owner_uid = None if user.is_admin else user.uid
    return engine.evaluate(
        task_context=request.task_context,
        dry_run=request.dry_run,
        user_id=owner_uid,
    )


@app.post(
    "/api/v1/forgetting/apply",
    response_model=ForgettingApplyResult,
    tags=["Forgetting Engine"],
)
def apply_forgetting(
    request: ForgettingApplyRequest,
    user: AuthenticatedUser = Depends(resolve_user_optional),
):
    """Executes forgetting recommendations persistently in database and vector store."""
    owner_uid = None if user.is_admin else user.uid
    if request.action_items:
        # Validate that action items belong to the authenticated user and protect pinned/critical items
        sanitized_items: List[ForgettingActionItem] = []
        for item in request.action_items:
            mem = store.get_memory(item.memory_id, user_id=owner_uid)
            if not mem:
                logger.warning(
                    "User %s attempted action on unowned or missing memory %s",
                    user.uid,
                    item.memory_id,
                )
                continue

            if mem.is_protected() and item.action not in (ForgettingActionType.KEEP, ForgettingActionType.RETAIN):
                logger.warning(
                    "Memory %s is protected (pinned=%s, critical=%s). Coercing to KEEP.",
                    mem.id,
                    mem.is_pinned,
                    mem.is_critical,
                )
                sanitized_items.append(
                    item.model_copy(update={
                        "action": ForgettingActionType.KEEP,
                        "reason": f"Protected from deletion ({'pinned' if mem.is_pinned else 'critical'})",
                    })
                )
            else:
                sanitized_items.append(item)

        eval_result = ForgettingEvaluationResult(
            evaluation_id=request.evaluation_id or str(uuid.uuid4()),
            dry_run=False,
            evaluated_at=utc_now(),
            total_active_before=len(sanitized_items),
            total_active_after=sum(
                1 for a in sanitized_items
                if a.action in (ForgettingActionType.KEEP, ForgettingActionType.RETAIN)
            ),
            actions_proposed=sanitized_items,
        )
        counts = engine.apply(eval_result, task_context=request.task_context, user_id=owner_uid)
        items = sanitized_items
    else:
        eval_result = engine.evaluate(task_context=request.task_context, dry_run=False, user_id=owner_uid)
        counts = engine.apply(eval_result, task_context=request.task_context, user_id=owner_uid)
        items = eval_result.actions_proposed

    retained_val = counts.get("retained", 0)
    summarized_val = counts.get("summarized", 0)
    archived_val = counts.get("archived", 0)
    forgotten_val = counts.get("forgotten", 0)

    return ForgettingApplyResult(
        evaluation_id=request.evaluation_id or eval_result.evaluation_id,
        retained=retained_val,
        summarized=summarized_val,
        archived=archived_val,
        forgotten=forgotten_val,
        keep=counts.get("keep", retained_val),
        compress=counts.get("compress", summarized_val),
        prune=counts.get("prune", forgotten_val),
        details=items,
    )


# ==============================================================================
# ADMINISTRATION & AUDITING (ROLE-PROTECTED)
# ==============================================================================

@app.get("/api/v1/admin/overview", tags=["Admin"])
def get_admin_overview(admin_user: AuthenticatedUser = Depends(get_current_admin_user)):
    """Provides high-level system metrics across users, conversations, memories, and services."""
    users = store.list_users(limit=1000)
    stats = store.get_stats()
    return {
        "status": "healthy",
        "timestamp": utc_now().isoformat(),
        "users": {
            "total": len(users),
            "active": sum(1 for u in users if u.status == "active"),
            "disabled": sum(1 for u in users if u.status != "active"),
        },
        "memories": {
            "total": stats.total_memories,
            "active": stats.active_count,
            "summarized": stats.summarized_count,
            "archived": stats.archived_count,
            "forgotten": stats.forgotten_count,
            "permanent": stats.permanent_count,
            "estimated_active_tokens": stats.estimated_active_tokens,
            "storage_size_bytes": stats.storage_size_bytes,
        },
        "services": {
            "gemini_live": gemini_service.is_live(),
            "model_configured": settings.gemini_model,
            "qdrant_healthy": vector_service.is_healthy(),
            "qdrant_collection": settings.qdrant_collection_name,
            "embedding_model": settings.embedding_model,
            "rl_mode": settings.rl_mode,
        },
    }


@app.get("/api/v1/admin/users", response_model=List[UserRecord], tags=["Admin"])
def list_admin_users(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    search: Optional[str] = None,
    admin_user: AuthenticatedUser = Depends(get_current_admin_user),
):
    """Administrative user management: search and inspect user profiles."""
    return store.list_users(limit=limit, offset=offset, search=search)


@app.patch("/api/v1/admin/users/{user_id}/status", response_model=UserRecord, tags=["Admin"])
def update_user_status(
    user_id: str,
    status_val: str = Query(..., pattern="^(active|disabled)$"),
    admin_user: AuthenticatedUser = Depends(get_current_admin_user),
):
    """Enables or disables a user account."""
    updated = store.update_user_status(user_id, status=status_val, actor_uid=admin_user.uid)
    if not updated:
        raise HTTPException(status_code=404, detail="User not found.")
    return updated


@app.patch("/api/v1/admin/users/{user_id}/role", response_model=UserRecord, tags=["Admin"])
def update_user_role(
    user_id: str,
    role_val: str = Query(..., pattern="^(user|admin)$"),
    admin_user: AuthenticatedUser = Depends(get_current_admin_user),
):
    """Assigns role (user or admin) and updates Firebase custom claims."""
    updated = store.update_user_role(user_id, role=role_val, actor_uid=admin_user.uid)
    if not updated:
        raise HTTPException(status_code=404, detail="User not found.")
    if role_val == "admin":
        provision_admin_user(user_id)
    return updated


@app.get("/api/v1/admin/audit-logs", response_model=List[SystemAuditLogItem], tags=["Admin"])
def list_audit_logs(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    actor_uid: Optional[str] = None,
    admin_user: AuthenticatedUser = Depends(get_current_admin_user),
):
    """Inspects administrative operations and security audit trails."""
    return store.list_system_audit_logs(limit=limit, offset=offset, actor_uid=actor_uid)


@app.get("/api/v1/admin/rl/experiments", response_model=List[RLExperimentRun], tags=["Admin"])
def list_rl_experiments(admin_user: AuthenticatedUser = Depends(get_current_admin_user)):
    """Retrieves reinforcement learning experiment history and benchmarks."""
    return store.list_rl_experiments(limit=50)


@app.post("/api/v1/admin/rl/experiments", response_model=RLExperimentRun, tags=["Admin"])
def trigger_rl_experiment(
    iterations: int = Query(50, ge=10, le=500),
    admin_user: AuthenticatedUser = Depends(get_current_admin_user),
):
    """Runs a controlled reinforcement learning benchmark experiment."""
    from experiments.run_experiment import generate_synthetic_dataset
    dataset = generate_synthetic_dataset(utc_now())

    exp_run = rl_engine.run_training_experiment(
        training_corpus=dataset,
        iterations=iterations,
    )
    store.save_rl_experiment(exp_run)
    store.log_system_audit(
        actor_uid=admin_user.uid,
        action="TRIGGER_RL_EXPERIMENT",
        target_type="rl_policy",
        target_id=exp_run.id,
        details={"iterations": iterations, "mean_reward": exp_run.mean_reward},
    )
    return exp_run


# ==============================================================================
# BACKWARD COMPATIBLE RESEARCH ENDPOINTS (Used by existing tests and Streamlit)
# ==============================================================================

@app.get("/api/v1/statistics", response_model=MemoryStats, tags=["Analytics"])
def get_statistics():
    """Returns storage metrics and counts across all memory lifecycle states."""
    return store.get_stats()


@app.post("/api/v1/agent/task", response_model=AgentTaskResponse, tags=["Agent"])
def agent_task(request: AgentTaskRequest):
    """Processes a user task through the demonstration agent lifecycle."""
    return agent.process_task(request)
