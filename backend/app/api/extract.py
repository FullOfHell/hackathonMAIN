from fastapi import APIRouter

from app.schemas import IntakeRequest, IntakeResponse
from app.services.intake import extract


router = APIRouter(prefix="/api/intake", tags=["intake"])


@router.post("/extract", response_model=IntakeResponse)
def extract_intake(draft: IntakeRequest) -> IntakeResponse:
    return extract(draft)
