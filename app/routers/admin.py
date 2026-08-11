"""
Operator dashboard analytics.

One endpoint, one snapshot. The dashboard renders ~8 charts and 6 KPI cards
from a single `/admin/overview` response, so every number on the screen is
computed from the same read and no two widgets can ever disagree.
"""
import calendar
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import require_staff_or_admin
from app.models.booking import Booking
from app.models.enums import (
    PAID_ORDER_STATUSES,
    BookingSource,
    BookingStatus,
    InquiryStatus,
    OrderStatus,
)
from app.models.inquiry import Inquiry
from app.models.order import Order
from app.models.property import Property
from app.models.user import User
from app.schemas.admin import (
    CountBreakdown,
    DashboardOverview,
    DashboardStats,
    OccupancyPoint,
    RevenueByEvent,
    RevenueByProperty,
    TimeseriesPoint,
)
from app.schemas.inquiry import InquiryOut
from app.schemas.order import OrderOut

router = APIRouter(prefix="/admin", tags=["admin"])

REFUND_STATUSES = (OrderStatus.REFUNDED, OrderStatus.PARTIALLY_REFUNDED)

# Statuses where money is still expected to arrive — drives the "outstanding" KPI.
OUTSTANDING_STATUSES = (OrderStatus.PENDING, OrderStatus.DEPOSIT_PAID, OrderStatus.BALANCE_DUE)


def _humanize(value: str) -> str:
    return value.replace("_", " ").replace("-", " ").title()


