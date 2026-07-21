from __future__ import annotations

import asyncio
import hashlib
from datetime import datetime, timezone
from pathlib import PurePosixPath
from urllib.parse import unquote, urlparse
from uuid import UUID

import httpx

from app.config import Settings
from app.db.repository import SupabaseRepository
from app.models.api import PipelineRunRequest
from app.models.domain import CaoPage
from app.parser.pdf_salary_parser import PdfSalaryParser
from app.scraper.fnv_crawler import FnvCrawler
from app.utils.text import sha256_bytes


class PipelineService:
    def __init__(
        self,
        *,
        settings: Settings,
        repository: SupabaseRepository,
        http_client: httpx.AsyncClient,
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.http_client = http_client
        self.parser = PdfSalaryParser()

    async def run(self, run_id: UUID, request: PipelineRunRequest) -> None:
        stats: dict[str, int] = {
            "discovered_caos": 0,
            "processed_caos": 0,
            "failed_caos": 0,
            "discovered_pdfs": 0,
            "new_documents": 0,
            "skipped_documents": 0,
            "processed_documents": 0,
            "failed_documents": 0,
            "salary_tables": 0,
            "salary_rows": 0,
        }
        errors: list[dict[str, str]] = []

        await self.repository.update_pipeline_run(
            run_id,
            status="running",
            started_at=datetime.now(timezone.utc).isoformat(),
            stats=stats,
        )

        try:
            crawler = FnvCrawler(
                self.http_client,
                start_url=self.settings.fnv_start_url,
                delay_seconds=self.settings.crawl_delay_seconds,
            )
            pages = await crawler.crawl(
                max_pages=request.max_pages,
                max_caos=request.max_caos,
            )
            stats["discovered_caos"] = len(pages)
            stats["discovered_pdfs"] = sum(len(page.pdfs) for page in pages)
            await self._save_progress(run_id, stats, errors)

            for page in pages:
                try:
                    await self._process_cao(page, request, stats, errors)
                    stats["processed_caos"] += 1
                except Exception as exc:  # individual CAO may fail without aborting all others
                    stats["failed_caos"] += 1
                    errors.append({"cao": page.name, "error": str(exc)})
                await self._save_progress(run_id, stats, errors)

            final_status = "completed" if not errors else "partial"
            await self.repository.update_pipeline_run(
                run_id,
                status=final_status,
                finished_at=datetime.now(timezone.utc).isoformat(),
                stats={**stats, "errors": errors[-100:]},
            )
        except Exception as exc:
            await self.repository.update_pipeline_run(
                run_id,
                status="failed",
                finished_at=datetime.now(timezone.utc).isoformat(),
                stats={**stats, "errors": errors[-100:]},
                error_message=str(exc),
            )

    async def _process_cao(
        self,
        page: CaoPage,
        request: PipelineRunRequest,
        stats: dict[str, int],
        errors: list[dict[str, str]],
    ) -> None:
        cao = await self.repository.upsert_cao(page)
        downloads: list[tuple[object, bytes, str, str]] = []

        for pdf in page.pdfs:
            try:
                content = await self._download_pdf(pdf.url)
                filename = self._filename(pdf.url)
                digest = sha256_bytes(content)
                downloads.append((pdf, content, filename, digest))
            except Exception as exc:
                stats["failed_documents"] += 1
                errors.append({"document": pdf.url, "error": str(exc)})

        if not downloads:
            return

        primary = next(
            (item for item in downloads if getattr(item[0], "document_type") == "cao"),
            downloads[0],
        )
        fingerprint_seed = "|".join(
            [
                page.source_url,
                str(page.effective_from or ""),
                str(page.effective_to or ""),
                primary[3],
            ]
        )
        source_fingerprint = hashlib.sha256(fingerprint_seed.encode("utf-8")).hexdigest()
        version_label = self._version_label(page, primary[2])
        version = await self.repository.get_or_create_version(
            cao_id=cao["id"],
            source_fingerprint=source_fingerprint,
            version_label=version_label,
            effective_from=page.effective_from,
            effective_to=page.effective_to,
        )
        await self.repository.update_version_status(version["id"], "processing")

        version_failed = False
        version_review_required = False
        for pdf, content, filename, digest in downloads:
            existing = await self.repository.find_document(version["id"], digest)
            if existing and not request.reprocess_existing:
                stats["skipped_documents"] += 1
                continue

            document = existing or await self.repository.create_document(
                version_id=version["id"],
                document_type=pdf.document_type,
                title=pdf.title,
                filename=filename,
                source_url=pdf.url,
                sha256=digest,
                file_size_bytes=len(content),
            )
            if not existing:
                stats["new_documents"] += 1

            processing_run = await self.repository.create_processing_run(document["id"])
            try:
                parsed = await asyncio.to_thread(self.parser.parse, content, filename)
                await self.repository.update_document_page_count(document["id"], parsed.page_count)
                table_count, row_count = await self.repository.replace_salary_data(
                    document["id"], parsed
                )
                stats["processed_documents"] += 1
                stats["salary_tables"] += table_count
                stats["salary_rows"] += row_count

                has_review = any(
                    table.review_status == "review_required" for table in parsed.tables
                )
                version_review_required = version_review_required or has_review
                status = "review_required" if has_review else "completed"
                await self.repository.finish_processing_run(
                    processing_run["id"],
                    status=status,
                    raw_output={
                        "filename": filename,
                        "candidate_pages": parsed.candidate_pages,
                        "salary_table_count": table_count,
                        "salary_row_count": row_count,
                        "warnings": parsed.warnings,
                    },
                )
            except Exception as exc:
                version_failed = True
                stats["failed_documents"] += 1
                errors.append({"document": pdf.url, "error": str(exc)})
                await self.repository.finish_processing_run(
                    processing_run["id"],
                    status="failed",
                    error_message=str(exc),
                )

        if version_failed:
            status = "failed"
        elif version_review_required:
            status = "review_required"
        else:
            status = "processed"
        await self.repository.update_version_status(version["id"], status)

    async def _download_pdf(self, url: str) -> bytes:
        response = await self.http_client.get(url)
        response.raise_for_status()
        content_type = response.headers.get("content-type", "").lower()
        content = response.content
        if not content.startswith(b"%PDF") and "application/pdf" not in content_type:
            raise ValueError("De download is geen PDF-bestand.")
        if len(content) > self.settings.max_pdf_size_bytes:
            raise ValueError(
                f"PDF is groter dan {self.settings.max_pdf_size_mb} MB en wordt overgeslagen."
            )
        return content

    async def _save_progress(
        self,
        run_id: UUID,
        stats: dict[str, int],
        errors: list[dict[str, str]],
    ) -> None:
        await self.repository.update_pipeline_run(
            run_id,
            stats={**stats, "errors": errors[-100:]},
        )

    @staticmethod
    def _filename(url: str) -> str:
        name = unquote(PurePosixPath(urlparse(url).path).name)
        return name if name.lower().endswith(".pdf") else f"{name or 'document'}.pdf"

    @staticmethod
    def _version_label(page: CaoPage, filename: str) -> str:
        if page.effective_from and page.effective_to:
            return f"{page.effective_from.isoformat()} t/m {page.effective_to.isoformat()}"
        if page.effective_from:
            return f"Vanaf {page.effective_from.isoformat()}"
        return filename
