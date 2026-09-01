from unittest.mock import Mock

from pymongo.errors import PyMongoError

from app.db import Database, db


class FakeCollection:
    def __init__(self, indexes=None, failing=False, failing_names=None):
        self.indexes = list(indexes or [])
        self.failing = failing
        self.failing_names = set(failing_names or [])
        self.create_calls = []

    def create_index(self, keys, *, name, **options):
        self.create_calls.append((keys, name, options))
        if self.failing or name in self.failing_names:
            raise PyMongoError("index creation failed")
        if not any(index["name"] == name for index in self.indexes):
            self.indexes.append({"name": name, "key": dict(keys), **options})
        return name

    def list_indexes(self):
        return list(self.indexes)


def make_fake_database(failing_collection=None, failing_index=None):
    collections = {}
    for specification in Database.EXPECTED_INDEXES:
        collection_name = specification["collection"]
        if collection_name not in collections:
            collections[collection_name] = FakeCollection(
                failing=collection_name == failing_collection,
                failing_names={failing_index} if failing_index else None,
            )
    return collections


def test_expected_index_specifications_are_centralized():
    names = {specification["name"] for specification in Database.EXPECTED_INDEXES}

    assert names == {
        "unique_email_idx",
        "conversations_participants_idx",
        "unique_conversation_participant_key_idx",
        "messages_conversation_id_idx",
        "messages_conversation_created_idx",
        "messages_conversation_created_id_idx",
        "otp_codes_identifier_purpose_created_idx",
        "otp_codes_expires_ttl_idx",
        "auth_challenges_jti_unique_idx",
        "auth_challenges_expires_ttl_idx",
        "auth_sessions_user_id_idx",
        "auth_sessions_token_hash_unique_idx",
        "auth_sessions_expires_ttl_idx",
        "organizations_org_id_unique_idx",
        "memberships_user_org_unique_idx",
        "memberships_org_id_idx",
        "requests_user_org_unique_idx",
        "requests_org_status_idx",
        "admin_users_email_unique_idx",
        "admin_sessions_token_hash_unique_idx",
        "admin_sessions_expires_ttl_idx",
        "conversations_org_updated_idx",
        "conversations_org_name_unique_idx",
        "audit_logs_created_at_idx",
        "audit_logs_org_created_at_idx",
        "audit_logs_actor_created_at_idx",
        "audit_logs_event_type_created_at_idx",
    }


def test_unique_email_index_has_expected_properties():
    index = next(item for item in db.get_db()["users"].list_indexes() if item["name"] == "unique_email_idx")

    assert index["key"] == {"email": 1}
    assert index["unique"] is True


def test_participant_key_index_is_sparse_and_unique():
    index = next(
        item
        for item in db.get_db()["conversations"].list_indexes()
        if item["name"] == "unique_conversation_participant_key_idx"
    )

    assert index["key"] == {"participant_key": 1}
    assert index["unique"] is True
    assert index["sparse"] is True


def test_conversation_participant_index_has_expected_key():
    index = next(
        item
        for item in db.get_db()["conversations"].list_indexes()
        if item["name"] == "conversations_participants_idx"
    )

    assert index["key"] == {"participants": 1}


def test_message_indexes_have_expected_keys():
    indexes = {
        item["name"]: item
        for item in db.get_db()["messages"].list_indexes()
    }

    assert indexes["messages_conversation_id_idx"]["key"] == {"conversation_id": 1}
    assert indexes["messages_conversation_created_idx"]["key"] == {
        "conversation_id": 1,
        "created_at": 1,
    }
    assert indexes["messages_conversation_created_id_idx"]["key"] == {
        "conversation_id": 1,
        "created_at": 1,
        "_id": 1,
    }


def test_pagination_index_is_centralized_with_exact_key_order():
    index = next(
        specification
        for specification in Database.EXPECTED_INDEXES
        if specification["name"] == "messages_conversation_created_id_idx"
    )

    assert index["collection"] == "messages"
    assert index["keys"] == [
        ("conversation_id", 1),
        ("created_at", 1),
        ("_id", 1),
    ]
    assert index["options"] == {}


def test_pagination_index_exists_in_configured_database():
    index = next(
        item
        for item in db.get_db()["messages"].list_indexes()
        if item["name"] == "messages_conversation_created_id_idx"
    )

    assert index["key"] == {
        "conversation_id": 1,
        "created_at": 1,
        "_id": 1,
    }


def test_ensure_indexes_is_idempotent(monkeypatch):
    fake_database = make_fake_database()
    monkeypatch.setattr(Database, "get_db", classmethod(lambda cls: fake_database))

    first = Database.ensure_indexes()
    second = Database.ensure_indexes()

    assert first == second
    expected_calls = {
        collection_name: sum(
            specification["collection"] == collection_name
            for specification in Database.EXPECTED_INDEXES
        ) * 2
        for collection_name in fake_database
    }
    assert all(
        len(fake_database[collection_name].create_calls) == call_count
        for collection_name, call_count in expected_calls.items()
    )
    assert all(
        len([index for index in collection.indexes if index["name"] == name]) == 1
        for collection_name, collection in fake_database.items()
        for name in {
            specification["name"]
            for specification in Database.EXPECTED_INDEXES
            if specification["collection"] == collection_name
        }
    )


