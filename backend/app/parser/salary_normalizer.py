import re
from decimal import Decimal, InvalidOperation


class SalaryNormalizationError(Exception):
    pass


def parse_euro(value: str | None) -> float | None:
    if not value:
        return None

    cleaned = (
        value.replace("€", "")
        .replace(".", "")
        .replace(",", ".")
        .replace(" ", "")
        .strip()
    )

    if not cleaned:
        return None

    try:
        return float(Decimal(cleaned))
    except InvalidOperation:
        return None


def parse_percentage(value: str | None) -> float | None:
    if not value:
        return None

    cleaned = value.replace("%", "").replace(",", ".").strip()

    try:
        return float(cleaned)
    except ValueError:
        return None


def is_scale_row(row: list[str | None]) -> bool:
    if not row or not row[0]:
        return False

    return bool(re.fullmatch(r"[A-Za-z0-9IVXLC\-]+", row[0].strip()))


def normalize_salary_row(
    row: list[str | None],
    effective_date: str | None,
) -> dict | None:
    if not is_scale_row(row):
        return None

    cleaned = [cell.strip() if cell else None for cell in row]

    if len(cleaned) < 8:
        return None

    return {
        "scale": cleaned[0],
        "minimum_monthly_salary": parse_euro(cleaned[1]),
        "minimum_tvi": parse_euro(cleaned[2]),
        "minimum_rsp": parse_percentage(cleaned[3]),
        "rsp100_tvi": parse_euro(cleaned[4]),
        "rsp100_monthly_salary": parse_euro(cleaned[5]),
        "rsp110_tvi": parse_euro(cleaned[6]),
        "rsp110_monthly_salary": parse_euro(cleaned[7]),
        "effective_date": effective_date,
    }


def normalize_salary_tables(pages: list[dict]) -> list[dict]:
    normalized_rows: list[dict] = []

    for page in pages:
        effective_date = page.get("effective_date")

        for table in page.get("tables", []):
            for row in table.get("rows", []):
                normalized = normalize_salary_row(
                    row=row,
                    effective_date=effective_date,
                )

                if normalized:
                    normalized_rows.append(normalized)

    return normalized_rows