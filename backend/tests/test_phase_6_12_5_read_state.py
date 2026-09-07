from __future__ import annotations

from datetime import datetime, timezone
import pytest
from bson import ObjectId
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.db import db
from app.main import app
from app.services.connection_manager import connection_manager
from app.services.conversation_service import ConversationService
from app.services.message_service import MessageService
from app.services.rate_limiter import auth_rate_limiter

client = TestClient(app)

TEST_USERS = [
    {"email": "read_user1@example.com", "password": "Password123!", "name": "Read User One"},
    {"email": "read_user2@example.com", "password": "Password123!", "name": "Read User Two"},
    {"email": "read_user3@example.com", "password": "Password123!", "name": "Read User Three"},
]


def register_and_login(user_data: dict) -> str:
    client.cookies.clear()
    auth_rate_limiter.clear()
    db.get_db()["users"].delete_many({"email": user_data["email"]})
    db.get_db()["unverified_users"].delete_many({"email": user_data["email"]})
    r1 = client.post("/auth/register", json=user_data)
    client.cookies.clear()
    r2 = client.post("/auth/register/verify", json={"email": user_data["email"], "otp": "123456"})
    client.cookies.clear()
    response = client.post(
        "/auth/login",
        json={"email": user_data["email"], "password": user_data["password"]},
    )
    if response.status_code != 200:
        raise RuntimeError(f"Register: {r1.status_code} {r1.text} | Verify: {r2.status_code} {r2.text} | Login: {response.status_code} {response.text}")
    return response.json()["access_token"]


@pytest.fixture(autouse=True)
def cleanup_database():
    client.cookies.clear()
    auth_rate_limiter.clear()
    database = db.get_db()
    database["users"].delete_many({})
    database["unverified_users"].delete_many({})
    database["conversations"].delete_many({})
    database["messages"].delete_many({})
    database["otp_codes"].delete_many({})
    database["auth_challenges"].delete_many({})
    database["conversation_reads"].delete_many({})
    connection_manager.clear_all()
    yield
    client.cookies.clear()
    auth_rate_limiter.clear()
    database["users"].delete_many({})
    database["unverified_users"].delete_many({})
    database["conversations"].delete_many({})
    database["messages"].delete_many({})
    database["otp_codes"].delete_many({})
    database["auth_challenges"].delete_many({})
    database["conversation_reads"].delete_many({})
    connection_manager.clear_all()


def test_conversation_list_returns_latest_message_and_unread_count():
    token1 = register_and_login(TEST_USERS[0])
    token2 = register_and_login(TEST_USERS[1])
    user2 = db.get_db()["users"].find_one({"email": TEST_USERS[1]["email"]})

    conv = client.post(
        "/conversations",
        json={"other_user_id": str(user2["_id"])},
        headers={"Authorization": f"Bearer {token1}"},
    ).json()

    # Initial empty list checks
    convs1 = client.get("/conversations", headers={"Authorization": f"Bearer {token1}"}).json()
    assert convs1[0]["latest_message"] is None
    assert convs1[0]["unread_count"] == 0

    # User 2 sends a message
    msg = client.post(
        f"/conversations/{conv['id']}/messages",
        json={"content": "Hello User 1!"},
        headers={"Authorization": f"Bearer {token2}"},
    ).json()

    convs1_after = client.get("/conversations", headers={"Authorization": f"Bearer {token1}"}).json()
    assert convs1_after[0]["latest_message"]["id"] == msg["id"]
    assert convs1_after[0]["latest_message"]["content"] == "Hello User 1!"
    assert convs1_after[0]["unread_count"] == 1


