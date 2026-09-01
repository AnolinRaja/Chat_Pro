from __future__ import annotations

import logging
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.dependencies import assert_admin_organization_access, require_org_admin, require_system_admin
from app.schemas.audit import AuditAction, AuditActorType, AuditEventType, AuditStatus
from app.schemas.organization import (
    OrganizationCreate,
    OrganizationMemberDetailResponse,
    OrganizationResponse,
)
from app.services.audit_service import AuditService
from app.services.organization_membership_service import OrganizationMembershipService
from app.services.organization_service import OrganizationService

router = APIRouter(prefix="/admin/organizations", tags=["admin-organizations"])
logger = logging.getLogger(__name__)


@router.post("", response_model=OrganizationResponse)
def create_organization(
    request: Request,
    payload: OrganizationCreate,
    current_admin: dict = Depends(require_system_admin),
):
    org = OrganizationService.create_organization(
        org_id=payload.org_id,
        name=payload.name,
        join_code=payload.join_code,
    )

    ip_address, user_agent = AuditService.extract_request_context(request)
    AuditService.log_event(
        event_type=AuditEventType.ORGANIZATION_CREATED,
        actor_type=AuditActorType.ADMIN,
        action=AuditAction.CREATE,
        status=AuditStatus.SUCCESS,
        actor_id=current_admin["id"],
        actor_role=current_admin.get("role", "system_admin"),
        organization_id=org["id"],
        target_type="organization",
        target_id=org["id"],
        metadata={"org_id": org["org_id"]},
        ip_address=ip_address,
        user_agent=user_agent,
    )

    try:
        from app.services.conversation_service import ConversationService
        ConversationService.create_organization_conversation(
            organization_id=org["id"],
            name="general",
            description="General discussion channel",
            created_by=None,
        )
    except Exception as e:
        logger.warning("Failed to auto-create default general channel for organization %s: %s", org["id"], e)

    return OrganizationResponse(**org)


@router.get("", response_model=list[OrganizationResponse])
def list_organizations(
    current_admin: dict = Depends(require_system_admin),
):
    orgs = OrganizationService.list_organizations()
    return [OrganizationResponse(**o) for o in orgs]


@router.get("/{organization_id}/members", response_model=list[OrganizationMemberDetailResponse])
def list_organization_members(
    organization_id: str,
    current_admin: dict = Depends(require_org_admin),
):
    try:
        ObjectId(organization_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid organization ID format."
        )

    org = OrganizationService.get_organization_by_id(organization_id)
    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found."
        )

    assert_admin_organization_access(current_admin, organization_id)

    members = OrganizationMembershipService.list_organization_members(organization_id)
    return [OrganizationMemberDetailResponse(**m) for m in members]
