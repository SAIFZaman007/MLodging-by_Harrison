from fastapi import APIRouter, Depends
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
    result = await db.execute(select(SeoMeta))
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
