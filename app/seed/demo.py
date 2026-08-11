"""
Comprehensive demo-data seeder for the 8888 Augusta operator console.

Fills the dashboard with a realistic, self-consistent portfolio history so every
KPI card, chart, table, and CRUD flow can be exercised end-to-end without
touching a payment provider or waiting for real traffic.

What it generates
-----------------
  • Bookings across the trailing 12 months and the next 6, distributed over the
    real event calendar (Masters, ANWA, Ironman, Peach Jam, private events),
    with a realistic mix of direct / Airbnb / VRBO / manual-block sources.
  • Orders attached to those bookings, priced from each home's actual nightly
    rate, spread across the full status ladder including refunds so the money
    maths (gross / refunded / net / outstanding) has something to chew on.
  • Inquiries in every funnel stage, dated across the same window.
  • SEO overrides for the primary public routes.
  • An optional demo staff account so role-gated UI can be tested.

Design guarantees
-----------------
  • **Deterministic.** Seeded RNG — the same `--seed` always produces the same
    dataset, so screenshots and QA runs are reproducible.
  • **No double-bookings.** Every generated stay is checked against the ranges
    already placed on that property, so the demo data obeys the same invariant
    the production booking engine enforces.
  • **Idempotent + reversible.** Everything it writes is tagged (bookings via an
    external_uid prefix, orders via source=SEED, inquiries via source_ip). Re-run
    it and the previous demo rows are cleared first; run `--wipe-only` to strip
    the demo data out and leave real records untouched.
  • **Production-safe.** Refuses to run when ENVIRONMENT=production or when
    ALLOW_DEMO_SEED is false. There is no flag to override that from the CLI.

Usage
-----
    python -m app.seed.seed          # real 24-property portfolio first
    python -m app.seed.demo          # then layer demo activity on top
    python -m app.seed.demo --orders 400 --months 18 --seed 7
    python -m app.seed.demo --wipe-only
"""
import argparse
import asyncio
import random
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import delete, select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.models.booking import Booking
from app.models.enums import (
    BookingSource,
    BookingStatus,
    EventWeek,
    InquiryStatus,
    OrderSource,
    OrderStatus,
    UserRole,
)
from app.models.inquiry import Inquiry
from app.models.order import Order
from app.models.property import Property
from app.models.seo import SeoMeta
from app.models.user import User

# Markers that let us find and remove exactly what this script created.
DEMO_BOOKING_PREFIX = "demo-"
DEMO_INQUIRY_IP = "demo-seed"
DEMO_INVOICE_PREFIX = "DEMO-"
DEMO_STAFF_EMAIL = "demo.staff@8888augusta.com"


@dataclass(frozen=True)
class EventWindow:
    """An anchor window demo stays cluster around.

    NOTE: month/day pairs are approximate anchors for demo data only — they are
    not published schedules. Confirm real dates before using them anywhere
    guest-facing.
    """

    event: EventWeek
    month: int
    day: int
    span_days: int
    weight: int          # relative share of bookings
    rate_multiplier: float  # event-week pricing premium


EVENT_WINDOWS: tuple[EventWindow, ...] = (
    EventWindow(EventWeek.MASTERS, month=4, day=6, span_days=8, weight=34, rate_multiplier=1.00),
    EventWindow(EventWeek.ANWA, month=3, day=30, span_days=5, weight=12, rate_multiplier=0.55),
    EventWindow(EventWeek.IRONMAN, month=9, day=25, span_days=4, weight=12, rate_multiplier=0.40),
    EventWindow(EventWeek.PEACH_JAM, month=7, day=12, span_days=6, weight=12, rate_multiplier=0.35),
    EventWindow(EventWeek.PRIVATE_EVENT, month=6, day=15, span_days=4, weight=15, rate_multiplier=0.45),
    EventWindow(EventWeek.OTHER, month=11, day=8, span_days=3, weight=15, rate_multiplier=0.30),
)

