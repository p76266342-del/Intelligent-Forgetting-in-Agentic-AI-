"""Cloud Firestore Integration for Chat History and Conversation Transcripts.

Provides multi-tenant, user-isolated chat transcript storage adhering to:
    users/{userId}/conversations/{conversationId}
    users/{userId}/conversations/{conversationId}/messages/{messageId}

Enforces ownership checks in application logic, supports pagination, server timestamps,
graceful handling of network timeouts / outages, and maintains complete decoupling from
cognitive memory lifecycle records.
"""

from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional
import uuid

from intelligent_forgetting.config import Settings, get_settings
from intelligent_forgetting.models import ChatMessage, Conversation, utc_now

logger = logging.getLogger("intelligent_forgetting.firestore")


class FirestoreChatService:
    """Manages chat conversation transcripts and message persistence in Cloud Firestore."""

    def __init__(self, settings: Optional[Settings] = None, client: Optional[Any] = None):
        self.settings = settings or get_settings()
        self.client = client
        self._is_active = False
        if self.client is not None:
            self._is_active = True
        else:
            self._init_client()

    def _init_client(self) -> None:
        """Initializes the Google Cloud Firestore client via Firebase Admin SDK."""
        try:
            from intelligent_forgetting.auth import initialize_firebase

            init_ok = initialize_firebase()
            if not init_ok:
                logger.info("Firebase Admin not configured for live Firestore; offline/fallback mode active.")
                self.client = None
                self._is_active = False
                self._fallback_reason = "Firebase Admin SDK initialization returned false (no service account credentials)"
                return

            from firebase_admin import firestore

            self.client = firestore.client()
            self._is_active = True
            self._fallback_reason = None
            logger.info("Cloud Firestore client initialized successfully for project: %s", self.settings.firebase_project_id)
        except Exception as e:
            # Mask sensitive details in log output
            logger.warning("Cloud Firestore client initialization skipped or unavailable (%s: %s). Fallback mode enabled.", type(e).__name__, e)
            self.client = None
            self._is_active = False
            self._fallback_reason = f"{type(e).__name__}: {str(e)}"

    def is_healthy(self) -> Dict[str, Any]:
        """Returns health and connection status of Cloud Firestore."""
        is_conn = self._is_active and self.client is not None
        return {
            "healthy": is_conn,
            "status": "connected" if is_conn else "unconfigured_or_fallback",
            "project_id": self.settings.firebase_project_id,
            "reason": None if is_conn else getattr(self, "_fallback_reason", "Service account credentials not provided"),
        }

    # ==========================================================================
    # CONVERSATION OPERATIONS (users/{userId}/conversations/{conversationId})
    # ==========================================================================

    def create_conversation(self, user_id: str, conv: Conversation) -> bool:
        """Stores conversation metadata document under users/{userId}/conversations/{conversationId}."""
        if not self._is_active or not self.client:
            return False

        try:
            doc_ref = (
                self.client.collection("users")
                .document(user_id)
                .collection("conversations")
                .document(conv.id)
            )

            payload = {
                "id": conv.id,
                "user_id": user_id,
                "title": conv.title,
                "createdAt": conv.created_at.isoformat(),
                "updatedAt": conv.updated_at.isoformat(),
                "messageCount": conv.message_count,
                "model": conv.model,
                "is_pinned": bool(conv.is_pinned),
                "metadata": conv.metadata or {},
            }
            doc_ref.set(payload)
            return True
        except Exception as e:
            logger.error("Failed to create conversation %s in Firestore for user %s: %s", conv.id, user_id, e)
            return False

    def get_conversation(self, user_id: str, conv_id: str) -> Optional[Conversation]:
        """Retrieves a conversation metadata document verifying user ownership."""
        if not self._is_active or not self.client:
            return None

        try:
            doc_ref = (
                self.client.collection("users")
                .document(user_id)
                .collection("conversations")
                .document(conv_id)
            )
            snapshot = doc_ref.get()
            if not snapshot.exists:
                return None

            data = snapshot.to_dict()
            if not data or data.get("user_id") != user_id:
                return None

            # Parse timestamps
            created_at = (
                datetime.fromisoformat(data["createdAt"])
                if isinstance(data.get("createdAt"), str)
                else utc_now()
            )
            updated_at = (
                datetime.fromisoformat(data["updatedAt"])
                if isinstance(data.get("updatedAt"), str)
                else utc_now()
            )

            return Conversation(
                id=data.get("id", conv_id),
                user_id=user_id,
                title=data.get("title", "Conversation"),
                created_at=created_at,
                updated_at=updated_at,
                is_pinned=bool(data.get("is_pinned", False)),
                model=data.get("model", "gemini-2.5-flash"),
                message_count=int(data.get("messageCount", 0)),
                metadata=data.get("metadata", {}),
            )
        except Exception as e:
            logger.error("Failed to fetch conversation %s from Firestore for user %s: %s", conv_id, user_id, e)
            return None

    def list_conversations(
        self,
        user_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Conversation]:
        """Lists conversations for the authenticated user ordered chronologically."""
        if not self._is_active or not self.client:
            return []

        try:
            col_ref = (
                self.client.collection("users")
                .document(user_id)
                .collection("conversations")
            )
            query = col_ref.order_by("updatedAt", direction="DESCENDING").offset(offset).limit(limit)
            docs = query.stream()

            conversations: List[Conversation] = []
            for doc in docs:
                data = doc.to_dict()
                if not data:
                    continue
                created_at = (
                    datetime.fromisoformat(data["createdAt"])
                    if isinstance(data.get("createdAt"), str)
                    else utc_now()
                )
                updated_at = (
                    datetime.fromisoformat(data["updatedAt"])
                    if isinstance(data.get("updatedAt"), str)
                    else utc_now()
                )

                conversations.append(
                    Conversation(
                        id=data.get("id", doc.id),
                        user_id=user_id,
                        title=data.get("title", "Conversation"),
                        created_at=created_at,
                        updated_at=updated_at,
                        is_pinned=bool(data.get("is_pinned", False)),
                        model=data.get("model", "gemini-2.5-flash"),
                        message_count=int(data.get("messageCount", 0)),
                        metadata=data.get("metadata", {}),
                    )
                )
            return conversations
        except Exception as e:
            logger.error("Failed to list conversations from Firestore for user %s: %s", user_id, e)
            return []

    def update_conversation(
        self,
        user_id: str,
        conv_id: str,
        title: Optional[str] = None,
        is_pinned: Optional[bool] = None,
    ) -> Optional[Conversation]:
        """Updates title or pin status of a conversation document in Firestore."""
        if not self._is_active or not self.client:
            return None

        try:
            doc_ref = (
                self.client.collection("users")
                .document(user_id)
                .collection("conversations")
                .document(conv_id)
            )

            snapshot = doc_ref.get()
            if not snapshot.exists:
                return None

            updates: Dict[str, Any] = {"updatedAt": utc_now().isoformat()}
            if title is not None:
                updates["title"] = title
            if is_pinned is not None:
                updates["is_pinned"] = bool(is_pinned)

            doc_ref.update(updates)
            return self.get_conversation(user_id, conv_id)
        except Exception as e:
            logger.error("Failed to update conversation %s in Firestore for user %s: %s", conv_id, user_id, e)
            return None

    def delete_conversation(self, user_id: str, conv_id: str) -> bool:
        """Cascades deletion of conversation messages subcollection and conversation document.
        
        NOTE: In accordance with project policy, deleting a conversation transcript NEVER deletes
        cognitive memory records in SQLite or Qdrant.
        """
        if not self._is_active or not self.client:
            return False

        try:
            conv_ref = (
                self.client.collection("users")
                .document(user_id)
                .collection("conversations")
                .document(conv_id)
            )

            # Delete all messages in subcollection
            messages_ref = conv_ref.collection("messages")
            for msg_doc in messages_ref.stream():
                msg_doc.reference.delete()

            # Delete the parent conversation document
            conv_ref.delete()
            logger.info("Deleted Firestore conversation transcript %s for user %s", conv_id, user_id)
            return True
        except Exception as e:
            logger.error("Failed to delete conversation %s from Firestore: %s", conv_id, e)
            return False

    # ==========================================================================
    # MESSAGE OPERATIONS (users/{userId}/conversations/{conversationId}/messages/{messageId})
    # ==========================================================================

    def save_message(self, user_id: str, conv_id: str, msg: ChatMessage) -> bool:
        """Stores a message with stable messageId in Firestore subcollection.
        
        Updates conversation updatedAt and messageCount.
        """
        if not self._is_active or not self.client:
            return False

        try:
            conv_ref = (
                self.client.collection("users")
                .document(user_id)
                .collection("conversations")
                .document(conv_id)
            )
            msg_ref = conv_ref.collection("messages").document(msg.id)

            payload = {
                "id": msg.id,
                "conversation_id": conv_id,
                "user_id": user_id,
                "role": msg.role,
                "content": msg.content,
                "createdAt": msg.created_at.isoformat(),
                "token_count": msg.token_count,
                "retrieved_memory_ids": msg.retrieved_memory_ids or [],
                "metadata": msg.metadata or {},
            }
            msg_ref.set(payload)

            # Update parent conversation document
            try:
                # Increment messageCount and touch updatedAt
                conv_snap = conv_ref.get()
                current_count = conv_snap.to_dict().get("messageCount", 0) if conv_snap.exists else 0
                conv_ref.set(
                    {
                        "id": conv_id,
                        "user_id": user_id,
                        "updatedAt": msg.created_at.isoformat(),
                        "messageCount": current_count + 1,
                    },
                    merge=True,
                )
            except Exception as meta_err:
                logger.warning("Could not update conversation metadata on message append: %s", meta_err)

            return True
        except Exception as e:
            logger.error("Failed to save message %s to Firestore for user %s: %s", msg.id, user_id, e)
            return False

    def mark_assistant_message_failed(
        self,
        user_id: str,
        conv_id: str,
        msg_id: str,
        error_detail: str,
    ) -> bool:
        """Persists a failed or interrupted assistant message state to Firestore."""
        if not self._is_active or not self.client:
            return False

        try:
            msg_ref = (
                self.client.collection("users")
                .document(user_id)
                .collection("conversations")
                .document(conv_id)
                .collection("messages")
                .document(msg_id)
            )
            payload = {
                "id": msg_id,
                "conversation_id": conv_id,
                "user_id": user_id,
                "role": "assistant",
                "content": "[Assistant response failed or was interrupted]",
                "createdAt": utc_now().isoformat(),
                "metadata": {
                    "status": "failed",
                    "error": error_detail,
                },
            }
            msg_ref.set(payload)
            return True
        except Exception as e:
            logger.error("Failed to record failed assistant message in Firestore: %s", e)
            return False

    def get_messages(
        self,
        user_id: str,
        conv_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> List[ChatMessage]:
        """Retrieves messages for a conversation ordered chronologically."""
        if not self._is_active or not self.client:
            return []

        try:
            msgs_ref = (
                self.client.collection("users")
                .document(user_id)
                .collection("conversations")
                .document(conv_id)
                .collection("messages")
            )
            query = msgs_ref.order_by("createdAt", direction="ASCENDING").offset(offset).limit(limit)
            docs = query.stream()

            messages: List[ChatMessage] = []
            for doc in docs:
                data = doc.to_dict()
                if not data:
                    continue
                created_at = (
                    datetime.fromisoformat(data["createdAt"])
                    if isinstance(data.get("createdAt"), str)
                    else utc_now()
                )
                messages.append(
                    ChatMessage(
                        id=data.get("id", doc.id),
                        conversation_id=conv_id,
                        user_id=user_id,
                        role=data.get("role", "user"),
                        content=data.get("content", ""),
                        created_at=created_at,
                        token_count=int(data.get("token_count", 0)),
                        retrieved_memory_ids=data.get("retrieved_memory_ids", []),
                        metadata=data.get("metadata", {}),
                    )
                )
            return messages
        except Exception as e:
            logger.error("Failed to load messages from Firestore for conv %s: %s", conv_id, e)
            return []
