#!/usr/bin/env python3
from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

# Ensure backend root directory is in sys.path
backend_root = Path(__file__).resolve().parent.parent
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))

from fastapi import HTTPException
from pydantic import ValidationError

from app.schemas.admin import AdminCreate
from app.services.admin_auth_service import AdminAuthService


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Provision an administrator account for ChatPRO."
    )
    parser.add_argument(
        "--email",
        type=str,
        help="Administrator email address.",
    )
    parser.add_argument(
        "--name",
        type=str,
        help="Administrator display name.",
    )
    parser.add_argument(
        "--role",
        type=str,
        choices=["system_admin", "org_admin"],
        help="Administrator role (system_admin or org_admin).",
    )
    parser.add_argument(
        "--org-id",
        type=str,
        dest="organization_id",
        help="Organization ObjectId (required for org_admin, prohibited for system_admin).",
    )
    return parser.parse_args(argv)


def get_interactive_input(prompt: str) -> str:
    try:
        return input(prompt).strip()
    except (KeyboardInterrupt, EOFError):
        print("\nOperation cancelled.", file=sys.stderr)
        sys.exit(1)


def get_secure_password() -> str:
    try:
        password = getpass.getpass("Enter admin password: ")
        if not password:
            print("Error: Password cannot be empty.", file=sys.stderr)
            sys.exit(1)
        if len(password) < 8:
            print("Error: Password must be at least 8 characters long.", file=sys.stderr)
            sys.exit(1)

        confirm = getpass.getpass("Confirm admin password: ")
        if password != confirm:
            print("Error: Passwords do not match.", file=sys.stderr)
            sys.exit(1)

        return password
    except (KeyboardInterrupt, EOFError):
        print("\nOperation cancelled.", file=sys.stderr)
        sys.exit(1)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    email = args.email
    if not email:
        email = get_interactive_input("Enter admin email: ")

    name = args.name
    if not name:
        name = get_interactive_input("Enter admin name: ")

    role = args.role
    if not role:
        role_input = get_interactive_input("Enter admin role [system_admin/org_admin] (default: system_admin): ")
        role = role_input.lower() if role_input else "system_admin"

    organization_id = args.organization_id
    if role == "system_admin":
        if organization_id:
            print("Error: System administrator must not be associated with an organization.", file=sys.stderr)
            return 1
        organization_id = None
    elif role == "org_admin":
        if not organization_id:
            organization_id = get_interactive_input("Enter organization ID (24-char hex ObjectId): ")

    password = get_secure_password()

    try:
        payload = AdminCreate(
            email=email,
            name=name,
            password=password,
            role=role,
            organization_id=organization_id,
        )
    except ValidationError as e:
        error_msgs = [err.get("msg", str(err)) for err in e.errors()]
        print(f"Validation error: {'; '.join(error_msgs)}", file=sys.stderr)
        return 1

    try:
        admin = AdminAuthService.create_admin(payload)
    except HTTPException as e:
        print(f"Error: {e.detail}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: Unexpected failure creating admin: {e}", file=sys.stderr)
        return 1

    print("\nAdmin account created successfully.")
    print(f"  ID:              {admin['id']}")
    print(f"  Email:           {admin['email']}")
    print(f"  Name:            {admin['name']}")
    print(f"  Role:            {admin['role']}")
    print(f"  Organization ID: {admin.get('organization_id') or 'None'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