def test_index_creation_failure_is_logged(monkeypatch, caplog):
    fake_database = make_fake_database(failing_collection="messages")
    monkeypatch.setattr(Database, "get_db", classmethod(lambda cls: fake_database))

    with caplog.at_level("ERROR"):
        result = Database.ensure_indexes()

    assert "collection=messages" in caplog.text
    assert "index=messages_conversation_id_idx" in caplog.text
    assert result["messages"]["missing"]


def test_pagination_index_creation_failure_is_logged_safely(monkeypatch, caplog):
    index_name = "messages_conversation_created_id_idx"
    fake_database = make_fake_database(failing_index=index_name)
    monkeypatch.setattr(Database, "get_db", classmethod(lambda cls: fake_database))

    with caplog.at_level("ERROR"):
        result = Database.ensure_indexes()

    assert f"collection=messages index={index_name}" in caplog.text
    assert index_name in result["messages"]["missing"]
    assert len(fake_database["messages"].create_calls) == 3


def test_one_failed_index_does_not_stop_other_index_attempts(monkeypatch):
    fake_database = make_fake_database(failing_collection="conversations")
    monkeypatch.setattr(Database, "get_db", classmethod(lambda cls: fake_database))

    Database.ensure_indexes()

    assert len(fake_database["users"].create_calls) == 1
    assert len(fake_database["messages"].create_calls) == 3
    assert len(fake_database["conversations"].create_calls) == 4


def test_verify_indexes_reports_missing_expected_indexes():
    fake_database = {
        "users": FakeCollection([{"name": "unique_email_idx", "key": {"email": 1}, "unique": True}]),
        "conversations": FakeCollection([]),
        "messages": FakeCollection([{"name": "messages_conversation_id_idx", "key": {"conversation_id": 1}}]),
    }

    result = Database.verify_indexes(fake_database)

    assert result["users"] == {
        "present": ["unique_email_idx"],
        "missing": [],
        "misconfigured": [],
    }
    assert result["conversations"]["present"] == []
    assert set(result["conversations"]["missing"]) == {
        "conversations_participants_idx",
        "unique_conversation_participant_key_idx",
        "conversations_org_updated_idx",
        "conversations_org_name_unique_idx",
    }
    assert result["conversations"]["misconfigured"] == []
    assert result["messages"] == {
        "present": ["messages_conversation_id_idx"],
        "missing": [
            "messages_conversation_created_idx",
            "messages_conversation_created_id_idx",
        ],
        "misconfigured": [],
    }


def test_index_verification_failure_is_logged(caplog):
    failing_collection = Mock()
    failing_collection.list_indexes.side_effect = PyMongoError("verification failed")
    fake_database = {
        "users": failing_collection,
        "conversations": FakeCollection(),
        "messages": FakeCollection(),
    }

    with caplog.at_level("ERROR"):
        result = Database.verify_indexes(fake_database)

    assert "Failed to verify MongoDB indexes collection=users" in caplog.text
    assert result["users"]["present"] == []
    assert result["users"]["missing"] == ["unique_email_idx"]
    assert result["users"]["misconfigured"] == []


def test_verify_indexes_reports_correctly_configured_indexes_as_present():
    fake_database = make_fake_database()

    for specification in Database.EXPECTED_INDEXES:
        fake_database[specification["collection"]].indexes.append(
            {
                "name": specification["name"],
                "key": dict(specification["keys"]),
                **specification["options"],
            }
        )
    result = Database.verify_indexes(fake_database)

    assert all(not values["missing"] and not values["misconfigured"] for values in result.values())


def test_verify_indexes_reports_wrong_key_order_as_misconfigured():
    fake_database = {
        "users": FakeCollection(),
        "conversations": FakeCollection(),
        "messages": FakeCollection([
            {
                "name": "messages_conversation_created_id_idx",
                "key": {"conversation_id": 1, "_id": 1, "created_at": 1},
            }
        ]),
    }

    result = Database.verify_indexes(fake_database)

    assert "messages_conversation_created_id_idx" in result["messages"]["misconfigured"]
    assert "messages_conversation_created_id_idx" not in result["messages"]["present"]


def test_verify_indexes_reports_wrong_key_field_as_misconfigured():
    fake_database = {
        "users": FakeCollection([{"name": "unique_email_idx", "key": {"name": 1}}]),
        "conversations": FakeCollection(),
        "messages": FakeCollection(),
    }

    result = Database.verify_indexes(fake_database)

    assert result["users"]["misconfigured"] == ["unique_email_idx"]
    assert result["users"]["present"] == []


def test_verify_indexes_reports_missing_unique_option_as_misconfigured():
    fake_database = {
        "users": FakeCollection([{"name": "unique_email_idx", "key": {"email": 1}}]),
        "conversations": FakeCollection(),
        "messages": FakeCollection(),
    }

    result = Database.verify_indexes(fake_database)

    assert result["users"]["misconfigured"] == ["unique_email_idx"]


