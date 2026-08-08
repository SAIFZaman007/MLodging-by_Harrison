from fastapi import APIRouter

from app.routers import admin, auth, bookings, inquiries, orders, properties, seo, site_info

api_router = APIRouter()

api_router.include_router(site_info.router)
api_router.include_router(auth.router)
api_router.include_router(properties.router)
api_router.include_router(bookings.router)
api_router.include_router(inquiries.router)
api_router.include_router(orders.router)
api_router.include_router(admin.router)
api_router.include_router(seo.router)
