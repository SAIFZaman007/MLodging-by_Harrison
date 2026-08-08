import uuid

from sqlalchemy import Date, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import BookingSource, BookingStatus, EventWeek
from app.models.mixins import TimestampMixin


class Booking(Base, TimestampMixin):
    """A date range that is occupied (or blocked) on a property.

    Covers three cases with one table, which is what makes double-booking
    prevention a single query: a direct booking made through the site, an
    externally-synced Airbnb/VRBO reservation (source != DIRECT, external_uid
    set for idempotent re-sync), or a manual block the operator sets by hand.
    """

    __tablename__ = "bookings"
    __table_args__ = (
        UniqueConstraint("property_id", "source", "external_uid", name="uq_booking_external_ref"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    property_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("properties.id", ondelete="CASCADE"), nullable=False, index=True
    )

    source: Mapped[BookingSource] = mapped_column(
        Enum(BookingSource, name="booking_source", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    status: Mapped[BookingStatus] = mapped_column(
        Enum(BookingStatus, name="booking_status", values_callable=lambda e: [m.value for m in e]),
        default=BookingStatus.CONFIRMED,
        nullable=False,
    )

    # Set only for externally-synced bookings; used as the idempotency key on re-sync.
    external_uid: Mapped[str | None] = mapped_column(String(255), nullable=True)

    check_in: Mapped[Date] = mapped_column(Date, nullable=False, index=True)
    check_out: Mapped[Date] = mapped_column(Date, nullable=False, index=True)

    event_week: Mapped[EventWeek | None] = mapped_column(
        Enum(EventWeek, name="event_week", values_callable=lambda e: [m.value for m in e]),
        nullable=True,
    )

    guest_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    guest_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    guest_phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    guests_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    property: Mapped["Property"] = relationship(back_populates="bookings")  # noqa: F821
    orders: Mapped[list["Order"]] = relationship(back_populates="booking")  # noqa: F821

    def __repr__(self) -> str:
        return f"<Booking {self.property_id} {self.check_in}->{self.check_out} ({self.source})>"
