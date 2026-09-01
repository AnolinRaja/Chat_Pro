from __future__ import annotations

import logging
from typing import Literal
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.dependencies import assert_admin_organization_access, require_org_admin
from app.schemas.organization import OrganizationRegistrationRequestResponse
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
    return OrganizationRegistrationRequestResponse(**updated)


@router.post("/{request_id}/reject", response_model=OrganizationRegistrationRequestResponse)
def reject_request(
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
    return OrganizationRegistrationRequestResponse(**updated)
