import logging
from datetime import datetime, timezone
from unittest.mock import Mock

import pytest
from bson import ObjectId
from pymongo.errors import PyMongoError

from app.services.message_service import MessageService


class FakeCollection:
    def __init__(self, *, conversation, message, update_errors=None):
        self.conversation = conversation
        self.message = message
        self.update_errors = list(update_errors or [])
        self.insert_calls = 0
        self.update_calls = 0

    def find_one(self, query):
        if "_id" in query and self.message is not None and query["_id"] == self.message["_id"]:
            return self.message
        return self.conversation

    def insert_one(self, document):
        self.insert_calls += 1
        self.message = {"_id": ObjectId(), **document}
        return Mock(inserted_id=self.message["_id"])

    def update_one(self, query, update):
        self.update_calls += 1
        if self.update_errors:
            error = self.update_errors.pop(0)
            raise error
        self.conversation["updated_at"] = update["$set"]["updated_at"]
        return Mock(acknowledged=True, modified_count=1)


@pytest.fixture
def message_context(monkeypatch):
    conversation_id = str(ObjectId())
    user_id = str(ObjectId())
    conversation = {
        "_id": ObjectId(conversation_id),
        "participants": [ObjectId(user_id)],
        "updated_at": datetime(2025, 1, 1, tzinfo=timezone.utc),
    }
    conversations = FakeCollection(conversation=conversation, message=None)
    messages = FakeCollection(conversation=conversation, message=None)
    monkeypatch.setattr(
        "app.services.message_service.db.get_db",
        lambda: {"conversations": conversations, "messages": messages},
    )
    return conversation_id, user_id, conversation, conversations, messages


def test_successful_message_creation_updates_conversation_activity(message_context):
    conversation_id, user_id, conversation, conversations, messages = message_context
    before = conversation["updated_at"]

    result = MessageService.send_message(conversation_id, user_id, "Hello")

    assert result["content"] == "Hello"
    assert conversation["updated_at"] > before
    assert conversations.update_calls == 1
    assert messages.insert_calls == 1


def test_activity_update_succeeds_normally(message_context):
    conversation_id, user_id, conversation, conversations, _ = message_context
    expected_time = datetime.now(timezone.utc)

    result = MessageService.send_message(conversation_id, user_id, "Activity")

    assert result["conversation_id"] == conversation_id
    assert conversation["updated_at"] >= expected_time
    assert conversations.update_calls == 1


def test_transient_activity_failure_is_retried_and_eventually_succeeds(message_context):
    conversation_id, user_id, conversation, conversations, messages = message_context
    conversations.update_errors = [PyMongoError("temporary failure"), PyMongoError("temporary failure")]

    result = MessageService.send_message(conversation_id, user_id, "Retry me")

    assert result["content"] == "Retry me"
    assert conversations.update_calls == 3
    assert messages.insert_calls == 1
    assert conversation["updated_at"] != datetime(2025, 1, 1, tzinfo=timezone.utc)


def test_repeated_activity_failure_stops_after_bounded_retry_count(message_context, caplog):
    conversation_id, user_id, _, conversations, messages = message_context
    conversations.update_errors = [PyMongoError("persistent failure") for _ in range(5)]

    with caplog.at_level(logging.ERROR):
        result = MessageService.send_message(conversation_id, user_id, "Do not expose this")

    assert result["content"] == "Do not expose this"
    assert conversations.update_calls == MessageService.ACTIVITY_UPDATE_ATTEMPTS
    assert messages.insert_calls == 1
    assert "Unable to update conversation activity" in caplog.text


def test_failed_activity_update_does_not_duplicate_message_insertion(message_context):
    conversation_id, user_id, _, conversations, messages = message_context
    conversations.update_errors = [PyMongoError("persistent failure") for _ in range(3)]

    MessageService.send_message(conversation_id, user_id, "One message")

    assert messages.insert_calls == 1
    assert conversations.update_calls == MessageService.ACTIVITY_UPDATE_ATTEMPTS


def test_failed_activity_update_does_not_delete_persisted_message(message_context):
    conversation_id, user_id, _, conversations, messages = message_context
    conversations.update_errors = [PyMongoError("persistent failure") for _ in range(3)]

    result = MessageService.send_message(conversation_id, user_id, "Persisted safely")

    assert messages.message is not None
    assert messages.message["content"] == "Persisted safely"
    assert result["id"] == str(messages.message["_id"])


def test_activity_failure_log_excludes_message_content(message_context, caplog):
    conversation_id, user_id, _, conversations, _ = message_context
    message_content = "private message content"
    conversations.update_errors = [PyMongoError("database update details") for _ in range(3)]

    with caplog.at_level(logging.ERROR):
        MessageService.send_message(conversation_id, user_id, message_content)

    assert conversation_id in caplog.text
    assert message_content not in caplog.text
    assert "database update details" in caplog.text


def test_message_response_shape_remains_unchanged(message_context):
    conversation_id, user_id, _, _, _ = message_context

    result = MessageService.send_message(conversation_id, user_id, "Shape")

    assert set(result) == {"id", "conversation_id", "sender_id", "content", "created_at"}
    assert result["conversation_id"] == conversation_id
    assert result["sender_id"] == user_id
