"""
Order management — full CRUD for the operator console.

Orders are money records, so two rules are enforced here rather than in the UI:
a refund can never exceed what was charged, and status transitions to a
refunded state always carry a matching `amount_refunded_cents`. That keeps the
dashboard's revenue maths correct no matter which client wrote the row.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import require_admin, require_staff_or_admin
from app.models.enums import EventWeek, OrderStatus
from app.models.order import Order
from app.models.user import User
from app.schemas.order import OrderCreate, OrderOut, OrderRefund, OrderUpdate

router = APIRouter(prefix="/orders", tags=["orders"])


def _next_invoice_number() -> str:
    return f"ML-{uuid.uuid4().hex[:10].upper()}"


async def _get_or_404(db: AsyncSession, order_id: uuid.UUID) -> Order:
    result = await db.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    return order


@router.get("", response_model=list[OrderOut])
async def list_orders(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_staff_or_admin),
    q: str | None = Query(default=None, description="Search invoice, customer name or email"),
    order_status: OrderStatus | None = Query(default=None, alias="status"),
    event_week: EventWeek | None = Query(default=None),
    property_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> list[Order]:
    stmt = select(Order)

    if q:
        needle = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Order.invoice_number.ilike(needle),
                Order.customer_name.ilike(needle),
                Order.customer_email.ilike(needle),
            )
        )
    if order_status is not None:
        stmt = stmt.where(Order.status == order_status)
    if event_week is not None:
        stmt = stmt.where(Order.event_week == event_week)
    if property_id is not None:
        stmt = stmt.where(Order.property_id == property_id)

    stmt = stmt.order_by(Order.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/{order_id}", response_model=OrderOut)
async def get_order(
    order_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_staff_or_admin),
) -> Order:
    return await _get_or_404(db, order_id)


@router.post("", response_model=OrderOut, status_code=status.HTTP_201_CREATED)
async def create_order(
    payload: OrderCreate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_staff_or_admin),
) -> Order:
    data = payload.model_dump(exclude={"invoice_number"})
    invoice_number = payload.invoice_number or _next_invoice_number()

    clash = await db.execute(select(Order).where(Order.invoice_number == invoice_number))
    if clash.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Invoice number already exists"
        )

    order = Order(**data, invoice_number=invoice_number)
    db.add(order)
    await db.commit()
    await db.refresh(order)
    return order


@router.patch("/{order_id}", response_model=OrderOut)
async def update_order(
    order_id: uuid.UUID,
    payload: OrderUpdate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_staff_or_admin),
) -> Order:
    order = await _get_or_404(db, order_id)

    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(order, field, value)

    if order.amount_refunded_cents > order.amount_cents:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Refunded amount cannot exceed the order amount",
        )

    await db.commit()
    await db.refresh(order)
    return order


@router.post("/{order_id}/refund", response_model=OrderOut)
async def refund_order(
    order_id: uuid.UUID,
    payload: OrderRefund,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_staff_or_admin),
) -> Order:
    """Record a refund. This writes the ledger entry only — settling the money
    with the payment provider is a separate step."""
    order = await _get_or_404(db, order_id)

    new_total = order.amount_refunded_cents + payload.amount_cents
    if new_total > order.amount_cents:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Refund exceeds the remaining balance "
                f"({(order.amount_cents - order.amount_refunded_cents) / 100:.2f} available)"
            ),
        )

    order.amount_refunded_cents = new_total
    order.status = (
        OrderStatus.REFUNDED if new_total == order.amount_cents else OrderStatus.PARTIALLY_REFUNDED
    )
    await db.commit()
    await db.refresh(order)
    return order


@router.delete("/{order_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_order(
    order_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> None:
    """Admin-only: deleting a financial record is destructive, so staff can edit
    an order but only an admin can remove one."""
    order = await _get_or_404(db, order_id)
    await db.delete(order)
    await db.commit()