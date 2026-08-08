import uuid

from pydantic import BaseModel, ConfigDict, Field


class PropertyImageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    thumb_url: str
    hero_url: str
    alt_text: str | None = None
    sort_order: int


class PropertyImageIn(BaseModel):
    thumb_url: str
    hero_url: str
    alt_text: str | None = None
    sort_order: int = 0


class PropertyBase(BaseModel):
    title: str
    address: str
    city: str = "Augusta"
    state: str = "GA"
    description: str | None = None
    guests: int = Field(ge=1)
    bedrooms: int = Field(ge=0)
    beds: int | None = None
    baths: float = Field(ge=0)
    price_cents: int | None = None
    rating: float | None = Field(default=None, ge=0, le=5)
    reviews_count: int | None = None
    airbnb_url: str | None = None
    vrbo_url: str | None = None
    airbnb_ical_url: str | None = None
    vrbo_ical_url: str | None = None
    walking_cluster: bool = False
    large_group: bool = False
    is_published: bool = True
    is_signature: bool = False
    lat: float | None = None
    lon: float | None = None
    miles_to_angc: float | None = None
    tags: list[str] = Field(default_factory=list)


class PropertyCreate(PropertyBase):
    slug: str
    listing_id: str
    images: list[PropertyImageIn] = Field(default_factory=list)


class PropertyUpdate(BaseModel):
    """All fields optional — PATCH semantics."""
    title: str | None = None
    address: str | None = None
    description: str | None = None
    guests: int | None = None
    bedrooms: int | None = None
    beds: int | None = None
    baths: float | None = None
    price_cents: int | None = None
    rating: float | None = None
    reviews_count: int | None = None
    airbnb_url: str | None = None
    vrbo_url: str | None = None
    airbnb_ical_url: str | None = None
    vrbo_ical_url: str | None = None
    walking_cluster: bool | None = None
    large_group: bool | None = None
    is_published: bool | None = None
    is_signature: bool | None = None
    lat: float | None = None
    lon: float | None = None
    miles_to_angc: float | None = None
    tags: list[str] | None = None


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
