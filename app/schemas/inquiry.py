import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.enums import EventWeek, InquiryStatus


class InquiryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    company: str | None = None
    email: EmailStr
    phone: str | None = None
    group_size: int | None = Field(default=None, ge=1, le=500)
    event_week: EventWeek | None = None
    check_in: date | None = None
    check_out: date | None = None
    property_slug: str | None = None
    notes: str | None = Field(default=None, max_length=4000)


class InquiryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    company: str | None
    email: EmailStr
    phone: str | None
    group_size: int | None
    event_week: EventWeek | None
    check_in: date | None
    check_out: date | None
    property_slug: str | None
    notes: str | None
    status: InquiryStatus
    created_at: datetime


class InquiryStatusUpdate(BaseModel):
    status: InquiryStatus
