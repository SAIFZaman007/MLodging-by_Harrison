import uuid

from sqlalchemy import Date, Enum, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.enums import EventWeek, InquiryStatus
from app.models.mixins import TimestampMixin


class Inquiry(Base, TimestampMixin):
    """A lead captured from any 'Request availability' / inquiry form on the site."""

    __tablename__ = "inquiries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    company: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)

    group_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    event_week: Mapped[EventWeek | None] = mapped_column(
        Enum(EventWeek, name="event_week", values_callable=lambda e: [m.value for m in e]),
        nullable=True,
    )
    check_in: Mapped[Date | None] = mapped_column(Date, nullable=True)
    check_out: Mapped[Date | None] = mapped_column(Date, nullable=True)

    property_slug: Mapped[str | None] = mapped_column(String(160), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[InquiryStatus] = mapped_column(
        Enum(InquiryStatus, name="inquiry_status", values_callable=lambda e: [m.value for m in e]),
        default=InquiryStatus.NEW,
        nullable=False,
        index=True,
    )

    # Basic anti-spam / abuse trail — never shown in the UI, just retained for audit.
    source_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)

    def __repr__(self) -> str:
        return f"<Inquiry {self.name} <{self.email}>>"
