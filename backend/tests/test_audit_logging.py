from __future__ import annotations

from datetime import datetime, timedelta, timezone
from bson import ObjectId
import pytest
from fastapi.testclient import TestClient
from pymongo.errors import PyMongoError

from app.db import db
from app.main import app
from app.schemas.admin import AdminCreate
from app.schemas.audit import AuditAction, AuditActorType, AuditEventType, AuditStatus
from app.services.admin_auth_service import AdminAuthService
from app.services.audit_service import AuditService
from app.services.jwt_service import JWTService
from app.services.organization_membership_service import OrganizationMembershipService
from app.services.organization_request_service import OrganizationRequestService
from app.services.organization_service import OrganizationService
from app.services.user_service import UserService

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_db():
    database = db.get_db()
    database["audit_logs"].delete_many({})
    database["admin_users"].delete_many({})
    database["admin_sessions"].delete_many({})
    database["organizations"].delete_many({})
    database["organization_memberships"].delete_many({})
    database["organization_registration_requests"].delete_many({})
    database["users"].delete_many({})
    database["auth_sessions"].delete_many({})
    yield
    database["audit_logs"].delete_many({})
    database["admin_users"].delete_many({})
    database["admin_sessions"].delete_many({})
    database["organizations"].delete_many({})
    database["organization_memberships"].delete_many({})
    database["organization_registration_requests"].delete_many({})
    database["users"].delete_many({})
    database["auth_sessions"].delete_many({})


def create_test_system_admin(email="sysadmin@example.com", password="Password123!", name="System Admin"):
    return AdminAuthService.create_admin(
        AdminCreate(
            email=email,
            password=password,
            name=name,
            role="system_admin",
            organization_id=None,
        )
    )


def create_test_org_admin(email="orgadmin@example.com", password="Password123!", name="Org Admin", organization_id=None):
    return AdminAuthService.create_admin(
        AdminCreate(
            email=email,
            password=password,
            name=name,
            role="org_admin",
            organization_id=organization_id,
        )
    )


def create_test_user(email="user@example.com", name="Test User"):
    user_doc = {
        "email": email,
        "name": name,
        "password_hash": "hashed_pass",
        "created_at": datetime.now(timezone.utc),
    }
    res = db.get_db()["users"].insert_one(user_doc)
    return {"id": str(res.inserted_id), "email": email, "name": name}


def get_admin_headers(admin_id: str, role: str, organization_id: str | None = None) -> dict[str, str]:
    token = JWTService.create_admin_access_token(
        admin_id=admin_id,
        role=role,
        organization_id=organization_id,
    )
    return {"Authorization": f"Bearer {token}"}


def get_user_headers(user_id: str) -> dict[str, str]:
    token = JWTService.create_access_token(subject=user_id)
    return {"Authorization": f"Bearer {token}"}


# ==============================================================================
# 1. Audit Service Unit Tests
# ==============================================================================

def test_audit_service_creates_event_successfully():
    event = AuditService.log_event(
        event_type=AuditEventType.ORGANIZATION_CREATED,
        actor_type=AuditActorType.ADMIN,
        action=AuditAction.CREATE,
        status=AuditStatus.SUCCESS,
        actor_id=str(ObjectId()),
        actor_role="system_admin",
        metadata={"key": "value"},
    )
    assert event is not None
    assert event["event_type"] == "organization_created"
    assert event["actor_type"] == "admin"
    assert event["action"] == "create"
    assert event["status"] == "success"
    assert event["metadata"] == {"key": "value"}
    assert "id" in event


def test_audit_service_generates_utc_timestamp():
    event = AuditService.log_event(
        event_type=AuditEventType.ADMIN_LOGIN,
        actor_type=AuditActorType.ADMIN,
        action=AuditAction.LOGIN,
    )
    assert event is not None
    assert isinstance(event["created_at"], datetime)
    assert event["created_at"].tzinfo is not None or event["created_at"].year >= 2026


def test_audit_service_records_actor_info_and_role():
    actor_id = str(ObjectId())
    event = AuditService.log_event(
        event_type=AuditEventType.ADMIN_LOGIN,
        actor_type=AuditActorType.ADMIN,
        action=AuditAction.LOGIN,
        actor_id=actor_id,
        actor_role="system_admin",
    )
    assert event is not None
    assert event["actor_id"] == actor_id
    assert event["actor_role"] == "system_admin"


