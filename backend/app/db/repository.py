from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Callable
from uuid import UUID

from supabase import Client

from app.models.domain import CaoPage, ParsedDocument, ParsedSalaryTable


class RepositoryError(RuntimeError):
    pass


class SupabaseRepository:
    """Small async wrapper around the synchronous Supabase Python client."""

    def __init__(self, client: Client) -> None:
        self.client = client

    async def _run(self, operation: Callable[[], Any]) -> Any:
        try:
            response = await asyncio.to_thread(operation)
            return response.data
        except Exception as exc:  # pragma: no cover - external SDK errors differ by version
            raise RepositoryError(str(exc)) from exc

    async def healthcheck(self) -> bool:
        await self._run(
            lambda: self.client.table("caos").select("id").limit(1).execute()
        )
        return True

    async def create_pipeline_run(self, request_payload: dict[str, Any]) -> dict[str, Any]:
        rows = await self._run(
            lambda: self.client.table("pipeline_runs")
            .insert(
                {
                    "status": "queued",
                    "request": request_payload,
                    "stats": {},
                }
            )
            .execute()
        )
        return rows[0]

    async def get_pipeline_run(self, run_id: str | UUID) -> dict[str, Any] | None:
        rows = await self._run(
            lambda: self.client.table("pipeline_runs")
            .select("*")
            .eq("id", str(run_id))
            .limit(1)
            .execute()
        )
        return rows[0] if rows else None

    async def get_active_pipeline_run(self) -> dict[str, Any] | None:
        rows = await self._run(
            lambda: self.client.table("pipeline_runs")
            .select("*")
            .in_("status", ["queued", "running"])
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        return rows[0] if rows else None

    async def update_pipeline_run(self, run_id: str | UUID, **fields: Any) -> None:
        await self._run(
            lambda: self.client.table("pipeline_runs")
            .update(fields)
            .eq("id", str(run_id))
            .execute()
        )

    async def mark_stale_runs_failed(self) -> None:
        now = datetime.now(timezone.utc).isoformat()
        await self._run(
            lambda: self.client.table("pipeline_runs")
            .update(
                {
                    "status": "failed",
                    "finished_at": now,
                    "error_message": "Backend werd opnieuw gestart tijdens deze run.",
                }
            )
            .in_("status", ["queued", "running"])
            .execute()
        )

    async def upsert_cao(self, page: CaoPage) -> dict[str, Any]:
        payload = {
            "name": page.name,
            "slug": page.slug,
            "sector": page.sector,
            "source_name": "FNV",
            "source_url": page.source_url,
            "effective_from": page.effective_from.isoformat() if page.effective_from else None,
            "effective_to": page.effective_to.isoformat() if page.effective_to else None,
            "is_active": True,
            "last_checked_at": datetime.now(timezone.utc).isoformat(),
        }
        rows = await self._run(
            lambda: self.client.table("caos")
            .upsert(payload, on_conflict="source_url")
            .execute()
        )
        return rows[0]

    async def get_or_create_version(
        self,
        *,
        cao_id: str,
        source_fingerprint: str,
        version_label: str,
        effective_from: date | None,
        effective_to: date | None,
    ) -> dict[str, Any]:
        existing = await self._run(
            lambda: self.client.table("cao_versions")
            .select("*")
            .eq("cao_id", cao_id)
            .eq("source_fingerprint", source_fingerprint)
            .limit(1)
            .execute()
        )
        if existing:
            return existing[0]

        payload = {
            "cao_id": cao_id,
            "source_fingerprint": source_fingerprint,
            "version_label": version_label,
            "effective_from": effective_from.isoformat() if effective_from else None,
            "effective_to": effective_to.isoformat() if effective_to else None,
            "status": "discovered",
        }
        rows = await self._run(
            lambda: self.client.table("cao_versions").insert(payload).execute()
        )
        return rows[0]

    async def update_version_status(self, version_id: str, status: str) -> None:
        await self._run(
            lambda: self.client.table("cao_versions")
            .update({"status": status})
            .eq("id", version_id)
            .execute()
        )

    async def find_document(self, version_id: str, sha256: str) -> dict[str, Any] | None:
        rows = await self._run(
            lambda: self.client.table("documents")
            .select("*")
            .eq("cao_version_id", version_id)
            .eq("sha256", sha256)
            .limit(1)
            .execute()
        )
        return rows[0] if rows else None

    async def create_document(
        self,
        *,
        version_id: str,
        document_type: str,
        title: str,
        filename: str,
        source_url: str,
        sha256: str,
        file_size_bytes: int,
    ) -> dict[str, Any]:
        payload = {
            "cao_version_id": version_id,
            "document_type": document_type,
            "title": title,
            "filename": filename,
            "source_url": source_url,
            "sha256": sha256,
            "file_size_bytes": file_size_bytes,
            "mime_type": "application/pdf",
        }
        rows = await self._run(
            lambda: self.client.table("documents").insert(payload).execute()
        )
        return rows[0]

    async def update_document_page_count(self, document_id: str, page_count: int) -> None:
        await self._run(
            lambda: self.client.table("documents")
            .update({"page_count": page_count})
            .eq("id", document_id)
            .execute()
        )

    async def create_processing_run(self, document_id: str) -> dict[str, Any]:
        rows = await self._run(
            lambda: self.client.table("processing_runs")
            .insert(
                {
                    "document_id": document_id,
                    "status": "running",
                    "parser_version": "2.0.0",
                    "started_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            .execute()
        )
        return rows[0]

    async def finish_processing_run(
        self,
        run_id: str,
        *,
        status: str,
        raw_output: dict[str, Any] | None = None,
        error_message: str | None = None,
    ) -> None:
        await self._run(
            lambda: self.client.table("processing_runs")
            .update(
                {
                    "status": status,
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                    "raw_output": raw_output,
                    "error_message": error_message,
                }
            )
            .eq("id", run_id)
            .execute()
        )

    async def replace_salary_data(
        self,
        document_id: str,
        parsed: ParsedDocument,
    ) -> tuple[int, int]:
        existing_tables = await self._run(
            lambda: self.client.table("salary_tables")
            .select("id")
            .eq("document_id", document_id)
            .execute()
        )
        if existing_tables:
            table_ids = [item["id"] for item in existing_tables]
            await self._run(
                lambda: self.client.table("salary_tables")
                .delete()
                .in_("id", table_ids)
                .execute()
            )

        table_count = 0
        row_count = 0
        for table in parsed.tables:
            table_id = await self._insert_salary_table(document_id, table)
            if table.rows:
                await self._insert_salary_rows(table_id, table)
            table_count += 1
            row_count += len(table.rows)
        return table_count, row_count

    async def _insert_salary_table(
        self,
        document_id: str,
        table: ParsedSalaryTable,
    ) -> str:
        payload = {
            "document_id": document_id,
            "title": table.title,
            "effective_date": table.effective_date.isoformat() if table.effective_date else None,
            "period": table.period,
            "currency": "EUR",
            "hours_per_week": self._decimal(table.hours_per_week),
            "source_page_start": table.source_page_start,
            "source_page_end": table.source_page_end,
            "extraction_method": "automatic",
            "confidence": table.confidence,
            "review_status": table.review_status,
        }
        rows = await self._run(
            lambda: self.client.table("salary_tables").insert(payload).execute()
        )
        return rows[0]["id"]

    async def _insert_salary_rows(
        self,
        table_id: str,
        table: ParsedSalaryTable,
    ) -> None:
        payload = []
        for row in table.rows:
            payload.append(
                {
                    "salary_table_id": table_id,
                    "row_key": row.row_key(),
                    "scale_name": row.scale_name,
                    "step_name": row.step_name,
                    "amount": self._decimal(row.amount),
                    "min_age": row.min_age,
                    "max_age": row.max_age,
                    "row_order": row.row_order,
                    "source_text": row.source_text,
                    "component_type": row.component_type,
                    "amount_period": row.amount_period,
                    "rsp_percentage": self._decimal(row.rsp_percentage),
                    "metadata": row.metadata,
                    "source_page": row.source_page,
                }
            )
        await self._run(
            lambda: self.client.table("salary_scale_rows").insert(payload).execute()
        )

    async def list_caos(
        self,
        *,
        limit: int,
        offset: int,
        search: str | None,
    ) -> list[dict[str, Any]]:
        def operation() -> Any:
            query = (
                self.client.table("caos")
                .select("*")
                .order("name")
                .range(offset, offset + limit - 1)
            )
            if search:
                query = query.ilike("name", f"%{search}%")
            return query.execute()

        return await self._run(operation)

    async def get_cao(self, cao_id: str) -> dict[str, Any] | None:
        rows = await self._run(
            lambda: self.client.table("caos")
            .select("*")
            .eq("id", cao_id)
            .limit(1)
            .execute()
        )
        return rows[0] if rows else None

    async def get_cao_salary_data(self, cao_id: str) -> dict[str, Any]:
        versions = await self._run(
            lambda: self.client.table("cao_versions")
            .select("*")
            .eq("cao_id", cao_id)
            .order("effective_from", desc=True)
            .execute()
        )
        if not versions:
            return {"versions": [], "documents": [], "salary_tables": []}

        version_ids = [item["id"] for item in versions]
        documents = await self._run(
            lambda: self.client.table("documents")
            .select("*")
            .in_("cao_version_id", version_ids)
            .execute()
        )
        if not documents:
            return {"versions": versions, "documents": [], "salary_tables": []}

        document_ids = [item["id"] for item in documents]
        tables = await self._run(
            lambda: self.client.table("salary_tables")
            .select("*")
            .in_("document_id", document_ids)
            .order("effective_date", desc=True)
            .execute()
        )
        if not tables:
            return {"versions": versions, "documents": documents, "salary_tables": []}

        table_ids = [item["id"] for item in tables]
        rows = await self._run(
            lambda: self.client.table("salary_scale_rows")
            .select("*")
            .in_("salary_table_id", table_ids)
            .order("row_order")
            .execute()
        )
        rows_by_table: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            rows_by_table.setdefault(row["salary_table_id"], []).append(row)
        for table in tables:
            table["rows"] = rows_by_table.get(table["id"], [])
        return {
            "versions": versions,
            "documents": documents,
            "salary_tables": tables,
        }

    async def dashboard_summary(self) -> dict[str, int]:
        tables = [
            "caos",
            "cao_versions",
            "documents",
            "salary_tables",
            "salary_scale_rows",
            "salary_changes",
        ]
        result: dict[str, int] = {}
        for table in tables:
            response = await asyncio.to_thread(
                lambda table=table: self.client.table(table)
                .select("id", count="exact")
                .limit(1)
                .execute()
            )
            result[table] = int(response.count or 0)
        return result

    async def reset_data(self) -> None:
        await self._run(lambda: self.client.rpc("reset_cao_monitor_data").execute())

    @staticmethod
    def _decimal(value: Decimal | None) -> str | None:
        return str(value) if value is not None else None
