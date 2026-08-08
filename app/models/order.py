import uuid

from sqlalchemy import Enum, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import EventWeek, OrderSource, OrderStatus
from app.models.mixins import TimestampMixin


class Order(Base, TimestampMixin):
    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    invoice_number: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)

    property_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("properties.id", ondelete="SET NULL"), nullable=True, index=True
    )
    booking_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bookings.id", ondelete="SET NULL"), nullable=True
    )

    customer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    customer_email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    amount_refunded_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)

    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus, name="order_status", values_callable=lambda e: [m.value for m in e]),
        default=OrderStatus.PENDING,
        nullable=False,
        index=True,
    )
    source: Mapped[OrderSource] = mapped_column(
        Enum(OrderSource, name="order_source", values_callable=lambda e: [m.value for m in e]),
        default=OrderSource.MANUAL,
        nullable=False,
    )
    event_week: Mapped[EventWeek | None] = mapped_column(
        Enum(EventWeek, name="event_week", values_callable=lambda e: [m.value for m in e]),
        nullable=True,
    )

    # Helcim (or future provider) transaction reference, for webhook reconciliation.
    payment_provider_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)

    booking: Mapped["Booking | None"] = relationship(back_populates="orders")
    property: Mapped["Property | None"] = relationship()  # noqa: F821

    def __repr__(self) -> str:
        return f"<Order {self.invoice_number} {self.status} ${self.amount_cents / 100:.2f}>"
