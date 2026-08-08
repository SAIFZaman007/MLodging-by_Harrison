import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import require_staff_or_admin
from app.core.limiter import limiter
from app.models.inquiry import Inquiry
from app.models.user import User
from app.schemas.inquiry import InquiryCreate, InquiryOut, InquiryStatusUpdate

router = APIRouter(prefix="/inquiries", tags=["inquiries"])


@router.post("", response_model=InquiryOut, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def submit_inquiry(request: Request, payload: InquiryCreate, db: AsyncSession = Depends(get_db)) -> Inquiry:
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
) -> list[Inquiry]:
    result = await db.execute(select(Inquiry).order_by(Inquiry.created_at.desc()))
    return list(result.scalars().all())


@router.patch("/{inquiry_id}", response_model=InquiryOut)
async def update_inquiry_status(
    inquiry_id: uuid.UUID,
    payload: InquiryStatusUpdate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_staff_or_admin),
) -> Inquiry:
    result = await db.execute(select(Inquiry).where(Inquiry.id == inquiry_id))
    inquiry = result.scalar_one_or_none()
    if inquiry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Inquiry not found")
    inquiry.status = payload.status
    await db.commit()
    await db.refresh(inquiry)
    return inquiry
