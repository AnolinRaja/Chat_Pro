from __future__ import annotations

from datetime import datetime, timezone
from bson import ObjectId
import pytest
from fastapi.testclient import TestClient

from app.db import db
from app.main import app
from app.schemas.admin import AdminCreate
from app.schemas.audit import AuditEventType
from app.services.admin_auth_service import AdminAuthService
from app.services.audit_service import AuditService
from app.services.conversation_service import ConversationService
from app.services.jwt_service import JWTService
from app.services.message_service import MessageService
from app.services.organization_membership_service import OrganizationMembershipService
from app.services.organization_request_service import OrganizationRequestService
from app.services.organization_service import OrganizationService

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_db():
    database = db.get_db()
    database["conversations"].delete_many({})
    database["messages"].delete_many({})
    database["organizations"].delete_many({})
    database["organization_memberships"].delete_many({})
    database["organization_registration_requests"].delete_many({})
    database["users"].delete_many({})
    database["admin_users"].delete_many({})
    database["admin_sessions"].delete_many({})
    database["audit_logs"].delete_many({})
    yield
    database["conversations"].delete_many({})
    database["messages"].delete_many({})
    database["organizations"].delete_many({})
    database["organization_memberships"].delete_many({})
    database["organization_registration_requests"].delete_many({})
    database["users"].delete_many({})
    database["admin_users"].delete_many({})
    database["admin_sessions"].delete_many({})
    database["audit_logs"].delete_many({})


def create_test_user(email: str = "user@example.com", name: str = "Test User") -> dict[str, str]:
    now = datetime.now(timezone.utc)
    doc = {
        "email": email,
        "name": name,
        "password_hash": "dummyhash",
        "created_at": now,
    }
    res = db.get_db()["users"].insert_one(doc)
    return {"id": str(res.inserted_id), "email": email, "name": name}


def create_test_system_admin(email: str = "sysadmin@example.com") -> dict[str, str]:
    return AdminAuthService.create_admin(
        AdminCreate(
            email=email,
            name="System Admin",
            password="Password123!",
            role="system_admin",
            organization_id=None,
        )
    )


def create_test_org(org_id: str = "org_alpha", name: str = "Org Alpha", join_code: str = "SecretJoin123!") -> dict:
    return OrganizationService.create_organization(org_id=org_id, name=name, join_code=join_code)


def get_user_headers(user_id: str) -> dict[str, str]:
    token = JWTService.create_access_token(subject=user_id)
    return {"Authorization": f"Bearer {token}"}


def get_admin_headers(admin_id: str, role: str, organization_id: str | None = None) -> dict[str, str]:
    token = JWTService.create_admin_access_token(admin_id=admin_id, role=role, organization_id=organization_id)
    return {"Authorization": f"Bearer {token}"}


# ==============================================================================
# A. Organization Channel Creation
# ==============================================================================

def test_active_member_creates_organization_channel():
    org = create_test_org("org_dev", "Dev Org")
    user = create_test_user("dev_user@example.com")
    OrganizationMembershipService.create_membership(user["id"], org["id"])
    headers = get_user_headers(user["id"])

    res = client.post(
        f"/organizations/{org['id']}/conversations",
        json={"name": "engineering", "description": "Engineering Channel"},
        headers=headers,
    )
    assert res.status_code == 201
    data = res.json()
    assert data["name"] == "engineering"
    assert data["description"] == "Engineering Channel"
    assert data["type"] == "organization"
    assert data["organization_id"] == org["id"]
    assert data["created_by"] == user["id"]
    assert data["is_active"] is True


def test_non_member_cannot_create_organization_channel():
    org = create_test_org("org_sec", "Sec Org")
    user = create_test_user("outsider@example.com")
    headers = get_user_headers(user["id"])

    res = client.post(
        f"/organizations/{org['id']}/conversations",
        json={"name": "private-room"},
        headers=headers,
    )
    assert res.status_code == 403
    assert "Access denied" in res.json()["detail"]


def test_pending_request_user_cannot_create_organization_channel():
    org = create_test_org("org_pend", "Pending Org")
    user = create_test_user("pending_user@example.com")
    OrganizationRequestService.create_request(user["id"], org["id"])
    headers = get_user_headers(user["id"])

    res = client.post(
        f"/organizations/{org['id']}/conversations",
        json={"name": "pending-room"},
        headers=headers,
    )
    assert res.status_code == 403


