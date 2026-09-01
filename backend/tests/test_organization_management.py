from __future__ import annotations

from datetime import datetime
from bson import ObjectId
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.db import db
from app.main import app
from app.schemas.admin import AdminCreate
from app.services.admin_auth_service import AdminAuthService
from app.services.jwt_service import JWTService
from app.services.organization_membership_service import OrganizationMembershipService
from app.services.organization_request_service import OrganizationRequestService
from app.services.organization_service import OrganizationService
from app.services.rate_limiter import auth_rate_limiter

client = TestClient(app)

SYS_ADMIN_EMAIL = "sysadmin@test.com"
ORG_A_ADMIN_EMAIL = "orgadmin_a@test.com"
ORG_B_ADMIN_EMAIL = "orgadmin_b@test.com"
USER_1_EMAIL = "user1@test.com"
USER_2_EMAIL = "user2@test.com"
PASSWORD = "StrongPassword123"


@pytest.fixture(autouse=True)
def clean_database():
    auth_rate_limiter.clear()
    db.get_db()["admin_users"].drop()
    db.get_db()["admin_sessions"].drop()
    db.get_db()["organizations"].drop()
    db.get_db()["organization_memberships"].drop()
    db.get_db()["organization_registration_requests"].drop()
    db.get_db()["users"].delete_many({"email": {"$in": [USER_1_EMAIL, USER_2_EMAIL, "user3@test.com"]}})
    db.ensure_indexes()

    yield

    auth_rate_limiter.clear()
    db.get_db()["admin_users"].drop()
    db.get_db()["admin_sessions"].drop()
    db.get_db()["organizations"].drop()
    db.get_db()["organization_memberships"].drop()
    db.get_db()["organization_registration_requests"].drop()
    db.get_db()["users"].delete_many({"email": {"$in": [USER_1_EMAIL, USER_2_EMAIL, "user3@test.com"]}})
    db.ensure_indexes()


def setup_system_admin() -> tuple[dict, str]:
    admin = AdminAuthService.create_admin(
        AdminCreate(
            email=SYS_ADMIN_EMAIL,
            name="System Admin",
            password=PASSWORD,
            role="system_admin",
            organization_id=None,
        )
    )
    token = JWTService.create_admin_access_token(admin["id"], admin["role"], admin["organization_id"])
    return admin, token


def setup_organization(org_id: str = "org-alpha", name: str = "Organization Alpha", join_code: str = "secret123") -> dict:
    return OrganizationService.create_organization(org_id, name, join_code)


def setup_org_admin(org_id: str, email: str = ORG_A_ADMIN_EMAIL) -> tuple[dict, str]:
    admin = AdminAuthService.create_admin(
        AdminCreate(
            email=email,
            name="Org Admin",
            password=PASSWORD,
            role="org_admin",
            organization_id=org_id,
        )
    )
    token = JWTService.create_admin_access_token(admin["id"], admin["role"], admin["organization_id"])
    return admin, token


def setup_user(email: str = USER_1_EMAIL, name: str = "Test User") -> tuple[dict, str]:
    client.post("/auth/register", json={"name": name, "email": email, "password": PASSWORD})
    client.post("/auth/register/verify", json={"email": email, "otp": "123456"})
    client.post("/auth/login", json={"email": email, "password": PASSWORD})
    verify_res = client.post("/auth/login/verify", json={"email": email, "otp": "123456"})
    token = verify_res.json()["access_token"]
    user = db.get_db()["users"].find_one({"email": email})
    return {"id": str(user["_id"]), "name": user["name"], "email": user["email"]}, token


# ==========================================
# A. Organization Creation Tests (1-7)
# ==========================================