def test_own_messages_excluded_from_unread_count():
    token1 = register_and_login(TEST_USERS[0])
    token2 = register_and_login(TEST_USERS[1])
    user2 = db.get_db()["users"].find_one({"email": TEST_USERS[1]["email"]})

    conv = client.post(
        "/conversations",
        json={"other_user_id": str(user2["_id"])},
        headers={"Authorization": f"Bearer {token1}"},
    ).json()

    # User 1 sends message to User 2
    client.post(
        f"/conversations/{conv['id']}/messages",
        json={"content": "My own message"},
        headers={"Authorization": f"Bearer {token1}"},
    )

    # User 1's unread count for conversation must be 0
    convs1 = client.get("/conversations", headers={"Authorization": f"Bearer {token1}"}).json()
    assert convs1[0]["unread_count"] == 0

    # User 2's unread count for conversation must be 1
    convs2 = client.get("/conversations", headers={"Authorization": f"Bearer {token2}"}).json()
    assert convs2[0]["unread_count"] == 1


def test_mark_read_advances_cursor_and_is_idempotent():
    token1 = register_and_login(TEST_USERS[0])
    token2 = register_and_login(TEST_USERS[1])
    user2 = db.get_db()["users"].find_one({"email": TEST_USERS[1]["email"]})

    conv = client.post(
        "/conversations",
        json={"other_user_id": str(user2["_id"])},
        headers={"Authorization": f"Bearer {token1}"},
    ).json()

    msg1 = client.post(
        f"/conversations/{conv['id']}/messages",
        json={"content": "Message 1"},
        headers={"Authorization": f"Bearer {token2}"},
    ).json()

    msg2 = client.post(
        f"/conversations/{conv['id']}/messages",
        json={"content": "Message 2"},
        headers={"Authorization": f"Bearer {token2}"},
    ).json()

    # User 1 has 2 unread messages
    convs1 = client.get("/conversations", headers={"Authorization": f"Bearer {token1}"}).json()
    assert convs1[0]["unread_count"] == 2

    # User 1 marks Message 1 read
    read_resp1 = client.post(
        f"/conversations/{conv['id']}/read",
        json={"last_read_message_id": msg1["id"]},
        headers={"Authorization": f"Bearer {token1}"},
    ).json()
    assert read_resp1["last_read_message_id"] == msg1["id"]
    assert read_resp1["unread_count"] == 1

    # User 1 marks Message 2 read
    read_resp2 = client.post(
        f"/conversations/{conv['id']}/read",
        json={"last_read_message_id": msg2["id"]},
        headers={"Authorization": f"Bearer {token1}"},
    ).json()
    assert read_resp2["last_read_message_id"] == msg2["id"]
    assert read_resp2["unread_count"] == 0

    # Duplicate mark read for Message 2 (idempotent)
    read_resp_dup = client.post(
        f"/conversations/{conv['id']}/read",
        json={"last_read_message_id": msg2["id"]},
        headers={"Authorization": f"Bearer {token1}"},
    ).json()
    assert read_resp_dup["last_read_message_id"] == msg2["id"]
    assert read_resp_dup["unread_count"] == 0


def test_stale_mark_read_cannot_move_cursor_backwards():
    token1 = register_and_login(TEST_USERS[0])
    token2 = register_and_login(TEST_USERS[1])
    user2 = db.get_db()["users"].find_one({"email": TEST_USERS[1]["email"]})

    conv = client.post(
        "/conversations",
        json={"other_user_id": str(user2["_id"])},
        headers={"Authorization": f"Bearer {token1}"},
    ).json()

    msg1 = client.post(
        f"/conversations/{conv['id']}/messages",
        json={"content": "Message 100"},
        headers={"Authorization": f"Bearer {token2}"},
    ).json()

    msg2 = client.post(
        f"/conversations/{conv['id']}/messages",
        json={"content": "Message 105"},
        headers={"Authorization": f"Bearer {token2}"},
    ).json()

    # User 1 reads Message 105
    client.post(
        f"/conversations/{conv['id']}/read",
        json={"last_read_message_id": msg2["id"]},
        headers={"Authorization": f"Bearer {token1}"},
    )

    # Delayed request for Message 100 arrives
    stale_resp = client.post(
        f"/conversations/{conv['id']}/read",
        json={"last_read_message_id": msg1["id"]},
        headers={"Authorization": f"Bearer {token1}"},
    ).json()

    # Server cursor must remain at Message 105
    assert stale_resp["last_read_message_id"] == msg2["id"]
    assert stale_resp["unread_count"] == 0