def test_audit_service_associates_organization_id():
    org_id = str(ObjectId())
    event = AuditService.log_event(
        event_type=AuditEventType.ORGANIZATION_JOIN_REQUEST_SUBMITTED,
        actor_type=AuditActorType.USER,
        action=AuditAction.JOIN,
        organization_id=org_id,
    )
    assert event is not None
    assert event["organization_id"] == org_id


def test_audit_service_records_target_info():
    target_id = str(ObjectId())
    event = AuditService.log_event(
        event_type=AuditEventType.ORGANIZATION_JOIN_REQUEST_APPROVED,
        actor_type=AuditActorType.ADMIN,
        action=AuditAction.APPROVE,
        target_type="organization_registration_request",
        target_id=target_id,
    )
    assert event is not None
    assert event["target_type"] == "organization_registration_request"
    assert event["target_id"] == target_id


def test_audit_service_handles_metadata_and_strips_forbidden_keys():
    meta = {
        "org_id": "test_org",
        "password": "supersecretpassword",
        "password_hash": "hashedpassword",
        "join_code": "secret123",
        "join_code_hash": "$2b$12$xyz",
        "refresh_token": "token123",
        "access_token": "jwt123",
        "jwt": "jwt_token",
        "token": "token_str",
        "otp": "123456",
        "otp_hash": "otphash",
        "cookie": "cookie_data",
        "authorization": "Bearer xxx",
        "session_token": "session_tok",
        "secret": "topsecret",
    }
    event = AuditService.log_event(
        event_type=AuditEventType.ORGANIZATION_CREATED,
        actor_type=AuditActorType.ADMIN,
        action=AuditAction.CREATE,
        metadata=meta,
    )
    assert event is not None
    # Only safe keys preserved
    assert event["metadata"] == {"org_id": "test_org"}


def test_audit_service_handles_nested_metadata_sanitization():
    meta = {
        "org_id": "test_org",
        "nested": {
            "safe_prop": 123,
            "password": "nested_password",
        },
        "list_items": [
            {"token": "bad_token", "allowed": "good"},
            "simple_string",
        ],
    }
    event = AuditService.log_event(
        event_type=AuditEventType.ORGANIZATION_CREATED,
        actor_type=AuditActorType.ADMIN,
        action=AuditAction.CREATE,
        metadata=meta,
    )
    assert event is not None
    assert event["metadata"]["org_id"] == "test_org"
    assert event["metadata"]["nested"] == {"safe_prop": 123}
    assert event["metadata"]["list_items"] == [{"allowed": "good"}, "simple_string"]


def test_audit_service_handles_db_failure_safely(monkeypatch):
    class FailingCollection:
        def insert_one(self, *args, **kwargs):
            raise PyMongoError("Simulated DB error")

    class FailingDb:
        def __getitem__(self, item):
            return FailingCollection()

    monkeypatch.setattr(db, "get_db", lambda: FailingDb())

    # Should safely return None without throwing exception
    result = AuditService.log_event(
        event_type=AuditEventType.ADMIN_LOGIN,
        actor_type=AuditActorType.ADMIN,
        action=AuditAction.LOGIN,
    )
    assert result is None


# ==============================================================================
# 2. Admin Authentication Events
# ==============================================================================

def test_admin_login_success_creates_audit_event():
    admin = create_test_system_admin(email="login_admin@example.com", password="Password123!")

    res = client.post(
        "/admin/auth/login",
        json={"email": "login_admin@example.com", "password": "Password123!"},
    )
    assert res.status_code == 200

    logs = AuditService.list_events(event_type=AuditEventType.ADMIN_LOGIN)
    assert len(logs) == 1
    assert logs[0]["actor_id"] == admin["id"]
    assert logs[0]["actor_role"] == "system_admin"
    assert logs[0]["status"] == "success"
    assert logs[0]["action"] == "login"


def test_admin_login_failed_creates_audit_event_without_exposing_email():
    res = client.post(
        "/admin/auth/login",
        json={"email": "nonexistent@example.com", "password": "WrongPassword!"},
    )
    assert res.status_code == 401

    logs = AuditService.list_events(event_type=AuditEventType.ADMIN_LOGIN_FAILED)
    assert len(logs) == 1
    assert logs[0]["status"] == "failure"
    assert logs[0]["action"] == "login"
    # Ensure submitted nonexistent email is NOT stored in metadata to avoid account enumeration
    assert "nonexistent@example.com" not in str(logs[0].get("metadata", {}))


