from __future__ import annotations

import pytest
from datetime import datetime, timezone
from bson import ObjectId
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.db import db
from app.main import app
from app.schemas.organization import OrganizationResponse
from app.services.organization_service import OrganizationService
from app.services.organization_membership_service import OrganizationMembershipService
from app.services.organization_request_service import OrganizationRequestService

client = TestClient(app)

TEST_ORG_ID = "pec2026"
TEST_ORG_NAME = "Panimalar Engineering College"
TEST_JOIN_CODE = "pecsecret123"


@pytest.fixture(autouse=True)
def cleanup_org_data():
    # Clean up collections before test
    db.get_db()["organizations"].drop()
    db.get_db()["organization_memberships"].drop()
    db.get_db()["organization_registration_requests"].drop()
    db.get_db()["users"].delete_many({"email": {"$in": ["orguser1@example.com", "orguser2@example.com"]}})
    db.ensure_indexes()
    
    yield
    
    # Clean up collections after test
    db.get_db()["organizations"].drop()
    db.get_db()["organization_memberships"].drop()
    db.get_db()["organization_registration_requests"].drop()
    db.get_db()["users"].delete_many({"email": {"$in": ["orguser1@example.com", "orguser2@example.com"]}})
    db.ensure_indexes()


def create_test_user(email: str = "orguser1@example.com") -> str:
    db.get_db()["users"].insert_one({
        "name": "Org User",
        "email": email,
        "password_hash": "dummy_password_hash",
        "created_at": datetime.now(timezone.utc),
    })
    user = db.get_db()["users"].find_one({"email": email})
    return str(user["_id"])


# --- Organizations Tests ---

def test_organization_creation():
    org = OrganizationService.create_organization(TEST_ORG_ID, TEST_ORG_NAME, TEST_JOIN_CODE)
    assert org["org_id"] == TEST_ORG_ID
    assert org["name"] == TEST_ORG_NAME
    assert org["is_active"] is True
    assert isinstance(org["created_at"], datetime)
    assert isinstance(org["updated_at"], datetime)


def test_duplicate_org_id_prevention():
    OrganizationService.create_organization(TEST_ORG_ID, TEST_ORG_NAME, TEST_JOIN_CODE)
    with pytest.raises(HTTPException) as exc_info:
        OrganizationService.create_organization(TEST_ORG_ID, "Another Name", "anothercode")
    assert exc_info.value.status_code == 409
    assert "Organization ID already exists" in exc_info.value.detail


def test_organization_lookup():
    created = OrganizationService.create_organization(TEST_ORG_ID, TEST_ORG_NAME, TEST_JOIN_CODE)
    found = OrganizationService.find_organization_by_org_id(TEST_ORG_ID)
    assert found is not None
    assert found["id"] == created["id"]
    assert found["org_id"] == TEST_ORG_ID
    
    # Non-existent lookup
    assert OrganizationService.find_organization_by_org_id("nonexistent") is None


def test_default_is_active_true():
    org = OrganizationService.create_organization(TEST_ORG_ID, TEST_ORG_NAME, TEST_JOIN_CODE)
    raw = db.get_db()["organizations"].find_one({"org_id": TEST_ORG_ID})
    assert raw is not None
    assert raw.get("is_active") is True


def test_join_code_is_never_stored_in_plaintext():
    OrganizationService.create_organization(TEST_ORG_ID, TEST_ORG_NAME, TEST_JOIN_CODE)
    raw = db.get_db()["organizations"].find_one({"org_id": TEST_ORG_ID})
    assert raw is not None
    assert "join_code" not in raw
    assert raw["join_code_hash"] != TEST_JOIN_CODE
    # Verify it looks like a bcrypt hash (starts with $2b$ or $2a$)
    assert raw["join_code_hash"].startswith(("$2b$", "$2a$"))


def test_correct_join_code_verification():
    org = OrganizationService.create_organization(TEST_ORG_ID, TEST_ORG_NAME, TEST_JOIN_CODE)
    assert OrganizationService.verify_join_code(TEST_JOIN_CODE, org["join_code_hash"]) is True


def test_incorrect_join_code_rejection():
    org = OrganizationService.create_organization(TEST_ORG_ID, TEST_ORG_NAME, TEST_JOIN_CODE)
    assert OrganizationService.verify_join_code("wrongcode123", org["join_code_hash"]) is False


