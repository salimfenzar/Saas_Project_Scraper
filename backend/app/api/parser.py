from fastapi import APIRouter, HTTPException

from app.database import supabase
from app.parser.pdf_text import (
    PdfParseError,
    extract_pdf_pages,
)
from app.parser.salary_tables import (
    SalaryTableExtractionError,
    extract_salary_tables,
)
from app.schemas.salary_table import ExtractSalaryTablesRequest
from app.parser.salary_normalizer import normalize_salary_tables
from app.services.salary_storage import (
    SalaryStorageError,
    store_salary_rows,
)

router = APIRouter(
    prefix="/parser",
    tags=["Parser"],
)


@router.post("/documents/{document_id}/extract-text")
def extract_document_text(document_id: str) -> dict:
    result = (
        supabase.table("documents")
        .select("id,storage_path")
        .eq("id", document_id)
        .limit(1)
        .execute()
    )

    if not result.data:
        raise HTTPException(
            status_code=404,
            detail="Document niet gevonden.",
        )

    document = result.data[0]
    storage_path = document.get("storage_path")

    if not storage_path:
        raise HTTPException(
            status_code=422,
            detail="Document heeft geen lokaal opslagpad.",
        )

    try:
        pages = extract_pdf_pages(storage_path)
    except PdfParseError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    salary_pages = [
        {
            "page_number": page["page_number"],
            "matched_keywords": page["matched_keywords"],
            "preview": page["text"][:500],
        }
        for page in pages
        if page["is_salary_candidate"]
    ]

    supabase.table("documents").update(
        {
            "page_count": len(pages),
        }
    ).eq(
        "id",
        document_id,
    ).execute()

    return {
        "document_id": document_id,
        "page_count": len(pages),
        "salary_candidate_count": len(salary_pages),
        "salary_pages": salary_pages,
    }
    
@router.post("/documents/{document_id}/extract-salary-tables")
def extract_document_salary_tables(document_id: str, payload: ExtractSalaryTablesRequest,) -> dict:
    result = (
        supabase.table("documents")
        .select("id,title,filename,storage_path")
        .eq("id", document_id)
        .limit(1)
        .execute()
    )

    if not result.data:
        raise HTTPException(
            status_code=404,
            detail="Document niet gevonden.",
        )

    document = result.data[0]
    storage_path = document.get("storage_path")

    if not storage_path:
        raise HTTPException(
            status_code=422,
            detail="Document heeft geen opslagpad.",
        )

    try:
        pages = extract_salary_tables(
            file_path=storage_path,
            page_numbers=payload.page_numbers,
        )

    except SalaryTableExtractionError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    normalized_rows = normalize_salary_tables(pages)

    return {
        "document_id": document_id,
        "filename": document["filename"],
        "requested_pages": payload.page_numbers,
        "normalized_row_count": len(normalized_rows),
        "salary_rows": normalized_rows,
        "raw_pages": pages,
    }
    
@router.post(
    "/documents/{document_id}/extract-and-store-salary-tables"
)
def extract_and_store_salary_tables(
    document_id: str,
    payload: ExtractSalaryTablesRequest,
) -> dict:
    result = (
        supabase.table("documents")
        .select("id,title,filename,storage_path")
        .eq("id", document_id)
        .limit(1)
        .execute()
    )

    if not result.data:
        raise HTTPException(
            status_code=404,
            detail="Document niet gevonden.",
        )

    document = result.data[0]
    storage_path = document.get("storage_path")

    if not storage_path:
        raise HTTPException(
            status_code=422,
            detail="Document heeft geen opslagpad.",
        )

    try:
        pages = extract_salary_tables(
            file_path=storage_path,
            page_numbers=payload.page_numbers,
        )

        normalized_rows = normalize_salary_tables(pages)

        storage_result = store_salary_rows(
            document_id=document_id,
            salary_rows=normalized_rows,
        )

    except SalaryTableExtractionError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    except SalaryStorageError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    return {
        "document_id": document_id,
        "filename": document["filename"],
        "requested_pages": payload.page_numbers,
        "normalized_row_count": len(normalized_rows),
        **storage_result,
    }