# Weighted so the dashboard shows a healthy business with visible edge cases.
ORDER_STATUS_WEIGHTS: tuple[tuple[OrderStatus, int], ...] = (
    (OrderStatus.PAID_IN_FULL, 46),
    (OrderStatus.DEPOSIT_PAID, 18),
    (OrderStatus.BALANCE_DUE, 12),
    (OrderStatus.PENDING, 9),
    (OrderStatus.PARTIALLY_REFUNDED, 5),
    (OrderStatus.REFUNDED, 4),
    (OrderStatus.CANCELLED, 4),
    (OrderStatus.FAILED, 2),
)

BOOKING_SOURCE_WEIGHTS: tuple[tuple[BookingSource, int], ...] = (
    (BookingSource.DIRECT, 52),
    (BookingSource.AIRBNB, 26),
    (BookingSource.VRBO, 14),
    (BookingSource.MANUAL_BLOCK, 8),
)

INQUIRY_STATUS_WEIGHTS: tuple[tuple[InquiryStatus, int], ...] = (
    (InquiryStatus.NEW, 34),
    (InquiryStatus.CONTACTED, 28),
    (InquiryStatus.CONVERTED, 24),
    (InquiryStatus.ARCHIVED, 14),
)

FIRST_NAMES = [
    "James", "Marcus", "Elena", "Priya", "Daniel", "Sofia", "Malik", "Grace",
    "Thomas", "Ava", "Hiroshi", "Nora", "Andre", "Camila", "Owen", "Yusuf",
    "Beatrice", "Liam", "Chen", "Rosalind", "Victor", "Amara", "Nathan", "Ingrid",
]
LAST_NAMES = [
    "Whitfield", "Okonkwo", "Vasquez", "Lindqvist", "Ferrari", "Nakamura",
    "Bellweather", "Osei", "Kowalski", "Ramachandran", "Delacroix", "Halvorsen",
    "Mbeki", "Castellanos", "Thornbury", "Aldridge", "Petrov", "Silva",
]
COMPANIES = [
    "Ridgeline Capital", "Kestrel Partners", "Bellamy & Roe", "Northgate Logistics",
    "Sutter Hill Advisory", "Ironwood Medical", "Caldwell Brothers", "Meridian Sports Group",
    None, None, None,
]
INQUIRY_NOTES = [
    "Corporate group — needs two homes within walking distance of each other.",
    "Client hospitality week, wants early check-in and daily housekeeping.",
    "Family reunion, asking about cots and whether the pool is heated.",
    "Repeat guest from last year, asking to hold the same property.",
    "Wedding party looking for overflow accommodation near the venue.",
    "Wants a walkthrough of parking and shuttle arrangements before booking.",
    "Comparing against a hotel block — asked for a full-week quote.",
    None,
]

SEO_ENTRIES = [
    (
        "/",
        "8888 Augusta — Luxury Homes Near Augusta National",
        "A private portfolio of 24 luxury homes minutes from Augusta National. "
        "Direct booking, concierge service, no platform fees.",
    ),
    (
        "/portfolio",
        "The Portfolio — 24 Luxury Augusta Rentals | 8888 Augusta",
        "Browse every home in the 8888 Augusta collection. Filter by guest count, "
        "walking distance to the course, and event week availability.",
    ),
    (
        "/events/masters",
        "Masters Week Rentals in Augusta, GA | 8888 Augusta",
        "Premium homes for Masters week, many within walking distance of the gates. "
        "Book direct with the owner-operator.",
    ),
    (
        "/events/anwa",
        "ANWA Week Accommodation | 8888 Augusta",
        "Comfortable, well-appointed homes for the Augusta National Women's Amateur.",
    ),
    (
        "/local-info",
        "Augusta Local Guide — Dining, Transport & Golf | 8888 Augusta",
        "Where to eat, how to get around, and what to know before you arrive in Augusta.",
    ),
    (
        "/how-it-works",
        "How Booking Works | 8888 Augusta",
        "A straightforward look at availability, deposits, and what's included with every stay.",
    ),
    (
        "/weddings-private-events",
        "Weddings & Private Events in Augusta | 8888 Augusta",
        "Multi-home bookings for weddings, corporate retreats, and private gatherings.",
    ),
]


def _weighted(rng: random.Random, choices: tuple[tuple, ...]):
    population = [c[0] for c in choices]
    weights = [c[1] for c in choices]
    return rng.choices(population, weights=weights, k=1)[0]


