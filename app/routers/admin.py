from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import require_staff_or_admin
from app.models.booking import Booking
from app.models.enums import PAID_ORDER_STATUSES, InquiryStatus, OrderStatus
from app.models.inquiry import Inquiry
from app.models.order import Order
from app.models.property import Property
from app.models.user import User
from app.schemas.admin import DashboardOverview, DashboardStats, RevenueByEvent, RevenueByProperty
from app.schemas.order import OrderOut

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/overview", response_model=DashboardOverview)
async def dashboard_overview(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_staff_or_admin),
) -> DashboardOverview:
    orders_result = await db.execute(select(Order))
    orders = list(orders_result.scalars().all())

    total_bookings = (await db.execute(select(func.count()).select_from(Booking))).scalar_one()
    total_properties = (await db.execute(select(func.count()).select_from(Property))).scalar_one()
    total_inquiries_new = (
        await db.execute(
            select(func.count()).select_from(Inquiry).where(Inquiry.status == InquiryStatus.NEW)
        )
    ).scalar_one()

    gross = sum(o.amount_cents for o in orders if o.status in PAID_ORDER_STATUSES)
    refunded = sum(
        o.amount_refunded_cents or o.amount_cents
        for o in orders
        if o.status in (OrderStatus.REFUNDED, OrderStatus.PARTIALLY_REFUNDED)
    )

    by_event: dict[str, RevenueByEvent] = {}
    by_property: dict[str, RevenueByProperty] = {}

    # Preload property slug/address lookups for grouping.
    prop_result = await db.execute(select(Property.id, Property.slug, Property.address))
    prop_lookup = {row.id: (row.slug, row.address) for row in prop_result.all()}

    for o in orders:
        ev = o.event_week.value if o.event_week else "other"
        bucket = by_event.setdefault(ev, RevenueByEvent(event_week=ev, orders=0, collected_cents=0))
        bucket.orders += 1
        if o.status in PAID_ORDER_STATUSES:
            bucket.collected_cents += o.amount_cents

        slug, address = prop_lookup.get(o.property_id, ("unknown", "Unknown property"))
        pbucket = by_property.setdefault(
            slug, RevenueByProperty(property_slug=slug, property_address=address, orders=0, collected_cents=0, bookings=0)
        )
        pbucket.orders += 1
        if o.status in PAID_ORDER_STATUSES:
            pbucket.collected_cents += o.amount_cents

    bookings_result = await db.execute(select(Booking.property_id))
    for (property_id,) in bookings_result.all():
        slug, address = prop_lookup.get(property_id, ("unknown", "Unknown property"))
        pbucket = by_property.setdefault(
            slug, RevenueByProperty(property_slug=slug, property_address=address, orders=0, collected_cents=0, bookings=0)
        )
        pbucket.bookings += 1

    stats = DashboardStats(
        total_orders=len(orders),
        total_bookings=total_bookings,
        total_properties=total_properties,
        total_inquiries_new=total_inquiries_new,
        gross_collected_cents=gross,
        refunded_total_cents=refunded,
        net_collected_cents=gross - refunded,
        by_event=sorted(by_event.values(), key=lambda r: r.collected_cents, reverse=True),
        by_property=sorted(by_property.values(), key=lambda r: r.collected_cents, reverse=True),
    )

    recent = sorted(orders, key=lambda o: o.created_at, reverse=True)[:6]

    return DashboardOverview(
        generated_at=datetime.now(timezone.utc).isoformat(),
        stats=stats,
        recent_orders=[OrderOut.model_validate(o) for o in recent],
    )
