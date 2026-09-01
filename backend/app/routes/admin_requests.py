from __future__ import annotations

import logging
from typing import Literal
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.dependencies import assert_admin_organization_access, require_org_admin
from app.schemas.audit import AuditAction, AuditActorType, AuditEventType, AuditStatus
from app.schemas.organization import OrganizationRegistrationRequestResponse
from app.services.audit_service import AuditService
from app.services.organization_request_service import OrganizationRequestService

router = APIRouter(prefix="/admin/requests", tags=["admin-requests"])
logger = logging.getLogger(__name__)


@router.get("", response_model=list[OrganizationRegistrationRequestResponse])
def list_admin_requests(
    status_filter: str = Query("PENDING", alias="status"),
    current_admin: dict = Depends(require_org_admin),
):
    if status_filter not in {"PENDING", "APPROVED", "REJECTED", "ALL"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid status filter. Must be PENDING, APPROVED, REJECTED, or ALL."
        )

    org_id_filter: str | None = None
    if current_admin.get("role") == "org_admin":
        org_id_filter = current_admin.get("organization_id")

    requests = OrganizationRequestService.list_requests(
        organization_id=org_id_filter,
        status=status_filter,
    )
    return [OrganizationRegistrationRequestResponse(**r) for r in requests]


@router.post("/{request_id}/approve", response_model=OrganizationRegistrationRequestResponse)
def approve_request(
    request: Request,
    request_id: str,
    current_admin: dict = Depends(require_org_admin),
):
    try:
        ObjectId(request_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid request ID format."
        )

    req = OrganizationRequestService.get_request_by_id(request_id)
    if not req:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Registration request not found."
        )

    assert_admin_organization_access(current_admin, req["organization_id"])

    updated = OrganizationRequestService.update_request_status(
        request_id=request_id,
        new_status="APPROVED",
        reviewed_by=current_admin["id"],
    )

    ip_address, user_agent = AuditService.extract_request_context(request)
    AuditService.log_event(
        event_type=AuditEventType.ORGANIZATION_JOIN_REQUEST_APPROVED,
        actor_type=AuditActorType.ADMIN,
        action=AuditAction.APPROVE,
        status=AuditStatus.SUCCESS,
        actor_id=current_admin["id"],
        actor_role=current_admin.get("role"),
        organization_id=req["organization_id"],
        target_type="organization_registration_request",
        target_id=request_id,
        metadata={"user_id": updated["user_id"]},
        ip_address=ip_address,
        user_agent=user_agent,
    )

    return OrganizationRegistrationRequestResponse(**updated)


@router.post("/{request_id}/reject", response_model=OrganizationRegistrationRequestResponse)
def reject_request(
    request: Request,
    request_id: str,
    current_admin: dict = Depends(require_org_admin),
):
    try:
        ObjectId(request_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid request ID format."
        )

    req = OrganizationRequestService.get_request_by_id(request_id)
    if not req:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Registration request not found."
        )

    assert_admin_organization_access(current_admin, req["organization_id"])

    updated = OrganizationRequestService.update_request_status(
        request_id=request_id,
        new_status="REJECTED",
        reviewed_by=current_admin["id"],
    )

    ip_address, user_agent = AuditService.extract_request_context(request)
    AuditService.log_event(
        event_type=AuditEventType.ORGANIZATION_JOIN_REQUEST_REJECTED,
        actor_type=AuditActorType.ADMIN,
        action=AuditAction.REJECT,
        status=AuditStatus.SUCCESS,
        actor_id=current_admin["id"],
        actor_role=current_admin.get("role"),
        organization_id=req["organization_id"],
        target_type="organization_registration_request",
        target_id=request_id,
        metadata={"user_id": updated["user_id"]},
        ip_address=ip_address,
        user_agent=user_agent,
    )

    return OrganizationRegistrationRequestResponse(**updated)
