"""
Background job scheduler. Started once from `main.py`'s lifespan handler.

Keeping this as APScheduler running inside the same process is the pragmatic
choice for a single-instance deployment. If this ever runs with multiple
backend replicas, move this to a dedicated worker (or a Postgres-advisory-lock
guard around `run_all_syncs`) so the sync doesn't fire once per replica.
"""
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.property import Property
from app.services.calendar_sync import sync_property_calendars

logger = logging.getLogger("scheduler")

scheduler = AsyncIOScheduler()


async def run_all_calendar_syncs() -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Property).where(
                Property.is_published.is_(True),
            )
        )
        properties = [
            p for p in result.scalars().all() if p.airbnb_ical_url or p.vrbo_ical_url
        ]
        for prop in properties:
            try:
                await sync_property_calendars(db, prop)
            except Exception:
                logger.exception("Calendar sync failed for property %s", prop.slug)


def start_scheduler() -> None:
    if not scheduler.running:
        scheduler.add_job(
            run_all_calendar_syncs,
            "interval",
            minutes=45,
            id="calendar_sync",
            replace_existing=True,
            max_instances=1,
        )
        scheduler.start()


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
