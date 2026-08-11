import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

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
    created_at: datetime
    updated_at: datetime


class OrderCreate(BaseModel):
    property_id: uuid.UUID | None = None
    booking_id: uuid.UUID | None = None
    customer_name: str = Field(min_length=1, max_length=255)
    customer_email: str | None = None
    amount_cents: int = Field(ge=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    status: OrderStatus = OrderStatus.PENDING
    source: OrderSource = OrderSource.MANUAL
    event_week: EventWeek | None = None
    payment_provider_ref: str | None = None
    # Optional override — omit and the API mints a sequential-safe invoice number.
    invoice_number: str | None = Field(default=None, max_length=64)


class OrderUpdate(BaseModel):
    """PATCH semantics — every field optional, only what's sent is applied."""

    property_id: uuid.UUID | None = None
    booking_id: uuid.UUID | None = None
    customer_name: str | None = Field(default=None, min_length=1, max_length=255)
    customer_email: str | None = None
    amount_cents: int | None = Field(default=None, ge=0)
    amount_refunded_cents: int | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    status: OrderStatus | None = None
    source: OrderSource | None = None
    event_week: EventWeek | None = None
    payment_provider_ref: str | None = None


class OrderRefund(BaseModel):
    """Record a refund against an order. Amount is additive to prior refunds."""

    amount_cents: int = Field(gt=0, description="Amount to refund, in cents")
    reason: str | None = Field(default=None, max_length=500)