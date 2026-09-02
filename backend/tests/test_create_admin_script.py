from __future__ import annotations

import sys
from unittest.mock import patch
import pytest
from bson import ObjectId

from app.db import db
from app.services.organization_service import OrganizationService
from scripts.create_admin import main, parse_args

TEST_SYSADMIN_EMAIL = "test_sysadmin_script@example.com"
TEST_ORGADMIN_EMAIL = "test_orgadmin_script@example.com"


@pytest.fixture(autouse=True)
def cleanup_test_admins():
    admin_collection = db.get_db()["admin_users"]
    org_collection = db.get_db()["organizations"]
    admin_collection.delete_many({"email": {"$in": [TEST_SYSADMIN_EMAIL, TEST_ORGADMIN_EMAIL]}})
    org_collection.delete_many({"org_id": "test-script-org"})
    yield
    admin_collection.delete_many({"email": {"$in": [TEST_SYSADMIN_EMAIL, TEST_ORGADMIN_EMAIL]}})
    org_collection.delete_many({"org_id": "test-script-org"})


def test_parse_args_does_not_accept_password_argument():
    with pytest.raises(SystemExit):
        parse_args(["--email", "test@test.com", "--password", "Secret123!"])


def test_parse_args_accepts_valid_arguments():
    args = parse_args([
        "--email", "admin@example.com",
        "--name", "Admin Name",
        "--role", "system_admin",
    ])
    assert args.email == "admin@example.com"
    assert args.name == "Admin Name"
    assert args.role == "system_admin"
    assert args.organization_id is None


def test_create_system_admin_success():
    argv = [
        "--email", TEST_SYSADMIN_EMAIL,
        "--name", "Script SysAdmin",
        "--role", "system_admin",
    ]

    with patch("scripts.create_admin.getpass.getpass", side_effect=["ValidPassword123!", "ValidPassword123!"]):
        exit_code = main(argv)

    assert exit_code == 0
    created = db.get_db()["admin_users"].find_one({"email": TEST_SYSADMIN_EMAIL})
    assert created is not None
    assert created["name"] == "Script SysAdmin"
    assert created["role"] == "system_admin"
    assert created["organization_id"] is None
    assert created["is_active"] is True
    assert created["password_hash"] != "ValidPassword123!"


def test_create_system_admin_rejects_organization_id(capsys):
    argv = [
        "--email", TEST_SYSADMIN_EMAIL,
        "--name", "Script SysAdmin",
        "--role", "system_admin",
        "--org-id", str(ObjectId()),
    ]

    exit_code = main(argv)
    assert exit_code == 1
    captured = capsys.readouterr()
    assert "System administrator must not be associated with an organization" in captured.err


def test_create_admin_mismatched_password(capsys):
    argv = [
        "--email", TEST_SYSADMIN_EMAIL,
        "--name", "Script SysAdmin",
        "--role", "system_admin",
    ]

    with patch("scripts.create_admin.getpass.getpass", side_effect=["ValidPassword123!", "DifferentPassword123!"]):
        with pytest.raises(SystemExit) as exc_info:
            main(argv)
        assert exc_info.value.code == 1

    captured = capsys.readouterr()
    assert "Passwords do not match" in captured.err


def test_create_admin_short_password(capsys):
    argv = [
        "--email", TEST_SYSADMIN_EMAIL,
        "--name", "Script SysAdmin",
        "--role", "system_admin",
    ]

    with patch("scripts.create_admin.getpass.getpass", side_effect=["short"]):
        with pytest.raises(SystemExit) as exc_info:
            main(argv)
        assert exc_info.value.code == 1

    captured = capsys.readouterr()
    assert "Password must be at least 8 characters long" in captured.err


def test_create_admin_invalid_email(capsys):
    argv = [
        "--email", "not-an-email",
        "--name", "Script SysAdmin",
        "--role", "system_admin",
    ]

    with patch("scripts.create_admin.getpass.getpass", side_effect=["ValidPassword123!", "ValidPassword123!"]):
        exit_code = main(argv)

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "Validation error" in captured.err


def test_create_admin_duplicate_email_handled_cleanly(capsys):
    argv = [
        "--email", TEST_SYSADMIN_EMAIL,
        "--name", "Script SysAdmin",
        "--role", "system_admin",
    ]

    with patch("scripts.create_admin.getpass.getpass", side_effect=["ValidPassword123!", "ValidPassword123!"]):
        first_code = main(argv)
    assert first_code == 0

    with patch("scripts.create_admin.getpass.getpass", side_effect=["ValidPassword123!", "ValidPassword123!"]):
        second_code = main(argv)
    assert second_code == 1

    captured = capsys.readouterr()
    assert "Error: Admin email already registered." in captured.err


def test_create_org_admin_success():
    org = OrganizationService.create_organization(
        org_id="test-script-org",
        name="Test Script Org",
        join_code="JoinCode123!",
    )
    org_id = org["id"]

    argv = [
        "--email", TEST_ORGADMIN_EMAIL,
        "--name", "Script OrgAdmin",
        "--role", "org_admin",
        "--org-id", org_id,
    ]

    with patch("scripts.create_admin.getpass.getpass", side_effect=["ValidPassword123!", "ValidPassword123!"]):
        exit_code = main(argv)

    assert exit_code == 0
    created = db.get_db()["admin_users"].find_one({"email": TEST_ORGADMIN_EMAIL})
    assert created is not None
    assert created["role"] == "org_admin"
    assert str(created["organization_id"]) == org_id

    # Clean up org
    db.get_db()["organizations"].delete_one({"_id": ObjectId(org_id)})


def test_create_org_admin_nonexistent_org(capsys):
    fake_org_id = str(ObjectId())
    argv = [
        "--email", TEST_ORGADMIN_EMAIL,
        "--name", "Script OrgAdmin",
        "--role", "org_admin",
        "--org-id", fake_org_id,
    ]

    with patch("scripts.create_admin.getpass.getpass", side_effect=["ValidPassword123!", "ValidPassword123!"]):
        exit_code = main(argv)

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "Organization not found." in captured.err


def test_interactive_fallback_prompts():
    inputs = iter([
        TEST_SYSADMIN_EMAIL,
        "Interactive Admin",
        "system_admin",
    ])

    with patch("scripts.create_admin.input", side_effect=lambda _: next(inputs)), \
         patch("scripts.create_admin.getpass.getpass", side_effect=["ValidPassword123!", "ValidPassword123!"]):
        exit_code = main([])

    assert exit_code == 0
    created = db.get_db()["admin_users"].find_one({"email": TEST_SYSADMIN_EMAIL})
    assert created is not None
    assert created["name"] == "Interactive Admin"