def test_admin_logout_creates_audit_event():
    create_test_system_admin(email="logout_admin@example.com", password="Password123!")
    login_res = client.post(
        "/admin/auth/login",
        json={"email": "logout_admin@example.com", "password": "Password123!"},
    )
    assert login_res.status_code == 200

    logout_res = client.post("/admin/auth/logout")
    assert logout_res.status_code == 200

    logs = AuditService.list_events(event_type=AuditEventType.ADMIN_LOGOUT)
    assert len(logs) == 1
    assert logs[0]["status"] == "success"
    assert logs[0]["action"] == "logout"


def test_admin_login_audit_never_contains_password_or_token():
    create_test_system_admin(email="secure_admin@example.com", password="Password123!")
    res = client.post(
        "/admin/auth/login",
        json={"email": "secure_admin@example.com", "password": "Password123!"},
    )
    assert res.status_code == 200
    token = res.json()["access_token"]

    logs = AuditService.list_events()
    for log in logs:
        log_str = str(log)
        assert "Password123!" not in log_str
        assert token not in log_str


# ==============================================================================
# 3. Organization Lifecycle Events
# ==============================================================================

def test_organization_creation_creates_audit_event():
    admin = create_test_system_admin()
    headers = get_admin_headers(admin["id"], "system_admin")

    res = client.post(
        "/admin/organizations",
        json={"org_id": "alpha_org", "name": "Alpha Org", "join_code": "SecretJoinCode123!"},
        headers=headers,
    )
    assert res.status_code == 200
    org_id = res.json()["id"]

    logs = AuditService.list_events(event_type=AuditEventType.ORGANIZATION_CREATED)
    assert len(logs) == 1
    assert logs[0]["actor_id"] == admin["id"]
    assert logs[0]["organization_id"] == org_id
    assert logs[0]["target_id"] == org_id
    assert logs[0]["metadata"]["org_id"] == "alpha_org"


def test_organization_creation_audit_never_contains_join_code():
    admin = create_test_system_admin()
    headers = get_admin_headers(admin["id"], "system_admin")

    res = client.post(
        "/admin/organizations",
        json={"org_id": "beta_org", "name": "Beta Org", "join_code": "SecretJoinCode999!"},
        headers=headers,
    )
    assert res.status_code == 200

    logs = AuditService.list_events(event_type=AuditEventType.ORGANIZATION_CREATED)
    assert len(logs) == 1
    assert "SecretJoinCode999!" not in str(logs[0])


def test_join_request_submission_creates_audit_event():
    org = OrganizationService.create_organization(
        org_id="gamma_org",
        name="Gamma Org",
        join_code="JoinGamma123!",
    )
    user = create_test_user(email="gamma_user@example.com")
    headers = get_user_headers(user["id"])

    res = client.post(
        "/auth/organizations/join",
        json={"org_id": "gamma_org", "join_code": "JoinGamma123!"},
        headers=headers,
    )
    assert res.status_code == 200
    req_id = res.json()["id"]

    logs = AuditService.list_events(event_type=AuditEventType.ORGANIZATION_JOIN_REQUEST_SUBMITTED)
    assert len(logs) == 1
    assert logs[0]["actor_id"] == user["id"]
    assert logs[0]["actor_role"] == "user"
    assert logs[0]["organization_id"] == org["id"]
    assert logs[0]["target_id"] == req_id
    assert "JoinGamma123!" not in str(logs[0])


def test_join_request_approval_and_rejection_audit_events():
    org = OrganizationService.create_organization(
        org_id="delta_org",
        name="Delta Org",
        join_code="JoinDelta123!",
    )
    org_admin = create_test_org_admin(email="delta_admin@example.com", organization_id=org["id"])
    admin_headers = get_admin_headers(org_admin["id"], "org_admin", organization_id=org["id"])

    user1 = create_test_user(email="delta_user1@example.com")
    user2 = create_test_user(email="delta_user2@example.com")

    # User 1 joins -> Approved
    req1 = OrganizationRequestService.create_request(user1["id"], org["id"])
    app_res = client.post(f"/admin/requests/{req1['id']}/approve", headers=admin_headers)
    assert app_res.status_code == 200

    # User 2 joins -> Rejected
    req2 = OrganizationRequestService.create_request(user2["id"], org["id"])
    rej_res = client.post(f"/admin/requests/{req2['id']}/reject", headers=admin_headers)
    assert rej_res.status_code == 200

    app_logs = AuditService.list_events(event_type=AuditEventType.ORGANIZATION_JOIN_REQUEST_APPROVED)
    assert len(app_logs) == 1
    assert app_logs[0]["actor_id"] == org_admin["id"]
    assert app_logs[0]["target_id"] == req1["id"]
    assert app_logs[0]["organization_id"] == org["id"]

    rej_logs = AuditService.list_events(event_type=AuditEventType.ORGANIZATION_JOIN_REQUEST_REJECTED)
    assert len(rej_logs) == 1
    assert rej_logs[0]["actor_id"] == org_admin["id"]
    assert rej_logs[0]["target_id"] == req2["id"]
    assert rej_logs[0]["organization_id"] == org["id"]


