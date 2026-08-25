from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class HealthResponse(BaseModel):
    status: str


@router.get("/api/health")
def health() -> HealthResponse:
    return {"status": "ok"}