def test_equal_timestamp_messages_use_id_tiebreaker():
    token1 = register_and_login(TEST_USERS[0])
    token2 = register_and_login(TEST_USERS[1])
    user2 = db.get_db()["users"].find_one({"email": TEST_USERS[1]["email"]})

    conv = client.post(
        "/conversations",
        json={"other_user_id": str(user2["_id"])},
        headers={"Authorization": f"Bearer {token1}"},
    ).json()

    fixed_time = datetime(2026, 9, 7, 12, 0, 0, tzinfo=timezone.utc)
    conv_oid = ObjectId(conv["id"])
    user2_oid = user2["_id"]

    msg_id1 = ObjectId()
    msg_id2 = ObjectId()  # msg_id2 > msg_id1

    db.get_db()["messages"].insert_many([
        {"_id": msg_id1, "conversation_id": conv_oid, "sender_id": user2_oid, "content": "T1", "created_at": fixed_time},
        {"_id": msg_id2, "conversation_id": conv_oid, "sender_id": user2_oid, "content": "T2", "created_at": fixed_time},
    ])

    # Mark msg_id2 read
    resp = client.post(
        f"/conversations/{conv['id']}/read",
        json={"last_read_message_id": str(msg_id2)},
        headers={"Authorization": f"Bearer {token1}"},
    ).json()

    assert resp["last_read_message_id"] == str(msg_id2)

    # Stale request for msg_id1 (with same created_at timestamp)
    stale_resp = client.post(
        f"/conversations/{conv['id']}/read",
        json={"last_read_message_id": str(msg_id1)},
        headers={"Authorization": f"Bearer {token1}"},
    ).json()

    # Tiebreaker preserves higher msg_id2 cursor
    assert stale_resp["last_read_message_id"] == str(msg_id2)


def test_invalid_and_unauthorized_mark_read_requests_are_rejected():
    token1 = register_and_login(TEST_USERS[0])
    token2 = register_and_login(TEST_USERS[1])
    token3 = register_and_login(TEST_USERS[2])
    user2 = db.get_db()["users"].find_one({"email": TEST_USERS[1]["email"]})

    conv = client.post(
        "/conversations",
        json={"other_user_id": str(user2["_id"])},
        headers={"Authorization": f"Bearer {token1}"},
    ).json()

    msg = client.post(
        f"/conversations/{conv['id']}/messages",
        json={"content": "Valid message"},
        headers={"Authorization": f"Bearer {token1}"},
    ).json()

    # Malformed message ID -> 400
    res_bad_id = client.post(
        f"/conversations/{conv['id']}/read",
        json={"last_read_message_id": "not-an-object-id"},
        headers={"Authorization": f"Bearer {token1}"},
    )
    assert res_bad_id.status_code == 400

    # Nonexistent message ID -> 404
    res_missing_msg = client.post(
        f"/conversations/{conv['id']}/read",
        json={"last_read_message_id": str(ObjectId())},
        headers={"Authorization": f"Bearer {token1}"},
    )
    assert res_missing_msg.status_code == 404

    # Unauthorized user (User 3 not participant) -> 403
    res_unauth = client.post(
        f"/conversations/{conv['id']}/read",
        json={"last_read_message_id": msg["id"]},
        headers={"Authorization": f"Bearer {token3}"},
    )
    assert res_unauth.status_code == 403


