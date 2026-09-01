from __future__ import annotations

import logging
from datetime import datetime
from fastapi import APIRouter, Depends, Query

from app.dependencies import require_org_admin
from app.schemas.audit import AuditLogResponse
from app.services.audit_service import AuditService

router = APIRouter(prefix="/admin/audit", tags=["admin-audit"])
logger = logging.getLogger(__name__)


@router.get("", response_model=list[AuditLogResponse])
def get_audit_logs(
    organization_id: str | None = Query(None),
    actor_id: str | None = Query(None),
    event_type: str | None = Query(None),
    status: str | None = Query(None),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
    current_admin: dict = Depends(require_org_admin),
):
    # Strict tenant isolation: org_admin is forced to their own organization scope
    effective_org_id = organization_id
    if current_admin.get("role") == "org_admin":
        effective_org_id = current_admin.get("organization_id")

    logs = AuditService.list_events(
        organization_id=effective_org_id,
        actor_id=actor_id,
        event_type=event_type,
        status=status,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )
    return [AuditLogResponse(**log) for log in logs]
