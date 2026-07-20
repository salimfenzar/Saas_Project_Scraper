from fastapi import APIRouter, HTTPException

from app.schemas.import_document import ImportDocumentRequest
from app.scraper.document_import import (
    DocumentImportError,
    import_cao_document,
)


router = APIRouter(
    prefix="/imports",
    tags=["Imports"],
)


@router.post("/document")
def import_document(payload: ImportDocumentRequest) -> dict:
    try:
        return import_cao_document(
            cao_id=str(payload.cao_id),
            pdf_url=str(payload.pdf_url),
            title=payload.title,
            document_type=payload.document_type,
        )

    except DocumentImportError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        print("Importfout:", repr(exc))

        raise HTTPException(
            status_code=500,
            detail="Onverwachte fout tijdens het importeren.",
        ) from exc