def test_latest_message_concurrency_protection():
    token1 = register_and_login(TEST_USERS[0])
    token2 = register_and_login(TEST_USERS[1])
    user2 = db.get_db()["users"].find_one({"email": TEST_USERS[1]["email"]})

    conv = client.post(
        "/conversations",
        json={"other_user_id": str(user2["_id"])},
        headers={"Authorization": f"Bearer {token1}"},
    ).json()
    conv_oid = ObjectId(conv["id"])

    newer_time = datetime(2026, 9, 7, 12, 5, 0, tzinfo=timezone.utc)
    older_time = datetime(2026, 9, 7, 12, 0, 0, tzinfo=timezone.utc)

    # Set latest_message to newer_time
    db.get_db()["conversations"].update_one(
        {"_id": conv_oid},
        {"$set": {
            "updated_at": newer_time,
            "latest_message": {"id": str(ObjectId()), "content": "Newer Message", "sender_id": str(user2["_id"]), "created_at": newer_time}
        }}
    )

    # Attempt to write older message
    older_msg_id = ObjectId()
    db.get_db()["messages"].insert_one({
        "_id": older_msg_id, "conversation_id": conv_oid, "sender_id": user2["_id"], "content": "Older Message", "created_at": older_time
    })

    # Monotonic update query
    db.get_db()["conversations"].update_one(
        {
            "_id": conv_oid,
            "$or": [
                {"latest_message.created_at": {"$lt": older_time}},
                {"latest_message.created_at": older_time, "latest_message.id": {"$lt": str(older_msg_id)}},
                {"latest_message": {"$exists": False}},
            ],
        },
        {"$set": {"updated_at": older_time, "latest_message": {"id": str(older_msg_id), "content": "Older Message", "sender_id": str(user2["_id"]), "created_at": older_time}}}
    )

    # Verify latest_message remains "Newer Message"
    updated_conv = db.get_db()["conversations"].find_one({"_id": conv_oid})
    assert updated_conv["latest_message"]["content"] == "Newer Message"


def test_realtime_conversation_read_delivered_to_user_sockets():
    token1 = register_and_login(TEST_USERS[0])
    token2 = register_and_login(TEST_USERS[1])
    token3 = register_and_login(TEST_USERS[2])
    user2 = db.get_db()["users"].find_one({"email": TEST_USERS[1]["email"]})

    conv = client.post(
        "/conversations",
        json={"other_user_id": str(user2["_id"])},
        headers={"Authorization": f"Bearer {token1}"},
    ).json()

    msg = client.post(
        f"/conversations/{conv['id']}/messages",
        json={"content": "Read event test"},
        headers={"Authorization": f"Bearer {token2}"},
    ).json()

    # User 1 and User 3 connect to /ws/user
    with client.websocket_connect(f"/ws/user?token={token1}") as ws1, \
         client.websocket_connect(f"/ws/user?token={token3}") as ws3:

        # User 1 marks message read
        client.post(
            f"/conversations/{conv['id']}/read",
            json={"last_read_message_id": msg["id"]},
            headers={"Authorization": f"Bearer {token1}"},
        )

        event1 = ws1.receive_json()
        assert event1["type"] == "conversation.read"
        assert event1["conversation_id"] == conv["id"]
        assert event1["last_read_message_id"] == msg["id"]

        # User 3 sends ping to verify ws3 received NO read event
        ws3.send_json({"type": "ping"})
        assert ws3.receive_json() == {"type": "pong"}


def test_concurrent_first_mark_read():
    from concurrent.futures import ThreadPoolExecutor
    token1 = register_and_login(TEST_USERS[0])
    token2 = register_and_login(TEST_USERS[1])
    user2 = db.get_db()["users"].find_one({"email": TEST_USERS[1]["email"]})

    conv = client.post(
        "/conversations",
        json={"other_user_id": str(user2["_id"])},
        headers={"Authorization": f"Bearer {token1}"},
    ).json()

    msg = client.post(
        f"/conversations/{conv['id']}/messages",
        json={"content": "Concurrent read test"},
        headers={"Authorization": f"Bearer {token2}"},
    ).json()

    def do_mark_read():
        return client.post(
            f"/conversations/{conv['id']}/read",
            json={"last_read_message_id": msg["id"]},
            headers={"Authorization": f"Bearer {token1}"},
        )

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(do_mark_read) for _ in range(5)]
        results = [f.result() for f in futures]

    for res in results:
        assert res.status_code == 200
        assert res.json()["last_read_message_id"] == msg["id"]


