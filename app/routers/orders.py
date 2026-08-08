from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import require_staff_or_admin
from app.models.order import Order
from app.models.user import User
from app.schemas.order import OrderCreate, OrderOut

router = APIRouter(prefix="/orders", tags=["orders"])


@router.get("", response_model=list[OrderOut])
async def list_orders(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_staff_or_admin),
    limit: int = Query(default=200, ge=1, le=1000),
) -> list[Order]:
    result = await db.execute(select(Order).order_by(Order.created_at.desc()).limit(limit))
    return list(result.scalars().all())


@router.post("", response_model=OrderOut, status_code=201)
async def create_order(
    payload: OrderCreate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_staff_or_admin),
) -> Order:
    order = Order(**payload.model_dump(), invoice_number=_next_invoice_number())
    db.add(order)
    await db.commit()
    await db.refresh(order)
    return order


def _next_invoice_number() -> str:
    import uuid as _uuid

    return f"ML-{_uuid.uuid4().hex[:10].upper()}"
