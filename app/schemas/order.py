import uuid

from pydantic import BaseModel, ConfigDict

from app.models.enums import EventWeek, OrderSource, OrderStatus


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    invoice_number: str
    property_id: uuid.UUID | None
    booking_id: uuid.UUID | None
    customer_name: str
    customer_email: str | None
    amount_cents: int
    amount_refunded_cents: int
    currency: str
    status: OrderStatus
    source: OrderSource
    event_week: EventWeek | None
    payment_provider_ref: str | None


class OrderCreate(BaseModel):
    property_id: uuid.UUID | None = None
    booking_id: uuid.UUID | None = None
    customer_name: str
    customer_email: str | None = None
    amount_cents: int
    currency: str = "USD"
    status: OrderStatus = OrderStatus.PENDING
    source: OrderSource = OrderSource.MANUAL
    event_week: EventWeek | None = None
    payment_provider_ref: str | None = None
