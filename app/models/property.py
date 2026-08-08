import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import TimestampMixin


class Property(Base, TimestampMixin):
    __tablename__ = "properties"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    slug: Mapped[str] = mapped_column(String(160), unique=True, index=True, nullable=False)
    listing_id: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[str] = mapped_column(String(255), nullable=False)
    city: Mapped[str] = mapped_column(String(120), default="Augusta")
    state: Mapped[str] = mapped_column(String(2), default="GA")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    guests: Mapped[int] = mapped_column(Integer, nullable=False)
    bedrooms: Mapped[int] = mapped_column(Integer, nullable=False)
    beds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    baths: Mapped[float] = mapped_column(Numeric(3, 1), nullable=False)

    # Nightly/weekly event price in USD cents. Null == "inquire for pricing".
    price_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)

    rating: Mapped[float | None] = mapped_column(Numeric(2, 1), nullable=True)
    reviews_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    airbnb_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    vrbo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # iCal feed URLs used by the calendar-sync service to prevent double bookings.
    airbnb_ical_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    vrbo_ical_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    last_synced_at: Mapped[str | None] = mapped_column(String(64), nullable=True)

    walking_cluster: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    large_group: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_published: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_signature: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    lat: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    lon: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    miles_to_angc: Mapped[float | None] = mapped_column(Numeric(4, 2), nullable=True)

    tags: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)

    images: Mapped[list["PropertyImage"]] = relationship(
        back_populates="property",
        cascade="all, delete-orphan",
        order_by="PropertyImage.sort_order",
    )
    bookings: Mapped[list["Booking"]] = relationship(back_populates="property")  # noqa: F821

    def __repr__(self) -> str:
        return f"<Property {self.slug}>"


class PropertyImage(Base):
    __tablename__ = "property_images"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    property_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("properties.id", ondelete="CASCADE"), nullable=False
    )
    thumb_url: Mapped[str] = mapped_column(String(500), nullable=False)
    hero_url: Mapped[str] = mapped_column(String(500), nullable=False)
    alt_text: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    property: Mapped["Property"] = relationship(back_populates="images")
