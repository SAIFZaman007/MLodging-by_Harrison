from pydantic import BaseModel

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


class DashboardStats(BaseModel):
    total_orders: int
    total_bookings: int
    total_properties: int
    total_inquiries_new: int
    gross_collected_cents: int
    refunded_total_cents: int
    net_collected_cents: int
    by_event: list[RevenueByEvent]
    by_property: list[RevenueByProperty]


class DashboardOverview(BaseModel):
    generated_at: str
    stats: DashboardStats
    recent_orders: list[OrderOut]