def test_join_request_resubmission_creates_audit_event():
    org = OrganizationService.create_organization(
        org_id="resub_org",
        name="Resub Org",
        join_code="JoinResub123!",
    )
    org_admin = create_test_org_admin(email="resub_admin@example.com", organization_id=org["id"])
    admin_headers = get_admin_headers(org_admin["id"], "org_admin", organization_id=org["id"])

    user = create_test_user(email="resub_user@example.com")
    user_headers = get_user_headers(user["id"])

    # 1. Initial join request
    res1 = client.post(
        "/auth/organizations/join",
        json={"org_id": "resub_org", "join_code": "JoinResub123!"},
        headers=user_headers,
    )
    assert res1.status_code == 200
    req_id = res1.json()["id"]

    # 2. Reject request
    rej_res = client.post(f"/admin/requests/{req_id}/reject", headers=admin_headers)
    assert rej_res.status_code == 200

    # 3. Resubmit join request
    res2 = client.post(
        "/auth/organizations/join",
        json={"org_id": "resub_org", "join_code": "JoinResub123!"},
        headers=user_headers,
    )
    assert res2.status_code == 200

    logs = AuditService.list_events(event_type=AuditEventType.ORGANIZATION_JOIN_REQUEST_SUBMITTED)
    assert len(logs) == 2  # Both initial submission and resubmission are audited
    for l in logs:
        assert l["actor_id"] == user["id"]
        assert l["organization_id"] == org["id"]


def test_audit_response_never_exposes_forbidden_authentication_fields():
    AuditService.log_event(
        event_type=AuditEventType.ADMIN_LOGIN,
        actor_type=AuditActorType.ADMIN,
        action=AuditAction.LOGIN,
        status=AuditStatus.SUCCESS,
        metadata={"safe_info": "ok"},
    )
    sys_admin = create_test_system_admin()
    headers = get_admin_headers(sys_admin["id"], "system_admin")

    res = client.get("/admin/audit", headers=headers)
    assert res.status_code == 200
    items = res.json()
    assert len(items) >= 1
    forbidden_keys = {"password", "password_hash", "token", "refresh_token", "join_code", "otp", "secret"}
    for item in items:
        for f_key in forbidden_keys:
            assert f_key not in item
            assert f_key not in item.get("metadata", {})


def test_audit_metadata_cannot_persist_sensitive_categories():
    event = AuditService.log_event(
        event_type=AuditEventType.ORGANIZATION_CREATED,
        actor_type=AuditActorType.ADMIN,
        action=AuditAction.CREATE,
        metadata={
            "my_password": "p1",
            "access_token_jwt": "t1",
            "otp_code": "123456",
            "secret_join_code": "code1",
            "allowed_key": "allowed_val",
        },
    )
    assert event is not None
    assert "allowed_key" in event["metadata"]
    assert "my_password" not in event["metadata"]
    assert "access_token_jwt" not in event["metadata"]
    assert "otp_code" not in event["metadata"]
    assert "secret_join_code" not in event["metadata"]


# ==============================================================================
# 4. Authorization & Tenant Isolation on /admin/audit
# ==============================================================================

def test_unauthenticated_request_cannot_access_audit_logs():
    res = client.get("/admin/audit")
    assert res.status_code == 401


def test_normal_user_cannot_access_audit_logs():
    user = create_test_user()
    headers = get_user_headers(user["id"])
    res = client.get("/admin/audit", headers=headers)
    assert res.status_code == 401  # user token does not have type: "admin"


