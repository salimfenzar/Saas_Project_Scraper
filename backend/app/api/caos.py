from fastapi import APIRouter, HTTPException, status

from app.database import supabase
from app.schemas.cao import CaoCreate, CaoResponse


router = APIRouter(prefix="/caos", tags=["CAO's"])


@router.get("", response_model=list[CaoResponse])
def get_caos() -> list[dict]:
    result = (
        supabase.table("caos")
        .select(
            "id,name,slug,sector,source_name,"
            "source_url,is_active"
        )
        .order("name")
        .execute()
    )

    return result.data


@router.post(
    "",
    response_model=CaoResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_cao(payload: CaoCreate) -> dict:
    data = payload.model_dump(mode="json")

    result = (
        supabase.table("caos")
        .insert(data)
        .execute()
    )

    if not result.data:
        raise HTTPException(
            status_code=500,
            detail="CAO kon niet worden opgeslagen.",
        )

    return result.data[0]