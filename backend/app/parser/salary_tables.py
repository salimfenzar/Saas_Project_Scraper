from datetime import datetime
from pathlib import Path
import re

import pdfplumber


class SalaryTableExtractionError(Exception):
    pass


DATE_PATTERN = re.compile(
    r"per\s+(\d{1,2})\s+"
    r"(januari|februari|maart|april|mei|juni|juli|augustus|"
    r"september|oktober|november|december)\s+(\d{4})",
    re.IGNORECASE,
)

MONTHS = {
    "januari": 1,
    "februari": 2,
    "maart": 3,
    "april": 4,
    "mei": 5,
    "juni": 6,
    "juli": 7,
    "augustus": 8,
    "september": 9,
    "oktober": 10,
    "november": 11,
    "december": 12,
}


def find_effective_date(text: str) -> str | None:
    match = DATE_PATTERN.search(text)

    if not match:
        return None

    day = int(match.group(1))
    month = MONTHS[match.group(2).lower()]
    year = int(match.group(3))

    return datetime(year, month, day).date().isoformat()


def clean_cell(value: object) -> str | None:
    if value is None:
        return None

    cleaned = " ".join(str(value).split())

    return cleaned or None


def extract_salary_tables(
    file_path: str,
    page_numbers: list[int],
) -> list[dict]:
    path = Path(file_path)

    if not path.exists():
        raise SalaryTableExtractionError(
            f"PDF-bestand bestaat niet: {file_path}"
        )

    extracted_pages: list[dict] = []

    try:
        with pdfplumber.open(path) as pdf:
            total_pages = len(pdf.pages)

            for page_number in page_numbers:
                if page_number < 1 or page_number > total_pages:
                    raise SalaryTableExtractionError(
                        f"Pagina {page_number} bestaat niet. "
                        f"De PDF heeft {total_pages} pagina's."
                    )

                page = pdf.pages[page_number - 1]
                text = page.extract_text() or ""
                effective_date = find_effective_date(text)

                raw_tables = page.extract_tables()

                tables: list[dict] = []

                for table_index, raw_table in enumerate(
                    raw_tables,
                    start=1,
                ):
                    cleaned_rows = [
                        [clean_cell(cell) for cell in row]
                        for row in raw_table
                    ]

                    cleaned_rows = [
                        row
                        for row in cleaned_rows
                        if any(cell is not None for cell in row)
                    ]

                    tables.append(
                        {
                            "table_index": table_index,
                            "row_count": len(cleaned_rows),
                            "rows": cleaned_rows,
                        }
                    )

                extracted_pages.append(
                    {
                        "page_number": page_number,
                        "effective_date": effective_date,
                        "table_count": len(tables),
                        "text_preview": text[:500],
                        "tables": tables,
                    }
                )

    except SalaryTableExtractionError:
        raise

    except Exception as exc:
        raise SalaryTableExtractionError(
            f"Tabellen konden niet worden uitgelezen: {exc}"
        ) from exc

    return extracted_pages