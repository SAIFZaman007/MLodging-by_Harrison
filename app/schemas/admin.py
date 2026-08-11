"""
Response shapes for the operator dashboard.

Everything the dashboard renders comes from a single `/admin/overview` call so
the console has one round-trip, one cache key, and one consistent snapshot —
no chart can disagree with the KPI card above it.
"""
from pydantic import BaseModel

from app.schemas.inquiry import InquiryOut
from app.schemas.order import OrderOut


class RevenueByEvent(BaseModel):
    event_week: str
    orders: int
    collected_cents: int


class RevenueByProperty(BaseModel):
    property_slug: str
    property_address: str
    orders: int
    collected_cents: int
    bookings: int


class TimeseriesPoint(BaseModel):
    """One month of activity. `period` is an ISO year-month (e.g. '2026-04')."""

    period: str
    label: str
    revenue_cents: int
    refunded_cents: int
    orders: int
    bookings: int
    inquiries: int


class OccupancyPoint(BaseModel):
    period: str
    label: str
    nights_booked: int
    nights_available: int
    occupancy_pct: float


class CountBreakdown(BaseModel):
    """Generic key/count bucket — powers the donut and stacked-bar charts."""

    key: str
    label: str
    count: int
    amount_cents: int = 0


class DashboardStats(BaseModel):
    # --- Headline counters ---
    total_orders: int
    total_bookings: int
    total_properties: int
    published_properties: int
    total_inquiries: int
    total_inquiries_new: int
    upcoming_bookings: int

    # --- Money ---
    gross_collected_cents: int
    refunded_total_cents: int
    net_collected_cents: int
    outstanding_balance_cents: int
    average_order_cents: int

    # --- Trend (current vs previous 30-day window), as a signed percentage ---
    revenue_change_pct: float
    orders_change_pct: float

    # --- Occupancy ---
    occupancy_next_30_pct: float

    # --- Breakdowns / series ---
    by_event: list[RevenueByEvent]
    by_property: list[RevenueByProperty]
    timeseries: list[TimeseriesPoint]
    occupancy_by_month: list[OccupancyPoint]
    orders_by_status: list[CountBreakdown]
    bookings_by_source: list[CountBreakdown]
    inquiries_by_status: list[CountBreakdown]


class DashboardOverview(BaseModel):
    generated_at: str
    months: int
    stats: DashboardStats
    recent_orders: list[OrderOut]
    recent_inquiries: list[InquiryOut]