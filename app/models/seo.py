import uuid

from sqlalchemy import String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import TimestampMixin


class SeoMeta(Base, TimestampMixin):
    """Editable SEO metadata keyed by frontend route path, e.g. '/', '/events/masters'.

    The frontend fetches this at render time and falls back to sensible
    hardcoded defaults if no override exists — so editors can tune title tags,
    meta descriptions, and OG images from the dashboard without a code deploy.
    """

    __tablename__ = "seo_meta"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    path: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    meta_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    og_image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    canonical_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    def __repr__(self) -> str:
        return f"<SeoMeta {self.path}>"