def test_public_schema_does_not_expose_join_code_hash():
    org = OrganizationService.create_organization(TEST_ORG_ID, TEST_ORG_NAME, TEST_JOIN_CODE)
    response_obj = OrganizationResponse(**org)
    serialized = response_obj.model_dump()
    assert "join_code_hash" not in serialized


# --- Memberships Tests ---

def test_membership_creation():
    user_id = create_test_user()
    org = OrganizationService.create_organization(TEST_ORG_ID, TEST_ORG_NAME, TEST_JOIN_CODE)
    
    membership = OrganizationMembershipService.create_membership(user_id, org["id"], "member")
    assert membership["user_id"] == user_id
    assert membership["organization_id"] == org["id"]
    assert membership["role"] == "member"
    assert isinstance(membership["created_at"], datetime)


def test_duplicate_user_org_membership_prevention():
    user_id = create_test_user()
    org = OrganizationService.create_organization(TEST_ORG_ID, TEST_ORG_NAME, TEST_JOIN_CODE)
    
    OrganizationMembershipService.create_membership(user_id, org["id"], "member")
    with pytest.raises(HTTPException) as exc_info:
        OrganizationMembershipService.create_membership(user_id, org["id"], "org_admin")
    assert exc_info.value.status_code == 409
    assert "already a member" in exc_info.value.detail


def test_membership_lookup():
    user_id = create_test_user()
    org = OrganizationService.create_organization(TEST_ORG_ID, TEST_ORG_NAME, TEST_JOIN_CODE)
    
    membership = OrganizationMembershipService.create_membership(user_id, org["id"], "member")
    found = OrganizationMembershipService.find_membership(user_id, org["id"])
    assert found is not None
    assert found["id"] == membership["id"]
    
    assert OrganizationMembershipService.check_membership(user_id, org["id"]) is True


def test_organization_membership_isolation():
    user_id_1 = create_test_user("orguser1@example.com")
    user_id_2 = create_test_user("orguser2@example.com")
    org = OrganizationService.create_organization(TEST_ORG_ID, TEST_ORG_NAME, TEST_JOIN_CODE)
    
    OrganizationMembershipService.create_membership(user_id_1, org["id"], "member")
    
    assert OrganizationMembershipService.check_membership(user_id_1, org["id"]) is True
    assert OrganizationMembershipService.check_membership(user_id_2, org["id"]) is False
    assert OrganizationMembershipService.find_membership(user_id_2, org["id"]) is None


# --- Requests Tests ---

def test_request_creation():
    user_id = create_test_user()
    org = OrganizationService.create_organization(TEST_ORG_ID, TEST_ORG_NAME, TEST_JOIN_CODE)
    
    req = OrganizationRequestService.create_request(user_id, org["id"])
    assert req["user_id"] == user_id
    assert req["organization_id"] == org["id"]
    assert req["status"] == "PENDING"
    assert req["reviewed_by"] is None
    assert req["reviewed_at"] is None
    assert isinstance(req["created_at"], datetime)
    assert isinstance(req["updated_at"], datetime)


def test_duplicate_pending_request_prevention():
    user_id = create_test_user()
    org = OrganizationService.create_organization(TEST_ORG_ID, TEST_ORG_NAME, TEST_JOIN_CODE)
    
    OrganizationRequestService.create_request(user_id, org["id"])
    with pytest.raises(HTTPException) as exc_info:
        OrganizationRequestService.create_request(user_id, org["id"])
    assert exc_info.value.status_code == 400
    assert "pending registration request already exists" in exc_info.value.detail


def test_request_status_values():
    user_id = create_test_user()
    org = OrganizationService.create_organization(TEST_ORG_ID, TEST_ORG_NAME, TEST_JOIN_CODE)
    
    req = OrganizationRequestService.create_request(user_id, org["id"])
    
    # Try updating status to invalid value
    with pytest.raises(HTTPException) as exc_info:
        OrganizationRequestService.update_request_status(req["id"], "INVALID_STATUS")
    assert exc_info.value.status_code == 400
    assert "Invalid request status" in exc_info.value.detail


