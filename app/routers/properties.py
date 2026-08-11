"""
Property catalogue.

Public reads are filtered to published homes; the admin surface at
`/properties/admin/*` returns everything with the full schema so the console
can manage visibility rather than only mirroring the public view.

Route order matters here: `/admin/all` is declared before `/{slug}` so the
literal path wins over the wildcard.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.deps import require_admin, require_staff_or_admin
from app.models.booking import Booking
from app.models.order import Order
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


async def _get_admin_or_404(db: AsyncSession, property_id: uuid.UUID) -> Property:
    result = await db.execute(
        select(Property).where(Property.id == property_id).options(selectinload(Property.images))
    )
    prop = result.scalar_one_or_none()
    if prop is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Property not found")
    return prop


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
    stmt = (
        select(Property)
        .where(Property.is_published.is_(True))
        .options(selectinload(Property.images))
    )

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


# ---------------------------------------------------------------------------
# Admin-only management endpoints (declared before /{slug})
# ---------------------------------------------------------------------------


@router.get("/admin/all", response_model=list[PropertyOut])
async def list_all_properties_admin(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_staff_or_admin),
    q: str | None = Query(default=None, description="Search address, title or listing ID"),
    published: bool | None = Query(default=None),
) -> list[Property]:
    """Returns every property — published and unpublished — with the full
    schema so the dashboard can actually manage the portfolio."""
    stmt = select(Property).options(selectinload(Property.images))

    if q:
        needle = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Property.address.ilike(needle),
                Property.title.ilike(needle),
                Property.listing_id.ilike(needle),
            )
        )
    if published is not None:
        stmt = stmt.where(Property.is_published.is_(published))

    result = await db.execute(stmt.order_by(Property.address))
    return list(result.scalars().all())


@router.get("/admin/{property_id}", response_model=PropertyOut)
async def get_property_admin(
    property_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_staff_or_admin),
) -> Property:
    return await _get_admin_or_404(db, property_id)


@router.post("", response_model=PropertyOut, status_code=status.HTTP_201_CREATED)
async def create_property(
    payload: PropertyCreate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_staff_or_admin),
) -> Property:
    clash = await db.execute(
        select(Property).where(
            or_(Property.slug == payload.slug, Property.listing_id == payload.listing_id)
        )
    )
    if clash.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A property with that slug or listing ID already exists",
        )

    prop = Property(**payload.model_dump(exclude={"images"}))
    prop.images = [
        PropertyImage(**img.model_dump()) for img in payload.images
    ]
    db.add(prop)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A property with that slug or listing ID already exists",
        ) from exc

    await db.refresh(prop, attribute_names=["images"])
    return prop


@router.patch("/{property_id}", response_model=PropertyOut)
async def update_property(
    property_id: uuid.UUID,
    payload: PropertyUpdate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_staff_or_admin),
) -> Property:
    prop = await _get_admin_or_404(db, property_id)
    changes = payload.model_dump(exclude_unset=True)
    images = changes.pop("images", None)

    for field, value in changes.items():
        setattr(prop, field, value)

    # Images are replace-in-full: the client always sends the complete, ordered
    # gallery, so there's no partial-diff ambiguity about what got removed.
    if images is not None:
        prop.images.clear()
        for index, img in enumerate(images):
            prop.images.append(
                PropertyImage(
                    thumb_url=img["thumb_url"],
                    hero_url=img["hero_url"],
                    alt_text=img.get("alt_text"),
                    sort_order=img.get("sort_order", index),
                )
            )

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That slug or listing ID is already taken by another property",
        ) from exc

    await db.refresh(prop, attribute_names=["images"])
    return prop


@router.delete("/{property_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_property(
    property_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
    force: bool = Query(
        default=False,
        description="Delete even when bookings or orders reference this property",
    ),
) -> None:
    """Admin-only, and refuses by default when the home still has history.

    Deleting cascades to its bookings, which would silently erase the record of
    real stays — so the caller has to opt in with `?force=true`. Unpublishing is
    almost always the right action instead.
    """
    prop = await _get_admin_or_404(db, property_id)

    if not force:
        booking_count = (
            await db.execute(
                select(func.count()).select_from(Booking).where(Booking.property_id == property_id)
            )
        ).scalar_one()
        order_count = (
            await db.execute(
                select(func.count()).select_from(Order).where(Order.property_id == property_id)
            )
        ).scalar_one()

        if booking_count or order_count:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"This property has {booking_count} booking(s) and {order_count} order(s). "
                    "Unpublish it instead, or re-send with force=true to delete anyway."
                ),
            )

    await db.delete(prop)
    await db.commit()


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