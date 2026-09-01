from __future__ import annotations

import logging
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import assert_admin_organization_access, require_org_admin, require_system_admin
from app.schemas.organization import (
    OrganizationCreate,
    OrganizationMemberDetailResponse,
    OrganizationResponse,
)
from app.services.organization_membership_service import OrganizationMembershipService
from app.services.organization_service import OrganizationService

router = APIRouter(prefix="/admin/organizations", tags=["admin-organizations"])
logger = logging.getLogger(__name__)


@router.post("", response_model=OrganizationResponse)
def create_organization(
    payload: OrganizationCreate,
    current_admin: dict = Depends(require_system_admin),
):
    org = OrganizationService.create_organization(
        org_id=payload.org_id,
        name=payload.name,
        join_code=payload.join_code,
    )
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
