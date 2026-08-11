import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import BookingSource, BookingStatus, EventWeek


class BookingBase(BaseModel):
    check_in: date
    check_out: date
    event_week: EventWeek | None = None
    guest_name: str | None = None
    guest_email: str | None = None
    guest_phone: str | None = None
    guests_count: int | None = Field(default=None, ge=1, le=100)
    notes: str | None = None

    @model_validator(mode="after")
    def check_dates(self) -> "BookingBase":
        if self.check_out <= self.check_in:
            raise ValueError("check_out must be after check_in")
        return self


class BookingCreate(BookingBase):
    property_id: uuid.UUID
    source: BookingSource = BookingSource.DIRECT
    status: BookingStatus = BookingStatus.PENDING


class BookingUpdate(BaseModel):
    """PATCH semantics. Dates are validated as a pair only when both are present;
    the router re-validates against the persisted row before saving."""

    property_id: uuid.UUID | None = None
    check_in: date | None = None
    check_out: date | None = None
    source: BookingSource | None = None
    status: BookingStatus | None = None
    event_week: EventWeek | None = None
    guest_name: str | None = None
    guest_email: str | None = None
    guest_phone: str | None = None
    guests_count: int | None = Field(default=None, ge=1, le=100)
    notes: str | None = None

    @model_validator(mode="after")
    def check_dates(self) -> "BookingUpdate":
        if self.check_in and self.check_out and self.check_out <= self.check_in:
            raise ValueError("check_out must be after check_in")
        return self


class BookingOut(BookingBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    property_id: uuid.UUID
    source: BookingSource
    status: BookingStatus
    external_uid: str | None = None
    created_at: datetime


class AvailabilityRequest(BaseModel):
    property_id: uuid.UUID
    check_in: date
    check_out: date


class AvailabilityResponse(BaseModel):
    available: bool
    conflicting_ranges: list[dict] = Field(default_factory=list)


class BlockedDateRange(BaseModel):
    """A read-only, calendar-friendly view of an occupied range for the public calendar UI."""

    model_config = ConfigDict(from_attributes=True)

    check_in: date
    check_out: date
    source: BookingSource