import enum


class UserRole(str, enum.Enum):
    ADMIN = "admin"       # full access — Chris / owner-operator
    STAFF = "staff"       # manages properties/bookings, no user management
    GUEST = "guest"       # reserved for future guest-account login


class BookingSource(str, enum.Enum):
    DIRECT = "direct"             # booked through 8888masters.com
    AIRBNB = "airbnb"             # pulled in via Airbnb iCal sync
    VRBO = "vrbo"                 # pulled in via VRBO iCal sync
    MANUAL_BLOCK = "manual_block" # operator manually blocked the dates


class BookingStatus(str, enum.Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class OrderStatus(str, enum.Enum):
    PENDING = "pending"
    DEPOSIT_PAID = "deposit_paid"
    BALANCE_DUE = "balance_due"
    PAID_IN_FULL = "paid_in_full"
    REFUNDED = "refunded"
    PARTIALLY_REFUNDED = "partially_refunded"
    CANCELLED = "cancelled"
    FAILED = "failed"


# Statuses that represent real money currently collected (mirrors legacy admin-data.js)
PAID_ORDER_STATUSES = {
    OrderStatus.DEPOSIT_PAID,
    OrderStatus.BALANCE_DUE,
    OrderStatus.PAID_IN_FULL,
}


class OrderSource(str, enum.Enum):
    HELCIM_WEBHOOK = "helcim_webhook"
    MANUAL = "manual"
    SEED = "seed"


class EventWeek(str, enum.Enum):
    MASTERS = "masters"
    ANWA = "anwa"
    IRONMAN = "ironman"
    PEACH_JAM = "peach-jam"
    PRIVATE_EVENT = "private-event"
    STUDENT_LIVING = "student-living"
    OTHER = "other"


class InquiryStatus(str, enum.Enum):
    NEW = "new"
    CONTACTED = "contacted"
    CONVERTED = "converted"
    ARCHIVED = "archived"