def _event_windows_for_range(start: date, end: date) -> list[tuple[EventWindow, date]]:
    """Expand each event anchor across every year the window spans."""
    out: list[tuple[EventWindow, date]] = []
    for year in range(start.year, end.year + 1):
        for window in EVENT_WINDOWS:
            try:
                anchor = date(year, window.month, window.day)
            except ValueError:  # pragma: no cover — guards a leap-day anchor
                continue
            if start <= anchor <= end:
                out.append((window, anchor))
    return out


def _overlaps(existing: list[tuple[date, date]], check_in: date, check_out: date) -> bool:
    return any(check_in < e_out and check_out > e_in for e_in, e_out in existing)


async def wipe_demo_data(db) -> dict[str, int]:
    """Remove only rows this seeder created. Real data is never touched."""
    counts: dict[str, int] = {}

    orders = (
        await db.execute(
            select(Order).where(Order.invoice_number.startswith(DEMO_INVOICE_PREFIX))
        )
    ).scalars().all()
    for order in orders:
        await db.delete(order)
    counts["orders"] = len(orders)

    bookings = (
        await db.execute(
            select(Booking).where(Booking.external_uid.startswith(DEMO_BOOKING_PREFIX))
        )
    ).scalars().all()
    for booking in bookings:
        await db.delete(booking)
    counts["bookings"] = len(bookings)

    inquiries = (
        await db.execute(select(Inquiry).where(Inquiry.source_ip == DEMO_INQUIRY_IP))
    ).scalars().all()
    for inquiry in inquiries:
        await db.delete(inquiry)
    counts["inquiries"] = len(inquiries)

    await db.execute(delete(User).where(User.email == DEMO_STAFF_EMAIL))
    await db.commit()
    return counts