def test_system_admin_creates_organization():
    _, sys_token = setup_system_admin()
    response = client.post(
        "/admin/organizations",
        json={"org_id": "pec2026", "name": "Panimalar College", "join_code": "pecsecret"},
        headers={"Authorization": f"Bearer {sys_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["org_id"] == "pec2026"
    assert data["name"] == "Panimalar College"
    assert data["is_active"] is True
    assert "join_code_hash" not in data


def test_org_admin_cannot_create_organization():
    org = setup_organization("org-alpha", "Alpha", "secret123")
    _, org_token = setup_org_admin(org["id"])
    response = client.post(
        "/admin/organizations",
        json={"org_id": "org-beta", "name": "Beta", "join_code": "secret123"},
        headers={"Authorization": f"Bearer {org_token}"},
    )
    assert response.status_code == 403


def test_normal_user_cannot_create_organization():
    _, user_token = setup_user()
    response = client.post(
        "/admin/organizations",
        json={"org_id": "org-gamma", "name": "Gamma", "join_code": "secret123"},
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert response.status_code == 401


def test_duplicate_org_id_returns_409():
    _, sys_token = setup_system_admin()
    client.post(
        "/admin/organizations",
        json={"org_id": "org-duplicate", "name": "Duplicate 1", "join_code": "secret123"},
        headers={"Authorization": f"Bearer {sys_token}"},
    )
    response = client.post(
        "/admin/organizations",
        json={"org_id": "org-duplicate", "name": "Duplicate 2", "join_code": "secret456"},
        headers={"Authorization": f"Bearer {sys_token}"},
    )
    assert response.status_code == 409
    assert "Organization ID already exists" in response.json()["detail"]


def test_organization_response_excludes_join_code_hash():
    _, sys_token = setup_system_admin()
    create_res = client.post(
        "/admin/organizations",
        json={"org_id": "org-safe", "name": "Safe Org", "join_code": "secret123"},
        headers={"Authorization": f"Bearer {sys_token}"},
    )
    assert "join_code_hash" not in create_res.json()
    assert "join_code" not in create_res.json()

    list_res = client.get(
        "/admin/organizations",
        headers={"Authorization": f"Bearer {sys_token}"},
    )
    assert list_res.status_code == 200
    for o in list_res.json():
        assert "join_code_hash" not in o
        assert "join_code" not in o


def test_invalid_org_id_rejected():
    _, sys_token = setup_system_admin()
    response = client.post(
        "/admin/organizations",
        json={"org_id": "Invalid Org ID with Spaces!", "name": "Invalid Org", "join_code": "secret123"},
        headers={"Authorization": f"Bearer {sys_token}"},
    )
    assert response.status_code == 422


def test_inactive_organization_cannot_be_joined():
    org = setup_organization("org-inactive", "Inactive Org", "secret123")
    db.get_db()["organizations"].update_one(
        {"_id": ObjectId(org["id"])},
        {"$set": {"is_active": False}},
    )
    _, user_token = setup_user()
    response = client.post(
        "/auth/organizations/join",
        json={"org_id": "org-inactive", "join_code": "secret123"},
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert response.status_code == 400
    assert "inactive" in response.json()["detail"].lower()


# ==========================================
# B. User Joining Tests (8-16)
# ==========================================

def test_valid_user_join_request():
    setup_organization("org-alpha", "Alpha Org", "alphaSecret123")
    _, user_token = setup_user()
    response = client.post(
        "/auth/organizations/join",
        json={"org_id": "org-alpha", "join_code": "alphaSecret123"},
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "PENDING"
    assert "id" in data
    assert "join_code" not in data


def test_nonexistent_org_returns_404():
    _, user_token = setup_user()
    response = client.post(
        "/auth/organizations/join",
        json={"org_id": "nonexistent-org", "join_code": "alphaSecret123"},
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert response.status_code == 404
    assert "Organization not found" in response.json()["detail"]


def test_incorrect_join_code_returns_400():
    setup_organization("org-alpha", "Alpha Org", "alphaSecret123")
    _, user_token = setup_user()
    response = client.post(
        "/auth/organizations/join",
        json={"org_id": "org-alpha", "join_code": "wrongCode123"},
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert response.status_code == 400
    assert "Invalid join code" in response.json()["detail"]


def test_already_member_receives_409():
    org = setup_organization("org-alpha", "Alpha Org", "alphaSecret123")
    user, user_token = setup_user()
    OrganizationMembershipService.create_membership(user["id"], org["id"])

    response = client.post(
        "/auth/organizations/join",
        json={"org_id": "org-alpha", "join_code": "alphaSecret123"},
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert response.status_code == 409
    assert "already a member" in response.json()["detail"]


def test_duplicate_pending_request_receives_409():
    setup_organization("org-alpha", "Alpha Org", "alphaSecret123")
    _, user_token = setup_user()

    # First join
    client.post(
        "/auth/organizations/join",
        json={"org_id": "org-alpha", "join_code": "alphaSecret123"},
        headers={"Authorization": f"Bearer {user_token}"},
    )

    # Duplicate join
    response = client.post(
        "/auth/organizations/join",
        json={"org_id": "org-alpha", "join_code": "alphaSecret123"},
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert response.status_code in {400, 409}


def test_rejected_request_can_be_resubmitted():
    org = setup_organization("org-alpha", "Alpha Org", "alphaSecret123")
    _, sys_token = setup_system_admin()
    user, user_token = setup_user()

    # Join
    join_res = client.post(
        "/auth/organizations/join",
        json={"org_id": "org-alpha", "join_code": "alphaSecret123"},
        headers={"Authorization": f"Bearer {user_token}"},
    )
    req_id = join_res.json()["id"]

    # Reject
    client.post(
        f"/admin/requests/{req_id}/reject",
        headers={"Authorization": f"Bearer {sys_token}"},
    )

    # Resubmit
    resubmit_res = client.post(
        "/auth/organizations/join",
        json={"org_id": "org-alpha", "join_code": "alphaSecret123"},
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert resubmit_res.status_code == 200
    assert resubmit_res.json()["status"] == "PENDING"


def test_approved_request_cannot_be_resubmitted():
    org = setup_organization("org-alpha", "Alpha Org", "alphaSecret123")
    _, sys_token = setup_system_admin()
    user, user_token = setup_user()

    # Join & approve
    join_res = client.post(
        "/auth/organizations/join",
        json={"org_id": "org-alpha", "join_code": "alphaSecret123"},
        headers={"Authorization": f"Bearer {user_token}"},
    )
    req_id = join_res.json()["id"]
    client.post(
        f"/admin/requests/{req_id}/approve",
        headers={"Authorization": f"Bearer {sys_token}"},
    )

    # Try join again
    resubmit_res = client.post(
        "/auth/organizations/join",
        json={"org_id": "org-alpha", "join_code": "alphaSecret123"},
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert resubmit_res.status_code == 409


def test_join_code_is_never_returned():
    setup_organization("org-alpha", "Alpha Org", "alphaSecret123")
    _, user_token = setup_user()
    response = client.post(
        "/auth/organizations/join",
        json={"org_id": "org-alpha", "join_code": "alphaSecret123"},
        headers={"Authorization": f"Bearer {user_token}"},
    )
    dumped = response.json()
    assert "join_code" not in dumped
    assert "join_code_hash" not in dumped


def test_join_code_hash_is_never_returned():
    setup_organization("org-alpha", "Alpha Org", "alphaSecret123")
    _, user_token = setup_user()
    response = client.post(
        "/auth/organizations/join",
        json={"org_id": "org-alpha", "join_code": "alphaSecret123"},
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert "join_code_hash" not in response.json()


# ==========================================
# C. Request Listing Tests (17-23)
# ==========================================

def test_system_admin_sees_global_requests():
    org_a = setup_organization("org-a", "Org A", "secret123")
    org_b = setup_organization("org-b", "Org B", "secret123")
    _, sys_token = setup_system_admin()
    _, user1_token = setup_user("user1@test.com", "User 1")
    _, user2_token = setup_user("user2@test.com", "User 2")

    client.post("/auth/organizations/join", json={"org_id": "org-a", "join_code": "secret123"}, headers={"Authorization": f"Bearer {user1_token}"})
    client.post("/auth/organizations/join", json={"org_id": "org-b", "join_code": "secret123"}, headers={"Authorization": f"Bearer {user2_token}"})

    response = client.get("/admin/requests?status=PENDING", headers={"Authorization": f"Bearer {sys_token}"})
    assert response.status_code == 200
    assert len(response.json()) == 2


def test_org_admin_sees_only_own_organization_requests():
    org_a = setup_organization("org-a", "Org A", "secret123")
    org_b = setup_organization("org-b", "Org B", "secret123")
    _, org_a_token = setup_org_admin(org_a["id"], ORG_A_ADMIN_EMAIL)
    _, user1_token = setup_user("user1@test.com", "User 1")
    _, user2_token = setup_user("user2@test.com", "User 2")

    client.post("/auth/organizations/join", json={"org_id": "org-a", "join_code": "secret123"}, headers={"Authorization": f"Bearer {user1_token}"})
    client.post("/auth/organizations/join", json={"org_id": "org-b", "join_code": "secret123"}, headers={"Authorization": f"Bearer {user2_token}"})

    response = client.get("/admin/requests?status=PENDING", headers={"Authorization": f"Bearer {org_a_token}"})
    assert response.status_code == 200
    items = response.json()
    assert len(items) == 1
    assert items[0]["organization_id"] == org_a["id"]


def test_org_admin_cannot_access_another_organization_requests():
    org_a = setup_organization("org-a", "Org A", "secret123")
    org_b = setup_organization("org-b", "Org B", "secret123")
    _, org_a_token = setup_org_admin(org_a["id"], ORG_A_ADMIN_EMAIL)
    _, user2_token = setup_user("user2@test.com", "User 2")

    client.post("/auth/organizations/join", json={"org_id": "org-b", "join_code": "secret123"}, headers={"Authorization": f"Bearer {user2_token}"})

    # Org A admin queries requests
    response = client.get("/admin/requests?status=PENDING", headers={"Authorization": f"Bearer {org_a_token}"})
    assert response.status_code == 200
    assert len(response.json()) == 0


def test_pending_filtering():
    org = setup_organization("org-filter", "Filter Org", "secret123")
    _, sys_token = setup_system_admin()
    _, user_token = setup_user()

    join_res = client.post("/auth/organizations/join", json={"org_id": "org-filter", "join_code": "secret123"}, headers={"Authorization": f"Bearer {user_token}"})
    req_id = join_res.json()["id"]

    res = client.get("/admin/requests?status=PENDING", headers={"Authorization": f"Bearer {sys_token}"})
    assert len(res.json()) == 1
    assert res.json()[0]["id"] == req_id


def test_approved_filtering():
    org = setup_organization("org-filter", "Filter Org", "secret123")
    _, sys_token = setup_system_admin()
    _, user_token = setup_user()

    join_res = client.post("/auth/organizations/join", json={"org_id": "org-filter", "join_code": "secret123"}, headers={"Authorization": f"Bearer {user_token}"})
    req_id = join_res.json()["id"]
    client.post(f"/admin/requests/{req_id}/approve", headers={"Authorization": f"Bearer {sys_token}"})

    res = client.get("/admin/requests?status=APPROVED", headers={"Authorization": f"Bearer {sys_token}"})
    assert len(res.json()) == 1
    assert res.json()[0]["status"] == "APPROVED"


def test_rejected_filtering():
    org = setup_organization("org-filter", "Filter Org", "secret123")
    _, sys_token = setup_system_admin()
    _, user_token = setup_user()

    join_res = client.post("/auth/organizations/join", json={"org_id": "org-filter", "join_code": "secret123"}, headers={"Authorization": f"Bearer {user_token}"})
    req_id = join_res.json()["id"]
    client.post(f"/admin/requests/{req_id}/reject", headers={"Authorization": f"Bearer {sys_token}"})

    res = client.get("/admin/requests?status=REJECTED", headers={"Authorization": f"Bearer {sys_token}"})
    assert len(res.json()) == 1
    assert res.json()[0]["status"] == "REJECTED"


def test_all_filtering():
    org = setup_organization("org-filter", "Filter Org", "secret123")
    _, sys_token = setup_system_admin()
    _, user1_token = setup_user("user1@test.com", "User 1")
    _, user2_token = setup_user("user2@test.com", "User 2")

    join1 = client.post("/auth/organizations/join", json={"org_id": "org-filter", "join_code": "secret123"}, headers={"Authorization": f"Bearer {user1_token}"})
    join2 = client.post("/auth/organizations/join", json={"org_id": "org-filter", "join_code": "secret123"}, headers={"Authorization": f"Bearer {user2_token}"})

    client.post(f"/admin/requests/{join1.json()['id']}/approve", headers={"Authorization": f"Bearer {sys_token}"})

    res = client.get("/admin/requests?status=ALL", headers={"Authorization": f"Bearer {sys_token}"})
    assert len(res.json()) == 2


# ==========================================
# D. Approval/Rejection Tests (24-31)
# ==========================================

def test_approve_pending_request():
    org = setup_organization("org-approve", "Approve Org", "secret123")
    _, sys_token = setup_system_admin()
    _, user_token = setup_user()

    join_res = client.post("/auth/organizations/join", json={"org_id": "org-approve", "join_code": "secret123"}, headers={"Authorization": f"Bearer {user_token}"})
    req_id = join_res.json()["id"]

    response = client.post(f"/admin/requests/{req_id}/approve", headers={"Authorization": f"Bearer {sys_token}"})
    assert response.status_code == 200
    assert response.json()["status"] == "APPROVED"
    assert response.json()["reviewed_by"] is not None


def test_approval_creates_membership():
    org = setup_organization("org-approve", "Approve Org", "secret123")
    _, sys_token = setup_system_admin()
    user, user_token = setup_user()

    join_res = client.post("/auth/organizations/join", json={"org_id": "org-approve", "join_code": "secret123"}, headers={"Authorization": f"Bearer {user_token}"})
    req_id = join_res.json()["id"]

    client.post(f"/admin/requests/{req_id}/approve", headers={"Authorization": f"Bearer {sys_token}"})

    membership = OrganizationMembershipService.find_membership(user["id"], org["id"])
    assert membership is not None
    assert membership["role"] == "member"


def test_reject_pending_request():
    org = setup_organization("org-reject", "Reject Org", "secret123")
    _, sys_token = setup_system_admin()
    _, user_token = setup_user()

    join_res = client.post("/auth/organizations/join", json={"org_id": "org-reject", "join_code": "secret123"}, headers={"Authorization": f"Bearer {user_token}"})
    req_id = join_res.json()["id"]

    response = client.post(f"/admin/requests/{req_id}/reject", headers={"Authorization": f"Bearer {sys_token}"})
    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"


def test_rejection_does_not_create_membership():
    org = setup_organization("org-reject", "Reject Org", "secret123")
    _, sys_token = setup_system_admin()
    user, user_token = setup_user()

    join_res = client.post("/auth/organizations/join", json={"org_id": "org-reject", "join_code": "secret123"}, headers={"Authorization": f"Bearer {user_token}"})
    req_id = join_res.json()["id"]

    client.post(f"/admin/requests/{req_id}/reject", headers={"Authorization": f"Bearer {sys_token}"})

    membership = OrganizationMembershipService.find_membership(user["id"], org["id"])
    assert membership is None


def test_approved_request_cannot_be_rejected():
    org = setup_organization("org-state", "State Org", "secret123")
    _, sys_token = setup_system_admin()
    _, user_token = setup_user()

    join_res = client.post("/auth/organizations/join", json={"org_id": "org-state", "join_code": "secret123"}, headers={"Authorization": f"Bearer {user_token}"})
    req_id = join_res.json()["id"]

    client.post(f"/admin/requests/{req_id}/approve", headers={"Authorization": f"Bearer {sys_token}"})

    # Attempt to reject an already approved request
    response = client.post(f"/admin/requests/{req_id}/reject", headers={"Authorization": f"Bearer {sys_token}"})
    assert response.status_code == 400
    assert "Only pending requests can be reviewed" in response.json()["detail"]


def test_rejected_request_cannot_be_approved():
    org = setup_organization("org-state", "State Org", "secret123")
    _, sys_token = setup_system_admin()
    _, user_token = setup_user()

    join_res = client.post("/auth/organizations/join", json={"org_id": "org-state", "join_code": "secret123"}, headers={"Authorization": f"Bearer {user_token}"})
    req_id = join_res.json()["id"]

    client.post(f"/admin/requests/{req_id}/reject", headers={"Authorization": f"Bearer {sys_token}"})

    # Attempt to approve an already rejected request
    response = client.post(f"/admin/requests/{req_id}/approve", headers={"Authorization": f"Bearer {sys_token}"})
    assert response.status_code == 400
    assert "Only pending requests can be reviewed" in response.json()["detail"]


def test_nonexistent_request_returns_404():
    _, sys_token = setup_system_admin()
    fake_id = str(ObjectId())
    response = client.post(f"/admin/requests/{fake_id}/approve", headers={"Authorization": f"Bearer {sys_token}"})
    assert response.status_code == 404


def test_malformed_request_object_id_handled_safely():
    _, sys_token = setup_system_admin()
    response = client.post("/admin/requests/not-an-id/approve", headers={"Authorization": f"Bearer {sys_token}"})
    assert response.status_code == 400
    assert "Invalid request ID format" in response.json()["detail"]


# ==========================================
# E. Tenant Isolation Tests (32-36)
# ==========================================

def test_org_a_admin_cannot_approve_org_b_request():
    org_a = setup_organization("org-a", "Org A", "secret123")
    org_b = setup_organization("org-b", "Org B", "secret123")
    _, org_a_token = setup_org_admin(org_a["id"], ORG_A_ADMIN_EMAIL)
    _, user_token = setup_user()

    # User requests Org B
    join_res = client.post("/auth/organizations/join", json={"org_id": "org-b", "join_code": "secret123"}, headers={"Authorization": f"Bearer {user_token}"})
    req_b_id = join_res.json()["id"]

    # Org A admin attempts to approve Org B request
    response = client.post(f"/admin/requests/{req_b_id}/approve", headers={"Authorization": f"Bearer {org_a_token}"})
    assert response.status_code == 403
    assert "Access denied for this organization" in response.json()["detail"]


def test_org_a_admin_cannot_reject_org_b_request():
    org_a = setup_organization("org-a", "Org A", "secret123")
    org_b = setup_organization("org-b", "Org B", "secret123")
    _, org_a_token = setup_org_admin(org_a["id"], ORG_A_ADMIN_EMAIL)
    _, user_token = setup_user()

    # User requests Org B
    join_res = client.post("/auth/organizations/join", json={"org_id": "org-b", "join_code": "secret123"}, headers={"Authorization": f"Bearer {user_token}"})
    req_b_id = join_res.json()["id"]

    # Org A admin attempts to reject Org B request
    response = client.post(f"/admin/requests/{req_b_id}/reject", headers={"Authorization": f"Bearer {org_a_token}"})
    assert response.status_code == 403
    assert "Access denied for this organization" in response.json()["detail"]


def test_org_a_admin_cannot_list_org_b_members():
    org_a = setup_organization("org-a", "Org A", "secret123")
    org_b = setup_organization("org-b", "Org B", "secret123")
    _, org_a_token = setup_org_admin(org_a["id"], ORG_A_ADMIN_EMAIL)

    response = client.get(f"/admin/organizations/{org_b['id']}/members", headers={"Authorization": f"Bearer {org_a_token}"})
    assert response.status_code == 403
    assert "Access denied for this organization" in response.json()["detail"]


def test_client_supplied_organization_id_cannot_bypass_admin_scope():
    org_a = setup_organization("org-a", "Org A", "secret123")
    org_b = setup_organization("org-b", "Org B", "secret123")
    _, org_a_token = setup_org_admin(org_a["id"], ORG_A_ADMIN_EMAIL)
    _, user_token = setup_user()

    # Create request in Org B
    client.post("/auth/organizations/join", json={"org_id": "org-b", "join_code": "secret123"}, headers={"Authorization": f"Bearer {user_token}"})

    # Org A admin supplies query parameter ?organization_id=<org_b_id>
    response = client.get(f"/admin/requests?organization_id={org_b['id']}", headers={"Authorization": f"Bearer {org_a_token}"})
    assert response.status_code == 200
    assert len(response.json()) == 0


def test_system_admin_can_access_both_organizations():
    org_a = setup_organization("org-a", "Org A", "secret123")
    org_b = setup_organization("org-b", "Org B", "secret123")
    _, sys_token = setup_system_admin()
    user1, _ = setup_user("user1@test.com", "User 1")
    user2, _ = setup_user("user2@test.com", "User 2")

    OrganizationMembershipService.create_membership(user1["id"], org_a["id"])
    OrganizationMembershipService.create_membership(user2["id"], org_b["id"])

    res_a = client.get(f"/admin/organizations/{org_a['id']}/members", headers={"Authorization": f"Bearer {sys_token}"})
    res_b = client.get(f"/admin/organizations/{org_b['id']}/members", headers={"Authorization": f"Bearer {sys_token}"})

    assert res_a.status_code == 200
    assert len(res_a.json()) == 1
    assert res_b.status_code == 200
    assert len(res_b.json()) == 1


# ==========================================
# F. Member Listing Tests (37-41)
# ==========================================

def test_organization_member_list_works():
    org = setup_organization("org-mem", "Member Org", "secret123")
    _, sys_token = setup_system_admin()
    user, _ = setup_user()
    OrganizationMembershipService.create_membership(user["id"], org["id"])

    response = client.get(f"/admin/organizations/{org['id']}/members", headers={"Authorization": f"Bearer {sys_token}"})
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["user_id"] == user["id"]
    assert data[0]["name"] == user["name"]
    assert data[0]["email"] == user["email"]


def test_member_list_contains_only_safe_user_fields():
    org = setup_organization("org-mem", "Member Org", "secret123")
    _, sys_token = setup_system_admin()
    user, _ = setup_user()
    OrganizationMembershipService.create_membership(user["id"], org["id"])

    response = client.get(f"/admin/organizations/{org['id']}/members", headers={"Authorization": f"Bearer {sys_token}"})
    item = response.json()[0]
    expected_keys = {"membership_id", "user_id", "name", "email", "role", "created_at"}
    assert set(item.keys()) == expected_keys


def test_password_hash_never_appears_in_members():
    org = setup_organization("org-mem", "Member Org", "secret123")
    _, sys_token = setup_system_admin()
    user, _ = setup_user()
    OrganizationMembershipService.create_membership(user["id"], org["id"])

    response = client.get(f"/admin/organizations/{org['id']}/members", headers={"Authorization": f"Bearer {sys_token}"})
    assert "password_hash" not in str(response.json())
    assert "password" not in str(response.json())


def test_otp_fields_never_appear_in_members():
    org = setup_organization("org-mem", "Member Org", "secret123")
    _, sys_token = setup_system_admin()
    user, _ = setup_user()
    OrganizationMembershipService.create_membership(user["id"], org["id"])

    response = client.get(f"/admin/organizations/{org['id']}/members", headers={"Authorization": f"Bearer {sys_token}"})
    assert "otp" not in str(response.json()).lower()


def test_token_session_fields_never_appear_in_members():
    org = setup_organization("org-mem", "Member Org", "secret123")
    _, sys_token = setup_system_admin()
    user, _ = setup_user()
    OrganizationMembershipService.create_membership(user["id"], org["id"])

    response = client.get(f"/admin/organizations/{org['id']}/members", headers={"Authorization": f"Bearer {sys_token}"})
    assert "token" not in str(response.json()).lower()
    assert "session" not in str(response.json()).lower()


# ==========================================
# G. User Status Tests (42-45)
# ==========================================

def test_user_can_view_own_memberships():
    org = setup_organization("org-stat", "Status Org", "secret123")
    user, user_token = setup_user()
    OrganizationMembershipService.create_membership(user["id"], org["id"])

    response = client.get("/auth/organizations/status", headers={"Authorization": f"Bearer {user_token}"})
    assert response.status_code == 200
    data = response.json()
    assert len(data["memberships"]) == 1
    assert data["memberships"][0]["organization_id"] == org["id"]
    assert data["memberships"][0]["organization_name"] == "Status Org"


def test_user_can_view_own_requests():
    setup_organization("org-stat", "Status Org", "secret123")
    _, user_token = setup_user()
    client.post("/auth/organizations/join", json={"org_id": "org-stat", "join_code": "secret123"}, headers={"Authorization": f"Bearer {user_token}"})

    response = client.get("/auth/organizations/status", headers={"Authorization": f"Bearer {user_token}"})
    assert response.status_code == 200
    data = response.json()
    assert len(data["requests"]) == 1
    assert data["requests"][0]["org_id"] == "org-stat"
    assert data["requests"][0]["status"] == "PENDING"


def test_user_cannot_view_another_user_organization_status():
    org = setup_organization("org-stat", "Status Org", "secret123")
    user1, user1_token = setup_user("user1@test.com", "User 1")
    user2, user2_token = setup_user("user2@test.com", "User 2")

    OrganizationMembershipService.create_membership(user1["id"], org["id"])

    # User 2 checks status
    response = client.get("/auth/organizations/status", headers={"Authorization": f"Bearer {user2_token}"})
    assert response.status_code == 200
    data = response.json()
    assert len(data["memberships"]) == 0
    assert len(data["requests"]) == 0


def test_status_response_excludes_sensitive_organization_fields():
    org = setup_organization("org-stat", "Status Org", "secret123")
    user, user_token = setup_user()
    OrganizationMembershipService.create_membership(user["id"], org["id"])
    client.post("/auth/organizations/join", json={"org_id": "org-stat", "join_code": "secret123"}, headers={"Authorization": f"Bearer {user_token}"})

    response = client.get("/auth/organizations/status", headers={"Authorization": f"Bearer {user_token}"})
    raw_str = str(response.json())
    assert "join_code_hash" not in raw_str
    assert "join_code" not in raw_str
    assert "password" not in raw_str


# ==========================================
# H. Authentication Boundary Tests (46-49)
# ==========================================

def test_normal_user_jwt_rejected_by_admin_endpoints():
    _, user_token = setup_user()
    res1 = client.get("/admin/organizations", headers={"Authorization": f"Bearer {user_token}"})
    res2 = client.get("/admin/requests", headers={"Authorization": f"Bearer {user_token}"})
    assert res1.status_code == 401
    assert res2.status_code == 401


def test_admin_jwt_rejected_by_normal_user_organization_endpoints():
    _, sys_token = setup_system_admin()
    res1 = client.post("/auth/organizations/join", json={"org_id": "some-org", "join_code": "code123"}, headers={"Authorization": f"Bearer {sys_token}"})
    res2 = client.get("/auth/organizations/status", headers={"Authorization": f"Bearer {sys_token}"})
    assert res1.status_code == 401
    assert res2.status_code == 401


def test_inactive_admin_rejected_on_organization_routes():
    admin, token = setup_system_admin()
    db.get_db()["admin_users"].update_one({"_id": ObjectId(admin["id"])}, {"$set": {"is_active": False}})

    response = client.get("/admin/organizations", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_org_admin_cannot_perform_system_admin_only_organization_creation():
    org = setup_organization("org-a", "Org A", "secret123")
    _, org_admin_token = setup_org_admin(org["id"])

    response = client.post(
        "/admin/organizations",
        json={"org_id": "org-new", "name": "New Org", "join_code": "secret123"},
        headers={"Authorization": f"Bearer {org_admin_token}"},
    )
    assert response.status_code == 403
    assert "System administrator access required" in response.json()["detail"]
