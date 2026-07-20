from uuid import UUID

from pydantic import BaseModel, ConfigDict, HttpUrl


class CaoCreate(BaseModel):
    name: str
    slug: str
    sector: str | None = None
    source_name: str = "FNV"
    source_url: HttpUrl


class CaoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str
    sector: str | None
    source_name: str
    source_url: str
    is_active: bool