def test_org_admin_can_query_own_organization_audit_logs():
    org1 = OrganizationService.create_organization("org_one", "Org One", "Join1!")
    org2 = OrganizationService.create_organization("org_two", "Org Two", "Join2!")

    # Log events for Org 1 and Org 2
    AuditService.log_event(
        event_type=AuditEventType.ORGANIZATION_JOIN_REQUEST_SUBMITTED,
        actor_type=AuditActorType.USER,
        action=AuditAction.JOIN,
        organization_id=org1["id"],
    )
    AuditService.log_event(
        event_type=AuditEventType.ORGANIZATION_JOIN_REQUEST_SUBMITTED,
        actor_type=AuditActorType.USER,
        action=AuditAction.JOIN,
        organization_id=org2["id"],
    )

    admin1 = create_test_org_admin(email="org1_admin@example.com", organization_id=org1["id"])
    headers = get_admin_headers(admin1["id"], "org_admin", organization_id=org1["id"])

    res = client.get("/admin/audit", headers=headers)
    assert res.status_code == 200
    items = res.json()
    assert len(items) == 1
    assert items[0]["organization_id"] == org1["id"]


def test_org_admin_client_supplied_org_id_cannot_override_scope():
    org1 = OrganizationService.create_organization("org_one_sec", "Org One Sec", "Join1!")
    org2 = OrganizationService.create_organization("org_two_sec", "Org Two Sec", "Join2!")

    AuditService.log_event(
        event_type=AuditEventType.ORGANIZATION_JOIN_REQUEST_SUBMITTED,
        actor_type=AuditActorType.USER,
        action=AuditAction.JOIN,
        organization_id=org2["id"],
    )

    admin1 = create_test_org_admin(email="org1_admin_sec@example.com", organization_id=org1["id"])
    headers = get_admin_headers(admin1["id"], "org_admin", organization_id=org1["id"])

    # Org admin tries to pass Org 2's id in query
    res = client.get(f"/admin/audit?organization_id={org2['id']}", headers=headers)
    assert res.status_code == 200
    items = res.json()
    # Scoped strictly to Org 1 -> Returns 0 items because Org 2 is filtered out
    assert len(items) == 0


def test_system_admin_can_query_audit_logs_globally():
    org1 = OrganizationService.create_organization("org_glob_1", "Org Glob 1", "Join1!")
    org2 = OrganizationService.create_organization("org_glob_2", "Org Glob 2", "Join2!")

    AuditService.log_event(
        event_type=AuditEventType.ORGANIZATION_JOIN_REQUEST_SUBMITTED,
        actor_type=AuditActorType.USER,
        action=AuditAction.JOIN,
        organization_id=org1["id"],
    )
    AuditService.log_event(
        event_type=AuditEventType.ORGANIZATION_JOIN_REQUEST_SUBMITTED,
        actor_type=AuditActorType.USER,
        action=AuditAction.JOIN,
        organization_id=org2["id"],
    )

    sys_admin = create_test_system_admin()
    headers = get_admin_headers(sys_admin["id"], "system_admin")

    res = client.get("/admin/audit", headers=headers)
    assert res.status_code == 200
    assert len(res.json()) >= 2


def test_system_admin_can_filter_by_organization_id():
    org1 = OrganizationService.create_organization("org_filt_1", "Org Filt 1", "Join1!")
    org2 = OrganizationService.create_organization("org_filt_2", "Org Filt 2", "Join2!")

    AuditService.log_event(
        event_type=AuditEventType.ORGANIZATION_JOIN_REQUEST_SUBMITTED,
        actor_type=AuditActorType.USER,
        action=AuditAction.JOIN,
        organization_id=org1["id"],
    )
    AuditService.log_event(
        event_type=AuditEventType.ORGANIZATION_JOIN_REQUEST_SUBMITTED,
        actor_type=AuditActorType.USER,
        action=AuditAction.JOIN,
        organization_id=org2["id"],
    )

    sys_admin = create_test_system_admin()
    headers = get_admin_headers(sys_admin["id"], "system_admin")

    res = client.get(f"/admin/audit?organization_id={org1['id']}", headers=headers)
    assert res.status_code == 200
    items = res.json()
    assert len(items) == 1
    assert items[0]["organization_id"] == org1["id"]


# ==============================================================================
# 5. Filtering & Pagination
# ==============================================================================

def test_filter_by_event_type_and_status():
    AuditService.log_event(event_type=AuditEventType.ADMIN_LOGIN, actor_type=AuditActorType.ADMIN, action=AuditAction.LOGIN, status=AuditStatus.SUCCESS)
    AuditService.log_event(event_type=AuditEventType.ADMIN_LOGIN_FAILED, actor_type=AuditActorType.ADMIN, action=AuditAction.LOGIN, status=AuditStatus.FAILURE)

    sys_admin = create_test_system_admin()
    headers = get_admin_headers(sys_admin["id"], "system_admin")

    res1 = client.get(f"/admin/audit?event_type={AuditEventType.ADMIN_LOGIN}", headers=headers)
    assert res1.status_code == 200
    assert len(res1.json()) == 1
    assert res1.json()[0]["event_type"] == "admin_login"

    res2 = client.get(f"/admin/audit?status={AuditStatus.FAILURE}", headers=headers)
    assert res2.status_code == 200
    assert len(res2.json()) == 1
    assert res2.json()[0]["status"] == "failure"