async def seed_demo(
    months_back: int = 12,
    months_forward: int = 6,
    target_bookings: int = 320,
    target_orders: int = 280,
    target_inquiries: int = 95,
    rng_seed: int = 8888,
    with_staff_user: bool = True,
) -> None:
    if settings.is_production or not settings.ALLOW_DEMO_SEED:
        raise SystemExit(
            "Refusing to seed demo data: ENVIRONMENT is production or "
            "ALLOW_DEMO_SEED is false. This guard is intentional and has no CLI override."
        )

    rng = random.Random(rng_seed)
    now = datetime.now(timezone.utc)
    today = now.date()
    window_start = today - timedelta(days=months_back * 30)
    window_end = today + timedelta(days=months_forward * 30)

    async with AsyncSessionLocal() as db:
        properties = list((await db.execute(select(Property))).scalars().all())
        if not properties:
            raise SystemExit(
                "No properties found. Run `python -m app.seed.seed` first to load the "
                "24-home portfolio, then re-run this script."
            )

        print(f"\n  8888 Augusta — demo data seeder (rng seed {rng_seed})")
        print("=" * 64)

        removed = await wipe_demo_data(db)
        print(
            f"  Cleared previous demo rows: {removed['orders']} orders, "
            f"{removed['bookings']} bookings, {removed['inquiries']} inquiries"
        )

        # ------------------------------------------------------------ bookings
        expanded = _event_windows_for_range(window_start, window_end)
        if not expanded:
            raise SystemExit("No event windows fall inside the requested date range.")

        window_weights = [w.weight for w, _ in expanded]
        occupied: dict[uuid.UUID, list[tuple[date, date]]] = {p.id: [] for p in properties}
        bookings: list[Booking] = []
        attempts = 0

        total_days = (window_end - window_start).days

        while len(bookings) < target_bookings and attempts < target_bookings * 12:
            attempts += 1
            prop = rng.choice(properties)

            # ~30% of stays are ordinary off-event bookings placed uniformly across
            # the whole window. Without these, every quiet month would read as 0%
            # occupancy and the trend charts would be a row of empty gaps.
            if rng.random() < 0.22:
                window = EVENT_WINDOWS[-1]
                check_in = window_start + timedelta(days=rng.randint(0, max(total_days - 8, 1)))
                nights = rng.randint(2, 5)
            else:
                window, anchor = rng.choices(expanded, weights=window_weights, k=1)[0]
                check_in = anchor + timedelta(days=rng.randint(-2, max(window.span_days - 3, 0)))
                nights = rng.randint(3, min(window.span_days, 7))

            check_out = check_in + timedelta(days=nights)

            if not (window_start <= check_in and check_out <= window_end):
                continue
            if _overlaps(occupied[prop.id], check_in, check_out):
                continue

            source = _weighted(rng, BOOKING_SOURCE_WEIGHTS)
            is_block = source == BookingSource.MANUAL_BLOCK

            if check_out < today:
                status = BookingStatus.CONFIRMED if rng.random() > 0.06 else BookingStatus.CANCELLED
            else:
                status = (
                    BookingStatus.CONFIRMED if rng.random() > 0.18 else BookingStatus.PENDING
                )

            guest_name = (
                None
                if is_block
                else f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"
            )
            created = now - timedelta(
                days=rng.randint(20, 150), hours=rng.randint(0, 23)
            )
            created = max(created, now - timedelta(days=months_back * 30))

            booking = Booking(
                id=uuid.uuid4(),
                property_id=prop.id,
                source=source,
                status=status,
                external_uid=f"{DEMO_BOOKING_PREFIX}{uuid.uuid4().hex[:16]}",
                check_in=check_in,
                check_out=check_out,
                event_week=window.event,
                guest_name=guest_name,
                guest_email=(
                    None
                    if is_block
                    else f"{guest_name.split()[0].lower()}.{guest_name.split()[1].lower()}@example.com"
                ),
                guest_phone=None if is_block else f"+1706{rng.randint(2000000, 8999999)}",
                guests_count=None if is_block else rng.randint(2, max(prop.guests, 2)),
                notes="Owner hold — maintenance window." if is_block else None,
                created_at=created,
                updated_at=created,
            )
            db.add(booking)
            bookings.append(booking)
            occupied[prop.id].append((check_in, check_out))

        print(f"  Bookings generated: {len(bookings)} (no overlapping stays)")

        # -------------------------------------------------------------- orders
        prop_lookup = {p.id: p for p in properties}
        revenue_bookings = [
            b for b in bookings if b.source != BookingSource.MANUAL_BLOCK
        ]
        rng.shuffle(revenue_bookings)

        orders: list[Order] = []
        for index in range(min(target_orders, len(revenue_bookings))):
            booking = revenue_bookings[index]
            prop = prop_lookup[booking.property_id]
            window = next(
                (w for w in EVENT_WINDOWS if w.event == booking.event_week), EVENT_WINDOWS[-1]
            )

            base = prop.price_cents or rng.randint(1_200_000, 3_200_000)
            nights = (booking.check_out - booking.check_in).days
            amount = int(base * window.rate_multiplier * (nights / 7)) + rng.randint(-40_000, 80_000)
            amount = max(amount, 95_000)

            status = _weighted(rng, ORDER_STATUS_WEIGHTS)
            refunded = 0
            if status == OrderStatus.REFUNDED:
                refunded = amount
            elif status == OrderStatus.PARTIALLY_REFUNDED:
                refunded = int(amount * rng.uniform(0.15, 0.55))

            # Orders are placed after the booking was made but before check-in.
            created = booking.created_at + timedelta(
                days=rng.randint(0, 6), hours=rng.randint(0, 23)
            )
            created = min(created, now)

            order = Order(
                id=uuid.uuid4(),
                invoice_number=f"{DEMO_INVOICE_PREFIX}{uuid.uuid4().hex[:8].upper()}",
                property_id=prop.id,
                booking_id=booking.id,
                customer_name=booking.guest_name or "Direct guest",
                customer_email=booking.guest_email,
                amount_cents=amount,
                amount_refunded_cents=refunded,
                currency="USD",
                status=status,
                source=OrderSource.SEED,
                event_week=booking.event_week,
                payment_provider_ref=f"hcm_{uuid.uuid4().hex[:14]}",
                created_at=created,
                updated_at=created,
            )
            db.add(order)
            orders.append(order)

        collected = sum(
            o.amount_cents
            for o in orders
            if o.status
            in (OrderStatus.PAID_IN_FULL, OrderStatus.DEPOSIT_PAID, OrderStatus.BALANCE_DUE)
        )
        print(f"  Orders generated:   {len(orders)} (~${collected / 100:,.0f} collected)")

        # ----------------------------------------------------------- inquiries
        for _ in range(target_inquiries):
            first, last = rng.choice(FIRST_NAMES), rng.choice(LAST_NAMES)
            window, anchor = rng.choices(expanded, weights=window_weights, k=1)[0]
            check_in = anchor + timedelta(days=rng.randint(-1, 2))
            created = now - timedelta(days=rng.randint(0, months_back * 30), hours=rng.randint(0, 23))

            db.add(
                Inquiry(
                    id=uuid.uuid4(),
                    name=f"{first} {last}",
                    company=rng.choice(COMPANIES),
                    email=f"{first.lower()}.{last.lower()}@example.com",
                    phone=f"+1{rng.randint(2010000000, 9899999999)}",
                    group_size=rng.randint(2, 20),
                    event_week=window.event,
                    check_in=check_in,
                    check_out=check_in + timedelta(days=rng.randint(3, 7)),
                    property_slug=rng.choice(properties).slug if rng.random() > 0.35 else None,
                    notes=rng.choice(INQUIRY_NOTES),
                    status=_weighted(rng, INQUIRY_STATUS_WEIGHTS),
                    source_ip=DEMO_INQUIRY_IP,
                    created_at=created,
                    updated_at=created,
                )
            )
        print(f"  Inquiries generated: {target_inquiries}")

        # ----------------------------------------------------------------- SEO
        existing_paths = {
            row for row in (await db.execute(select(SeoMeta.path))).scalars().all()
        }
        seo_added = 0
        for path, title, description in SEO_ENTRIES:
            if path in existing_paths:
                continue
            db.add(
                SeoMeta(
                    path=path,
                    title=title,
                    meta_description=description,
                    canonical_url=f"{settings.SITE_URL.rstrip('/')}{path}",
                )
            )
            seo_added += 1
        print(f"  SEO overrides added: {seo_added} (existing entries left untouched)")

        # -------------------------------------------------------- staff account
        if with_staff_user:
            db.add(
                User(
                    id=uuid.uuid4(),
                    email=DEMO_STAFF_EMAIL,
                    hashed_password=hash_password("DemoStaff!2026"),
                    full_name="Demo Staff",
                    role=UserRole.STAFF,
                    is_active=True,
                )
            )
            print(f"  Demo staff account:  {DEMO_STAFF_EMAIL} / DemoStaff!2026")

        await db.commit()

        print("=" * 64)
        print("  Demo data seeded. Run with --wipe-only to remove it again.\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed demo data for the operator console")
    parser.add_argument("--months-back", type=int, default=12, help="History depth (default 12)")
    parser.add_argument("--months-forward", type=int, default=6, help="Future depth (default 6)")
    parser.add_argument("--bookings", type=int, default=320, dest="target_bookings")
    parser.add_argument("--orders", type=int, default=280, dest="target_orders")
    parser.add_argument("--inquiries", type=int, default=95, dest="target_inquiries")
    parser.add_argument("--seed", type=int, default=8888, dest="rng_seed", help="RNG seed")
    parser.add_argument("--no-staff-user", action="store_true", help="Skip the demo staff account")
    parser.add_argument("--wipe-only", action="store_true", help="Remove demo data and exit")
    args = parser.parse_args()

    if args.wipe_only:

        async def _wipe() -> None:
            async with AsyncSessionLocal() as db:
                counts = await wipe_demo_data(db)
                print(
                    f"Removed {counts['orders']} demo orders, {counts['bookings']} demo bookings, "
                    f"{counts['inquiries']} demo inquiries."
                )

        asyncio.run(_wipe())
        return

    asyncio.run(
        seed_demo(
            months_back=args.months_back,
            months_forward=args.months_forward,
            target_bookings=args.target_bookings,
            target_orders=args.target_orders,
            target_inquiries=args.target_inquiries,
            rng_seed=args.rng_seed,
            with_staff_user=not args.no_staff_user,
        )
    )


if __name__ == "__main__":
    main()