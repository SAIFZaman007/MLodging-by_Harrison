import re
import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator

SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class PropertyImageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    thumb_url: str
    hero_url: str
    alt_text: str | None = None
    sort_order: int


class PropertyImageIn(BaseModel):
    thumb_url: str = Field(min_length=1, max_length=500)
    hero_url: str = Field(min_length=1, max_length=500)
    alt_text: str | None = Field(default=None, max_length=255)
    sort_order: int = 0


class PropertyBase(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    address: str = Field(min_length=1, max_length=255)
    city: str = "Augusta"
    state: str = Field(default="GA", min_length=2, max_length=2)
    description: str | None = None
    guests: int = Field(ge=1, le=100)
    bedrooms: int = Field(ge=0, le=50)
    beds: int | None = Field(default=None, ge=0, le=100)
    baths: float = Field(ge=0, le=50)
    price_cents: int | None = Field(default=None, ge=0)
    rating: float | None = Field(default=None, ge=0, le=5)
    reviews_count: int | None = Field(default=None, ge=0)
    airbnb_url: str | None = None
    vrbo_url: str | None = None
    airbnb_ical_url: str | None = None
    vrbo_ical_url: str | None = None
    walking_cluster: bool = False
    large_group: bool = False
    is_published: bool = True
    is_signature: bool = False
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    miles_to_angc: float | None = Field(default=None, ge=0)
    tags: list[str] = Field(default_factory=list)


class PropertyCreate(PropertyBase):
    slug: str = Field(min_length=1, max_length=160)
    listing_id: str = Field(min_length=1, max_length=40)
    images: list[PropertyImageIn] = Field(default_factory=list)

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: str) -> str:
        v = v.strip().lower()
        if not SLUG_RE.match(v):
            raise ValueError("Slug must be lowercase words separated by single hyphens")
        return v


class PropertyUpdate(BaseModel):
    """All fields optional — PATCH semantics.

    `images`, when present, replaces the whole gallery in the given order.
    Omit the key entirely to leave existing photos untouched.
    """

    slug: str | None = Field(default=None, min_length=1, max_length=160)
    listing_id: str | None = Field(default=None, min_length=1, max_length=40)
    title: str | None = Field(default=None, min_length=1, max_length=255)
    address: str | None = Field(default=None, min_length=1, max_length=255)
    city: str | None = None
    state: str | None = Field(default=None, min_length=2, max_length=2)
    description: str | None = None
    guests: int | None = Field(default=None, ge=1, le=100)
    bedrooms: int | None = Field(default=None, ge=0, le=50)
    beds: int | None = Field(default=None, ge=0, le=100)
    baths: float | None = Field(default=None, ge=0, le=50)
    price_cents: int | None = Field(default=None, ge=0)
    rating: float | None = Field(default=None, ge=0, le=5)
    reviews_count: int | None = Field(default=None, ge=0)
    airbnb_url: str | None = None
    vrbo_url: str | None = None
    airbnb_ical_url: str | None = None
    vrbo_ical_url: str | None = None
    walking_cluster: bool | None = None
    large_group: bool | None = None
    is_published: bool | None = None
    is_signature: bool | None = None
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    miles_to_angc: float | None = Field(default=None, ge=0)
    tags: list[str] | None = None
    images: list[PropertyImageIn] | None = None

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip().lower()
        if not SLUG_RE.match(v):
            raise ValueError("Slug must be lowercase words separated by single hyphens")
        return v


class PropertyOut(PropertyBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    listing_id: str
    images: list[PropertyImageOut] = Field(default_factory=list)


class PropertySummaryOut(BaseModel):
    """Lightweight shape used for grid/map listings — avoids shipping full descriptions."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    title: str
    address: str
    guests: int
    bedrooms: int
    baths: float
    price_cents: int | None
    rating: float | None
    reviews_count: int | None
    walking_cluster: bool
    large_group: bool
    is_signature: bool
    lat: float | None
    lon: float | None
    miles_to_angc: float | None
    tags: list[str]
    thumb_url: str | None = None
    image_count: int = 0