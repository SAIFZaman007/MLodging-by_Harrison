"""
Seed the database with the real 24-property Augusta portfolio.

Idempotent: safe to re-run. Existing properties (matched by slug) are updated
in place rather than duplicated, so this doubles as a "resync from the JSON
export" tool if the source data changes.

Usage:
    python -m app.seed.seed
"""
import asyncio
import json
import re
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.database import AsyncSessionLocal
from app.models.property import Property, PropertyImage

DATA_FILE = Path(__file__).parent / "properties.json"
BEDS_RE = re.compile(r"(\d+)\s*beds?")


def _extract_beds(capacity: str) -> int | None:
    m = BEDS_RE.search(capacity or "")
    return int(m.group(1)) if m else None


def _asset_url(relative_path: str) -> str:
    """Legacy paths are relative ('assets/galleries/...'); the frontend serves
    the same folder from its /public root, so we just root-anchor it."""
    return "/" + relative_path.lstrip("/")


async def seed() -> None:
    records = json.loads(DATA_FILE.read_text())
    print(f"\n🚀 Loaded {len(records)} properties from {DATA_FILE.name}\n" + "-" * 60)

    async with AsyncSessionLocal() as db:
        created, updated = 0, 0

        # 1. Fetch ALL existing properties along with their images in a SINGLE query
        result = await db.execute(
            select(Property).options(selectinload(Property.images))
        )
        existing_map = {p.slug: p for p in result.scalars().all()}

        for idx, rec in enumerate(records, start=1):
            slug = rec["slug"]
            price_cents = int(round(rec["price"] * 100)) if rec.get("price") else None
            images_data = rec.get("images", [])

            fields = dict(
                listing_id=rec["listing_id"],
                title=rec["title"],
                address=rec["address"],
                city="Augusta",
                state="GA",
                guests=rec["guests"],
                bedrooms=rec["bedrooms"],
                beds=_extract_beds(rec.get("capacity", "")),
                baths=rec["baths"],
                price_cents=price_cents,
                rating=rec.get("rating"),
                reviews_count=rec.get("reviews"),
                airbnb_url=rec.get("airbnb"),
                walking_cluster=bool(rec.get("walking_cluster")),
                large_group=bool(rec.get("large_group")),
                is_published=True,
                is_signature=bool(rec.get("rating") and rec.get("rating") >= 4.8),
                lat=rec.get("lat"),
                lon=rec.get("lon"),
                miles_to_angc=rec.get("miles_to_angc"),
                tags=rec.get("tags", []),
            )

            prop = existing_map.get(slug)

            if prop is None:
                prop = Property(slug=slug, **fields)
                db.add(prop)
                created += 1
                status = "[CREATED]"
            else:
                for k, v in fields.items():
                    setattr(prop, k, v)
                
                # Safely clear old images using SQLAlchemy relationship management
                prop.images.clear()
                updated += 1
                status = "[UPDATED]"

            # 2. Add new images
            for i, img in enumerate(images_data):
                prop.images.append(
                    PropertyImage(
                        thumb_url=_asset_url(img["thumb"]),
                        hero_url=_asset_url(img["hero"]),
                        alt_text=f"{rec['title']} — photo {i + 1}",
                        sort_order=i,
                    )
                )

            # Log property details to terminal
            print(f"{idx:02d}. {status} {rec['title']}")
            print(f"    ├─ Slug: {slug}")
            print(f"    ├─ Address: {rec['address']}, Augusta, GA")
            print(f"    └─ Images: {len(images_data)} loaded")

        # 3. Single commit for all changes
        await db.commit()
        print("-" * 60)
        print(f"✨ Seed complete — {created} created, {updated} updated.\n")


if __name__ == "__main__":
    asyncio.run(seed())