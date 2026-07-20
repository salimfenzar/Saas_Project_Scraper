from pydantic import BaseModel, HttpUrl


class DiscoverPdfRequest(BaseModel):
    page_url: HttpUrl


class PdfLink(BaseModel):
    title: str | None = None
    url: str
    document_type: str


class DiscoverPdfResponse(BaseModel):
    page_url: str
    pdf_count: int
    pdfs: list[PdfLink]