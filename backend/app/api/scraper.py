from fastapi import APIRouter, HTTPException

from app.schemas.scraper import (
    DiscoverPdfRequest,
    DiscoverPdfResponse,
)
from app.scraper.pdf_discovery import (
    PdfDiscoveryError,
    discover_pdf_links,
)


router = APIRouter(
    prefix="/scraper",
    tags=["Scraper"],
)


@router.post(
    "/discover-pdfs",
    response_model=DiscoverPdfResponse,
)
def discover_pdfs(
    payload: DiscoverPdfRequest,
) -> DiscoverPdfResponse:
    page_url = str(payload.page_url)

    try:
        pdfs = discover_pdf_links(page_url)

    except PdfDiscoveryError as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        ) from exc

    return DiscoverPdfResponse(
        page_url=page_url,
        pdf_count=len(pdfs),
        pdfs=pdfs,
    )