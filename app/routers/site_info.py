from fastapi import APIRouter

from app.core.config import settings

router = APIRouter(tags=["site-info"])


@router.get("/site-info")
async def site_info() -> dict:
    """Feeds the frontend footer, contact links, and JSON-LD schema — one source of truth
    so the phone/email/business name only ever need to change in one place (env vars)."""
    return {
        "business_name": settings.BUSINESS_NAME,
        "phone": settings.BUSINESS_PHONE,
        "email": settings.BUSINESS_EMAIL,
        "site_url": settings.SITE_URL,
    }
