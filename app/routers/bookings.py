import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import require_staff_or_admin
from app.models.booking import Booking
from app.models.enums import BookingStatus
from app.models.property import Property
from app.models.user import User
from app.schemas.booking import (
    AvailabilityRequest,
    AvailabilityResponse,
    BlockedDateRange,
    BookingCreate,
    BookingOut,
)
from app.services.availability import find_conflicts, is_available
from app.services.calendar_sync import sync_property_calendars

router = APIRouter(prefix="/bookings", tags=["bookings"])


@router.post("/availability", response_model=AvailabilityResponse)
async def check_availability(payload: AvailabilityRequest, db: AsyncSession = Depends(get_db)) -> AvailabilityResponse:
    conflicts = await find_conflicts(db, payload.property_id, payload.check_in, payload.check_out)
    return AvailabilityResponse(
        available=len(conflicts) == 0,
        conflicting_ranges=[
            {"check_in": str(c.check_in), "check_out": str(c.check_out), "source": c.source.value}
            for c in conflicts
        ],
    )


@router.get("/calendar/{property_slug}", response_model=list[BlockedDateRange])
async def property_calendar(property_slug: str, db: AsyncSession = Depends(get_db)) -> list[Booking]:
    """Public, read-only blocked-date list for a property — powers the availability calendar UI.
    Deliberately omits guest PII (name/email/phone/notes)."""
    prop_result = await db.execute(select(Property).where(Property.slug == property_slug))
    prop = prop_result.scalar_one_or_none()
    if prop is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Property not found")

    result = await db.execute(
        select(Booking).where(
            Booking.property_id == prop.id,
            Booking.status != BookingStatus.CANCELLED,
        )
    )
    return list(result.scalars().all())


@router.post("", response_model=BookingOut, status_code=status.HTTP_201_CREATED)
async def create_booking(payload: BookingCreate, db: AsyncSession = Depends(get_db)) -> Booking:
    if not await is_available(db, payload.property_id, payload.check_in, payload.check_out):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="These dates are no longer available for this property",
        )

    booking = Booking(**payload.model_dump())
    db.add(booking)
    await db.commit()
    await db.refresh(booking)
    return booking


@router.post("/{property_id}/sync-calendar", status_code=status.HTTP_200_OK)
async def sync_calendar(
    property_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_staff_or_admin),
) -> dict:
    result = await db.execute(select(Property).where(Property.id == property_id))
    prop = result.scalar_one_or_none()
    if prop is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Property not found")
    if not prop.airbnb_ical_url and not prop.vrbo_ical_url:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No iCal URLs configured for this property")

    synced = await sync_property_calendars(db, prop)
    return {"ok": True, "synced": synced}


@router.get("", response_model=list[BookingOut])
async def list_bookings(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_staff_or_admin),
    limit: int = Query(default=200, ge=1, le=1000),
) -> list[Booking]:
    result = await db.execute(select(Booking).order_by(Booking.check_in.asc()).limit(limit))
    return list(result.scalars().all())