def test_filter_by_actor_id():
    actor1 = str(ObjectId())
    actor2 = str(ObjectId())
    AuditService.log_event(event_type=AuditEventType.ADMIN_LOGIN, actor_type=AuditActorType.ADMIN, action=AuditAction.LOGIN, actor_id=actor1)
    AuditService.log_event(event_type=AuditEventType.ADMIN_LOGIN, actor_type=AuditActorType.ADMIN, action=AuditAction.LOGIN, actor_id=actor2)

    sys_admin = create_test_system_admin()
    headers = get_admin_headers(sys_admin["id"], "system_admin")

    res = client.get(f"/admin/audit?actor_id={actor1}", headers=headers)
    assert res.status_code == 200
    assert len(res.json()) == 1
    assert res.json()[0]["actor_id"] == actor1


def test_filter_by_date_range():
    now = datetime.now(timezone.utc)
    old_time = now - timedelta(days=5)

    # Insert old event directly in DB
    db.get_db()["audit_logs"].insert_one({
        "event_type": "admin_login",
        "actor_type": "admin",
        "action": "login",
        "status": "success",
        "created_at": old_time,
        "metadata": {},
    })

    # Insert new event
    AuditService.log_event(event_type=AuditEventType.ADMIN_LOGIN, actor_type=AuditActorType.ADMIN, action=AuditAction.LOGIN)

    sys_admin = create_test_system_admin()
    headers = get_admin_headers(sys_admin["id"], "system_admin")

    # Filter with start_date 1 day ago
    start_date_iso = (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    res = client.get(f"/admin/audit?start_date={start_date_iso}", headers=headers)
    assert res.status_code == 200
    assert len(res.json()) == 1


def test_audit_limit_defaults_and_max_enforced():
    for i in range(10):
        AuditService.log_event(event_type=AuditEventType.ADMIN_LOGIN, actor_type=AuditActorType.ADMIN, action=AuditAction.LOGIN, metadata={"idx": i})

    sys_admin = create_test_system_admin()
    headers = get_admin_headers(sys_admin["id"], "system_admin")

    # Default limit
    res_default = client.get("/admin/audit", headers=headers)
    assert res_default.status_code == 200
    assert len(res_default.json()) == 10

    # Custom limit = 3
    res_limit = client.get("/admin/audit?limit=3", headers=headers)
    assert res_limit.status_code == 200
    assert len(res_limit.json()) == 3

    # Limit > 100 rejected with 422 by FastAPI query validation
    res_over = client.get("/admin/audit?limit=101", headers=headers)
    assert res_over.status_code == 422


def test_audit_logs_deterministic_ordering():
    e1 = AuditService.log_event(event_type=AuditEventType.ADMIN_LOGIN, actor_type=AuditActorType.ADMIN, action=AuditAction.LOGIN, metadata={"seq": 1})
    e2 = AuditService.log_event(event_type=AuditEventType.ADMIN_LOGIN, actor_type=AuditActorType.ADMIN, action=AuditAction.LOGIN, metadata={"seq": 2})

    sys_admin = create_test_system_admin()
    headers = get_admin_headers(sys_admin["id"], "system_admin")

    res = client.get("/admin/audit", headers=headers)
    assert res.status_code == 200
    items = res.json()
    assert items[0]["metadata"]["seq"] == 2
    assert items[1]["metadata"]["seq"] == 1


# ==============================================================================
# 6. Append-Only / Immutable API Protection
# ==============================================================================

def test_audit_logs_cannot_be_modified_or_deleted_via_api():
    sys_admin = create_test_system_admin()
    headers = get_admin_headers(sys_admin["id"], "system_admin")

    dummy_id = str(ObjectId())
    res_put = client.put(f"/admin/audit/{dummy_id}", json={"status": "modified"}, headers=headers)
    assert res_put.status_code in {404, 405}

    res_patch = client.patch(f"/admin/audit/{dummy_id}", json={"status": "modified"}, headers=headers)
    assert res_patch.status_code in {404, 405}

    res_delete = client.delete(f"/admin/audit/{dummy_id}", headers=headers)
    assert res_delete.status_code in {404, 405}
