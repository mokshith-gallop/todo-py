from fastapi import APIRouter

from app.api.v1.lists import router as lists_router
from app.api.v1.tasks import router as tasks_router

v1_router = APIRouter(prefix="/v1")
v1_router.include_router(lists_router)
v1_router.include_router(tasks_router)