def _month_key(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def _month_label(d: date) -> str:
    return f"{calendar.month_abbr[d.month]} {d.year % 100:02d}"


def _month_starts(months: int, today: date) -> list[date]:
    """The first day of each of the last `months` months, oldest first."""
    starts: list[date] = []
    year, month = today.year, today.month
    for _ in range(months):
        starts.append(date(year, month, 1))
        month -= 1
        if month == 0:
            month, year = 12, year - 1
    return list(reversed(starts))


def _overlap_nights(start: date, end: date, window_start: date, window_end: date) -> int:
    """Nights of [start, end) that fall inside [window_start, window_end)."""
    lo = max(start, window_start)
    hi = min(end, window_end)
    return max((hi - lo).days, 0)


def _pct_change(current: float, previous: float) -> float:
    if previous == 0:
        return 100.0 if current > 0 else 0.0
    return round(((current - previous) / previous) * 100, 1)


@router.get("/overview", response_model=DashboardOverview)
async def dashboard_overview(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_staff_or_admin),
    months: int = Query(default=12, ge=3, le=24, description="Trailing months to chart"),
) -> DashboardOverview:
    now = datetime.now(timezone.utc)
    today = now.date()

    orders = list((await db.execute(select(Order))).scalars().all())
    bookings = list((await db.execute(select(Booking))).scalars().all())
    inquiries = list((await db.execute(select(Inquiry))).scalars().all())

    total_properties = (await db.execute(select(func.count()).select_from(Property))).scalar_one()
    published_properties = (
        await db.execute(
            select(func.count()).select_from(Property).where(Property.is_published.is_(True))
        )
    ).scalar_one()

    prop_rows = (await db.execute(select(Property.id, Property.slug, Property.address))).all()
    prop_lookup = {row.id: (row.slug, row.address) for row in prop_rows}

    live_bookings = [b for b in bookings if b.status != BookingStatus.CANCELLED]

    # ---------------------------------------------------------------- money
    gross = sum(o.amount_cents for o in orders if o.status in PAID_ORDER_STATUSES)
    refunded = sum(
        o.amount_refunded_cents or o.amount_cents for o in orders if o.status in REFUND_STATUSES
    )
    outstanding = sum(
        max(o.amount_cents - o.amount_refunded_cents, 0)
        for o in orders
        if o.status in OUTSTANDING_STATUSES
    )
    paid_orders = [o for o in orders if o.status in PAID_ORDER_STATUSES]
    average_order = round(gross / len(paid_orders)) if paid_orders else 0

    # ------------------------------------------------------- 30-day momentum
    win_start = now - timedelta(days=30)
    prev_start = now - timedelta(days=60)
    cur_rev = sum(o.amount_cents for o in paid_orders if o.created_at >= win_start)
    prev_rev = sum(o.amount_cents for o in paid_orders if prev_start <= o.created_at < win_start)
    cur_cnt = sum(1 for o in orders if o.created_at >= win_start)
    prev_cnt = sum(1 for o in orders if prev_start <= o.created_at < win_start)

    # ------------------------------------------------------------ breakdowns
    by_event: dict[str, RevenueByEvent] = {}
    by_property: dict[str, RevenueByProperty] = {}

    def _prop_bucket(property_id) -> RevenueByProperty:
        slug, address = prop_lookup.get(property_id, ("unassigned", "Unassigned"))
        return by_property.setdefault(
            slug,
            RevenueByProperty(
                property_slug=slug,
                property_address=address,
                orders=0,
                collected_cents=0,
                bookings=0,
            ),
        )

    for o in orders:
        ev = o.event_week.value if o.event_week else "other"
        bucket = by_event.setdefault(
            ev, RevenueByEvent(event_week=ev, orders=0, collected_cents=0)
        )
        bucket.orders += 1
        pbucket = _prop_bucket(o.property_id)
        pbucket.orders += 1
        if o.status in PAID_ORDER_STATUSES:
            bucket.collected_cents += o.amount_cents
            pbucket.collected_cents += o.amount_cents

    for b in live_bookings:
        _prop_bucket(b.property_id).bookings += 1

    orders_by_status: dict[str, CountBreakdown] = {}
    for o in orders:
        row = orders_by_status.setdefault(
            o.status.value,
            CountBreakdown(key=o.status.value, label=_humanize(o.status.value), count=0),
        )
        row.count += 1
        row.amount_cents += o.amount_cents

    bookings_by_source: dict[str, CountBreakdown] = {
        s.value: CountBreakdown(key=s.value, label=_humanize(s.value), count=0)
        for s in BookingSource
    }
    for b in live_bookings:
        bookings_by_source[b.source.value].count += 1

    inquiries_by_status: dict[str, CountBreakdown] = {
        s.value: CountBreakdown(key=s.value, label=_humanize(s.value), count=0)
        for s in InquiryStatus
    }
    for i in inquiries:
        inquiries_by_status[i.status.value].count += 1

    # ------------------------------------------------------------- timeseries
    starts = _month_starts(months, today)
    series: dict[str, TimeseriesPoint] = {}
    occupancy: dict[str, OccupancyPoint] = {}
    denominator = published_properties or total_properties

    for start in starts:
        key = _month_key(start)
        days_in_month = calendar.monthrange(start.year, start.month)[1]
        end = start + timedelta(days=days_in_month)
        series[key] = TimeseriesPoint(
            period=key,
            label=_month_label(start),
            revenue_cents=0,
            refunded_cents=0,
            orders=0,
            bookings=0,
            inquiries=0,
        )
        nights_booked = sum(
            _overlap_nights(b.check_in, b.check_out, start, end) for b in live_bookings
        )
        nights_available = denominator * days_in_month
        occupancy[key] = OccupancyPoint(
            period=key,
            label=_month_label(start),
            nights_booked=nights_booked,
            nights_available=nights_available,
            occupancy_pct=round(nights_booked / nights_available * 100, 1)
            if nights_available
            else 0.0,
        )

    for o in orders:
        point = series.get(_month_key(o.created_at.date()))
        if point is None:
            continue
        point.orders += 1
        if o.status in PAID_ORDER_STATUSES:
            point.revenue_cents += o.amount_cents
        if o.status in REFUND_STATUSES:
            point.refunded_cents += o.amount_refunded_cents or o.amount_cents

    for b in live_bookings:
        point = series.get(_month_key(b.check_in))
        if point is not None:
            point.bookings += 1

    for i in inquiries:
        point = series.get(_month_key(i.created_at.date()))
        if point is not None:
            point.inquiries += 1

    # ------------------------------------------------- forward-looking occupancy
    horizon_end = today + timedelta(days=30)
    booked_ahead = sum(
        _overlap_nights(b.check_in, b.check_out, today, horizon_end) for b in live_bookings
    )
    available_ahead = denominator * 30
    occupancy_next_30 = (
        round(booked_ahead / available_ahead * 100, 1) if available_ahead else 0.0
    )
    upcoming = sum(1 for b in live_bookings if b.check_in >= today)

    stats = DashboardStats(
        total_orders=len(orders),
        total_bookings=len(live_bookings),
        total_properties=total_properties,
        published_properties=published_properties,
        total_inquiries=len(inquiries),
        total_inquiries_new=sum(1 for i in inquiries if i.status == InquiryStatus.NEW),
        upcoming_bookings=upcoming,
        gross_collected_cents=gross,
        refunded_total_cents=refunded,
        net_collected_cents=gross - refunded,
        outstanding_balance_cents=outstanding,
        average_order_cents=average_order,
        revenue_change_pct=_pct_change(cur_rev, prev_rev),
        orders_change_pct=_pct_change(cur_cnt, prev_cnt),
        occupancy_next_30_pct=occupancy_next_30,
        by_event=sorted(by_event.values(), key=lambda r: r.collected_cents, reverse=True),
        by_property=sorted(by_property.values(), key=lambda r: r.collected_cents, reverse=True)[:10],
        timeseries=[series[_month_key(s)] for s in starts],
        occupancy_by_month=[occupancy[_month_key(s)] for s in starts],
        orders_by_status=sorted(orders_by_status.values(), key=lambda r: r.count, reverse=True),
        bookings_by_source=[r for r in bookings_by_source.values() if r.count > 0],
        inquiries_by_status=list(inquiries_by_status.values()),
    )

    recent_orders = sorted(orders, key=lambda o: o.created_at, reverse=True)[:8]
    recent_inquiries = sorted(inquiries, key=lambda i: i.created_at, reverse=True)[:6]

    return DashboardOverview(
        generated_at=now.isoformat(),
        months=months,
        stats=stats,
        recent_orders=[OrderOut.model_validate(o) for o in recent_orders],
        recent_inquiries=[InquiryOut.model_validate(i) for i in recent_inquiries],
    )