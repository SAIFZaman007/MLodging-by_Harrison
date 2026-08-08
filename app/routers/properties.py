import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.deps import require_staff_or_admin
from app.models.property import Property, PropertyImage
from app.models.user import User
from app.schemas.property import (
    PropertyCreate,
    PropertyOut,
    PropertySummaryOut,
    PropertyUpdate,
)

router = APIRouter(prefix="/properties", tags=["properties"])


def _to_summary(p: Property) -> PropertySummaryOut:
    first_image = p.images[0] if p.images else None
    return PropertySummaryOut(
        id=p.id,
        slug=p.slug,
        title=p.title,
        address=p.address,
        guests=p.guests,
        bedrooms=p.bedrooms,
        baths=float(p.baths),
        price_cents=p.price_cents,
        rating=float(p.rating) if p.rating is not None else None,
        reviews_count=p.reviews_count,
        walking_cluster=p.walking_cluster,
        large_group=p.large_group,
        is_signature=p.is_signature,
        lat=float(p.lat) if p.lat is not None else None,
        lon=float(p.lon) if p.lon is not None else None,
        miles_to_angc=float(p.miles_to_angc) if p.miles_to_angc is not None else None,
        tags=p.tags or [],
        thumb_url=first_image.thumb_url if first_image else None,
        image_count=len(p.images),
    )


@router.get("", response_model=list[PropertySummaryOut])
async def list_properties(
    db: AsyncSession = Depends(get_db),
    walking_cluster: bool | None = Query(default=None),
    large_group: bool | None = Query(default=None),
    signature: bool | None = Query(default=None),
    min_guests: int | None = Query(default=None, ge=1),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[PropertySummaryOut]:
    stmt = select(Property).where(Property.is_published.is_(True)).options(selectinload(Property.images))

    if walking_cluster is not None:
        stmt = stmt.where(Property.walking_cluster.is_(walking_cluster))
    if large_group is not None:
        stmt = stmt.where(Property.large_group.is_(large_group))
    if signature is not None:
        stmt = stmt.where(Property.is_signature.is_(signature))
    if min_guests is not None:
        stmt = stmt.where(Property.guests >= min_guests)

    stmt = stmt.order_by(Property.price_cents.desc().nullslast()).offset(offset).limit(limit)
    result = await db.execute(stmt)
    return [_to_summary(p) for p in result.scalars().all()]


@router.get("/{slug}", response_model=PropertyOut)
async def get_property(slug: str, db: AsyncSession = Depends(get_db)) -> Property:
    stmt = (
        select(Property)
        .where(Property.slug == slug, Property.is_published.is_(True))
        .options(selectinload(Property.images))
    )
    result = await db.execute(stmt)
    prop = result.scalar_one_or_none()
    if prop is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Property not found")
    return prop


# ---------------------------------------------------------------------------
# Admin-only management endpoints
# ---------------------------------------------------------------------------


@router.get("/admin/all", response_model=list[PropertyOut])
async def list_all_properties_admin(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_staff_or_admin),
) -> list[Property]:
    """Unlike GET /properties (public), this returns every property — published
    and unpublished — with the full schema (including is_published) so the
    dashboard can actually manage visibility instead of just viewing the
    public-filtered list."""
    stmt = select(Property).options(selectinload(Property.images)).order_by(Property.address)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.post("", response_model=PropertyOut, status_code=status.HTTP_201_CREATED)
async def create_property(
    payload: PropertyCreate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_staff_or_admin),
) -> Property:
    existing = await db.execute(select(Property).where(Property.slug == payload.slug))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Slug already exists")

    data = payload.model_dump(exclude={"images"})
    prop = Property(**data)
    prop.images = [PropertyImage(**img.model_dump()) for img in payload.images]
    db.add(prop)
    await db.commit()
    await db.refresh(prop, attribute_names=["images"])
    return prop


@router.patch("/{property_id}", response_model=PropertyOut)
async def update_property(
    property_id: uuid.UUID,
    payload: PropertyUpdate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_staff_or_admin),
) -> Property:
    result = await db.execute(
        select(Property).where(Property.id == property_id).options(selectinload(Property.images))
    )
    prop = result.scalar_one_or_none()
    if prop is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Property not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(prop, field, value)

    await db.commit()
    await db.refresh(prop, attribute_names=["images"])
    return prop


@router.delete("/{property_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_property(
    property_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_staff_or_admin),
) -> None:
    result = await db.execute(select(Property).where(Property.id == property_id))
    prop = result.scalar_one_or_none()
    if prop is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Property not found")
    await db.delete(prop)
    await db.commit()
