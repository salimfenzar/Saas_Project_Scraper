from __future__ import annotations

import io
import re
from collections import defaultdict
from datetime import date
from decimal import Decimal
from statistics import median

import pdfplumber

from app.models.domain import ParsedDocument, ParsedSalaryRow, ParsedSalaryTable
from app.utils.text import clean_whitespace, parse_all_dutch_dates, parse_decimal

EURO_PATTERN = re.compile(r"€\s*\d{1,3}(?:\.\d{3})*(?:,\d{2})|€\s*\d+(?:,\d{2})")
SECTION_TITLE_PATTERN = re.compile(
    r"(?:salarisschalen?|loonschaal|loontabel|loongebouw).*?"
    r"(?:per|vanaf)\s+\d{1,2}\s+"
    r"(?:januari|februari|maart|april|mei|juni|juli|augustus|september|oktober|november|december)\s+20\d{2}",
    re.IGNORECASE,
)
SALARY_KEYWORDS = (
    "salarisschaal",
    "salarisschalen",
    "loonschaal",
    "loontabel",
    "loongebouw",
    "maandsalaris",
    "uurlonen",
    "uurloon",
    "rsp 100",
    "rsp 110",
)


class PdfSalaryParser:
    """Rule-based parser for machine-generated Dutch CAO PDFs.

    It deliberately stores a table as review_required when the structure is
    uncertain instead of inventing values.
    """

    def parse(self, content: bytes, filename: str) -> ParsedDocument:
        warnings: list[str] = []
        candidates: list[int] = []
        extracted_tables: list[ParsedSalaryTable] = []

        with pdfplumber.open(io.BytesIO(content)) as pdf:
            for page_number, page in enumerate(pdf.pages, start=1):
                text = page.extract_text(x_tolerance=2, y_tolerance=3) or ""
                normalized = clean_whitespace(text).lower()
                euro_count = len(EURO_PATTERN.findall(text))
                has_keyword = any(keyword in normalized for keyword in SALARY_KEYWORDS)
                has_section_title = bool(SECTION_TITLE_PATTERN.search(text))

                if not ((has_keyword and euro_count >= 4) or (has_section_title and euro_count >= 2)):
                    continue

                candidates.append(page_number)
                page_tables = self._parse_page(text, page_number)
                extracted_tables.extend(page_tables)

            if not candidates:
                warnings.append(
                    "Geen machineleesbare salaristabellen gevonden. Mogelijk is de PDF gescand."
                )

            merged_tables = self._merge_tables(extracted_tables)
            return ParsedDocument(
                page_count=len(pdf.pages),
                candidate_pages=candidates,
                tables=merged_tables,
                warnings=warnings,
            )

    def _parse_page(self, text: str, page_number: int) -> list[ParsedSalaryTable]:
        sections = self._split_sections(text)
        result: list[ParsedSalaryTable] = []
        for title, section_text in sections:
            if "rsp 100" in section_text.lower() and "rsp 110" in section_text.lower():
                table = self._parse_apg_rsp_section(title, section_text, page_number)
                if table.rows:
                    result.append(table)
                    continue

            table = self._parse_matrix_section(title, section_text, page_number)
            if table.rows:
                result.append(table)
                continue

            table = self._parse_simple_section(title, section_text, page_number)
            if table.rows:
                result.append(table)
        return result

    def _split_sections(self, text: str) -> list[tuple[str, str]]:
        lines = [clean_whitespace(line) for line in text.splitlines() if clean_whitespace(line)]
        starts: list[int] = []
        for index, line in enumerate(lines):
            if SECTION_TITLE_PATTERN.search(line):
                starts.append(index)

        if not starts:
            title = next(
                (line for line in lines if any(keyword in line.lower() for keyword in SALARY_KEYWORDS)),
                "Salaristabel",
            )
            return [(title, "\n".join(lines))]

        sections: list[tuple[str, str]] = []
        for position, start in enumerate(starts):
            end = starts[position + 1] if position + 1 < len(starts) else len(lines)
            title = lines[start]
            sections.append((title, "\n".join(lines[start:end])))
        return sections

    def _parse_matrix_section(
        self,
        title: str,
        text: str,
        page_number: int,
    ) -> ParsedSalaryTable:
        lines = [clean_whitespace(line) for line in text.splitlines() if clean_whitespace(line)]
        header_index = -1
        scales: list[str] = []
        for index, line in enumerate(lines):
            if "trede/schaal" not in line.lower() and "trede schaal" not in line.lower():
                continue
            header_index = index
            header_tail = re.split(r"trede\s*/?\s*schaal", line, flags=re.IGNORECASE)[-1]
            scales = [
                token.upper()
                for token in re.findall(r"\b(?:[A-Z]{1,4}|\d{1,2})\b", header_tail.upper())
                if token.upper() not in {"WML"}
            ]
            break

        if header_index < 0 or not scales:
            return self._empty_table(title, text, page_number)

        period = self.detect_period(text, [])
        effective_date = self._effective_date(title + "\n" + text)
        rows: list[ParsedSalaryRow] = []
        previous_line = ""
        order = 0

        for line in lines[header_index + 1 :]:
            age_match = re.match(r"^(15|16|17|18)\s*jaar\*?", line, re.IGNORECASE)
            step_match = re.match(r"^(\d{1,3})\s+", line)
            if not age_match and not step_match:
                previous_line = line
                continue

            label = f"{age_match.group(1)} jaar" if age_match else step_match.group(1)
            amounts = self._euro_amounts(line)
            if not amounts:
                previous_line = line
                continue

            if (
                len(amounts) > len(scales)
                and amounts[0] < Decimal("5")
                and max(amounts[1:], default=Decimal("0")) > Decimal("10")
            ):
                amounts = amounts[1:]

            if len(amounts) > len(scales):
                amounts = amounts[-len(scales) :]

            align_right = len(amounts) < len(scales) and (
                "wml" in line.lower()
                or "wml" in previous_line.lower()
                or (step_match is not None and int(step_match.group(1)) >= 8)
            )
            selected_scales = scales[-len(amounts) :] if align_right else scales[: len(amounts)]

            for scale_name, amount in zip(selected_scales, amounts, strict=False):
                order += 1
                min_age = int(age_match.group(1)) if age_match else None
                rows.append(
                    ParsedSalaryRow(
                        scale_name=scale_name,
                        step_name=label,
                        amount=amount,
                        component_type="base_salary",
                        amount_period=period,
                        source_page=page_number,
                        row_order=order,
                        min_age=min_age,
                        max_age=min_age,
                        source_text=line,
                    )
                )
            previous_line = line

        confidence = 0.92 if len(rows) >= 10 else 0.78
        return ParsedSalaryTable(
            title=self._table_title(title, effective_date),
            effective_date=effective_date,
            period=period,
            source_page_start=page_number,
            source_page_end=page_number,
            confidence=confidence,
            review_status="approved" if confidence >= 0.9 else "review_required",
            rows=rows,
            hours_per_week=self._detect_hours(text),
        )

    def _parse_apg_rsp_section(
        self,
        title: str,
        text: str,
        page_number: int,
    ) -> ParsedSalaryTable:
        effective_date = self._effective_date(title + "\n" + text)
        rows: list[ParsedSalaryRow] = []
        order = 0
        for line in text.splitlines():
            line = clean_whitespace(line)
            scale_match = re.match(r"^(\d{1,2})\s+", line)
            if not scale_match:
                continue
            amounts = self._euro_amounts(line)
            if len(amounts) < 6:
                continue
            amounts = amounts[:6]
            rsp_match = re.search(r"(\d{2,3})%", line)
            minimum_rsp = Decimal(rsp_match.group(1)) if rsp_match else None
            definitions = [
                ("minimum", "month", amounts[0], minimum_rsp),
                ("minimum", "year", amounts[1], minimum_rsp),
                ("rsp_100", "year", amounts[2], Decimal("100")),
                ("rsp_100", "month", amounts[3], Decimal("100")),
                ("rsp_110", "year", amounts[4], Decimal("110")),
                ("rsp_110", "month", amounts[5], Decimal("110")),
            ]
            for component, amount_period, amount, percentage in definitions:
                order += 1
                rows.append(
                    ParsedSalaryRow(
                        scale_name=scale_match.group(1),
                        step_name="",
                        amount=amount,
                        component_type=component,
                        amount_period=amount_period,
                        rsp_percentage=percentage,
                        source_page=page_number,
                        row_order=order,
                        source_text=line,
                    )
                )

        confidence = 0.95 if rows else 0.0
        return ParsedSalaryTable(
            title=self._table_title(title, effective_date),
            effective_date=effective_date,
            period="unknown",
            source_page_start=page_number,
            source_page_end=page_number,
            confidence=confidence,
            review_status="approved" if rows else "review_required",
            rows=rows,
            hours_per_week=self._detect_hours(text),
        )

    def _parse_simple_section(
        self,
        title: str,
        text: str,
        page_number: int,
    ) -> ParsedSalaryTable:
        effective_date = self._effective_date(title + "\n" + text)
        raw_rows: list[tuple[str, str, Decimal, str]] = []
        for line in text.splitlines():
            line = clean_whitespace(line)
            amounts = self._euro_amounts(line)
            if not amounts:
                continue
            match = re.match(
                r"^(?:schaal\s+)?(?P<scale>[A-Z]{1,4}|\d{1,3})"
                r"(?:\s+(?:trede\s+)?(?P<step>\d{1,3}|\d{2}\s*jaar))?",
                line,
                re.IGNORECASE,
            )
            if not match:
                continue
            scale = match.group("scale").upper()
            step = clean_whitespace(match.group("step") or "")
            raw_rows.append((scale, step, amounts[-1], line))

        period = self.detect_period(text, [item[2] for item in raw_rows])
        rows = [
            ParsedSalaryRow(
                scale_name=scale,
                step_name=step,
                amount=amount,
                component_type="base_salary",
                amount_period=period,
                source_page=page_number,
                row_order=index,
                source_text=line,
            )
            for index, (scale, step, amount, line) in enumerate(raw_rows, start=1)
        ]
        confidence = 0.72 if len(rows) >= 3 else 0.55
        return ParsedSalaryTable(
            title=self._table_title(title, effective_date),
            effective_date=effective_date,
            period=period,
            source_page_start=page_number,
            source_page_end=page_number,
            confidence=confidence,
            review_status="review_required",
            rows=rows,
            hours_per_week=self._detect_hours(text),
        )

    def _merge_tables(self, tables: list[ParsedSalaryTable]) -> list[ParsedSalaryTable]:
        groups: dict[tuple[date | None, str], list[ParsedSalaryTable]] = defaultdict(list)
        for table in tables:
            if not table.rows:
                continue
            groups[(table.effective_date, table.period)].append(table)

        merged: list[ParsedSalaryTable] = []
        for (effective_date, period), candidates in groups.items():
            candidates.sort(key=lambda item: (len(item.rows), item.confidence), reverse=True)
            chosen_rows: dict[str, ParsedSalaryRow] = {}
            for candidate in candidates:
                for row in candidate.rows:
                    chosen_rows.setdefault(row.row_key(), row)

            rows = list(chosen_rows.values())
            rows.sort(key=lambda row: (row.source_page, row.row_order, row.scale_name, row.step_name))
            for index, row in enumerate(rows, start=1):
                row.row_order = index

            source_pages = [row.source_page for row in rows]
            confidence = max(candidate.confidence for candidate in candidates)
            merged.append(
                ParsedSalaryTable(
                    title=self._table_title(candidates[0].title, effective_date),
                    effective_date=effective_date,
                    period=period,
                    source_page_start=min(source_pages),
                    source_page_end=max(source_pages),
                    confidence=confidence,
                    review_status="approved" if confidence >= 0.9 and len(rows) >= 5 else "review_required",
                    rows=rows,
                    hours_per_week=next(
                        (item.hours_per_week for item in candidates if item.hours_per_week),
                        None,
                    ),
                )
            )

        merged.sort(key=lambda item: (item.effective_date or date.min, item.title))
        return merged

    @staticmethod
    def detect_period(text: str, amounts: list[Decimal]) -> str:
        lowered = clean_whitespace(text).lower()
        hourly_terms = ("uurloon", "uurlonen", "per uur", "loontabellen per uur")
        monthly_terms = ("maandloon", "maandsalaris", "per maand")
        yearly_terms = ("jaarsalaris", "jaarbedrag", "per jaar")
        four_week_terms = ("vierweken", "4 weken", "per vier weken")

        if any(term in lowered for term in hourly_terms):
            return "hour"
        if any(term in lowered for term in four_week_terms):
            return "four_weeks"
        if any(term in lowered for term in monthly_terms):
            return "month"
        if any(term in lowered for term in yearly_terms):
            return "year"

        detected_amounts = amounts or PdfSalaryParser._euro_amounts(text)
        if detected_amounts:
            middle = Decimal(str(median([float(value) for value in detected_amounts])))
            if middle < Decimal("100"):
                return "hour"
            if middle < Decimal("20000"):
                return "month"
            return "year"
        return "unknown"

    @staticmethod
    def _euro_amounts(text: str) -> list[Decimal]:
        result: list[Decimal] = []
        for match in EURO_PATTERN.findall(text):
            amount = parse_decimal(match)
            if amount is not None:
                result.append(amount)
        return result

    @staticmethod
    def _effective_date(text: str) -> date | None:
        dates = parse_all_dutch_dates(text)
        return dates[0] if dates else None

    @staticmethod
    def _detect_hours(text: str) -> Decimal | None:
        match = re.search(r"\b(36|37|38|39|40|42)\s*uur\b", text, re.IGNORECASE)
        return Decimal(match.group(1)) if match else None

    @staticmethod
    def _table_title(title: str, effective_date: date | None) -> str:
        if effective_date:
            return f"Salarisschalen per {effective_date.isoformat()}"
        return clean_whitespace(title)[:240] or "Salaristabel"

    def _empty_table(self, title: str, text: str, page_number: int) -> ParsedSalaryTable:
        effective_date = self._effective_date(title + "\n" + text)
        return ParsedSalaryTable(
            title=self._table_title(title, effective_date),
            effective_date=effective_date,
            period=self.detect_period(text, []),
            source_page_start=page_number,
            source_page_end=page_number,
            confidence=0,
            review_status="review_required",
            rows=[],
        )
