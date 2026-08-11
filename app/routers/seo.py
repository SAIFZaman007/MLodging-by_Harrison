"""
Per-route SEO overrides.

GET is public (the site reads it at render time); writes require an operator.
The upsert is a single atomic Postgres statement, so two editors saving the
same path can't produce a duplicate row or a lost update.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete as sql_delete
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import require_staff_or_admin
from app.models.seo import SeoMeta
from app.models.user import User
from app.schemas.seo import SeoMetaOut, SeoMetaUpsert

router = APIRouter(prefix="/seo", tags=["seo"])


@router.get("", response_model=list[SeoMetaOut])
async def list_seo_meta(db: AsyncSession = Depends(get_db)) -> list[SeoMeta]:
    """Public — the frontend fetches this once at build/runtime to override default meta tags."""
    result = await db.execute(select(SeoMeta).order_by(SeoMeta.path))
    return list(result.scalars().all())


@router.get("/by-path", response_model=SeoMetaOut | None)
async def get_seo_meta_for_path(path: str, db: AsyncSession = Depends(get_db)) -> SeoMeta | None:
    result = await db.execute(select(SeoMeta).where(SeoMeta.path == path))
    return result.scalar_one_or_none()


@router.put("", response_model=SeoMetaOut)
async def upsert_seo_meta(
    payload: SeoMetaUpsert,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_staff_or_admin),
) -> SeoMeta:
    if not payload.path.startswith("/"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Path must start with '/' (e.g. /events/masters)",
        )

    stmt = (
        pg_insert(SeoMeta)
        .values(**payload.model_dump())
        .on_conflict_do_update(
            index_elements=[SeoMeta.path],
            set_=payload.model_dump(exclude={"path"}),
        )
        .returning(SeoMeta)
    )
    result = await db.execute(stmt)
    await db.commit()
    return result.scalar_one()


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_seo_meta(
    path: str = Query(..., description="Exact route path to clear, e.g. /events/masters"),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_staff_or_admin),
) -> None:
    """Removing an override reverts that route to the page component's built-in
    defaults — nothing on the public site breaks."""
    existing = await db.execute(select(SeoMeta).where(SeoMeta.path == path))
    if existing.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No override exists for that path"
        )
    await db.execute(sql_delete(SeoMeta).where(SeoMeta.path == path))
    await db.commit()