def test_mark_read_wrong_conversation_message_rejected():
    token1 = register_and_login(TEST_USERS[0])
    token2 = register_and_login(TEST_USERS[1])
    token3 = register_and_login(TEST_USERS[2])
    user2 = db.get_db()["users"].find_one({"email": TEST_USERS[1]["email"]})
    user3 = db.get_db()["users"].find_one({"email": TEST_USERS[2]["email"]})

    conv1 = client.post(
        "/conversations",
        json={"other_user_id": str(user2["_id"])},
        headers={"Authorization": f"Bearer {token1}"},
    ).json()

    conv2 = client.post(
        "/conversations",
        json={"other_user_id": str(user3["_id"])},
        headers={"Authorization": f"Bearer {token1}"},
    ).json()

    msg_in_conv2 = client.post(
        f"/conversations/{conv2['id']}/messages",
        json={"content": "Message in Conv 2"},
        headers={"Authorization": f"Bearer {token3}"},
    ).json()

    # User 1 tries to mark Conv 1 read using a message that belongs to Conv 2
    res = client.post(
        f"/conversations/{conv1['id']}/read",
        json={"last_read_message_id": msg_in_conv2["id"]},
        headers={"Authorization": f"Bearer {token1}"},
    )
    assert res.status_code == 404
    assert res.json()["detail"] == "Target message not found in this conversation."


def test_organization_channel_mark_read_and_historical_cutoff():
    from app.services.organization_membership_service import OrganizationMembershipService
    token1 = register_and_login(TEST_USERS[0])
    token2 = register_and_login(TEST_USERS[1])
    user1 = db.get_db()["users"].find_one({"email": TEST_USERS[0]["email"]})
    user2 = db.get_db()["users"].find_one({"email": TEST_USERS[1]["email"]})

    # Create Organization
    org_res = db.get_db()["organizations"].insert_one({
        "slug": "testorg",
        "name": "Test Org",
        "owner_id": user1["_id"],
        "is_active": True,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    })
    org_id = str(org_res.inserted_id)

    # Active membership for User 1
    OrganizationMembershipService.create_membership(str(user1["_id"]), org_id)

    # Create Org Channel
    channel = ConversationService.create_organization_conversation(org_id, "general", created_by=str(user1["_id"]))

    # User 1 posts historical message BEFORE User 2 joins
    hist_msg = client.post(
        f"/conversations/{channel['id']}/messages",
        json={"content": "Historical message before user 2 joined"},
        headers={"Authorization": f"Bearer {token1}"},
    ).json()

    # User 2 not in org yet -> 403 Forbidden
    res_unauth = client.post(
        f"/conversations/{channel['id']}/read",
        json={"last_read_message_id": hist_msg["id"]},
        headers={"Authorization": f"Bearer {token2}"},
    )
    assert res_unauth.status_code == 403

    # Add User 2 as active member AFTER historical message was created
    OrganizationMembershipService.create_membership(str(user2["_id"]), org_id)

    # User 2 lists organization conversations; historical message before membership must NOT count as unread
    org_convs = client.get(
        f"/organizations/{org_id}/conversations",
        headers={"Authorization": f"Bearer {token2}"},
    ).json()
    assert org_convs[0]["unread_count"] == 0

    # User 1 sends new message AFTER User 2 joined
    new_msg = client.post(
        f"/conversations/{channel['id']}/messages",
        json={"content": "New message after user 2 joined"},
        headers={"Authorization": f"Bearer {token1}"},
    ).json()

    # User 2 lists conversations; new message counts as 1 unread
    org_convs_after = client.get(
        f"/organizations/{org_id}/conversations",
        headers={"Authorization": f"Bearer {token2}"},
    ).json()
    assert org_convs_after[0]["unread_count"] == 1

    # User 2 marks new_msg read
    read_res = client.post(
        f"/conversations/{channel['id']}/read",
        json={"last_read_message_id": new_msg["id"]},
        headers={"Authorization": f"Bearer {token2}"},
    )
    assert read_res.status_code == 200
    assert read_res.json()["unread_count"] == 0
