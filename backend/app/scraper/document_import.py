import hashlib
from pathlib import Path
from urllib.parse import urlparse

import httpx

from app.database import supabase


DOWNLOAD_DIR = Path("downloads")


class DocumentImportError(Exception):
    pass


def download_pdf(pdf_url: str) -> tuple[bytes, str]:
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; CAOMonitorBot/0.1)"
    }

    try:
        response = httpx.get(
            pdf_url,
            headers=headers,
            timeout=60.0,
            follow_redirects=True,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise DocumentImportError(
            f"PDF kon niet worden gedownload: {exc}"
        ) from exc

    content_type = response.headers.get("content-type", "").lower()

    if "pdf" not in content_type and not response.content.startswith(b"%PDF"):
        raise DocumentImportError(
            "De gedownloade inhoud lijkt geen geldige PDF te zijn."
        )

    filename = Path(urlparse(str(response.url)).path).name

    if not filename:
        filename = "document.pdf"

    if not filename.lower().endswith(".pdf"):
        filename += ".pdf"

    return response.content, filename


def calculate_sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def save_pdf_locally(content: bytes, filename: str, sha256: str) -> str:
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

    safe_filename = f"{sha256[:12]}-{filename}"
    file_path = DOWNLOAD_DIR / safe_filename
    file_path.write_bytes(content)

    return str(file_path)


def import_cao_document(
    cao_id: str,
    pdf_url: str,
    title: str | None = None,
    document_type: str = "cao",
) -> dict:
    content, filename = download_pdf(pdf_url)
    sha256 = calculate_sha256(content)

    existing = (
        supabase.table("documents")
        .select("id,cao_version_id,sha256,filename")
        .eq("sha256", sha256)
        .limit(1)
        .execute()
    )

    if existing.data:
        return {
            "status": "duplicate",
            "document": existing.data[0],
        }

    version_result = (
        supabase.table("cao_versions")
        .insert(
            {
                "cao_id": cao_id,
                "version_label": filename,
                "status": "discovered",
            }
        )
        .execute()
    )

    if not version_result.data:
        raise DocumentImportError(
            "CAO-versie kon niet worden aangemaakt."
        )

    version = version_result.data[0]
    storage_path = save_pdf_locally(content, filename, sha256)

    try:
        document_result = (
            supabase.table("documents")
            .insert(
                {
                    "cao_version_id": version["id"],
                    "document_type": document_type,
                    "title": title,
                    "filename": filename,
                    "source_url": pdf_url,
                    "storage_path": storage_path,
                    "mime_type": "application/pdf",
                    "sha256": sha256,
                    "file_size_bytes": len(content),
                }
            )
            .execute()
        )

        if not document_result.data:
            raise DocumentImportError(
                "Document kon niet worden opgeslagen."
            )

    except Exception:
        supabase.table("cao_versions").delete().eq(
            "id",
            version["id"],
        ).execute()
        raise

    return {
        "status": "imported",
        "version": version,
        "document": document_result.data[0],
    }