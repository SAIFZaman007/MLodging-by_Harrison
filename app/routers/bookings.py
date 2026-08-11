"""
Booking management.

Every write path — public create, admin create, and admin edit — funnels
through the same overlap check in `app.services.availability`, so it is
structurally impossible to double-book a home by picking a different endpoint.
Edits pass `exclude_booking_id` so a booking never conflicts with itself.
"""
import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import require_staff_or_admin
from app.models.booking import Booking
from app.models.enums import BookingSource, BookingStatus
from app.models.property import Property
from app.models.user import User
from app.schemas.booking import (
    AvailabilityRequest,
    AvailabilityResponse,
    BlockedDateRange,
    BookingCreate,
    BookingOut,
    BookingUpdate,
)
from app.services.availability import find_conflicts, is_available
from app.services.calendar_sync import sync_property_calendars

router = APIRouter(prefix="/bookings", tags=["bookings"])


async def _get_or_404(db: AsyncSession, booking_id: uuid.UUID) -> Booking:
    result = await db.execute(select(Booking).where(Booking.id == booking_id))
    booking = result.scalar_one_or_none()
    if booking is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")
    return booking


async def _assert_property_exists(db: AsyncSession, property_id: uuid.UUID) -> None:
    result = await db.execute(select(Property.id).where(Property.id == property_id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Property not found")


@router.post("/availability", response_model=AvailabilityResponse)
async def check_availability(
    payload: AvailabilityRequest, db: AsyncSession = Depends(get_db)
) -> AvailabilityResponse:
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
    await _assert_property_exists(db, payload.property_id)

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


@router.get("", response_model=list[BookingOut])
async def list_bookings(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_staff_or_admin),
    property_id: uuid.UUID | None = Query(default=None),
    source: BookingSource | None = Query(default=None),
    booking_status: BookingStatus | None = Query(default=None, alias="status"),
    date_from: date | None = Query(default=None, description="Only bookings ending on/after this"),
    date_to: date | None = Query(default=None, description="Only bookings starting on/before this"),
    limit: int = Query(default=500, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
) -> list[Booking]:
    stmt = select(Booking)

    if property_id is not None:
        stmt = stmt.where(Booking.property_id == property_id)
    if source is not None:
        stmt = stmt.where(Booking.source == source)
    if booking_status is not None:
        stmt = stmt.where(Booking.status == booking_status)
    if date_from is not None:
        stmt = stmt.where(Booking.check_out >= date_from)
    if date_to is not None:
        stmt = stmt.where(Booking.check_in <= date_to)

    stmt = stmt.order_by(Booking.check_in.asc()).offset(offset).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/{booking_id}", response_model=BookingOut)
async def get_booking(
    booking_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_staff_or_admin),
) -> Booking:
    return await _get_or_404(db, booking_id)


@router.patch("/{booking_id}", response_model=BookingOut)
async def update_booking(
    booking_id: uuid.UUID,
    payload: BookingUpdate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_staff_or_admin),
) -> Booking:
    booking = await _get_or_404(db, booking_id)
    changes = payload.model_dump(exclude_unset=True)

    target_property = changes.get("property_id", booking.property_id)
    check_in = changes.get("check_in", booking.check_in)
    check_out = changes.get("check_out", booking.check_out)
    target_status = changes.get("status", booking.status)

    if check_out <= check_in:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="check_out must be after check_in",
        )

    if "property_id" in changes:
        await _assert_property_exists(db, target_property)

    # A cancelled hold blocks nothing, so it never needs an availability check.
    if target_status != BookingStatus.CANCELLED:
        conflicts = await find_conflicts(
            db, target_property, check_in, check_out, exclude_booking_id=booking.id
        )
        if conflicts:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Those dates overlap an existing booking on this property",
            )

    for field, value in changes.items():
        setattr(booking, field, value)

    await db.commit()
    await db.refresh(booking)
    return booking


@router.delete("/{booking_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_booking(
    booking_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_staff_or_admin),
) -> None:
    booking = await _get_or_404(db, booking_id)
    await db.delete(booking)
    await db.commit()


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
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No iCal URLs configured for this property",
        )

    synced = await sync_property_calendars(db, prop)
    return {"ok": True, "synced": synced}