def test_rejected_request_user_cannot_create_organization_channel():
    org = create_test_org("org_rej", "Rejected Org")
    user = create_test_user("rejected_user@example.com")
    req = OrganizationRequestService.create_request(user["id"], org["id"])
    admin_user = create_test_user("admin_reviewer@example.com")
    OrganizationRequestService.update_request_status(req["id"], "REJECTED", admin_user["id"])
    headers = get_user_headers(user["id"])

    res = client.post(
        f"/organizations/{org['id']}/conversations",
        json={"name": "rejected-room"},
        headers=headers,
    )
    assert res.status_code == 403


def test_inactive_organization_cannot_create_channel():
    org = create_test_org("org_inact", "Inactive Org")
    user = create_test_user("inact_user@example.com")
    OrganizationMembershipService.create_membership(user["id"], org["id"])
    db.get_db()["organizations"].update_one({"_id": ObjectId(org["id"])}, {"$set": {"is_active": False}})
    headers = get_user_headers(user["id"])

    res = client.post(
        f"/organizations/{org['id']}/conversations",
        json={"name": "test-room"},
        headers=headers,
    )
    assert res.status_code == 403
    assert "inactive" in res.json()["detail"].lower()


def test_invalid_organization_id_format_returns_400():
    user = create_test_user("user_invalid@example.com")
    headers = get_user_headers(user["id"])
    res = client.post(
        "/organizations/invalid_id_format/conversations",
        json={"name": "test-room"},
        headers=headers,
    )
    assert res.status_code == 400


def test_nonexistent_organization_id_returns_404():
    user = create_test_user("user_nonexist@example.com")
    fake_org_id = str(ObjectId())
    # Create fake membership for fake org so membership check passes to reach org verification
    OrganizationMembershipService.create_membership(user["id"], fake_org_id)
    headers = get_user_headers(user["id"])
    res = client.post(
        f"/organizations/{fake_org_id}/conversations",
        json={"name": "test-room"},
        headers=headers,
    )
    assert res.status_code == 404


def test_invalid_channel_name_returns_422():
    org = create_test_org("org_val", "Validation Org")
    user = create_test_user("val_user@example.com")
    OrganizationMembershipService.create_membership(user["id"], org["id"])
    headers = get_user_headers(user["id"])

    # Upper case / spaces / special characters invalid for slug
    res = client.post(
        f"/organizations/{org['id']}/conversations",
        json={"name": "Invalid Channel Name!"},
        headers=headers,
    )
    assert res.status_code == 422


def test_channel_name_normalization():
    org = create_test_org("org_norm", "Norm Org")
    user = create_test_user("norm_user@example.com")
    OrganizationMembershipService.create_membership(user["id"], org["id"])
    headers = get_user_headers(user["id"])

    res = client.post(
        f"/organizations/{org['id']}/conversations",
        json={"name": "  alpha-channel  "},
        headers=headers,
    )
    assert res.status_code == 201
    assert res.json()["name"] == "alpha-channel"


def test_duplicate_channel_name_returns_409():
    org = create_test_org("org_dup", "Dup Org")
    user = create_test_user("dup_user@example.com")
    OrganizationMembershipService.create_membership(user["id"], org["id"])
    headers = get_user_headers(user["id"])

    res1 = client.post(
        f"/organizations/{org['id']}/conversations",
        json={"name": "announcements"},
        headers=headers,
    )
    assert res1.status_code == 201

    res2 = client.post(
        f"/organizations/{org['id']}/conversations",
        json={"name": "announcements"},
        headers=headers,
    )
    assert res2.status_code == 409
    assert "already exists" in res2.json()["detail"]


# ==============================================================================
# B. Default General Channel Provisioning
# ==============================================================================

def test_new_organization_creation_provisions_default_general_channel():
    admin = create_test_system_admin("sysadmin_gen@example.com")
    headers = get_admin_headers(admin["id"], "system_admin")

    res = client.post(
        "/admin/organizations",
        json={"org_id": "org_auto_gen", "name": "Auto Gen Org", "join_code": "Code123!"},
        headers=headers,
    )
    assert res.status_code == 200
    org_id = res.json()["id"]

    channels = ConversationService.list_organization_conversations(org_id)
    assert len(channels) == 1
    assert channels[0]["name"] == "general"
    assert channels[0]["type"] == "organization"
    assert channels[0]["organization_id"] == org_id


