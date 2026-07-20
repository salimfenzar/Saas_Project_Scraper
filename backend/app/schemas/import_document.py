from typing import Literal
from uuid import UUID

from pydantic import BaseModel, HttpUrl


class ImportDocumentRequest(BaseModel):
    cao_id: UUID
    pdf_url: HttpUrl
    title: str | None = None
    document_type: Literal[
        "cao",
        "salary_table",
        "appendix",
        "amendment",
        "other",
    ] = "cao"