def test_rejected_request_can_be_reset():
    user_id = create_test_user()
    org = OrganizationService.create_organization(TEST_ORG_ID, TEST_ORG_NAME, TEST_JOIN_CODE)
    
    req = OrganizationRequestService.create_request(user_id, org["id"])
    
    # Reject the request
    rejected = OrganizationRequestService.update_request_status(req["id"], "REJECTED", reviewed_by=str(ObjectId()))
    assert rejected["status"] == "REJECTED"
    assert rejected["reviewed_by"] is not None
    
    # Resubmitting should reset it to PENDING and clear reviewed fields
    resubmitted = OrganizationRequestService.create_request(user_id, org["id"])
    assert resubmitted["id"] == req["id"]
    assert resubmitted["status"] == "PENDING"
    assert resubmitted["reviewed_by"] is None
    assert resubmitted["reviewed_at"] is None


def test_reviewed_metadata_handling():
    user_id = create_test_user()
    org = OrganizationService.create_organization(TEST_ORG_ID, TEST_ORG_NAME, TEST_JOIN_CODE)
    
    req = OrganizationRequestService.create_request(user_id, org["id"])
    reviewer_id = str(ObjectId())
    
    updated = OrganizationRequestService.update_request_status(req["id"], "REJECTED", reviewed_by=reviewer_id)
    assert updated["status"] == "REJECTED"
    assert updated["reviewed_by"] == reviewer_id
    assert isinstance(updated["reviewed_at"], datetime)


# --- Database Indexes Tests ---

def test_organization_unique_index_exists():
    indexes = db.get_db()["organizations"].list_indexes()
    unique_idx = next((idx for idx in indexes if idx["name"] == "organizations_org_id_unique_idx"), None)
    assert unique_idx is not None
    assert unique_idx["key"] == {"org_id": 1}
    assert unique_idx["unique"] is True


def test_membership_unique_compound_index_exists():
    indexes = db.get_db()["organization_memberships"].list_indexes()
    unique_idx = next((idx for idx in indexes if idx["name"] == "memberships_user_org_unique_idx"), None)
    assert unique_idx is not None
    assert unique_idx["key"] == {"user_id": 1, "organization_id": 1}
    assert unique_idx["unique"] is True


def test_membership_organization_index_exists():
    indexes = db.get_db()["organization_memberships"].list_indexes()
    idx = next((idx for idx in indexes if idx["name"] == "memberships_org_id_idx"), None)
    assert idx is not None
    assert idx["key"] == {"organization_id": 1}


def test_request_unique_compound_index_exists():
    indexes = db.get_db()["organization_registration_requests"].list_indexes()
    unique_idx = next((idx for idx in indexes if idx["name"] == "requests_user_org_unique_idx"), None)
    assert unique_idx is not None
    assert unique_idx["key"] == {"user_id": 1, "organization_id": 1}
    assert unique_idx["unique"] is True


def test_request_organization_status_index_exists():
    indexes = db.get_db()["organization_registration_requests"].list_indexes()
    idx = next((idx for idx in indexes if idx["name"] == "requests_org_status_idx"), None)
    assert idx is not None
    assert idx["key"] == {"organization_id": 1, "status": 1}


def test_ready_endpoint_reports_all_new_indexes():
    # Make sure indexes exist
    db.ensure_indexes()
    
    response = client.get("/ready")
    assert response.status_code == 200
    res_json = response.json()
    assert res_json["ready"] is True
    
    # Assert new collection indexes are present in the response
    indexes_info = res_json["indexes"]
    assert "organizations" in indexes_info
    assert "organizations_org_id_unique_idx" in indexes_info["organizations"]["present"]
    
    assert "organization_memberships" in indexes_info
    assert "memberships_user_org_unique_idx" in indexes_info["organization_memberships"]["present"]
    assert "memberships_org_id_idx" in indexes_info["organization_memberships"]["present"]
    
    assert "organization_registration_requests" in indexes_info
    assert "requests_user_org_unique_idx" in indexes_info["organization_registration_requests"]["present"]
    assert "requests_org_status_idx" in indexes_info["organization_registration_requests"]["present"]


