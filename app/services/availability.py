"""
Availability / double-booking prevention.

The rule is a classic date-range overlap check done in a single indexed query:
two ranges [check_in, check_out) overlap iff  A.check_in < B.check_out AND
A.check_out > B.check_in. We only consider bookings with status != CANCELLED,
so a cancelled hold never blocks new reservations.
"""
import uuid
from datetime import date

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking
from app.models.enums import BookingStatus


async def find_conflicts(
    db: AsyncSession,
    property_id: uuid.UUID,
    check_in: date,
    check_out: date,
    exclude_booking_id: uuid.UUID | None = None,
) -> list[Booking]:
    conditions = [
        Booking.property_id == property_id,
        Booking.status != BookingStatus.CANCELLED,
        Booking.check_in < check_out,
        Booking.check_out > check_in,
    ]
    if exclude_booking_id is not None:
        conditions.append(Booking.id != exclude_booking_id)

    result = await db.execute(select(Booking).where(and_(*conditions)))
    return list(result.scalars().all())


async def is_available(
    db: AsyncSession,
    property_id: uuid.UUID,
    check_in: date,
    check_out: date,
) -> bool:
    conflicts = await find_conflicts(db, property_id, check_in, check_out)
    return len(conflicts) == 0