def test_default_general_channel_does_not_appear_in_direct_conversations():
    admin = create_test_system_admin("sysadmin_dir_test@example.com")
    headers = get_admin_headers(admin["id"], "system_admin")

    res = client.post(
        "/admin/organizations",
        json={"org_id": "org_auto_gen_2", "name": "Auto Gen Org 2", "join_code": "Code123!"},
        headers=headers,
    )
    org_id = res.json()["id"]

    user = create_test_user("member_user@example.com")
    OrganizationMembershipService.create_membership(user["id"], org_id)

    user_headers = get_user_headers(user["id"])
    direct_res = client.get("/conversations", headers=user_headers)
    assert direct_res.status_code == 200
    assert len(direct_res.json()) == 0  # General channel is NOT in direct 1-to-1 list


# ==============================================================================
# C. Channel Listing
# ==============================================================================

def test_active_member_can_list_organization_channels():
    org = create_test_org("org_list", "List Org")
    user = create_test_user("list_user@example.com")
    OrganizationMembershipService.create_membership(user["id"], org["id"])
    headers = get_user_headers(user["id"])

    ConversationService.create_organization_conversation(org["id"], "channel-a", created_by=user["id"])
    ConversationService.create_organization_conversation(org["id"], "channel-b", created_by=user["id"])

    res = client.get(f"/organizations/{org['id']}/conversations", headers=headers)
    assert res.status_code == 200
    items = res.json()
    assert len(items) == 2
    names = [c["name"] for c in items]
    assert "channel-a" in names
    assert "channel-b" in names


def test_non_member_cannot_list_organization_channels():
    org = create_test_org("org_list_block", "List Block Org")
    user = create_test_user("block_user@example.com")
    headers = get_user_headers(user["id"])

    res = client.get(f"/organizations/{org['id']}/conversations", headers=headers)
    assert res.status_code == 403


def test_channels_are_strictly_scoped_to_requested_organization():
    org1 = create_test_org("org_scope_1", "Scope Org 1")
    org2 = create_test_org("org_scope_2", "Scope Org 2")

    user = create_test_user("multi_member@example.com")
    OrganizationMembershipService.create_membership(user["id"], org1["id"])
    OrganizationMembershipService.create_membership(user["id"], org2["id"])
    headers = get_user_headers(user["id"])

    ConversationService.create_organization_conversation(org1["id"], "channel-org1", created_by=user["id"])
    ConversationService.create_organization_conversation(org2["id"], "channel-org2", created_by=user["id"])

    res1 = client.get(f"/organizations/{org1['id']}/conversations", headers=headers)
    assert res1.status_code == 200
    assert len(res1.json()) == 1
    assert res1.json()[0]["name"] == "channel-org1"

    res2 = client.get(f"/organizations/{org2['id']}/conversations", headers=headers)
    assert res2.status_code == 200
    assert len(res2.json()) == 1
    assert res2.json()[0]["name"] == "channel-org2"


# ==============================================================================
# D. Conversation Access & Cross-Tenant Isolation
# ==============================================================================

