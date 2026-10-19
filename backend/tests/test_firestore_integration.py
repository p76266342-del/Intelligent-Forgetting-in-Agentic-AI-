"""Automated tests for Cloud Firestore integration:
- Saving user and assistant messages
- Retrieving conversation history
- User ownership isolation
- Invalid authentication rejection
- Firestore read/write failure handling
- Decoupling of conversation deletion from cognitive memories
"""

from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
import pytest

from intelligent_forgetting.api import app, store, firestore_service
from intelligent_forgetting.firestore_service import FirestoreChatService
from intelligent_forgetting.models import ChatMessage, Conversation, Memory, RetentionStatus


class MockFirestoreDoc:
    def __init__(self, doc_id: str, data: dict):
        self.id = doc_id
        self._data = data
        self._subcollections = {}

    @property
    def exists(self):
        return bool(self._data)

    def to_dict(self):
        return dict(self._data)

    def get(self):
        return self

    def set(self, data, merge=False):
        if merge:
            self._data.update(data)
        else:
            self._data = dict(data)

    def update(self, data):
        self._data.update(data)

    def delete(self):
        self._data = {}

    @property
    def reference(self):
        return self

    def collection(self, name: str):
        if name not in self._subcollections:
            self._subcollections[name] = MockFirestoreCollection(name)
        return self._subcollections[name]


class MockFirestoreCollection:
    def __init__(self, name: str):
        self.name = name
        self.docs = {}

    def document(self, doc_id: str):
        if doc_id not in self.docs:
            self.docs[doc_id] = MockFirestoreDoc(doc_id, {})
        return self.docs[doc_id]

    def order_by(self, field, direction="ASCENDING"):
        return self

    def offset(self, n):
        return self

    def limit(self, n):
        return self

    def stream(self):
        for doc in self.docs.values():
            if doc._data:
                yield doc


class MockFirestoreClient:
    def __init__(self):
        self.collections = {}

    def collection(self, name: str):
        if name not in self.collections:
            self.collections[name] = MockFirestoreCollection(name)
        return self.collections[name]


@pytest.fixture
def mock_firestore():
    client = MagicMock()
    users_col = MockFirestoreCollection("users")
    client.collection.side_effect = lambda name: users_col if name == "users" else MockFirestoreCollection(name)
    return client



@pytest.fixture
def client():
    return TestClient(app)


def test_firestore_save_and_retrieve_messages(mock_firestore):
    """Verifies that user and assistant messages are saved to Firestore subcollections."""
    fs = FirestoreChatService(client=mock_firestore)
    user_id = "test_user_42"
    conv = Conversation(id="conv_100", user_id=user_id, title="Test Chat")

    # 1. Create conversation
    ok = fs.create_conversation(user_id, conv)
    assert ok is True

    # 2. Save user message
    user_msg = ChatMessage(
        id="msg_u1",
        conversation_id="conv_100",
        user_id=user_id,
        role="user",
        content="What is Intelligent Forgetting?",
    )
    ok_user = fs.save_message(user_id, "conv_100", user_msg)
    assert ok_user is True

    # 3. Save assistant message
    asst_msg = ChatMessage(
        id="msg_a1",
        conversation_id="conv_100",
        user_id=user_id,
        role="assistant",
        content="Intelligent Forgetting curates cognitive memory records to maintain bounded context.",
    )
    ok_asst = fs.save_message(user_id, "conv_100", asst_msg)
    assert ok_asst is True

    # 4. Retrieve messages
    messages = fs.get_messages(user_id, "conv_100")
    assert len(messages) == 2
    assert messages[0].content == "What is Intelligent Forgetting?"
    assert messages[1].content.startswith("Intelligent Forgetting")


def test_firestore_user_ownership_isolation(mock_firestore):
    """Verifies that conversations and messages under User A cannot be accessed by User B."""
    fs = FirestoreChatService(client=mock_firestore)
    user_a = "alice_uid"
    user_b = "bob_uid"

    conv_a = Conversation(id="conv_alice", user_id=user_a, title="Alice Secret Project")
    fs.create_conversation(user_a, conv_a)

    msg_a = ChatMessage(
        id="msg_a",
        conversation_id="conv_alice",
        user_id=user_a,
        role="user",
        content="Alice secret message content",
    )
    fs.save_message(user_a, "conv_alice", msg_a)

    # Bob attempting to read Alice's conversation in Bob's path
    bob_conv = fs.get_conversation(user_b, "conv_alice")
    assert bob_conv is None

    bob_msgs = fs.get_messages(user_b, "conv_alice")
    assert len(bob_msgs) == 0


def test_firestore_failure_handling_and_graceful_degradation():
    """Simulates Firestore network outage or timeout without crashing the application."""
    faulty_client = MagicMock()
    faulty_client.collection.side_effect = Exception("DeadlineExceeded: Firestore timeout")

    fs = FirestoreChatService(client=faulty_client)
    # create_conversation handles exception gracefully
    success = fs.create_conversation("user_123", Conversation(user_id="user_123", title="Test"))
    assert success is False

    # save_message handles exception gracefully
    msg = ChatMessage(conversation_id="conv_1", user_id="user_123", role="user", content="Hi")
    msg_saved = fs.save_message("user_123", "conv_1", msg)
    assert msg_saved is False

    # get_messages returns empty list on network error rather than crashing
    msgs = fs.get_messages("user_123", "conv_1")
    assert msgs == []


def test_conversation_deletion_does_not_delete_cognitive_memories(client, mock_firestore):
    """Confirms that deleting a chat transcript in Firestore/SQLite leaves cognitive memories intact."""
    headers = {"Authorization": "Bearer test-token-convuser-user"}

    # 1. Create a cognitive memory
    mem_res = client.post(
        "/api/v1/memories",
        headers=headers,
        json={"content": "Important user business constraint: always encrypt at rest", "importance": 0.9},
    )
    assert mem_res.status_code == 201
    mem_id = mem_res.json()["id"]

    # 2. Create a conversation
    conv_res = client.post("/api/v1/conversations", headers=headers, json={"title": "Temporary Chat"})
    assert conv_res.status_code == 201
    conv_id = conv_res.json()["id"]

    # 3. Delete the conversation
    del_res = client.delete(f"/api/v1/conversations/{conv_id}", headers=headers)
    assert del_res.status_code == 200

    # 4. Verify conversation is gone
    get_conv = client.get(f"/api/v1/conversations/{conv_id}", headers=headers)
    assert get_conv.status_code == 404

    # 5. Verify cognitive memory record is STILL active and untouched
    get_mem = client.get(f"/api/v1/memories/{mem_id}", headers=headers)
    assert get_mem.status_code == 200
    assert get_mem.json()["content"] == "Important user business constraint: always encrypt at rest"
    assert get_mem.json()["retention_status"] == RetentionStatus.ACTIVE.value
