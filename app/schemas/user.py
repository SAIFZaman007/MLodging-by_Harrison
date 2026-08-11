import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.enums import UserRole


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    full_name: str
    role: UserRole
    is_active: bool
    created_at: datetime


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    full_name: str = Field(min_length=1, max_length=255)
    role: UserRole = UserRole.STAFF


class UserUpdate(BaseModel):
    """PATCH semantics. Password is intentionally NOT here — it has its own
    endpoint so a password change is always an explicit, auditable action."""

    email: EmailStr | None = None
    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    role: UserRole | None = None
    is_active: bool | None = None


class PasswordReset(BaseModel):
    """Admin-initiated reset for another operator's account."""

    new_password: str = Field(min_length=10, max_length=128)


class PasswordChange(BaseModel):
    """Self-service change — requires proof of the current password."""

    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=10, max_length=128)