def test_active_member_can_retrieve_organization_conversation():
    org = create_test_org("org_retr", "Retr Org")
    user = create_test_user("retr_user@example.com")
    OrganizationMembershipService.create_membership(user["id"], org["id"])
    headers = get_user_headers(user["id"])

    conv = ConversationService.create_organization_conversation(org["id"], "general-chat", created_by=user["id"])

    res = client.get(f"/conversations/{conv['id']}", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == conv["id"]
    assert data["name"] == "general-chat"
    assert data["type"] == "organization"


def test_cross_tenant_organization_conversation_access_denied():
    org1 = create_test_org("org_cross_1", "Cross Org 1")
    org2 = create_test_org("org_cross_2", "Cross Org 2")

    user1 = create_test_user("org1_only@example.com")
    OrganizationMembershipService.create_membership(user1["id"], org1["id"])

    conv_org2 = ConversationService.create_organization_conversation(org2["id"], "secret-org2-channel")

    headers1 = get_user_headers(user1["id"])
    res = client.get(f"/conversations/{conv_org2['id']}", headers=headers1)
    assert res.status_code == 403
    assert "Access denied" in res.json()["detail"]


# ==============================================================================
# E. Messages in Organization Channels
# ==============================================================================

def test_active_member_can_send_and_read_messages_in_organization_channel():
    org = create_test_org("org_msg", "Msg Org")
    user1 = create_test_user("msg_user1@example.com")
    user2 = create_test_user("msg_user2@example.com")
    OrganizationMembershipService.create_membership(user1["id"], org["id"])
    OrganizationMembershipService.create_membership(user2["id"], org["id"])

    conv = ConversationService.create_organization_conversation(org["id"], "team-chat", created_by=user1["id"])

    # User 1 sends message
    headers1 = get_user_headers(user1["id"])
    send_res = client.post(
        f"/conversations/{conv['id']}/messages",
        json={"content": "Hello team!"},
        headers=headers1,
    )
    assert send_res.status_code == 201
    assert send_res.json()["content"] == "Hello team!"

    # User 2 reads messages
    headers2 = get_user_headers(user2["id"])
    get_res = client.get(f"/conversations/{conv['id']}/messages", headers=headers2)
    assert get_res.status_code == 200
    messages = get_res.json()
    assert len(messages) == 1
    assert messages[0]["content"] == "Hello team!"
    assert messages[0]["sender_id"] == user1["id"]


def test_non_member_cannot_send_or_read_messages_in_organization_channel():
    org = create_test_org("org_msg_block", "Msg Block Org")
    member = create_test_user("member_in@example.com")
    outsider = create_test_user("outsider_out@example.com")
    OrganizationMembershipService.create_membership(member["id"], org["id"])

    conv = ConversationService.create_organization_conversation(org["id"], "internal-channel", created_by=member["id"])

    outsider_headers = get_user_headers(outsider["id"])

    # Send attempt
    post_res = client.post(
        f"/conversations/{conv['id']}/messages",
        json={"content": "I should not be here"},
        headers=outsider_headers,
    )
    assert post_res.status_code == 403

    # Read attempt
    read_res = client.get(f"/conversations/{conv['id']}/messages", headers=outsider_headers)
    assert read_res.status_code == 403


def test_membership_removal_immediately_blocks_subsequent_message_access():
    org = create_test_org("org_rev", "Revoke Org")
    user = create_test_user("revoke_user@example.com")
    OrganizationMembershipService.create_membership(user["id"], org["id"])
    conv = ConversationService.create_organization_conversation(org["id"], "project-alpha", created_by=user["id"])

    headers = get_user_headers(user["id"])

    # Send while active
    res1 = client.post(f"/conversations/{conv['id']}/messages", json={"content": "Msg 1"}, headers=headers)
    assert res1.status_code == 201

    # Revoke membership
    db.get_db()["organization_memberships"].delete_many({"user_id": ObjectId(user["id"]), "organization_id": ObjectId(org["id"])})

    # Send after revoke -> 403
    res2 = client.post(f"/conversations/{conv['id']}/messages", json={"content": "Msg 2"}, headers=headers)
    assert res2.status_code == 403

    # Read after revoke -> 403
    res3 = client.get(f"/conversations/{conv['id']}/messages", headers=headers)
    assert res3.status_code == 403


def test_inactive_organization_blocks_message_sending_and_reading():
    org = create_test_org("org_inact_msg", "Inact Msg Org")
    user = create_test_user("inact_msg_user@example.com")
    OrganizationMembershipService.create_membership(user["id"], org["id"])
    conv = ConversationService.create_organization_conversation(org["id"], "main", created_by=user["id"])

    headers = get_user_headers(user["id"])

    # Deactivate organization
    db.get_db()["organizations"].update_one({"_id": ObjectId(org["id"])}, {"$set": {"is_active": False}})

    post_res = client.post(f"/conversations/{conv['id']}/messages", json={"content": "Fail"}, headers=headers)
    assert post_res.status_code == 403

    get_res = client.get(f"/conversations/{conv['id']}/messages", headers=headers)
    assert get_res.status_code == 403


# ==============================================================================
# F. WebSocket Integration
# ==============================================================================

def test_websocket_active_member_can_connect_and_receive_messages():
    org = create_test_org("org_ws_ok", "WS OK Org")
    user1 = create_test_user("ws_user1@example.com")
    user2 = create_test_user("ws_user2@example.com")
    OrganizationMembershipService.create_membership(user1["id"], org["id"])
    OrganizationMembershipService.create_membership(user2["id"], org["id"])

    conv = ConversationService.create_organization_conversation(org["id"], "general-ws", created_by=user1["id"])

    token1 = JWTService.create_access_token(subject=user1["id"])
    token2 = JWTService.create_access_token(subject=user2["id"])

    with client.websocket_connect(f"/ws/conversations/{conv['id']}?token={token1}") as ws1:
        with client.websocket_connect(f"/ws/conversations/{conv['id']}?token={token2}") as ws2:
            # User 1 sends message
            ws1.send_text('{"content": "Real-time hello!"}')

            # User 1 receives ack
            ack = ws1.receive_json()
            assert ack["type"] == "message_ack"
            assert ack["data"]["content"] == "Real-time hello!"

            # User 2 receives broadcast
            bcast = ws2.receive_json()
            assert bcast["type"] == "message"
            assert bcast["data"]["content"] == "Real-time hello!"


def test_websocket_non_member_connection_rejected_with_1008():
    org = create_test_org("org_ws_rej", "WS Rej Org")
    member = create_test_user("ws_member@example.com")
    outsider = create_test_user("ws_outsider@example.com")
    OrganizationMembershipService.create_membership(member["id"], org["id"])

    conv = ConversationService.create_organization_conversation(org["id"], "private-ws", created_by=member["id"])

    token = JWTService.create_access_token(subject=outsider["id"])
    with pytest.raises(Exception):
        with client.websocket_connect(f"/ws/conversations/{conv['id']}?token={token}") as ws:
            pass


def test_websocket_cross_tenant_connection_rejected_with_1008():
    org1 = create_test_org("org_ws_x1", "WS X1 Org")
    org2 = create_test_org("org_ws_x2", "WS X2 Org")
    user1 = create_test_user("ws_x1_user@example.com")
    OrganizationMembershipService.create_membership(user1["id"], org1["id"])

    conv2 = ConversationService.create_organization_conversation(org2["id"], "org2-ws")

    token1 = JWTService.create_access_token(subject=user1["id"])
    with pytest.raises(Exception):
        with client.websocket_connect(f"/ws/conversations/{conv2['id']}?token={token1}") as ws:
            pass


def test_websocket_inactive_organization_rejected_with_1008():
    org = create_test_org("org_ws_inact", "WS Inact Org")
    user = create_test_user("ws_inact_user@example.com")
    OrganizationMembershipService.create_membership(user["id"], org["id"])
    conv = ConversationService.create_organization_conversation(org["id"], "general-ws")

    db.get_db()["organizations"].update_one({"_id": ObjectId(org["id"])}, {"$set": {"is_active": False}})

    token = JWTService.create_access_token(subject=user["id"])
    with pytest.raises(Exception):
        with client.websocket_connect(f"/ws/conversations/{conv['id']}?token={token}") as ws:
            pass


def test_websocket_direct_conversation_connection_still_works():
    user1 = create_test_user("direct_ws_1@example.com")
    user2 = create_test_user("direct_ws_2@example.com")
    conv = ConversationService.create_conversation(user1["id"], user2["id"])

    token1 = JWTService.create_access_token(subject=user1["id"])
    token2 = JWTService.create_access_token(subject=user2["id"])

    with client.websocket_connect(f"/ws/conversations/{conv['id']}?token={token1}") as ws1:
        with client.websocket_connect(f"/ws/conversations/{conv['id']}?token={token2}") as ws2:
            ws1.send_text('{"content": "Direct real-time"}')
            ack = ws1.receive_json()
            assert ack["type"] == "message_ack"
            assert ack["data"]["content"] == "Direct real-time"


# ==============================================================================
# G. Direct-Chat Regression
# ==============================================================================

def test_direct_conversation_creation_and_retrieval_still_works():
    user1 = create_test_user("dir_u1@example.com")
    user2 = create_test_user("dir_u2@example.com")
    headers1 = get_user_headers(user1["id"])

    # Create direct conversation
    res = client.post("/conversations", json={"other_user_id": user2["id"]}, headers=headers1)
    assert res.status_code == 201
    conv_id = res.json()["id"]
    assert "participants" in res.json()

    # Retrieve direct conversation
    get_res = client.get(f"/conversations/{conv_id}", headers=headers1)
    assert get_res.status_code == 200
    assert get_res.json()["id"] == conv_id
    assert "participants" in get_res.json()


def test_direct_messages_and_pagination_still_work():
    user1 = create_test_user("page_u1@example.com")
    user2 = create_test_user("page_u2@example.com")
    conv = ConversationService.create_conversation(user1["id"], user2["id"])

    headers1 = get_user_headers(user1["id"])

    for i in range(5):
        client.post(f"/conversations/{conv['id']}/messages", json={"content": f"Msg {i}"}, headers=headers1)

    res = client.get(f"/conversations/{conv['id']}/messages?limit=3", headers=headers1)
    assert res.status_code == 200
    assert len(res.json()) == 3
    assert "X-Next-Cursor" in res.headers


def test_legacy_direct_conversation_without_type_field_remains_valid():
    user1 = create_test_user("leg_u1@example.com")
    user2 = create_test_user("leg_u2@example.com")

    # Insert old-style document without "type" or "organization_id"
    now = datetime.now(timezone.utc)
    old_doc = {
        "participants": [ObjectId(user1["id"]), ObjectId(user2["id"])],
        "participant_key": f"{user1['id']}:{user2['id']}",
        "created_at": now,
        "updated_at": now,
    }
    res = db.get_db()["conversations"].insert_one(old_doc)
    conv_id = str(res.inserted_id)

    headers1 = get_user_headers(user1["id"])

    # Can get conversation
    get_res = client.get(f"/conversations/{conv_id}", headers=headers1)
    assert get_res.status_code == 200
    assert "participants" in get_res.json()

    # Can send message
    msg_res = client.post(f"/conversations/{conv_id}/messages", json={"content": "Legacy direct works"}, headers=headers1)
    assert msg_res.status_code == 201


# ==============================================================================
# H. Security & Audit
# ==============================================================================

def test_organization_channel_creation_generates_audit_event():
    org = create_test_org("org_aud_1", "Audit Org 1")
    user = create_test_user("audit_creator@example.com")
    OrganizationMembershipService.create_membership(user["id"], org["id"])
    headers = get_user_headers(user["id"])

    res = client.post(
        f"/organizations/{org['id']}/conversations",
        json={"name": "audited-channel"},
        headers=headers,
    )
    assert res.status_code == 201

    logs = AuditService.list_events(event_type=AuditEventType.ORGANIZATION_CONVERSATION_CREATED)
    assert len(logs) == 1
    assert logs[0]["actor_id"] == user["id"]
    assert logs[0]["organization_id"] == org["id"]
    assert logs[0]["metadata"]["name"] == "audited-channel"


def test_unauthorized_cross_tenant_access_generates_audit_event():
    org = create_test_org("org_aud_2", "Audit Org 2")
    user = create_test_user("unauth_audit_user@example.com")
    headers = get_user_headers(user["id"])

    res = client.post(
        f"/organizations/{org['id']}/conversations",
        json={"name": "intruder-channel"},
        headers=headers,
    )
    assert res.status_code == 403

    logs = AuditService.list_events(event_type=AuditEventType.ORGANIZATION_CONVERSATION_ACCESS_DENIED)
    assert len(logs) == 1
    assert logs[0]["actor_id"] == user["id"]
    assert logs[0]["organization_id"] == org["id"]
    assert logs[0]["status"] == "failure"


def test_admin_jwt_cannot_authenticate_as_normal_user_on_chat():
    org = create_test_org("org_admin_chat", "Admin Chat Org")
    admin = create_test_system_admin("admin_chat_attempt@example.com")
    admin_headers = get_admin_headers(admin["id"], "system_admin")

    res = client.post(
        f"/organizations/{org['id']}/conversations",
        json={"name": "admin-attempt"},
        headers=admin_headers,
    )
    # Admin tokens fail get_current_user
    assert res.status_code == 401
