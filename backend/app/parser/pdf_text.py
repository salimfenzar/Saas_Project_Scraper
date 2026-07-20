from pathlib import Path

import pdfplumber


class PdfParseError(Exception):
    pass


SALARY_KEYWORDS = (
    "salarisschaal",
    "salarisschalen",
    "salaristabel",
    "salaristabellen",
    "loonschaal",
    "loonschalen",
    "loontabel",
    "bruto maandsalaris",
    "functieschaal",
    "schaalbedragen",
)


def extract_pdf_pages(file_path: str) -> list[dict]:
    path = Path(file_path)

    if not path.exists():
        raise PdfParseError(
            f"PDF-bestand bestaat niet: {file_path}"
        )

    pages: list[dict] = []

    try:
        with pdfplumber.open(path) as pdf:
            for page_number, page in enumerate(pdf.pages, start=1):
                text = page.extract_text() or ""

                normalized_text = text.lower()

                matched_keywords = [
                    keyword
                    for keyword in SALARY_KEYWORDS
                    if keyword in normalized_text
                ]

                pages.append(
                    {
                        "page_number": page_number,
                        "text": text,
                        "is_salary_candidate": bool(matched_keywords),
                        "matched_keywords": matched_keywords,
                    }
                )

    except Exception as exc:
        raise PdfParseError(
            f"PDF kon niet worden gelezen: {exc}"
        ) from exc

    return pages