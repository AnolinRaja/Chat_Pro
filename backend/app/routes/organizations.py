from __future__ import annotations

import logging
from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.dependencies import get_current_user
from app.schemas.audit import AuditAction, AuditActorType, AuditEventType, AuditStatus
from app.schemas.organization import (
    OrganizationJoinRequest,
    OrganizationRegistrationRequestResponse,
    UserOrganizationMembershipStatus,
    UserOrganizationRequestStatus,
    UserOrganizationStatusResponse,
)
from app.services.audit_service import AuditService
from app.services.organization_membership_service import OrganizationMembershipService
from app.services.organization_request_service import OrganizationRequestService
from app.services.organization_service import OrganizationService

router = APIRouter(prefix="/auth/organizations", tags=["organizations"])
logger = logging.getLogger(__name__)


@router.post("/join", response_model=OrganizationRegistrationRequestResponse)
def join_organization(
    request: Request,
    payload: OrganizationJoinRequest,
    current_user: dict = Depends(get_current_user),
):
    ip_address, user_agent = AuditService.extract_request_context(request)
    org = OrganizationService.find_organization_by_org_id(payload.org_id)
    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found."
        )

    if not org.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Organization is inactive."
        )

    if not OrganizationService.verify_join_code(payload.join_code, org["join_code_hash"]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid join code."
        )

    if OrganizationMembershipService.check_membership(current_user["id"], org["id"]):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You are already a member of this organization."
        )

    req = OrganizationRequestService.create_request(current_user["id"], org["id"])

    AuditService.log_event(
        event_type=AuditEventType.ORGANIZATION_JOIN_REQUEST_SUBMITTED,
        actor_type=AuditActorType.USER,
        action=AuditAction.JOIN,
        status=AuditStatus.SUCCESS,
        actor_id=current_user["id"],
        actor_role="user",
        organization_id=org["id"],
        target_type="organization_registration_request",
        target_id=req["id"],
        metadata={"org_id": org["org_id"]},
        ip_address=ip_address,
        user_agent=user_agent,
    )

    return OrganizationRegistrationRequestResponse(**req)


@router.get("/status", response_model=UserOrganizationStatusResponse)
def get_user_organization_status(
    current_user: dict = Depends(get_current_user),
):
    memberships = OrganizationMembershipService.list_user_memberships(current_user["id"])
    requests = OrganizationRequestService.list_user_requests(current_user["id"])

    return {
        "memberships": [UserOrganizationMembershipStatus(**m) for m in memberships],
        "requests": [UserOrganizationRequestStatus(**r) for r in requests],
    }
