from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any


@dataclass(slots=True)
class DiscoveredPdf:
    title: str
    url: str
    document_type: str


@dataclass(slots=True)
class CaoPage:
    name: str
    slug: str
    sector: str | None
    source_url: str
    effective_from: date | None
    effective_to: date | None
    pdfs: list[DiscoveredPdf] = field(default_factory=list)


@dataclass(slots=True)
class ParsedSalaryRow:
    scale_name: str
    step_name: str
    amount: Decimal
    component_type: str
    amount_period: str
    source_page: int
    row_order: int
    min_age: int | None = None
    max_age: int | None = None
    rsp_percentage: Decimal | None = None
    source_text: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def row_key(self) -> str:
        age_key = f"{self.min_age or ''}-{self.max_age or ''}"
        rsp_key = str(self.rsp_percentage or "")
        return "|".join(
            [
                self.scale_name.strip().lower(),
                self.step_name.strip().lower(),
                self.component_type,
                self.amount_period,
                age_key,
                rsp_key,
            ]
        )


@dataclass(slots=True)
class ParsedSalaryTable:
    title: str
    effective_date: date | None
    period: str
    source_page_start: int
    source_page_end: int
    confidence: float
    review_status: str
    rows: list[ParsedSalaryRow] = field(default_factory=list)
    hours_per_week: Decimal | None = None


@dataclass(slots=True)
class ParsedDocument:
    page_count: int
    candidate_pages: list[int]
    tables: list[ParsedSalaryTable]
    warnings: list[str] = field(default_factory=list)
