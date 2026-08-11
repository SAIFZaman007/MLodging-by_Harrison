"""
Inquiry (lead) management.

POST is public and rate-limited — it's the site's "Request availability" form.
Everything else requires an operator session.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import require_admin, require_staff_or_admin
from app.core.limiter import limiter
from app.models.enums import EventWeek, InquiryStatus
from app.models.inquiry import Inquiry
from app.models.user import User
from app.schemas.inquiry import InquiryCreate, InquiryOut, InquiryStatusUpdate, InquiryUpdate

router = APIRouter(prefix="/inquiries", tags=["inquiries"])


async def _get_or_404(db: AsyncSession, inquiry_id: uuid.UUID) -> Inquiry:
    result = await db.execute(select(Inquiry).where(Inquiry.id == inquiry_id))
    inquiry = result.scalar_one_or_none()
    if inquiry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Inquiry not found")
    return inquiry


@router.post("", response_model=InquiryOut, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def submit_inquiry(
    request: Request, payload: InquiryCreate, db: AsyncSession = Depends(get_db)
) -> Inquiry:
    inquiry = Inquiry(
        **payload.model_dump(),
        source_ip=request.client.host if request.client else None,
    )
    db.add(inquiry)
    await db.commit()
    await db.refresh(inquiry)
    # NOTE: wire a notification here (email/SMS/Slack webhook) so the operator
    # is alerted the moment a lead comes in — see README "Next steps".
    return inquiry


@router.get("", response_model=list[InquiryOut])
async def list_inquiries(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_staff_or_admin),
    q: str | None = Query(default=None, description="Search name, email or company"),
    inquiry_status: InquiryStatus | None = Query(default=None, alias="status"),
    event_week: EventWeek | None = Query(default=None),
    limit: int = Query(default=300, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> list[Inquiry]:
    stmt = select(Inquiry)

    if q:
        needle = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Inquiry.name.ilike(needle),
                Inquiry.email.ilike(needle),
                Inquiry.company.ilike(needle),
            )
        )
    if inquiry_status is not None:
        stmt = stmt.where(Inquiry.status == inquiry_status)
    if event_week is not None:
        stmt = stmt.where(Inquiry.event_week == event_week)

    stmt = stmt.order_by(Inquiry.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/{inquiry_id}", response_model=InquiryOut)
async def get_inquiry(
    inquiry_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_staff_or_admin),
) -> Inquiry:
    return await _get_or_404(db, inquiry_id)


@router.post("/manual", response_model=InquiryOut, status_code=status.HTTP_201_CREATED)
async def create_inquiry_manually(
    payload: InquiryCreate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_staff_or_admin),
) -> Inquiry:
    """Log a lead that arrived by phone or email. Bypasses the public form's
    rate limit because it's an authenticated operator action."""
    inquiry = Inquiry(**payload.model_dump(), source_ip="operator-entry")
    db.add(inquiry)
    await db.commit()
    await db.refresh(inquiry)
    return inquiry


@router.patch("/{inquiry_id}", response_model=InquiryOut)
async def update_inquiry_status(
    inquiry_id: uuid.UUID,
    payload: InquiryStatusUpdate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_staff_or_admin),
) -> Inquiry:
    """Status-only update — the fast path used by the inline dropdown."""
    inquiry = await _get_or_404(db, inquiry_id)
    inquiry.status = payload.status
    await db.commit()
    await db.refresh(inquiry)
    return inquiry


@router.put("/{inquiry_id}", response_model=InquiryOut)
async def update_inquiry(
    inquiry_id: uuid.UUID,
    payload: InquiryUpdate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_staff_or_admin),
) -> Inquiry:
    """Full edit — used by the lead detail drawer."""
    inquiry = await _get_or_404(db, inquiry_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(inquiry, field, value)
    await db.commit()
    await db.refresh(inquiry)
    return inquiry


@router.delete("/{inquiry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_inquiry(
    inquiry_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> None:
    """Admin-only. Archiving is the reversible option and should be preferred;
    this exists for genuine spam removal / GDPR erasure requests."""
    inquiry = await _get_or_404(db, inquiry_id)
    await db.delete(inquiry)
    await db.commit()