def test_verify_indexes_reports_missing_sparse_option_as_misconfigured():
    fake_database = {
        "users": FakeCollection(),
        "conversations": FakeCollection([
            {"name": "unique_conversation_participant_key_idx", "key": {"participant_key": 1}, "unique": True}
        ]),
        "messages": FakeCollection(),
    }

    result = Database.verify_indexes(fake_database)

    assert result["conversations"]["misconfigured"] == [
        "unique_conversation_participant_key_idx"
    ]


def test_verify_indexes_reports_wrong_unique_and_sparse_values_as_misconfigured():
    fake_database = {
        "users": FakeCollection(),
        "conversations": FakeCollection([
            {
                "name": "unique_conversation_participant_key_idx",
                "key": {"participant_key": 1},
                "unique": False,
                "sparse": False,
            }
        ]),
        "messages": FakeCollection(),
    }

    result = Database.verify_indexes(fake_database)

    assert result["conversations"]["misconfigured"] == [
        "unique_conversation_participant_key_idx"
    ]


def test_verify_indexes_reports_misconfiguration_without_blocking_other_collections():
    fake_database = {
        "users": FakeCollection([{"name": "unique_email_idx", "key": {"name": 1}}]),
        "conversations": FakeCollection([
            {"name": "conversations_participants_idx", "key": {"participants": 1}}
        ]),
        "messages": FakeCollection([
            {"name": "messages_conversation_id_idx", "key": {"conversation_id": 1}}
        ]),
    }

    result = Database.verify_indexes(fake_database)

    assert result["users"]["misconfigured"] == ["unique_email_idx"]
    assert result["conversations"]["present"] == ["conversations_participants_idx"]
    assert result["messages"]["present"] == ["messages_conversation_id_idx"]


def test_misconfiguration_logging_contains_only_safe_identifiers(caplog):
    fake_database = {
        "users": FakeCollection(),
        "conversations": FakeCollection(),
        "messages": FakeCollection([
            {
                "name": "messages_conversation_created_id_idx",
                "key": {"wrong_field": 1},
                "content": "must not be logged",
            }
        ]),
    }

    with caplog.at_level("ERROR"):
        Database.verify_indexes(fake_database)

    assert "collection=messages" in caplog.text
    assert "index=messages_conversation_created_id_idx" in caplog.text
    assert "must not be logged" not in caplog.text


def test_audit_logs_indexes_have_expected_keys_and_properties():
    Database.ensure_indexes()
    indexes = {item["name"]: item for item in db.get_db()["audit_logs"].list_indexes()}

    assert indexes["audit_logs_created_at_idx"]["key"] == {"created_at": -1}
    assert indexes["audit_logs_org_created_at_idx"]["key"] == {"organization_id": 1, "created_at": -1}
    assert indexes["audit_logs_actor_created_at_idx"]["key"] == {"actor_id": 1, "created_at": -1}
    assert indexes["audit_logs_event_type_created_at_idx"]["key"] == {"event_type": 1, "created_at": -1}


def test_audit_indexes_are_centralized_with_exact_key_order():
    specs = {spec["name"]: spec for spec in Database.EXPECTED_INDEXES if spec["collection"] == "audit_logs"}

    assert specs["audit_logs_created_at_idx"]["keys"] == [("created_at", -1)]
    assert specs["audit_logs_org_created_at_idx"]["keys"] == [("organization_id", 1), ("created_at", -1)]
    assert specs["audit_logs_actor_created_at_idx"]["keys"] == [("actor_id", 1), ("created_at", -1)]
    assert specs["audit_logs_event_type_created_at_idx"]["keys"] == [("event_type", 1), ("created_at", -1)]


def test_organization_conversation_indexes_have_expected_keys_and_properties():
    Database.ensure_indexes()
    indexes = {item["name"]: item for item in db.get_db()["conversations"].list_indexes()}

    assert indexes["conversations_org_updated_idx"]["key"] == {"organization_id": 1, "updated_at": -1}
    assert indexes["conversations_org_updated_idx"]["sparse"] is True

    assert indexes["conversations_org_name_unique_idx"]["key"] == {"organization_id": 1, "name": 1}
    assert indexes["conversations_org_name_unique_idx"]["unique"] is True
    assert indexes["conversations_org_name_unique_idx"]["sparse"] is True


def test_organization_conversation_indexes_are_centralized_with_exact_key_order():
    specs = {spec["name"]: spec for spec in Database.EXPECTED_INDEXES if spec["collection"] == "conversations"}

    assert specs["conversations_org_updated_idx"]["keys"] == [("organization_id", 1), ("updated_at", -1)]
    assert specs["conversations_org_updated_idx"]["options"] == {"sparse": True}

    assert specs["conversations_org_name_unique_idx"]["keys"] == [("organization_id", 1), ("name", 1)]
    assert specs["conversations_org_name_unique_idx"]["options"] == {"unique": True, "sparse": True}
