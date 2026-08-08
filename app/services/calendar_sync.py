"""
Airbnb / VRBO calendar sync.

Both Airbnb and VRBO publish a per-listing iCal export URL (found in each
platform's host calendar settings, no OAuth app review required). We poll
that feed, parse VEVENTs into (start, end) date ranges, and upsert them as
`Booking` rows with source=AIRBNB/VRBO and external_uid=<the iCal UID>.

Re-running a sync is idempotent: the unique constraint on
(property_id, source, external_uid) means re-syncing the same feed just
updates existing rows rather than duplicating them. Cancelled Airbnb/VRBO
reservations disappear from the feed on the next poll and are removed here.

Call `sync_property_calendars(db, property)` from:
  - the admin "Sync now" button (POST /api/v1/admin/properties/{id}/sync-calendar)
  - a scheduled job (see app/services/scheduler.py) every ~30-60 minutes
"""
from datetime import date, timedelta

import httpx
from icalendar import Calendar
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking
from app.models.enums import BookingSource, BookingStatus
from app.models.property import Property


def _to_date(value) -> date:
    """icalendar returns either date or datetime for DTSTART/DTEND — normalize to date."""
    if hasattr(value.dt, "date"):
        return value.dt.date()
    return value.dt


async def _fetch_ical(url: str) -> Calendar:
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return Calendar.from_ical(resp.content)


async def _sync_one_feed(db: AsyncSession, property_id, source: BookingSource, ical_url: str) -> int:
    cal = await _fetch_ical(ical_url)

    seen_uids: set[str] = set()
    synced = 0

    for component in cal.walk("VEVENT"):
        uid = str(component.get("UID"))
        dtstart = component.get("DTSTART")
        dtend = component.get("DTEND")
        if not uid or not dtstart or not dtend:
            continue

        check_in = _to_date(dtstart)
        check_out = _to_date(dtend)
        # Airbnb/VRBO sometimes emit a same-day "blocked" placeholder — skip zero-length ranges.
        if check_out <= check_in:
            check_out = check_in + timedelta(days=1)

        seen_uids.add(uid)

        existing = await db.execute(
            select(Booking).where(
                Booking.property_id == property_id,
                Booking.source == source,
                Booking.external_uid == uid,
            )
        )
        booking = existing.scalar_one_or_none()
        if booking:
            booking.check_in = check_in
            booking.check_out = check_out
            booking.status = BookingStatus.CONFIRMED
        else:
            db.add(
                Booking(
                    property_id=property_id,
                    source=source,
                    status=BookingStatus.CONFIRMED,
                    external_uid=uid,
                    check_in=check_in,
                    check_out=check_out,
                )
            )
        synced += 1

    # Remove synced bookings that dropped out of the feed (cancellations on the other platform).
    stale = await db.execute(
        select(Booking).where(Booking.property_id == property_id, Booking.source == source)
    )
    for booking in stale.scalars().all():
        if booking.external_uid and booking.external_uid not in seen_uids:
            await db.execute(delete(Booking).where(Booking.id == booking.id))

    return synced


async def sync_property_calendars(db: AsyncSession, prop: Property) -> dict[str, int]:
    """Sync whichever of Airbnb/VRBO iCal URLs are configured for this property."""
    results: dict[str, int] = {}

    if prop.airbnb_ical_url:
        results["airbnb"] = await _sync_one_feed(db, prop.id, BookingSource.AIRBNB, prop.airbnb_ical_url)
    if prop.vrbo_ical_url:
        results["vrbo"] = await _sync_one_feed(db, prop.id, BookingSource.VRBO, prop.vrbo_ical_url)

    prop.last_synced_at = date.today().isoformat()
    await db.commit()
    return results