def test_approved_request_cannot_be_changed_to_rejected():
    user_id = create_test_user()
    org = OrganizationService.create_organization(TEST_ORG_ID, TEST_ORG_NAME, TEST_JOIN_CODE)
    req = OrganizationRequestService.create_request(user_id, org["id"])
    
    # Approve first
    OrganizationRequestService.update_request_status(req["id"], "APPROVED", reviewed_by=str(ObjectId()))
    
    # Attempt to reject should fail
    with pytest.raises(HTTPException) as exc_info:
        OrganizationRequestService.update_request_status(req["id"], "REJECTED", reviewed_by=str(ObjectId()))
    assert exc_info.value.status_code == 400
    assert "Only pending requests can be reviewed" in exc_info.value.detail


def test_approved_request_cannot_be_reviewed_again():
    user_id = create_test_user()
    org = OrganizationService.create_organization(TEST_ORG_ID, TEST_ORG_NAME, TEST_JOIN_CODE)
    req = OrganizationRequestService.create_request(user_id, org["id"])
    
    # Approve first
    OrganizationRequestService.update_request_status(req["id"], "APPROVED", reviewed_by=str(ObjectId()))
    
    # Attempt to approve again should fail
    with pytest.raises(HTTPException) as exc_info:
        OrganizationRequestService.update_request_status(req["id"], "APPROVED", reviewed_by=str(ObjectId()))
    assert exc_info.value.status_code == 400
    assert "Only pending requests can be reviewed" in exc_info.value.detail


def test_rejected_request_cannot_be_changed_directly_to_approved():
    user_id = create_test_user()
    org = OrganizationService.create_organization(TEST_ORG_ID, TEST_ORG_NAME, TEST_JOIN_CODE)
    req = OrganizationRequestService.create_request(user_id, org["id"])
    
    # Reject first
    OrganizationRequestService.update_request_status(req["id"], "REJECTED", reviewed_by=str(ObjectId()))
    
    # Attempt to approve directly should fail
    with pytest.raises(HTTPException) as exc_info:
        OrganizationRequestService.update_request_status(req["id"], "APPROVED", reviewed_by=str(ObjectId()))
    assert exc_info.value.status_code == 400
    assert "Only pending requests can be reviewed" in exc_info.value.detail


def test_rejected_request_can_be_recycled_to_pending_via_create_request():
    user_id = create_test_user()
    org = OrganizationService.create_organization(TEST_ORG_ID, TEST_ORG_NAME, TEST_JOIN_CODE)
    req = OrganizationRequestService.create_request(user_id, org["id"])
    
    # Reject first
    OrganizationRequestService.update_request_status(req["id"], "REJECTED", reviewed_by=str(ObjectId()))
    
    # Recycle via create_request
    recycled = OrganizationRequestService.create_request(user_id, org["id"])
    assert recycled["id"] == req["id"]
    assert recycled["status"] == "PENDING"
    assert recycled["reviewed_by"] is None


def test_duplicate_key_race_condition_raises_409():
    user_id = create_test_user()
    org = OrganizationService.create_organization(TEST_ORG_ID, TEST_ORG_NAME, TEST_JOIN_CODE)
    
    # Insert a document manually to cause duplicate key on insert
    db.get_db()["organization_registration_requests"].insert_one({
        "user_id": ObjectId(user_id),
        "organization_id": ObjectId(org["id"]),
        "status": "PENDING",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    })
    
    # Mock find_one to return None so it proceeds to insert_one
    import unittest.mock as mock
    with mock.patch("pymongo.collection.Collection.find_one", return_value=None):
        with pytest.raises(HTTPException) as exc_info:
            OrganizationRequestService.create_request(user_id, org["id"])
        assert exc_info.value.status_code == 409
        assert "A registration request already exists" in exc_info.value.detail


def test_direct_service_call_with_invalid_org_id_is_rejected():
    with pytest.raises(HTTPException) as exc_info:
        OrganizationService.create_organization("invalid org name!", "Invalid Org", TEST_JOIN_CODE)
    assert exc_info.value.status_code == 400
    assert "Organization ID must be alphanumeric" in exc_info.value.detail


def test_valid_normalized_organization_ids_still_work():
    org = OrganizationService.create_organization("  PEC-2026_id  ", TEST_ORG_NAME, TEST_JOIN_CODE)
    assert org["org_id"] == "pec-2026_id"

